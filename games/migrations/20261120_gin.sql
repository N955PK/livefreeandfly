-- Run once in the existing Supabase project's SQL editor (safe to run again; it keeps games in progress).
--
-- games/gin: two-player gin rummy. The deck, both hands, and the scoring live here so neither player's browser ever
-- holds a card it shouldn't see. Everything sits in the private "gin" schema, which the API doesn't expose; the page
-- can only call the public gin_* functions below, and each one checks the caller's seat token before doing anything.
--
-- Cards are numbers 0-51: rank = card % 13 (0 is the ace, 12 the king), suit = card / 13. An ace counts 1, faces 10.
-- Seats are 0 and 1. Postgres arrays count from 1, so seat s is element s + 1.

create schema if not exists gin;
revoke all on schema gin from public;

create table if not exists gin.games (
  code        text primary key,                      -- the six letters in the share link
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  version     int  not null default 1,               -- goes up on every change; pages ask "anything since N?"
  mode        text not null check (mode in ('single', 'hollywood')),
  target      int  not null check (target between 10 and 1000),
  status      text not null default 'waiting' check (status in ('waiting', 'playing', 'hand_over', 'game_over')),
  tokens      text[] not null,                       -- each seat's secret, kept in that player's browser
  names       text[] not null,
  avatars     text[] not null,
  colors      text[] not null,
  seen        timestamptz[] not null,
  match_no    int  not null default 1,
  hand_no     int  not null default 0,
  dealer      int  not null default 0,
  turn        int  not null default 0,
  phase       text not null default '',              -- upcard, upcard2, draw, discard, layoff
  stock_only  boolean not null default false,        -- both passed on the upcard: the next draw must be from the stock
  knock       int  not null default 10,
  upcard      int,
  stock       int[] not null default '{}',           -- the last element is the top
  pile        int[] not null default '{}',           -- the discard pile; the last element is the top
  hand0       int[] not null default '{}',
  hand1       int[] not null default '{}',
  drawn       int,                                   -- the card the player to discard just picked up
  drawn_from  text,
  last        jsonb,                                 -- the last move, as far as both players may know it
  knocked     jsonb,                                 -- the knocker's spread, while the other player lays off
  result      jsonb,
  log         jsonb not null default '[]',
  totals      jsonb not null default '[[0,0],[0,0],[0,0]]',   -- totals[game][seat]
  entered     int[] not null default '{0,0}',        -- Hollywood: the highest game each seat is scoring in
  winners     int[] not null default '{-1,-1,-1}'    -- who won each game, -1 while it's open
);
alter table gin.games enable row level security;     -- and no policies: only the functions below can touch it

/* ---------- helpers (private) ---------- */

create or replace function gin.val(c int) returns int language sql immutable as $$
  select least(c % 13 + 1, 10)
$$;

create or replace function gin.points(cards int[]) returns int language sql immutable as $$
  select coalesce(sum(gin.val(c)), 0)::int from unnest(cards) c
$$;

create or replace function gin.minus(a int[], b int[]) returns int[] language sql immutable as $$
  select coalesce(array_agg(x order by ord), '{}') from unnest(a) with ordinality t(x, ord) where x <> all(b)
$$;

create or replace function gin.ints(j jsonb) returns int[] language plpgsql immutable as $$
begin
  if j is null or jsonb_typeof(j) = 'null' then return '{}'; end if;
  if jsonb_typeof(j) <> 'array' then raise exception 'Expected a list of cards'; end if;
  return (select coalesce(array_agg(x::int order by ord), '{}') from jsonb_array_elements_text(j) with ordinality t(x, ord));
end $$;

-- Three or four of a rank, or three or more in a row in one suit (the ace is low only).
create or replace function gin.is_meld(m int[]) returns boolean language sql immutable as $$
  select coalesce(
    cardinality(m) >= 3
    and (select count(distinct c) = cardinality(m) and bool_and(c between 0 and 51) from unnest(m) c)
    and (
      (cardinality(m) <= 4 and (select count(distinct c % 13) = 1 from unnest(m) c))
      or (select count(distinct c / 13) = 1 and max(c % 13) - min(c % 13) = cardinality(m) - 1 from unnest(m) c)
    ), false)
$$;

-- Checks a player's melds against the cards they hold and returns every card used.
create or replace function gin.meld_cards(melds jsonb, pool int[]) returns int[] language plpgsql immutable as $$
declare m jsonb; cards int[]; used int[] := '{}';
begin
  if melds is null or jsonb_typeof(melds) <> 'array' then raise exception 'Melds must be a list'; end if;
  for m in select * from jsonb_array_elements(melds) loop
    cards := gin.ints(m);
    if not gin.is_meld(cards) then raise exception 'That is not a meld'; end if;
    if not (cards <@ pool) or (cards && used) then raise exception 'Those cards are not yours to meld'; end if;
    used := used || cards;
  end loop;
  return used;
end $$;

create or replace function gin.new_code() returns text language sql volatile as $$
  select string_agg(substr('ABCDEFGHJKMNPQRSTUVWXYZ23456789', 1 + get_byte(b, i) % 31, 1), '')
  from (select uuid_send(gen_random_uuid()) b) r, generate_series(0, 5) i
$$;

create or replace function gin.clean_name(t text) returns text language sql immutable as $$
  select case when length(btrim(coalesce(t, ''))) between 1 and 20 then btrim(t) else 'Player' end
$$;
create or replace function gin.clean_avatar(t text) returns text language sql immutable as $$
  select case when length(coalesce(t, '')) between 1 and 16 and t !~ '[<>&"'']' then t else '🃏' end
$$;
create or replace function gin.clean_color(t text) returns text language sql immutable as $$
  select case when coalesce(t, '') ~ '^#[0-9a-fA-F]{6}$' then lower(t) else '#a31f34' end
$$;

-- Finds the table, locks it for this move, and returns it. Raises if the code is unknown.
create or replace function gin.open(p_code text) returns gin.games language plpgsql as $$
declare g gin.games;
begin
  select * into g from gin.games where code = upper(btrim(coalesce(p_code, ''))) for update;
  if not found then raise exception 'No table with that code'; end if;
  return g;
end $$;

create or replace function gin.seat(g gin.games, p_token text) returns int language plpgsql immutable as $$
declare s int;
begin
  if p_token is null or length(p_token) < 32 then raise exception 'You are not sitting at this table'; end if;
  s := array_position(g.tokens, p_token);
  if s is null then raise exception 'You are not sitting at this table'; end if;
  return s - 1;
end $$;

-- What one seat is allowed to see.
create or replace function gin.view(g gin.games, s int) returns jsonb language sql stable as $$
  select jsonb_build_object(
    'v', g.version, 'code', g.code, 'status', g.status, 'mode', g.mode, 'target', g.target, 'you', s,
    'names', to_jsonb(g.names), 'avatars', to_jsonb(g.avatars), 'colors', to_jsonb(g.colors),
    'away', jsonb_build_array(g.seen[1] < now() - interval '40 seconds', g.seen[2] < now() - interval '40 seconds'),
    'match_no', g.match_no, 'hand_no', g.hand_no, 'dealer', g.dealer, 'turn', g.turn, 'phase', g.phase,
    'stock_only', g.stock_only, 'knock', g.knock, 'upcard', g.upcard,
    'stock', cardinality(g.stock), 'pile', cardinality(g.pile), 'top', g.pile[cardinality(g.pile)],
    'hand', to_jsonb(case when s = 0 then g.hand0 else g.hand1 end),
    'opp', cardinality(case when s = 0 then g.hand1 else g.hand0 end),
    'drawn', case when g.turn = s and g.phase = 'discard' then g.drawn end,
    'drawn_from', case when g.turn = s and g.phase = 'discard' then g.drawn_from end,
    'last', g.last, 'knocked', g.knocked, 'result', g.result,
    'log', g.log, 'totals', g.totals, 'winners', to_jsonb(g.winners)
  )
$$;

create or replace function gin.out(p_code text, s int) returns jsonb language sql stable as $$
  select gin.view(g, s) from gin.games g where g.code = p_code
$$;

create or replace function gin.deal(p_code text, p_dealer int) returns void language plpgsql as $$
declare d int[];
begin
  select array_agg(c order by gen_random_uuid()) into d from generate_series(0, 51) c;
  update gin.games set
    status = 'playing', hand_no = hand_no + 1, dealer = p_dealer, turn = 1 - p_dealer, phase = 'upcard',
    stock_only = false, hand0 = d[1:10], hand1 = d[11:20], upcard = d[21], pile = array[d[21]], stock = d[22:52],
    knock = gin.val(d[21]), drawn = null, drawn_from = null, last = null, knocked = null,   -- result stays: the last hand, until the next one ends
    version = version + 1, updated_at = now()
  where code = p_code;
end $$;

-- Ends the hand. p_winner is null for a dead hand. In Hollywood a player's first winning hand scores in game one,
-- the second in games one and two, and every one after in all three; a finished game takes no more points, and a
-- player who hasn't scored yet starts in the first game still open.
create or replace function gin.finish(g gin.games, p_winner int, p_pts int, p_type text, p_detail jsonb) returns void
language plpgsql as $$
declare
  n int := case g.mode when 'hollywood' then 3 else 1 end;
  e int; i int; t int; cols int[] := '{}'; over boolean := false;
  v_totals jsonb := g.totals; v_winners int[] := g.winners; v_entered int[] := g.entered;
begin
  if p_winner is not null then
    e := v_entered[p_winner + 1];
    for i in e + 1 .. n loop
      if v_winners[i] = -1 then e := i; exit; end if;
    end loop;
    v_entered[p_winner + 1] := e;
    for i in 1 .. e loop
      if v_winners[i] = -1 then
        t := (v_totals -> (i - 1) ->> p_winner)::int + p_pts;
        v_totals := jsonb_set(v_totals, array[(i - 1)::text, p_winner::text], to_jsonb(t));
        cols := cols || (i - 1);
        if t >= g.target then v_winners[i] := p_winner; end if;
      end if;
    end loop;
    over := not (-1 = any(v_winners[1:n]));
  end if;
  update gin.games set
    status = case when over then 'game_over' else 'hand_over' end, phase = '', knocked = null,
    totals = v_totals, winners = v_winners, entered = v_entered,
    log = log || jsonb_build_array(jsonb_build_object(
      'hand', g.hand_no, 'type', p_type, 'winner', p_winner, 'pts', p_pts, 'cols', to_jsonb(cols))),
    result = p_detail || jsonb_build_object('type', p_type, 'winner', p_winner, 'pts', p_pts, 'cols', to_jsonb(cols),
      'hand', g.hand_no, 'match', g.match_no, 'over', over, 'totals', v_totals, 'winners', to_jsonb(v_winners)),
    version = version + 1, updated_at = now()
  where code = g.code;
end $$;

/* ---------- the API (public) ---------- */

create or replace function public.gin_create(p_name text, p_avatar text, p_color text, p_mode text, p_target int)
returns jsonb language plpgsql security definer set search_path = gin, public, pg_temp as $$
declare v_code text; v_token text := replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', '');
begin
  if p_mode is null or p_mode not in ('single', 'hollywood') then raise exception 'Pick single game or Hollywood'; end if;
  if p_target is null or p_target not between 10 and 1000 then raise exception 'Play to somewhere between 10 and 1000'; end if;
  delete from gin.games where updated_at < now() - interval '45 days';
  if (select count(*) from gin.games) >= 20000 then raise exception 'The card room is full. Try again later.'; end if;
  loop
    v_code := gin.new_code();
    begin
      insert into gin.games (code, mode, target, tokens, names, avatars, colors, seen)
      values (v_code, p_mode, p_target, array[v_token, ''], array[gin.clean_name(p_name), ''],
              array[gin.clean_avatar(p_avatar), ''], array[gin.clean_color(p_color), ''], array[now(), now()]);
      exit;
    exception when unique_violation then null;
    end;
  end loop;
  return jsonb_build_object('code', v_code, 'token', v_token, 'state', gin.out(v_code, 0));
end $$;

-- What anyone holding the link can see before sitting down.
create or replace function public.gin_peek(p_code text)
returns jsonb language sql stable security definer set search_path = gin, public, pg_temp as $$
  select coalesce((
    select jsonb_build_object('found', true, 'open', g.status = 'waiting', 'mode', g.mode, 'target', g.target,
      'host', jsonb_build_object('name', g.names[1], 'avatar', g.avatars[1], 'color', g.colors[1]))
    from gin.games g where g.code = upper(btrim(coalesce(p_code, '')))), jsonb_build_object('found', false))
$$;

create or replace function public.gin_join(p_code text, p_name text, p_avatar text, p_color text)
returns jsonb language plpgsql security definer set search_path = gin, public, pg_temp as $$
declare g gin.games := gin.open(p_code); v_token text := replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', '');
begin
  if g.status <> 'waiting' then raise exception 'Both seats at this table are taken'; end if;
  update gin.games set tokens[2] = v_token, names[2] = gin.clean_name(p_name), avatars[2] = gin.clean_avatar(p_avatar),
    colors[2] = gin.clean_color(p_color), seen[2] = now() where code = g.code;
  perform gin.deal(g.code, get_byte(uuid_send(gen_random_uuid()), 0) % 2);
  return jsonb_build_object('code', g.code, 'token', v_token, 'state', gin.out(g.code, 1));
end $$;

-- The page calls this every few seconds. It answers {"same": true} when nothing has changed since p_since.
create or replace function public.gin_state(p_code text, p_token text, p_since int default -1)
returns jsonb language plpgsql security definer set search_path = gin, public, pg_temp as $$
declare g gin.games; s int;
begin
  select * into g from gin.games where code = upper(btrim(coalesce(p_code, '')));
  if not found then raise exception 'No table with that code'; end if;
  s := gin.seat(g, p_token);
  if g.seen[s + 1] < now() - interval '10 seconds' then
    update gin.games set seen[s + 1] = now() where code = g.code;
    g.seen[s + 1] := now();
  end if;
  if g.version = p_since then
    return jsonb_build_object('same', true, 'away',
      jsonb_build_array(g.seen[1] < now() - interval '40 seconds', g.seen[2] < now() - interval '40 seconds'));
  end if;
  return gin.view(g, s);
end $$;

create or replace function public.gin_profile(p_code text, p_token text, p_name text, p_avatar text, p_color text)
returns jsonb language plpgsql security definer set search_path = gin, public, pg_temp as $$
declare g gin.games := gin.open(p_code); s int := gin.seat(g, p_token);
begin
  update gin.games set names[s + 1] = gin.clean_name(p_name), avatars[s + 1] = gin.clean_avatar(p_avatar),
    colors[s + 1] = gin.clean_color(p_color), version = version + 1, updated_at = now() where code = g.code;
  return gin.out(g.code, s);
end $$;

-- Passing on the turned-up card at the start of a hand.
create or replace function public.gin_pass(p_code text, p_token text)
returns jsonb language plpgsql security definer set search_path = gin, public, pg_temp as $$
declare g gin.games := gin.open(p_code); s int := gin.seat(g, p_token);
begin
  if g.status <> 'playing' or g.turn <> s or g.phase not in ('upcard', 'upcard2') then
    raise exception 'There is nothing to pass on right now';
  end if;
  update gin.games set
    phase = case when g.phase = 'upcard' then 'upcard2' else 'draw' end,
    turn = case when g.phase = 'upcard' then g.dealer else 1 - g.dealer end,
    stock_only = (g.phase = 'upcard2'),
    last = jsonb_build_object('seat', s, 'type', 'pass'),
    version = version + 1, updated_at = now()
  where code = g.code;
  return gin.out(g.code, s);
end $$;

create or replace function public.gin_draw(p_code text, p_token text, p_source text)
returns jsonb language plpgsql security definer set search_path = gin, public, pg_temp as $$
declare g gin.games := gin.open(p_code); s int := gin.seat(g, p_token); c int; h int[];
begin
  if g.status <> 'playing' or g.turn <> s or g.phase not in ('upcard', 'upcard2', 'draw') then
    raise exception 'It is not your turn to draw';
  end if;
  if p_source = 'discard' then
    if g.stock_only then raise exception 'You both passed on that card. Draw from the deck.'; end if;
    if cardinality(g.pile) = 0 then raise exception 'The discard pile is empty'; end if;
    c := g.pile[cardinality(g.pile)];
    g.pile := g.pile[1:cardinality(g.pile) - 1];
  elsif p_source = 'stock' then
    if g.phase <> 'draw' then raise exception 'Take the turned-up card or pass'; end if;
    c := g.stock[cardinality(g.stock)];
    g.stock := g.stock[1:cardinality(g.stock) - 1];
  else
    raise exception 'Draw from the deck or the discard pile';
  end if;
  h := (case when s = 0 then g.hand0 else g.hand1 end) || c;
  update gin.games set
    stock = g.stock, pile = g.pile,
    hand0 = case when s = 0 then h else hand0 end, hand1 = case when s = 1 then h else hand1 end,
    drawn = c, drawn_from = p_source, phase = 'discard', stock_only = false,
    last = case when p_source = 'discard' then jsonb_build_object('seat', s, 'type', 'take', 'card', c)
                else jsonb_build_object('seat', s, 'type', 'stock') end,
    version = version + 1, updated_at = now()
  where code = g.code;
  return gin.out(g.code, s);
end $$;

create or replace function public.gin_discard(p_code text, p_token text, p_card int)
returns jsonb language plpgsql security definer set search_path = gin, public, pg_temp as $$
declare g gin.games := gin.open(p_code); s int := gin.seat(g, p_token); h int[];
begin
  if g.status <> 'playing' or g.turn <> s or g.phase <> 'discard' then raise exception 'It is not your turn to discard'; end if;
  h := case when s = 0 then g.hand0 else g.hand1 end;
  if p_card is null or not (p_card = any(h)) then raise exception 'That card is not in your hand'; end if;
  if g.drawn_from = 'discard' and p_card = g.drawn then
    raise exception 'You can''t discard the card you just picked up';
  end if;
  h := array_remove(h, p_card);
  update gin.games set
    hand0 = case when s = 0 then h else hand0 end, hand1 = case when s = 1 then h else hand1 end,
    pile = pile || p_card, drawn = null, drawn_from = null, turn = 1 - s, phase = 'draw',
    last = jsonb_build_object('seat', s, 'type', 'discard', 'card', p_card),
    version = version + 1, updated_at = now()
  where code = g.code;
  if cardinality(g.stock) <= 2 then   -- two cards left and nobody went down: the hand is dead
    select * into g from gin.games where code = g.code;
    perform gin.finish(g, null, 0, 'dead', jsonb_build_object('hands', jsonb_build_array(g.hand0, g.hand1)));
  end if;
  return gin.out(g.code, s);
end $$;

-- Going down: discard p_card and spread p_melds (a list of lists of cards). What's left over has to add up to the
-- knock card or less; nothing left over is gin.
create or replace function public.gin_knock(p_code text, p_token text, p_card int, p_melds jsonb)
returns jsonb language plpgsql security definer set search_path = gin, public, pg_temp as $$
declare g gin.games := gin.open(p_code); s int := gin.seat(g, p_token); h int[]; dead int[]; dw int;
begin
  if g.status <> 'playing' or g.turn <> s or g.phase <> 'discard' then raise exception 'It is not your turn to knock'; end if;
  h := case when s = 0 then g.hand0 else g.hand1 end;
  if p_card is null or not (p_card = any(h)) then raise exception 'That card is not in your hand'; end if;
  if g.drawn_from = 'discard' and p_card = g.drawn then
    raise exception 'You can''t discard the card you just picked up';
  end if;
  h := array_remove(h, p_card);
  dead := gin.minus(h, gin.meld_cards(p_melds, h));
  dw := gin.points(dead);
  if dw > g.knock then raise exception 'You need % or less to go down, and that leaves %', g.knock, dw; end if;
  update gin.games set
    hand0 = case when s = 0 then h else hand0 end, hand1 = case when s = 1 then h else hand1 end,
    pile = pile || p_card, drawn = null, drawn_from = null, turn = 1 - s, phase = 'layoff',
    knocked = jsonb_build_object('seat', s, 'melds', p_melds, 'dead', to_jsonb(dead), 'deadwood', dw, 'gin', dw = 0),
    last = jsonb_build_object('seat', s, 'type', 'knock', 'card', p_card),
    version = version + 1, updated_at = now()
  where code = g.code;
  return gin.out(g.code, s);
end $$;

-- The other player's answer to a knock: their own melds, plus the cards they add to each of the knocker's melds
-- (p_layoffs lines up with the knocker's melds; nothing can be laid off on gin). Then the hand is scored.
create or replace function public.gin_layoff(p_code text, p_token text, p_melds jsonb, p_layoffs jsonb)
returns jsonb language plpgsql security definer set search_path = gin, public, pg_temp as $$
declare
  g gin.games := gin.open(p_code); s int := gin.seat(g, p_token);
  h int[]; rest int[]; laid int[] := '{}'; lay int[]; dead int[]; d int; k int; ks int; i int; n int;
  v_winner int; v_pts int; v_type text; v_layoffs jsonb := '[]';
begin
  if g.status <> 'playing' or g.turn <> s or g.phase <> 'layoff' then raise exception 'There is no knock to answer'; end if;
  h := case when s = 0 then g.hand0 else g.hand1 end;
  rest := gin.minus(h, gin.meld_cards(p_melds, h));
  n := jsonb_array_length(g.knocked -> 'melds');
  for i in 0 .. n - 1 loop
    lay := gin.ints(case when jsonb_typeof(p_layoffs) = 'array' then p_layoffs -> i end);
    if cardinality(lay) > 0 then
      if (g.knocked ->> 'gin')::boolean then raise exception 'You can''t lay off on gin'; end if;
      if not (lay <@ rest) or (lay && laid) or not gin.is_meld(gin.ints(g.knocked -> 'melds' -> i) || lay) then
        raise exception 'That card doesn''t fit there';
      end if;
      laid := laid || lay;
    end if;
    v_layoffs := v_layoffs || jsonb_build_array(to_jsonb(lay));
  end loop;
  dead := gin.minus(rest, laid);
  d := gin.points(dead);
  k := (g.knocked ->> 'deadwood')::int;
  ks := (g.knocked ->> 'seat')::int;
  if (g.knocked ->> 'gin')::boolean then v_winner := ks; v_pts := 25 + d;       v_type := 'gin';
  elsif d <= k then                      v_winner := s;  v_pts := 25 + (k - d); v_type := 'undercut';
  else                                   v_winner := ks; v_pts := d - k;        v_type := 'knock';
  end if;
  perform gin.finish(g, v_winner, v_pts, v_type, jsonb_build_object(
    'knocker', jsonb_build_object('seat', ks, 'melds', g.knocked -> 'melds', 'dead', g.knocked -> 'dead', 'deadwood', k),
    'other', jsonb_build_object('seat', s, 'melds', p_melds, 'layoffs', v_layoffs, 'dead', to_jsonb(dead), 'deadwood', d)));
  return gin.out(g.code, s);
end $$;

-- Deals the next hand, or a fresh game once one is over. The loser of a hand deals the next; a dead hand is dealt
-- again by the same dealer. p_hand_no is the hand the caller is looking at, so two taps can't deal twice.
create or replace function public.gin_next(p_code text, p_token text, p_hand_no int)
returns jsonb language plpgsql security definer set search_path = gin, public, pg_temp as $$
declare g gin.games := gin.open(p_code); s int := gin.seat(g, p_token); v_dealer int;
begin
  if g.status in ('hand_over', 'game_over') and g.hand_no = p_hand_no then
    v_dealer := case when g.result ->> 'winner' is null then g.dealer else 1 - (g.result ->> 'winner')::int end;
    if g.status = 'game_over' then
      update gin.games set match_no = match_no + 1, hand_no = 0, log = '[]', totals = '[[0,0],[0,0],[0,0]]',
        entered = '{0,0}', winners = '{-1,-1,-1}' where code = g.code;
    end if;
    perform gin.deal(g.code, v_dealer);
  end if;
  return gin.out(g.code, s);
end $$;

/* ---------- who may call what ---------- */

do $$
declare f record;
begin
  for f in select p.oid::regprocedure as sig from pg_proc p join pg_namespace n on n.oid = p.pronamespace
           where n.nspname = 'public' and p.proname like 'gin\_%' loop
    execute format('revoke all on function %s from public', f.sig);
    if exists (select 1 from pg_roles where rolname = 'anon') then
      execute format('grant execute on function %s to anon, authenticated', f.sig);
    end if;
  end loop;
end $$;
