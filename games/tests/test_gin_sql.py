"""Plays gin rummy against the real SQL in games/migrations, on a throwaway local Postgres.

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

MIGRATION = Path(__file__).resolve().parents[1] / "migrations" / "20261120_gin.sql"


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


@pytest.fixture(scope="module")
def db():
    with tempfile.TemporaryDirectory() as tmp:
        server = pgserver.get_server(tmp)
        conn = psycopg2.connect(server.get_uri())
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("do $$ begin create role anon nologin; create role authenticated nologin; "
                    "exception when duplicate_object then null; end $$")
        sql = MIGRATION.read_text()
        cur.execute(sql)
        cur.execute(sql)  # safe to run twice
        yield cur
        conn.close()
        server.cleanup()


def call(cur, fn, **args):
    names = ", ".join(f"{k} => %s" for k in args)
    vals = [json.dumps(v) if isinstance(v, (list, dict)) else v for v in args.values()]
    cur.execute(f"select public.{fn}({names})", vals)
    return cur.fetchone()[0]


def new_table(cur, mode="single", target=150):
    made = call(cur, "gin_create", p_name="Ann", p_avatar="🦊", p_color="#3aa8ff", p_mode=mode, p_target=target)
    joined = call(cur, "gin_join", p_code=made["code"], p_name="Bob", p_avatar="🐻", p_color="#ffa32e")
    return made["code"], [made["token"], joined["token"]]


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
            # The loser deals next; a dead hand is dealt again by the same dealer. A second tap deals nothing.
            nxt = call(db, "gin_next", p_code=code, p_token=tokens[0], p_hand_no=st["hand_no"])
            again = call(db, "gin_next", p_code=code, p_token=tokens[1], p_hand_no=st["hand_no"])
            assert nxt["hand_no"] == again["hand_no"] == st["hand_no"] + 1
            assert nxt["dealer"] == (before["dealer"] if r["winner"] is None else 1 - r["winner"])
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
    made = call(db, "gin_create", p_name="  ", p_avatar="<b>", p_color="red", p_mode="single", p_target=150)
    code, t0 = made["code"], made["token"]
    assert made["state"]["names"][0] == "Player" and made["state"]["avatars"][0] == "🃏"
    assert made["state"]["status"] == "waiting" and made["state"]["hand"] == []
    assert call(db, "gin_peek", p_code=code.lower())["open"] is True
    assert call(db, "gin_peek", p_code="NOPE12") == {"found": False}
    fails(db, "gin_state", "not sitting", p_code=code, p_token="")
    fails(db, "gin_state", "not sitting", p_code=code, p_token="x" * 64)
    fails(db, "gin_create", "between 10 and 1000", p_name="A", p_avatar="a", p_color="", p_mode="single", p_target=5)
    t1 = call(db, "gin_join", p_code=code, p_name="Bob", p_avatar="🐻", p_color="#ffa32e")["token"]
    fails(db, "gin_join", "taken", p_code=code, p_name="Eve", p_avatar="🐍", p_color="#000000")
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
    fails(db, "gin_discard", "just picked up", p_code=code, p_token=dealer, p_card=took["drawn"])
    fails(db, "gin_knock", "just picked up", p_code=code, p_token=dealer, p_card=took["drawn"], p_melds=[])
    named = call(db, "gin_profile", p_code=code, p_token=t1, p_name="Bobby", p_avatar="🦉", p_color="#39D0A4")
    assert named["names"][1] == "Bobby" and named["colors"][1] == "#39d0a4"


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
    assert out["dealer"] == 1 and call(db, "gin_next", p_code=code, p_token=t1, p_hand_no=out["hand_no"])["dealer"] == 0

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
    db.execute("select has_schema_privilege('anon', 'gin', 'usage'), "
               "has_function_privilege('anon', 'public.gin_state(text, text, int)', 'execute')")
    assert db.fetchone() == (False, True)
