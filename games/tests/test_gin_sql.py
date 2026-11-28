"""Plays gin rummy against the real SQL in games/sql, on a throwaway local Postgres.

    pip install pgserver psycopg2-binary pytest
    pytest games/tests

Two bots play whole games through the same gin_* functions the page calls, and the rules are checked from outside:
the 52 cards are always all accounted for, nobody sees the other hand, and the scores match the cards shown.
"""
import itertools
import json
import random
import tempfile
from pathlib import Path

import pgserver
import psycopg2
import pytest

HERE = Path(__file__).resolve().parent
SQL = [HERE.parent / "sql" / "1_room.sql", HERE.parent / "sql" / "2_gin.sql"]
V1 = HERE / "fixtures" / "gin_v1.sql"   # gin as it first went live, to check the upgrade keeps tables in play


def val(c):
    return min(c % 13 + 1, 10)


def candidate_melds(cards):
    out = []
    by_rank = {}
    for c in cards:
        by_rank.setdefault(c % 13, []).append(c)
    for group in by_rank.values():
        if len(group) >= 3:
            out.append(tuple(group))
            if len(group) == 4:
                out.extend(itertools.combinations(group, 3))
    have = set(cards)
    for c in cards:
        run = [c]
        while run[-1] % 13 < 12 and run[-1] + 1 in have:
            run.append(run[-1] + 1)
            if len(run) >= 3:
                out.append(tuple(run))
    return out


def best_melds(cards):
    """The melds that leave the least deadwood: (deadwood points, melds)."""
    cands = candidate_melds(cards)
    best = (sum(val(c) for c in cards), [])

    def go(i, used, chosen, saved):
        nonlocal best
        total = sum(val(c) for c in cards) - saved
        if total < best[0]:
            best = (total, list(chosen))
        for j in range(i, len(cands)):
            m = cands[j]
            if not used.intersection(m):
                go(j + 1, used.union(m), chosen + [list(m)], saved + sum(val(c) for c in m))

    go(0, frozenset(), [], 0)
    return best


def is_meld(m):
    if len(m) < 3 or len(set(m)) != len(m):
        return False
    if len({c % 13 for c in m}) == 1:
        return len(m) <= 4
    ranks = sorted(c % 13 for c in m)
    return len({c // 13 for c in m}) == 1 and ranks[-1] - ranks[0] == len(m) - 1


def best_answer(hand, knocker_melds, gin):
    """The defender's melds and layoffs that leave the least deadwood."""
    cands = candidate_melds(hand)
    best = None

    def layoff(rest):
        melds = [list(m) for m in knocker_melds]
        added = [[] for _ in melds]
        left = list(rest)
        moved = not gin
        while moved:
            moved = False
            for c in list(left):
                order = sorted(range(len(melds)), key=lambda i: len({x % 13 for x in melds[i]}) == 1)  # runs first
                for i in order:
                    if is_meld(melds[i] + [c]):
                        melds[i].append(c)
                        added[i].append(c)
                        left.remove(c)
                        moved = True
                        break
        return sum(val(c) for c in left), added

    def go(i, used, chosen):
        nonlocal best
        dead, added = layoff([c for c in hand if c not in used])
        if best is None or dead < best[0]:
            best = (dead, list(chosen), added)
        for j in range(i, len(cands)):
            if not used.intersection(cands[j]):
                go(j + 1, used.union(cands[j]), chosen + [list(cands[j])])

    go(0, frozenset(), [])
    return best


ROLES = ("do $$ begin create role anon nologin; create role authenticated nologin; "
         "exception when duplicate_object then null; end $$")


@pytest.fixture(scope="module")
def server():
    with tempfile.TemporaryDirectory() as tmp:
        srv = pgserver.get_server(tmp)
        yield srv
        srv.cleanup()


def connect(server, dbname="postgres"):
    conn = psycopg2.connect(server.get_uri().replace("/postgres?", f"/{dbname}?"))
    conn.autocommit = True
    return conn


def install(cur):
    for f in SQL:
        cur.execute(f.read_text())


@pytest.fixture(scope="module")
def db(server):
    conn = connect(server)
    cur = conn.cursor()
    cur.execute(ROLES)
    install(cur)
    install(cur)  # safe to run twice
    yield cur
    conn.close()


def call(cur, fn, **args):
    names = ", ".join(f"{k} => %s" for k in args)
    vals = [json.dumps(v) if isinstance(v, (list, dict)) else v for v in args.values()]
    cur.execute(f"select public.{fn}({names})", vals)
    return cur.fetchone()[0]


def hello(cur, name, avatar="🦊", color="#3aa8ff", token=None):
    return call(cur, "room_hello", p_token=token, p_name=name, p_avatar=avatar, p_color=color)["token"]


def new_table(cur, mode="single", target=150, players=None):
    a, b = players or (hello(cur, "Ann"), hello(cur, "Bob", "🐻", "#ffa32e"))
    made = call(cur, "gin_create", p_token=a, p_mode=mode, p_target=target)
    call(cur, "gin_join", p_token=b, p_code=made["code"])
    return made["code"], [a, b]


def raw(cur, code):
    cur.execute("select to_jsonb(g) from gin.games g where code = %s", (code,))
    return cur.fetchone()[0]


def check_cards(cur, code):
    g = raw(cur, code)
    cards = g["stock"] + g["pile"] + g["hand0"] + g["hand1"]
    assert sorted(cards) == list(range(52)), "every card is somewhere exactly once"


def play_hand(cur, code, tokens, rng, knock_eagerly=True):
    """Plays one hand to its end and returns the result."""
    while True:
        s = None
        views = [call(cur, "gin_state", p_code=code, p_token=t) for t in tokens]
        for v in views:
            assert len(v["hand"]) in (10, 11) and v["opp"] in (10, 11)
            assert "hand0" not in v and "tokens" not in v and "stock" in v and isinstance(v["stock"], int)
        st = views[0]
        if st["status"] != "playing":
            return st["result"]
        check_cards(cur, code)
        s = st["turn"]
        me, tok = views[s], tokens[s]
        if st["phase"] in ("upcard", "upcard2"):
            before, _ = best_melds(me["hand"])
            after = min(best_melds([c for c in me["hand"] + [st["top"]] if c != x])[0] for x in me["hand"])
            if after < before:
                call(cur, "gin_draw", p_code=code, p_token=tok, p_source="discard")
            else:
                call(cur, "gin_pass", p_code=code, p_token=tok)
        elif st["phase"] == "draw":
            src = "stock"
            if not st["stock_only"] and rng.random() < 0.3:
                src = "discard"
            call(cur, "gin_draw", p_code=code, p_token=tok, p_source=src)
        elif st["phase"] == "discard":
            options = []
            for x in me["hand"]:
                if me["drawn_from"] == "discard" and x == me["drawn"]:
                    continue
                dead, melds = best_melds([c for c in me["hand"] if c != x])
                options.append((dead, -val(x), x, melds))
            dead, _, x, melds = min(options)
            if dead <= st["knock"] and (knock_eagerly or dead == 0):
                call(cur, "gin_knock", p_code=code, p_token=tok, p_card=x, p_melds=melds)
            else:
                call(cur, "gin_discard", p_code=code, p_token=tok, p_card=x)
        elif st["phase"] == "layoff":
            k = st["knocked"]
            assert k["deadwood"] <= st["knock"]
            dead, melds, added = best_answer(me["hand"], k["melds"], k["gin"])
            out = call(cur, "gin_layoff", p_code=code, p_token=tok, p_melds=melds, p_layoffs=added)
            r = out["result"]
            assert r["other"]["deadwood"] == dead
            if r["type"] == "gin":
                assert k["deadwood"] == 0 and r["pts"] == 25 + dead and r["winner"] == k["seat"]
                assert all(not a for a in r["other"]["layoffs"])
            elif r["type"] == "undercut":
                assert dead <= k["deadwood"] and r["pts"] == 25 + k["deadwood"] - dead and r["winner"] == s
            else:
                assert r["type"] == "knock" and dead > k["deadwood"]
                assert r["pts"] == dead - k["deadwood"] and r["winner"] == k["seat"]


def expected_totals(log, mode, target):
    """Scores the hands again from the log, the way the rules read."""
    n = 3 if mode == "hollywood" else 1
    totals = [[0, 0] for _ in range(3)]
    winners = [-1, -1, -1]
    entered = [0, 0]
    for h in log:
        w = h["winner"]
        if w is None:
            continue
        nxt = next((i for i in range(entered[w] + 1, n + 1) if winners[i - 1] == -1), None)
        if nxt:
            entered[w] = nxt
        for i in range(1, entered[w] + 1):
            if winners[i - 1] == -1:
                totals[i - 1][w] += h["pts"]
                if totals[i - 1][w] >= target:
                    winners[i - 1] = w
    return totals, winners


@pytest.mark.parametrize("mode,target", [("single", 150), ("hollywood", 150), ("hollywood", 40), ("single", 25)])
def test_whole_games(db, mode, target):
    rng = random.Random(f"{mode}{target}")
    for game in range(4):
        code, tokens = new_table(db, mode, target)
        kinds = set()
        for _ in range(400):
            before = call(db, "gin_state", p_code=code, p_token=tokens[0])
            r = play_hand(db, code, tokens, rng, knock_eagerly=game % 2 == 0)
            kinds.add(r["type"])
            st = call(db, "gin_state", p_code=code, p_token=tokens[1])
            totals, winners = expected_totals(st["log"], mode, target)
            assert st["totals"] == totals and st["winners"] == winners
            if st["status"] == "game_over":
                n = 3 if mode == "hollywood" else 1
                assert all(w != -1 for w in winners[:n]) and r["over"]
                break
            # The winner deals next; a dead hand is dealt again by the same dealer. A second tap deals nothing.
            nxt = call(db, "gin_next", p_code=code, p_token=tokens[0], p_hand_no=st["hand_no"])
            again = call(db, "gin_next", p_code=code, p_token=tokens[1], p_hand_no=st["hand_no"])
            assert nxt["hand_no"] == again["hand_no"] == st["hand_no"] + 1
            assert nxt["dealer"] == (before["dealer"] if r["winner"] is None else r["winner"])
            assert nxt["knock"] == val(nxt["upcard"]) and nxt["turn"] == 1 - nxt["dealer"]
        else:
            pytest.fail("the game never ended")
        # A rematch starts clean.
        st = call(db, "gin_next", p_code=code, p_token=tokens[0], p_hand_no=st["hand_no"])
        assert st["status"] == "playing" and st["hand_no"] == 1 and st["match_no"] == 2 and st["log"] == []
        assert st["totals"] == [[0, 0]] * 3


def fails(cur, fn, match, **args):
    with pytest.raises(psycopg2.Error, match=match):
        call(cur, fn, **args)


def rig(cur, code, **cols):
    sets = ", ".join(f"{k} = %s" for k in cols)
    cur.execute(f"update gin.games set {sets} where code = %s", [*cols.values(), code])


def C(s):
    """'5H' -> card number. Suits are S, H, D, C in that order."""
    return "SHDC".index(s[-1]) * 13 + "A23456789TJQK".index(s[:-1])


def hand(text):
    return [C(x) for x in text.split()]


def test_seats_and_turns(db):
    t0 = hello(db, "  ", "<b>", "red")
    made = call(db, "gin_create", p_token=t0, p_mode="single", p_target=150)
    code = made["code"]
    assert made["state"]["names"] == ["Player", ""] and made["state"]["avatars"][0] == "🃏"
    assert made["state"]["status"] == "waiting" and made["state"]["hand"] == []
    assert call(db, "gin_peek", p_code=code.lower())["open"] is True
    assert call(db, "gin_peek", p_code="NOPE12") == {"found": False}
    fails(db, "gin_state", "doesn't know this browser", p_code=code, p_token="")
    fails(db, "gin_state", "doesn't know this browser", p_code=code, p_token="x" * 64)
    fails(db, "gin_create", "between 10 and 1000", p_token=t0, p_mode="single", p_target=5)
    fails(db, "gin_create", "doesn't know this browser", p_token=None, p_mode="single", p_target=150)
    assert call(db, "gin_join", p_token=t0, p_code=code)["state"]["status"] == "waiting"   # the host opening their own link
    t1 = hello(db, "Bob", "🐻", "#ffa32e")
    eve = hello(db, "Eve", "🐍", "#000000")
    fails(db, "gin_state", "not sitting", p_code=code, p_token=t1)
    assert call(db, "gin_join", p_token=t1, p_code=code)["state"]["status"] == "playing"
    assert call(db, "gin_join", p_token=t1, p_code=code)["state"]["hand_no"] == 1          # sitting down twice deals once
    fails(db, "gin_join", "taken", p_token=eve, p_code=code)
    fails(db, "gin_state", "not sitting", p_code=code, p_token=eve)
    assert call(db, "gin_peek", p_code=code)["open"] is False
    tokens = [t0, t1]
    st = call(db, "gin_state", p_code=code, p_token=t0)
    first, dealer = tokens[st["turn"]], tokens[st["dealer"]]
    assert st["turn"] == 1 - st["dealer"] and st["phase"] == "upcard" and st["stock"] == 31
    assert call(db, "gin_state", p_code=code, p_token=t0, p_since=st["v"])["same"] is True
    fails(db, "gin_pass", "nothing to pass", p_code=code, p_token=dealer)
    fails(db, "gin_draw", "turned-up card or pass", p_code=code, p_token=first, p_source="stock")
    call(db, "gin_pass", p_code=code, p_token=first)
    fails(db, "gin_draw", "not your turn", p_code=code, p_token=first, p_source="discard")
    st = call(db, "gin_pass", p_code=code, p_token=dealer)
    assert st["phase"] == "draw" and st["stock_only"] and st["turn"] == 1 - st["dealer"]
    fails(db, "gin_draw", "both passed", p_code=code, p_token=first, p_source="discard")
    me = call(db, "gin_draw", p_code=code, p_token=first, p_source="stock")
    assert len(me["hand"]) == 11 and me["drawn"] in me["hand"] and me["drawn_from"] == "stock"
    other = call(db, "gin_state", p_code=code, p_token=dealer)
    assert other["drawn"] is None and other["last"] == {"seat": me["you"], "type": "stock"} and other["opp"] == 11
    fails(db, "gin_discard", "not in your hand", p_code=code, p_token=first, p_card=other["hand"][0])
    fails(db, "gin_discard", "not your turn", p_code=code, p_token=dealer, p_card=other["hand"][0])
    call(db, "gin_discard", p_code=code, p_token=first, p_card=me["hand"][0])
    took = call(db, "gin_draw", p_code=code, p_token=dealer, p_source="discard")
    assert took["drawn"] == me["hand"][0]
    # The card just taken off the pile may be thrown straight back; going down with it still needs the count.
    fails(db, "gin_knock", "or less to go down", p_code=code, p_token=dealer, p_card=took["drawn"], p_melds=[])
    back = call(db, "gin_discard", p_code=code, p_token=dealer, p_card=took["drawn"])
    assert back["top"] == took["drawn"] and back["phase"] == "draw" and back["turn"] == 1 - back["you"]
    # A line said across the table reaches the other seat without a move being made, cleaned and cut to length.
    v = call(db, "gin_state", p_code=code, p_token=first)["v"]
    said = call(db, "gin_say", p_code=code, p_token=dealer, p_text="  nice\nthrow " + "x" * 200)["said"]
    assert said["seat"] == back["you"] and said["n"] == 1 and said["text"].startswith("nice throw x") and len(said["text"]) == 140
    heard = call(db, "gin_state", p_code=code, p_token=first, p_since=v)
    assert heard["said"]["text"] == said["text"] and heard["phase"] == "draw" and heard["last"]["type"] == "discard"
    assert call(db, "gin_say", p_code=code, p_token=first, p_text="thanks")["said"]["n"] == 2
    fails(db, "gin_say", "Say something", p_code=code, p_token=first, p_text="   ")
    # A new name shows up for the other player without a move being made.
    v = call(db, "gin_state", p_code=code, p_token=t0)["v"]
    assert hello(db, "Bobby", "🦉", "#39D0A4", token=t1) == t1
    named = call(db, "gin_state", p_code=code, p_token=t0, p_since=v)
    assert named["names"][1] == "Bobby" and named["colors"][1] == "#39d0a4" and named["v"] > v


def test_the_room(db):
    ann, bob, cy = hello(db, "Ann"), hello(db, "Bob"), hello(db, "Cy")
    assert hello(db, "Ann", token="y" * 40) not in ("y" * 40, ann)       # a key the room doesn't know gets a fresh one
    quiet = call(db, "gin_create", p_token=ann, p_mode="single", p_target=100)["code"]
    listed = call(db, "gin_create", p_token=ann, p_mode="hollywood", p_target=200, p_listed=True)["code"]
    lobby = {t["code"]: t for t in call(db, "room_lobby", p_token=bob)}
    assert quiet not in lobby and lobby[listed]["host"]["name"] == "Ann" and not lobby[listed]["mine"]
    assert lobby[listed]["options"] == {"mode": "hollywood", "target": 200, "cents": 1} and lobby[listed]["game"] == "gin"
    assert {t["code"]: t for t in call(db, "room_lobby", p_token=ann)}[listed]["mine"]
    call(db, "gin_join", p_token=bob, p_code=listed)
    assert listed not in {t["code"] for t in call(db, "room_lobby")}      # full tables drop off the list
    st = call(db, "gin_state", p_code=listed, p_token=ann)
    mine = {t["code"]: t for t in call(db, "room_mine", p_token=ann)}
    assert set(mine) == {quiet, listed} and mine[quiet]["status"] == "waiting" and mine[quiet]["players"][1] is None
    assert mine[listed]["status"] == "playing" and mine[listed]["your_turn"] == (st["turn"] == 0)
    assert [p["name"] for p in mine[listed]["players"]] == ["Ann", "Bob"] and mine[listed]["summary"]["hand"] == 1
    theirs = {t["code"]: t for t in call(db, "room_mine", p_token=bob)}
    assert theirs[listed]["your_turn"] == (st["turn"] == 1) and theirs[listed]["seat"] == 1
    assert call(db, "room_mine", p_token=cy) == []

    # Taking down a table nobody joined removes it; getting up from one in play closes it for both.
    fails(db, "room_leave", "not sitting", p_token=cy, p_code=quiet)
    call(db, "room_leave", p_token=ann, p_code=quiet)
    assert call(db, "gin_peek", p_code=quiet) == {"found": False}
    v = call(db, "gin_state", p_code=listed, p_token=ann)["v"]
    call(db, "room_leave", p_token=bob, p_code=listed)
    st = call(db, "gin_state", p_code=listed, p_token=ann, p_since=v)
    assert st["closed"] and st["left"] == 1 and st["v"] > v
    fails(db, "gin_pass", "closed", p_code=listed, p_token=ann)
    fails(db, "gin_draw", "closed", p_code=listed, p_token=bob, p_source="discard")
    assert call(db, "room_mine", p_token=ann) == [] and call(db, "room_mine", p_token=bob) == []

    # A second device: its own key's seats fold into the first. A table still waiting for someone comes along too.
    phone = hello(db, "Ann's phone")
    code, _ = new_table(db, players=(phone, bob))
    waiting = call(db, "gin_create", p_token=phone, p_mode="single", p_target=150)["code"]
    assert call(db, "room_who", p_token=phone)["name"] == "Ann's phone"
    assert call(db, "room_adopt", p_token=ann, p_other=phone) == {"moved": 2}
    assert call(db, "gin_state", p_code=code, p_token=ann)["names"] == ["Ann", "Bob"]
    assert call(db, "gin_state", p_code=waiting, p_token=ann)["status"] == "waiting"
    fails(db, "gin_state", "doesn't know this browser", p_code=code, p_token=phone)
    assert call(db, "room_adopt", p_token=ann, p_other=phone) == {"moved": 0}
    assert call(db, "room_adopt", p_token=ann, p_other=ann) == {"moved": 0}


def test_record_between_two_players(db):
    code, tokens = new_table(db, target=25)
    rng = random.Random(7)
    wins = [0, 0]
    for _ in range(3):
        while True:
            play_hand(db, code, tokens, rng)
            st = call(db, "gin_state", p_code=code, p_token=tokens[0])
            if st["status"] == "game_over":
                break
            call(db, "gin_next", p_code=code, p_token=tokens[0], p_hand_no=st["hand_no"])
        wins[st["winners"][0]] += 1
        assert st["record"] == wins
        assert call(db, "gin_state", p_code=code, p_token=tokens[1])["record"] == wins[::-1]
        call(db, "gin_next", p_code=code, p_token=tokens[1], p_hand_no=st["hand_no"])
    other, _ = new_table(db, players=(tokens[1], tokens[0]))            # a new table between the same two
    assert call(db, "gin_state", p_code=other, p_token=tokens[0])["record"] == wins


def test_accounts_and_the_leaderboard(db):
    def play_game(code, tokens, seed):
        rng = random.Random(seed)
        while True:
            play_hand(db, code, tokens, rng)
            st = call(db, "gin_state", p_code=code, p_token=tokens[0])
            if st["status"] == "game_over":
                return st["winners"][0]
            call(db, "gin_next", p_code=code, p_token=tokens[0], p_hand_no=st["hand_no"])

    ann, bob = hello(db, "Ann"), hello(db, "Bob", "🐻", "#ffa32e")
    # A login name and a password are attached to the browser's player; the name is one person's.
    fails(db, "room_register", "3 to 20", p_token=ann, p_handle="a!", p_password="secret1")
    fails(db, "room_register", "6 to 72", p_token=ann, p_handle="ann", p_password="short")
    made = call(db, "room_register", p_token=ann, p_handle=" Ann ", p_password="secret1")
    assert made["handle"] == "ann" and made["token"] == ann and call(db, "room_who", p_token=ann)["handle"] == "ann"
    fails(db, "room_register", "already logged in", p_token=ann, p_handle="ann2", p_password="secret1")
    fails(db, "room_register", "taken", p_token=bob, p_handle="ANN", p_password="secret2")
    call(db, "room_register", p_token=bob, p_handle="bob", p_password="secret2")
    db.execute("select pass from room.players where handle = 'ann'")
    stored = db.fetchone()[0]
    assert "secret1" not in stored and len(stored.split("$")) == 2          # a salt and a hash are kept, not the password

    # Ann and Bob play a game; a guest plays Ann too. Only the game between two accounts is on the leaderboard.
    code, tokens = new_table(db, target=25, players=(ann, bob))
    winner = play_game(code, tokens, 3)
    guest = hello(db, "Guest", "👻")
    other, t2 = new_table(db, target=25, players=(ann, guest))
    play_game(other, t2, 5)
    board = call(db, "room_leaderboard", p_game="gin", p_token=ann)
    assert [(row["handle"], row["wins"], row["losses"]) for row in board] == \
        ([("ann", 1, 0), ("bob", 0, 1)] if winner == 0 else [("bob", 1, 0), ("ann", 0, 1)])
    assert [row["me"] for row in board if row["handle"] == "ann"] == [True] and "token" not in json.dumps(board)
    assert call(db, "room_leaderboard", p_game="chess") == []

    # Logging in on another device hands it the account's key, and that device finds the account's tables. A guest
    # who was playing in that browser has their table folded into the account.
    laptop = hello(db, "Someone", "🦉")
    spare, _ = new_table(db, players=(laptop, hello(db, "Cy")))
    back = call(db, "room_login", p_handle="Ann", p_password="secret1", p_token=laptop)
    assert back["token"] == ann and back["name"] == "Ann" and back["handle"] == "ann"
    mine = {row["code"] for row in call(db, "room_mine", p_token=back["token"])}
    assert {code, other, spare} <= mine
    fails(db, "room_who", "doesn't know this browser", p_token=laptop)      # the guest is gone, folded in

    # A wrong password says so without saying which part was wrong; five in a row lock the name for a while,
    # even against the right password.
    assert "don't match" in call(db, "room_login", p_handle="nobody", p_password="secret1")["error"]
    for _ in range(5):
        assert "don't match" in call(db, "room_login", p_handle="bob", p_password="wrong")["error"]
    assert "Too many" in call(db, "room_login", p_handle="bob", p_password="secret2")["error"]
    db.execute("update room.players set locked_until = now() - interval '1 second' where handle = 'bob'")
    assert call(db, "room_login", p_handle="bob", p_password="secret2")["token"] == bob

    # A new password needs the old one.
    assert "not your current" in call(db, "room_password", p_token=ann, p_old="nope", p_new="better99")["error"]
    assert call(db, "room_password", p_token=ann, p_old="secret1", p_new="better99") == {"changed": True}
    assert "error" in call(db, "room_login", p_handle="ann", p_password="secret1")
    assert call(db, "room_login", p_handle="ann", p_password="better99")["token"] == ann
    # An account is never folded into another player, and is not swept out with the idle guests.
    assert call(db, "room_adopt", p_token=guest, p_other=ann) == {"moved": 0}
    db.execute("update room.players set seen_at = now() - interval '400 days'")
    new_table(db)
    db.execute("select count(*) from room.players where handle in ('ann', 'bob')")
    assert db.fetchone()[0] == 2


def test_stakes_and_settling_up(db):
    # The usual convention: the winner of a game takes the game bonus and each player a box for every hand won;
    # the loser pays the difference, at so much a point. Every figure can be set when the table is opened.
    ann, bob = hello(db, "Ann"), hello(db, "Bob", "🐻", "#ffa32e")
    made = call(db, "gin_create", p_token=ann, p_mode="single", p_target=100)
    assert made["state"]["stakes"] == {"cents": 1, "game": 100, "box": 25, "shutout": "bonus", "gin": 25, "undercut": 25}
    assert call(db, "gin_peek", p_code=made["code"])["stakes"]["cents"] == 1
    odd = call(db, "gin_create", p_token=ann, p_mode="single", p_target=100,
               p_stakes={"cents": 2.5, "game": 150, "box": 20, "shutout": "total", "gin": 30, "undercut": 99999, "junk": 1})
    assert odd["state"]["stakes"] == {"cents": 2.5, "game": 150, "box": 20, "shutout": "total", "gin": 30, "undercut": 500}

    def settle(mode, totals, winners, log, stakes=None):
        db.execute("select gin.settle(%s, %s::jsonb, %s::int[], %s::jsonb, %s::jsonb)",
                   (mode, json.dumps(totals), winners, json.dumps(log), json.dumps(stakes or {})))
        return db.fetchone()[0]

    hands = lambda wins: [{"hand": i + 1, "winner": w, "pts": 10, "cols": [0]} for i, w in enumerate(wins)]
    # Seat 0 wins 104 to 37 with five boxes to two: 67 points, the 100 for the game, and three boxes more.
    out = settle("single", [[104, 37], [0, 0], [0, 0]], [0, -1, -1], hands([0, 1, 0, 0, 1, 0, 0]))
    assert out == {"games": [{"winner": 0, "net": 67 + 100 + 75, "boxes": [5, 2], "shutout": False}], "net0": 242, "cents": 1, "money0": 242}
    # A shutout doubles the game bonus by default, doubles the lot when the table says so, or pays no more.
    blank = ([[110, 0], [0, 0], [0, 0]], [0, -1, -1], hands([0, 0, 0]))
    assert settle("single", *blank)["net0"] == 110 + 200 + 75
    assert settle("single", *blank, {"shutout": "total"})["net0"] == (110 + 100 + 75) * 2
    assert settle("single", *blank, {"shutout": "none", "cents": 5})["money0"] == (110 + 100 + 75) * 5
    # Seat 1 winning leaves seat 0 down; a table that plays for nothing settles in points alone.
    lost = settle("single", [[20, 100], [0, 0], [0, 0]], [1, -1, -1], hands([0, 1, 1, 1]), {"cents": 0, "box": 20, "game": 50})
    assert (lost["net0"], lost["money0"]) == (-(80 + 50 + 40), 0)
    # Hollywood settles its three games one by one: a hand is a box in each game it counted in.
    log = [{"hand": 1, "winner": 0, "pts": 60, "cols": [0]}, {"hand": 2, "winner": 0, "pts": 50, "cols": [0, 1]},
           {"hand": 3, "winner": 1, "pts": 30, "cols": [0]}, {"hand": 4, "winner": 0, "pts": 110, "cols": [1, 2]},
           {"hand": 5, "winner": 1, "pts": 105, "cols": [0, 1]}]
    three = settle("hollywood", [[110, 135], [160, 105], [110, 0]], [1, 0, 0], log)
    assert [g["net"] for g in three["games"]] == [25 + 100 + 0, 55 + 100 + 25, 110 + 200 + 25]
    assert three["net0"] == -125 + 180 + 335

    # At the table: gin and undercut bonuses come from the stakes, and the match is settled when it ends.
    code = call(db, "gin_create", p_token=ann, p_mode="single", p_target=40, p_stakes={"cents": 10, "gin": 30})["code"]
    call(db, "gin_join", p_token=bob, p_code=code)
    h0 = hand("3H 4H 5H 6H 9S 9D 9C JD QD KD") + [C("QS")]
    h1 = hand("7C 8C 9H KC 7H AS AD 2D 4C 3S")
    rest = [c for c in range(52) if c not in h0 + h1]
    rig(db, code, hand0=h0, hand1=h1, pile=rest[:1], stock=rest[1:], knock=9, turn=0, phase="discard",
        drawn=C("QS"), drawn_from="stock", dealer=1, stock_only=False)
    call(db, "gin_knock", p_code=code, p_token=ann, p_card=C("QS"), p_melds=[hand("3H 4H 5H 6H"), hand("9S 9D 9C"), hand("JD QD KD")])
    done = call(db, "gin_layoff", p_code=code, p_token=bob, p_melds=[], p_layoffs=[[], [], []])
    dead = sum(val(c) for c in h1)
    r = done["result"]
    assert (r["type"], r["pts"], r["over"]) == ("gin", 30 + dead, True)
    assert r["settle"]["net0"] == (30 + dead) + 200 + 25 and r["settle"]["money0"] == r["settle"]["net0"] * 10
    # The running balance between the two follows each of them, and carries to another table.
    assert done["money"] == -r["settle"]["money0"]
    assert call(db, "gin_state", p_code=code, p_token=ann)["money"] == r["settle"]["money0"]
    other, _ = new_table(db, players=(bob, ann))
    assert call(db, "gin_state", p_code=other, p_token=ann)["money"] == r["settle"]["money0"]
    # The book between the two lists each settled match from each side, and adds up to the balance.
    book = call(db, "gin_state", p_code=other, p_token=ann)["ledger"]
    assert [(m["won"], m["net"], m["money"], m["cents"], m["target"]) for m in book] == \
        [(True, r["settle"]["net0"], r["settle"]["money0"], 10, 40)]
    theirs = call(db, "gin_state", p_code=other, p_token=bob)["ledger"]
    assert [(m["won"], m["net"], m["money"]) for m in theirs] == [(False, -r["settle"]["net0"], -r["settle"]["money0"])]


def test_phone_numbers(db):
    ann, bob, cy = hello(db, "Ann"), hello(db, "Bob"), hello(db, "Cy")
    code, _ = new_table(db, players=(ann, bob))
    fails(db, "room_phone_set", "Log in first", p_token=bob, p_phone="555 123 4567")
    call(db, "room_register", p_token=bob, p_handle="bobphone", p_password="secret1")
    fails(db, "room_phone_set", "digits", p_token=bob, p_phone="call me")
    fails(db, "room_phone_set", "7 to 15", p_token=bob, p_phone="12345")
    assert call(db, "room_phone_set", p_token=bob, p_phone=" +1 (555) 123-4567 ") == "+15551234567"
    assert call(db, "room_who", p_token=bob)["phone"] == "+15551234567"
    assert call(db, "room_phones", p_token=ann, p_code=code) == [{"name": "Bob", "phone": "+15551234567"}]
    assert call(db, "room_phones", p_token=bob, p_code=code) == []                 # Ann gave none, and not his own
    fails(db, "room_phones", "not sitting", p_token=cy, p_code=code)
    assert "phone" not in json.dumps(call(db, "gin_state", p_code=code, p_token=ann))   # not in what the table shows
    assert "5551234567" not in json.dumps(call(db, "room_leaderboard"))
    assert call(db, "room_phone_set", p_token=bob, p_phone="") is None
    assert call(db, "room_phones", p_token=ann, p_code=code) == []


def test_notifications(db):
    code, (ann, bob) = new_table(db)
    cy = hello(db, "Cy")
    sub = {"endpoint": "https://web.push.apple.com/abc123", "keys": {"p256dh": "B" * 87, "auth": "a" * 22}}
    fails(db, "room_push_on", "not something", p_token=bob, p_sub={"endpoint": "http://x/y", "keys": sub["keys"]})
    assert call(db, "room_push_on", p_token=bob, p_sub=sub)
    job = lambda who, kind, text=None: call(db, "push_job", p_code=code, p_token=who, p_kind=kind, p_text=text)
    fails(db, "push_job", "not sitting", p_code=code, p_token=cy, p_kind="ring")
    fails(db, "push_job", "Unknown kind", p_code=code, p_token=ann, p_kind="shout")
    db.execute("select t.turn = p.id from room.tables t, room.players p where t.code = %s and p.key = %s", [code, bob])
    bobs_turn = db.fetchone()[0]
    # Bob is at the table and looking: a turn or a line is not worth a notification, a ring is.
    assert job(ann, "turn")["subs"] == [] and job(ann, "say", "hello")["subs"] == []
    rung = job(ann, "ring")
    assert [s["endpoint"] for s in rung["subs"]] == [sub["endpoint"]] and rung["subs"][0]["p256dh"] == "B" * 87
    assert rung["title"] == "gin/rummy" and rung["body"] == "Ann is waiting for you at the table."
    assert rung["url"] == f"/games/gin/?t={code}" and rung["tag"] == code
    assert job(ann, "ring")["subs"] == []                                   # not twice in twenty seconds
    assert job(bob, "ring")["subs"] == []                                   # Ann has no device, and Bob is not told of himself
    # Bob steps away: now a line reaches him, and a turn does when the move is his.
    db.execute("update room.players set seen_at = now() - interval '2 minutes' where key = %s", [bob])
    db.execute("update room.push set last_at = null")
    said = job(ann, "say", "  your\nmove ")
    assert len(said["subs"]) == 1 and said["body"] == "Ann: your move"
    db.execute("update room.push set last_at = null")
    assert len(job(ann, "turn")["subs"]) == (1 if bobs_turn else 0)
    db.execute("update room.push set last_at = null")
    assert job(ann, "say", "   ")["subs"] == []
    # The signing keys are stored once and never replaced.
    assert call(db, "push_keys") is None
    assert call(db, "push_keys", p_set={"public": "one"}) == {"public": "one"}
    assert call(db, "push_keys", p_set={"public": "two"}) == {"public": "one"}
    # A device that has gone is forgotten; so is one its owner turns off.
    assert call(db, "room_push_on", p_token=ann, p_sub={**sub, "endpoint": "https://fcm.googleapis.com/fcm/send/zzz"})
    assert call(db, "room_push_off", p_token=ann, p_endpoint="https://fcm.googleapis.com/fcm/send/zzz")
    assert call(db, "push_gone", p_endpoint=sub["endpoint"]) is True
    db.execute("select count(*) from room.push")
    assert db.fetchone()[0] == 0
    # No page may call the sender's functions.
    db.execute("select has_function_privilege('anon', 'public.push_job(text, text, text, text)', 'execute'), "
               "has_function_privilege('anon', 'public.push_keys(jsonb)', 'execute'), "
               "has_function_privilege('anon', 'public.room_push_on(text, jsonb)', 'execute')")
    assert db.fetchone() == (False, False, True)


def test_upgrade_keeps_tables_in_play(server):
    admin = connect(server)
    admin.cursor().execute("create database upgrade")
    admin.close()
    conn = connect(server, "upgrade")
    cur = conn.cursor()
    cur.execute(ROLES)
    cur.execute(V1.read_text())
    # Two tables from before the room existed: one mid-hand, one still waiting for a second player.
    made = call(cur, "gin_create", p_name="Ann", p_avatar="🦊", p_color="#3aa8ff", p_mode="hollywood", p_target=150)
    code, ann = made["code"], made["token"]
    bob = call(cur, "gin_join", p_code=code, p_name="Bob", p_avatar="🐻", p_color="#ffa32e")["token"]
    rng = random.Random(3)
    play_hand(cur, code, [ann, bob], rng)
    st = call(cur, "gin_state", p_code=code, p_token=ann)
    call(cur, "gin_next", p_code=code, p_token=ann, p_hand_no=st["hand_no"])
    before = [call(cur, "gin_state", p_code=code, p_token=t) for t in (ann, bob)]
    lonely = call(cur, "gin_create", p_name="Cy", p_avatar="🐸", p_color="#39d0a4", p_mode="single", p_target=100)

    install(cur)
    install(cur)
    after = [call(cur, "gin_state", p_code=code, p_token=t) for t in (ann, bob)]
    for b, a in zip(before, after):
        for k in ("hand", "names", "avatars", "colors", "totals", "log", "turn", "phase", "top", "knock", "hand_no", "result"):
            assert a[k] == b[k], k
    assert not after[0]["closed"] and after[0]["record"] == [0, 0]
    play_hand(cur, code, [ann, bob], rng)                                   # the old keys still play
    mine = call(cur, "room_mine", p_token=ann)
    assert [t["code"] for t in mine] == [code] and mine[0]["options"] == {"mode": "hollywood", "target": 150}
    # The waiting table is still joinable, by a page from before the upgrade or after it.
    assert call(cur, "gin_peek", p_code=lonely["code"])["host"]["name"] == "Cy"
    dee = call(cur, "gin_join", p_code=lonely["code"], p_name="Dee", p_avatar="🐼", p_color="#d95ce8")
    assert dee["state"]["status"] == "playing" and dee["state"]["names"] == ["Cy", "Dee"]
    assert call(cur, "gin_state", p_code=lonely["code"], p_token=lonely["token"])["hand_no"] == 1
    old_page = call(cur, "gin_create", p_name="Old", p_avatar="🎩", p_color="#5b6b7a", p_mode="single", p_target=150)
    assert call(cur, "gin_state", p_code=old_page["code"], p_token=old_page["token"])["status"] == "waiting"
    named = call(cur, "gin_profile", p_code=code, p_token=bob, p_name="Bobby", p_avatar="🦉", p_color="#39D0A4")
    assert named["names"][1] == "Bobby"
    # A browser holding several of the old per-table keys gathers them under one player.
    me = hello(cur, "Ann")
    assert call(cur, "room_adopt", p_token=me, p_other=ann) == {"moved": 1}
    assert call(cur, "gin_state", p_code=code, p_token=me)["you"] == 0
    conn.close()


def test_knock_layoff_and_undercut(db):
    code, tokens = new_table(db)
    # Seat 0 holds three kings, 4-5-6 of hearts, and 2S 3D 4C (9), plus a queen to throw. The knock card is a 9.
    # Seat 1 holds 7-8-9 of clubs, the fourth king and the 7 of hearts (which both go on seat 0's melds), and
    # A 2 2 3 4, so 12 after layoffs. Seat 0's knock stands and scores 12 - 9 = 3.
    h0 = hand("KS KH KD 4H 5H 6H 2S 3D 4C QS")
    h1 = hand("7C 8C 9C KC 7H AS 2H 2D 3C 4S")
    rest = [c for c in range(52) if c not in h0 + h1]
    pile, stock = rest[:1], rest[1:]
    rig(db, code, hand0=h0 + [stock[-1]], hand1=h1, pile=pile, stock=stock[:-1], knock=9, turn=0, phase="discard",
        drawn=stock[-1], drawn_from="stock", dealer=1)
    melds = [hand("KS KH KD"), hand("4H 5H 6H")]
    t0, t1 = tokens
    fails(db, "gin_knock", "not a meld", p_code=code, p_token=t0, p_card=C("QS"), p_melds=[hand("KS KH 4H")])
    fails(db, "gin_knock", "not yours", p_code=code, p_token=t0, p_card=C("QS"), p_melds=[hand("7C 8C 9C")])
    fails(db, "gin_knock", "not yours", p_code=code, p_token=t0, p_card=C("QS"),
          p_melds=[hand("KS KH KD"), hand("KS KH KD")])
    fails(db, "gin_knock", "9 or less", p_code=code, p_token=t0, p_card=C("2S"), p_melds=melds)
    extra = stock[-1]
    fails(db, "gin_knock", "or less", p_code=code, p_token=t0, p_card=C("QS"), p_melds=melds[:1])
    # Throw the drawn card away first so the hand is exactly what the comment above says.
    rig(db, code, hand0=h0, pile=pile + [extra], drawn=C("QS"))
    st = call(db, "gin_knock", p_code=code, p_token=t0, p_card=C("QS"), p_melds=melds)
    assert st["phase"] == "layoff" and st["turn"] == 1 and st["knocked"]["deadwood"] == 9 and not st["knocked"]["gin"]
    assert sorted(st["knocked"]["dead"]) == sorted(hand("2S 3D 4C"))
    fails(db, "gin_layoff", "doesn't fit", p_code=code, p_token=t1, p_melds=[hand("7C 8C 9C")],
          p_layoffs=[[C("AS")], []])
    fails(db, "gin_layoff", "doesn't fit", p_code=code, p_token=t1, p_melds=[hand("7C 8C 9C")],
          p_layoffs=[[C("9C")], []])                      # already in a meld of their own
    out = call(db, "gin_layoff", p_code=code, p_token=t1, p_melds=[hand("7C 8C 9C")],
               p_layoffs=[[C("KC")], [C("7H")]])
    r = out["result"]
    assert (r["type"], r["winner"], r["pts"]) == ("knock", 0, 3) and r["other"]["deadwood"] == 12
    assert out["status"] == "hand_over" and out["totals"][0] == [3, 0]

    # Same deal, but seat 1's low cards are lower: laying off gets them to 8, under the knocker's 9. Undercut: 25 + 1.
    call(db, "gin_next", p_code=code, p_token=t0, p_hand_no=out["hand_no"])
    h1 = hand("7C 8C 9C KC 7H AS AD 2D AC 3S")
    rest = [c for c in range(52) if c not in h0 + h1]
    rig(db, code, hand0=h0, hand1=h1, pile=rest[:1], stock=rest[1:], knock=9, turn=0, phase="discard",
        drawn=C("QS"), drawn_from="stock", dealer=1, stock_only=False)
    call(db, "gin_knock", p_code=code, p_token=t0, p_card=C("QS"), p_melds=melds)
    out = call(db, "gin_layoff", p_code=code, p_token=t1, p_melds=[hand("7C 8C 9C")], p_layoffs=[[C("KC")], [C("7H")]])
    r = out["result"]
    assert (r["type"], r["winner"], r["pts"]) == ("undercut", 1, 26) and out["totals"][0] == [3, 26]
    assert out["dealer"] == 1 and call(db, "gin_next", p_code=code, p_token=t1, p_hand_no=out["hand_no"])["dealer"] == 1

    # A tie goes to the other player too: 25 and nothing more. And gin takes no layoffs.
    h1 = hand("7C 8C 9C KC 7H AS AD 2D 2C 3S")
    rest = [c for c in range(52) if c not in h0 + h1]
    rig(db, code, hand0=h0, hand1=h1, pile=rest[:1], stock=rest[1:], knock=10, turn=0, phase="discard",
        drawn=C("QS"), drawn_from="stock", stock_only=False)
    call(db, "gin_knock", p_code=code, p_token=t0, p_card=C("QS"), p_melds=melds)
    out = call(db, "gin_layoff", p_code=code, p_token=t1, p_melds=[hand("7C 8C 9C")], p_layoffs=[[C("KC")], [C("7H")]])
    assert (out["result"]["type"], out["result"]["pts"]) == ("undercut", 25)

    call(db, "gin_next", p_code=code, p_token=t0, p_hand_no=out["hand_no"])
    h1 = hand("7C 8C 9C KC 7H AS AD 2D 2C 3D")
    g0 = hand("KS KH KD 4H 5H 6H 2S 3S 4S 5S QS")
    rest = [c for c in range(52) if c not in g0 + h1]
    rig(db, code, hand0=g0, hand1=h1, pile=rest[:1], stock=rest[1:], knock=1, turn=0, phase="discard",
        drawn=C("QS"), drawn_from="stock", stock_only=False)
    gin_melds = [hand("KS KH KD"), hand("4H 5H 6H"), hand("2S 3S 4S 5S")]
    st = call(db, "gin_knock", p_code=code, p_token=t0, p_card=C("QS"), p_melds=gin_melds)
    assert st["knocked"]["gin"]
    fails(db, "gin_layoff", "lay off on gin", p_code=code, p_token=t1, p_melds=[hand("7C 8C 9C")],
          p_layoffs=[[C("KC")], [], []])
    out = call(db, "gin_layoff", p_code=code, p_token=t1, p_melds=[hand("7C 8C 9C")], p_layoffs=[[], [], []])
    assert (out["result"]["type"], out["result"]["winner"], out["result"]["pts"]) == ("gin", 0, 25 + 26)


def test_dead_hand(db):
    code, tokens = new_table(db)
    st = call(db, "gin_state", p_code=code, p_token=tokens[0])
    g = raw(db, code)
    rig(db, code, stock=g["stock"][:3], pile=g["pile"] + g["stock"][3:], turn=0, phase="draw", stock_only=False)
    me = call(db, "gin_draw", p_code=code, p_token=tokens[0], p_source="stock")
    out = call(db, "gin_discard", p_code=code, p_token=tokens[0], p_card=me["drawn"])
    assert out["status"] == "hand_over" and out["result"]["type"] == "dead" and out["result"]["winner"] is None
    assert out["totals"][0] == [0, 0] and len(out["result"]["hands"]) == 2
    nxt = call(db, "gin_next", p_code=code, p_token=tokens[1], p_hand_no=out["hand_no"])
    assert nxt["dealer"] == st["dealer"] and nxt["hand_no"] == 2


def test_only_the_api_is_reachable(db):
    db.execute("select has_schema_privilege('anon', 'gin', 'usage'), has_schema_privilege('anon', 'room', 'usage'), "
               "has_function_privilege('anon', 'public.gin_state(text, text, int)', 'execute'), "
               "has_function_privilege('anon', 'public.room_hello(text, text, text, text)', 'execute')")
    assert db.fetchone() == (False, False, True, True)
