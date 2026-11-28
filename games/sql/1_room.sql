-- game/room, part 1 of 2: the room itself. Run this, then 2_gin.sql, in the Supabase project's SQL editor.
-- Both files are the whole current definition and are safe to run again at any time; they upgrade what's there
-- in place and keep every table in play.
--
-- The room is everything the games share: who a player is, which tables exist, who sits where, the list of open
-- tables, sitting down and leaving. Each game keeps its own cards and rules in its own schema (gin, so far) and hangs
-- them off a row in room.tables. Nothing here is reachable through the API except the public room_* functions.
--
-- A player is a browser: the page keeps a long random key and sends it with every call. A player may also take a
-- login name and a password (an account), and then logging in on any device hands that device the same key, so
-- their tables and their record follow them; the leaderboard is kept among players with accounts. The member_id
-- column is where a ski/lease member will be attached once the two are joined up; nothing reads it yet.

create schema if not exists room;
revoke all on schema room from public;

create table if not exists room.players (
  id          uuid primary key default gen_random_uuid(),
  key         text not null unique,                   -- the secret this player's browsers hold
  name        text not null,
  avatar      text not null,
  color       text not null,
  member_id   uuid unique,                            -- reserved for the ski/lease member, once linked
  created_at  timestamptz not null default now(),
  seen_at     timestamptz not null default now()
);

-- Accounts: a login name, the password's salted hash (never the password), and a count of wrong tries that locks
-- the name for a few minutes when it runs up.
alter table room.players add column if not exists handle text;
alter table room.players add column if not exists pass text;
alter table room.players add column if not exists fails int not null default 0;
alter table room.players add column if not exists locked_until timestamptz;
create unique index if not exists players_handle on room.players (handle) where handle is not null;

create table if not exists room.tables (
  code        text primary key,                       -- the six letters in the share link
  game        text not null,                          -- 'gin', and whatever comes next
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  rev         int  not null default 0,                -- goes up when the room changes something the game didn't
  seats       uuid[] not null,                        -- player ids in seat order; null is an empty chair
  listed      boolean not null default false,         -- shown in the room's list of open tables
  status      text not null default 'waiting' check (status in ('waiting', 'playing', 'over', 'closed')),
  turn        uuid,                                   -- whose move it is, for "your turn" in the lists
  options     jsonb not null default '{}',            -- what the host chose, for the lists
  summary     jsonb not null default '{}',            -- the score so far, in the game's own shape
  left_by     uuid                                    -- who got up, when status is 'closed'
);
create index if not exists tables_seats on room.tables using gin (seats);

create table if not exists room.results (
  id       bigint generated always as identity primary key,
  game     text not null,
  code     text not null,
  at       timestamptz not null default now(),
  players  uuid[] not null,
  winner   uuid,
  detail   jsonb not null default '{}'
);
create index if not exists results_players on room.results using gin (players);

alter table room.players enable row level security;   -- and no policies: only the functions below can touch them
alter table room.tables  enable row level security;
alter table room.results enable row level security;

/* ---------- helpers (private) ---------- */

create or replace function room.clean_name(t text) returns text language sql immutable as $$
  select case when length(btrim(coalesce(t, ''))) between 1 and 20 then btrim(t) else 'Player' end
$$;
create or replace function room.clean_avatar(t text) returns text language sql immutable as $$
  select case when length(coalesce(t, '')) between 1 and 16 and t !~ '[<>&"'']' then t else '🃏' end
$$;
create or replace function room.clean_color(t text) returns text language sql immutable as $$
  select case when coalesce(t, '') ~ '^#[0-9a-fA-F]{6}$' then lower(t) else '#a31f34' end
$$;

-- A password's hash: SHA-256 of the salt and the password, then fed back through itself twenty thousand times so
-- that guessing is slow. It uses only what Postgres has built in, so it needs no extension. Kept as "salt$hash".
create or replace function room.hash_pass(p_password text, p_salt text) returns text language plpgsql immutable as $$
declare v bytea := sha256(convert_to(p_salt || p_password, 'UTF8')); pw bytea := convert_to(p_password, 'UTF8');
begin
  for i in 1..20000 loop v := sha256(v || pw); end loop;
  return p_salt || '$' || encode(v, 'hex');
end $$;
create or replace function room.new_pass(p_password text) returns text language sql volatile as $$
  select room.hash_pass(p_password, replace(gen_random_uuid()::text, '-', ''))
$$;
create or replace function room.pass_ok(p_password text, p_stored text) returns boolean language sql immutable as $$
  select p_stored is not null and p_stored = room.hash_pass(coalesce(p_password, ''), split_part(p_stored, '$', 1))
$$;

create or replace function room.new_key() returns text language sql volatile as $$
  select replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', '')
$$;
create or replace function room.new_code() returns text language sql volatile as $$
  select string_agg(substr('ABCDEFGHJKMNPQRSTUVWXYZ23456789', 1 + get_byte(b, i) % 31, 1), '')
  from (select uuid_send(gen_random_uuid()) b) r, generate_series(0, 5) i
$$;
create or replace function room.code(t text) returns text language sql immutable as $$
  select upper(btrim(coalesce(t, '')))
$$;

-- The player a key belongs to. Also notes that they're here, for "stepped away".
create or replace function room.me(p_token text) returns room.players language plpgsql as $$
declare p room.players;
begin
  if p_token is not null and length(p_token) >= 32 then
    select * into p from room.players where key = p_token;
  end if;
  if p.id is null then raise exception 'The game room doesn''t know this browser yet'; end if;
  if p.seen_at < now() - interval '10 seconds' then
    update room.players set seen_at = now() where id = p.id;
    p.seen_at := now();
  end if;
  return p;
end $$;

create or replace function room.face(p_id uuid) returns jsonb language sql stable as $$
  select jsonb_build_object('name', p.name, 'avatar', p.avatar, 'color', p.color,
                            'away', p.seen_at < now() - interval '40 seconds')
  from room.players p where p.id = p_id
$$;

-- Everyone at a table in seat order; an empty chair is null.
create or replace function room.faces(p_seats uuid[]) returns jsonb language sql stable as $$
  select coalesce(jsonb_agg(room.face(p_seats[i]) order by i), '[]') from generate_subscripts(p_seats, 1) i
$$;

-- Opens a table with the host in the first chair and returns its code. Also sweeps out what's gone stale.
create or replace function room.new_table(p_game text, p_host uuid, p_chairs int, p_listed boolean, p_options jsonb)
returns text language plpgsql as $$
declare v_code text;
begin
  delete from room.tables where updated_at < now() - interval '45 days';
  delete from room.players p where p.seen_at < now() - interval '180 days' and p.handle is null   -- accounts are kept
    and not exists (select 1 from room.tables t where p.id = any(t.seats));
  delete from room.results where at < now() - interval '2 years';
  if (select count(*) from room.tables) >= 20000 then raise exception 'The game room is full. Try again later.'; end if;
  if (select count(*) from room.tables where seats[1] = p_host and status = 'waiting') >= 8 then
    raise exception 'You already have a few tables waiting. Close one first.';
  end if;
  loop
    v_code := room.new_code();
    begin
      insert into room.tables (code, game, seats, listed, options)
      values (v_code, p_game, array[p_host] || array_fill(null::uuid, array[p_chairs - 1]), coalesce(p_listed, false),
              coalesce(p_options, '{}'));
      exit;
    exception when unique_violation then null;
    end;
  end loop;
  return v_code;
end $$;

-- Puts a player in the first empty chair and returns its seat number (from 0). If they're already at the table it
-- returns the seat they have.
create or replace function room.sit(p_code text, p_player uuid) returns int language plpgsql as $$
declare t room.tables; s int;
begin
  select * into t from room.tables where code = p_code for update;
  if not found then raise exception 'No table with that code'; end if;
  s := array_position(t.seats, p_player);
  if s is not null then return s - 1; end if;
  s := array_position(t.seats, null);
  if t.status <> 'waiting' or s is null then raise exception 'Every seat at this table is taken'; end if;
  t.seats[s] := p_player;
  update room.tables set seats = t.seats, rev = rev + 1, updated_at = now() where code = p_code;
  return s - 1;
end $$;

-- The seat a player has at a table (from 0). Raises if they have none, or if the table is closed and they're
-- trying to make a move.
create or replace function room.seat(p_code text, p_token text, p_moving boolean default true) returns int
language plpgsql as $$
declare me room.players := room.me(p_token); t room.tables; s int;
begin
  select * into t from room.tables where code = p_code;
  s := array_position(t.seats, me.id);
  if s is null then raise exception 'You are not sitting at this table'; end if;
  if p_moving and t.status = 'closed' then raise exception 'This table is closed'; end if;
  return s - 1;
end $$;

/* ---------- the API (public) ---------- */

-- Says who you are. With no key, or one the room has forgotten, you get a new one; otherwise your name, face, and
-- color are updated. The page keeps the key it gets back and sends it with everything else.
create or replace function public.room_hello(p_token text, p_name text, p_avatar text, p_color text)
returns jsonb language plpgsql security definer set search_path = room, public, pg_temp as $$
declare p room.players;
begin
  if p_token is not null and length(p_token) >= 32 then
    select * into p from room.players where key = p_token;
  end if;
  if p.id is null then
    insert into room.players (key, name, avatar, color)
    values (room.new_key(), room.clean_name(p_name), room.clean_avatar(p_avatar), room.clean_color(p_color))
    returning * into p;
  elsif (p.name, p.avatar, p.color) is distinct from
        (room.clean_name(p_name), room.clean_avatar(p_avatar), room.clean_color(p_color)) then
    update room.players set name = room.clean_name(p_name), avatar = room.clean_avatar(p_avatar),
      color = room.clean_color(p_color), seen_at = now() where id = p.id returning * into p;
    update room.tables set rev = rev + 1 where p.id = any(seats);    -- so the others see the new face
  end if;
  return jsonb_build_object('token', p.key, 'name', p.name, 'avatar', p.avatar, 'color', p.color);
end $$;

-- The name and face a key belongs to, for a browser that was just handed the key (a second device).
create or replace function public.room_who(p_token text)
returns jsonb language plpgsql security definer set search_path = room, public, pg_temp as $$
declare me room.players := room.me(p_token);
begin
  return jsonb_build_object('token', me.key, 'name', me.name, 'avatar', me.avatar, 'color', me.color, 'handle', me.handle);
end $$;

-- The open tables anyone in the room can sit down at.
create or replace function public.room_lobby(p_token text default null)
returns jsonb language sql stable security definer set search_path = room, public, pg_temp as $$
  select coalesce(jsonb_agg(jsonb_build_object('code', t.code, 'game', t.game, 'options', t.options,
      'host', room.face(t.seats[1]), 'mine', coalesce(t.seats[1] = me.id, false)) order by t.created_at desc), '[]')
  from room.tables t left join room.players me on me.key = p_token and length(p_token) >= 32
  where t.listed and t.status = 'waiting' and t.updated_at > now() - interval '3 days'
$$;

-- Every table you're sitting at, your turn first.
create or replace function public.room_mine(p_token text)
returns jsonb language plpgsql security definer set search_path = room, public, pg_temp as $$
declare me room.players := room.me(p_token);
begin
  return (
    select coalesce(jsonb_agg(x.item order by x.mine desc, x.at desc), '[]') from (
      select coalesce(t.turn = me.id, false) as mine, t.updated_at as at, jsonb_build_object(
        'code', t.code, 'game', t.game, 'status', t.status, 'options', t.options, 'summary', t.summary,
        'seat', array_position(t.seats, me.id) - 1, 'your_turn', coalesce(t.turn = me.id, false),
        'players', room.faces(t.seats), 'updated_at', t.updated_at) as item
      from room.tables t where me.id = any(t.seats) and t.status <> 'closed'
      order by 1 desc, 2 desc limit 40) x);
end $$;

-- Getting up. A table nobody has joined is simply taken down; one in play is closed for both players, with the
-- scores left as they stand.
create or replace function public.room_leave(p_token text, p_code text)
returns jsonb language plpgsql security definer set search_path = room, public, pg_temp as $$
declare me room.players := room.me(p_token); t room.tables;
begin
  select * into t from room.tables where code = room.code(p_code) for update;
  if not found or array_position(t.seats, me.id) is null then   -- not "= any": an empty chair makes that null
    raise exception 'You are not sitting at this table';
  end if;
  if t.status = 'waiting' then
    delete from room.tables where code = t.code;
  elsif t.status <> 'closed' then
    update room.tables set status = 'closed', left_by = me.id, turn = null, rev = rev + 1, updated_at = now()
    where code = t.code;
  end if;
  return jsonb_build_object('left', true);
end $$;

-- Folds another key's seats into yours, so one person can carry their tables to a second phone or laptop (and so
-- tables from before players existed find their owner). Where both already sit at a table, it's left alone.
create or replace function public.room_adopt(p_token text, p_other text)
returns jsonb language plpgsql security definer set search_path = room, public, pg_temp as $$
declare me room.players := room.me(p_token); other room.players; n int;
begin
  select * into other from room.players where key = p_other and length(p_other) >= 32;
  -- An account is never folded into anything: its tables are reached by logging in to it.
  if other.id is null or other.id = me.id or other.handle is not null then return jsonb_build_object('moved', 0); end if;
  update room.tables set seats = array_replace(seats, other.id, me.id),
    turn = case when turn = other.id then me.id else turn end,
    left_by = case when left_by = other.id then me.id else left_by end, rev = rev + 1
  where other.id = any(seats) and array_position(seats, me.id) is null;
  get diagnostics n = row_count;
  update room.results set players = array_replace(players, other.id, me.id),
    winner = case when winner = other.id then me.id else winner end
  where other.id = any(players) and array_position(players, me.id) is null;
  delete from room.players p where p.id = other.id and not exists (select 1 from room.tables t where p.id = any(t.seats));
  return jsonb_build_object('moved', n);
end $$;

/* ---------- accounts and the leaderboard ---------- */

-- Gives this browser's player a login name and a password. From then on, logging in anywhere hands that device
-- this player's key. A name is 3 to 20 letters, digits or underscores; a password at least 6 characters.
create or replace function public.room_register(p_token text, p_handle text, p_password text)
returns jsonb language plpgsql security definer set search_path = room, public, pg_temp as $$
declare me room.players := room.me(p_token); v_handle text := lower(btrim(coalesce(p_handle, '')));
begin
  if me.handle is not null then raise exception 'You are already logged in as %', me.handle; end if;
  if v_handle !~ '^[a-z0-9_]{3,20}$' then raise exception 'A login name is 3 to 20 letters, digits or underscores'; end if;
  if length(coalesce(p_password, '')) < 6 or length(p_password) > 72 then raise exception 'A password is 6 to 72 characters'; end if;
  begin
    update room.players set handle = v_handle, pass = room.new_pass(p_password), fails = 0, locked_until = null
    where id = me.id;
  exception when unique_violation then raise exception 'That login name is taken';
  end;
  return jsonb_build_object('token', me.key, 'name', me.name, 'avatar', me.avatar, 'color', me.color, 'handle', v_handle);
end $$;

-- Logs in. A wrong name or password is answered {"error": ...} and not raised, so the count of wrong tries is kept:
-- five in a row lock the name for five minutes. On success the answer carries the account's key, and a guest who
-- was playing in this browser (p_token) has their tables and results folded into the account.
create or replace function public.room_login(p_handle text, p_password text, p_token text default null)
returns jsonb language plpgsql security definer set search_path = room, public, pg_temp as $$
declare p room.players; guest room.players; v_handle text := lower(btrim(coalesce(p_handle, '')));
begin
  select * into p from room.players where handle = v_handle for update;
  if p.id is null then
    perform room.new_pass(coalesce(p_password, ''));                 -- as long as a real check takes
    return jsonb_build_object('error', 'That name and password don''t match.');
  end if;
  if p.locked_until is not null and p.locked_until > now() then
    return jsonb_build_object('error', 'Too many wrong tries. Wait a few minutes and try again.');
  end if;
  if not room.pass_ok(p_password, p.pass) then
    update room.players set fails = fails + 1,
      locked_until = case when fails + 1 >= 5 then now() + interval '5 minutes' else null end where id = p.id;
    return jsonb_build_object('error', 'That name and password don''t match.');
  end if;
  update room.players set fails = 0, locked_until = null, seen_at = now() where id = p.id;
  if p_token is not null and length(p_token) >= 32 then
    select * into guest from room.players where key = p_token;
    if guest.id is not null and guest.id <> p.id and guest.handle is null then
      update room.tables set seats = array_replace(seats, guest.id, p.id),
        turn = case when turn = guest.id then p.id else turn end,
        left_by = case when left_by = guest.id then p.id else left_by end, rev = rev + 1
      where guest.id = any(seats) and array_position(seats, p.id) is null;
      update room.results set players = array_replace(players, guest.id, p.id),
        winner = case when winner = guest.id then p.id else winner end
      where guest.id = any(players) and array_position(players, p.id) is null;
      delete from room.players g where g.id = guest.id and not exists (select 1 from room.tables t where g.id = any(t.seats));
    end if;
  end if;
  return jsonb_build_object('token', p.key, 'name', p.name, 'avatar', p.avatar, 'color', p.color, 'handle', p.handle);
end $$;

-- A new password for the account this browser is logged in to. The old one is asked for, and counted like a login.
create or replace function public.room_password(p_token text, p_old text, p_new text)
returns jsonb language plpgsql security definer set search_path = room, public, pg_temp as $$
declare me room.players := room.me(p_token);
begin
  if me.handle is null then raise exception 'Log in first'; end if;
  if length(coalesce(p_new, '')) < 6 or length(p_new) > 72 then raise exception 'A password is 6 to 72 characters'; end if;
  if me.locked_until is not null and me.locked_until > now() then
    return jsonb_build_object('error', 'Too many wrong tries. Wait a few minutes and try again.');
  end if;
  if not room.pass_ok(p_old, me.pass) then
    update room.players set fails = fails + 1,
      locked_until = case when fails + 1 >= 5 then now() + interval '5 minutes' else null end where id = me.id;
    return jsonb_build_object('error', 'That is not your current password.');
  end if;
  update room.players set pass = room.new_pass(p_new), fails = 0, locked_until = null where id = me.id;
  return jsonb_build_object('changed', true);
end $$;

-- The leaderboard: players with accounts, by games won. Only a game between players who both have accounts counts,
-- so a record cannot be run up against throwaway guests. p_game narrows it to one game; p_token marks the caller.
create or replace function public.room_leaderboard(p_game text default null, p_token text default null)
returns jsonb language sql stable security definer set search_path = room, public, pg_temp as $$
  select coalesce(jsonb_agg(jsonb_build_object('name', x.name, 'avatar', x.avatar, 'color', x.color, 'handle', x.handle,
      'wins', x.wins, 'losses', x.games - x.wins, 'me', x.me) order by x.wins desc, x.games, x.handle), '[]')
  from (
    select p.name, p.avatar, p.color, p.handle, count(*) filter (where r.winner = p.id) as wins, count(*) as games,
           coalesce(p.key = p_token, false) as me
    from room.players p join room.results r on p.id = any(r.players)
    where p.handle is not null and r.winner is not null and (p_game is null or r.game = p_game)
      and not exists (select 1 from unnest(r.players) q left join room.players o on o.id = q where o.handle is null)
    group by p.id order by 5 desc, 6 limit 50) x
$$;

/* ---------- notifications: a buzz on a player's phone when the table is waiting on them ---------- */

-- A phone or browser that asked to be told. The endpoint is the address its maker (Apple, Google, Mozilla) gave it
-- for messages; the two keys seal a message so only that device can read it.
create table if not exists room.push (
  endpoint    text primary key,
  player      uuid not null references room.players (id) on delete cascade,
  p256dh      text not null,
  auth        text not null,
  created_at  timestamptz not null default now(),
  last_at     timestamptz                              -- when it was last sent something, to keep from pestering
);
create index if not exists push_player on room.push (player);
alter table room.push enable row level security;      -- and no policies

-- What the sender keeps to itself: the key pair that signs every notification. Made by the sender the first time
-- it runs, and never handed to a page.
create table if not exists room.secrets (name text primary key, value jsonb not null);
alter table room.secrets enable row level security;   -- and no policies

-- This device wants notifications. p_sub is what the browser hands back: {endpoint, keys: {p256dh, auth}}.
create or replace function public.room_push_on(p_token text, p_sub jsonb)
returns boolean language plpgsql security definer set search_path = room, public, pg_temp as $$
declare me room.players := room.me(p_token); v_end text := p_sub ->> 'endpoint';
  v_key text := p_sub -> 'keys' ->> 'p256dh'; v_auth text := p_sub -> 'keys' ->> 'auth';
begin
  if v_end is null or v_end !~ '^https://[a-z0-9.-]+/' or length(v_end) > 1000
     or v_key is null or length(v_key) not between 80 and 120 or v_auth is null or length(v_auth) not between 16 and 40 then
    raise exception 'That is not something notifications can be sent to';
  end if;
  insert into room.push (endpoint, player, p256dh, auth) values (v_end, me.id, v_key, v_auth)
  on conflict (endpoint) do update set player = excluded.player, p256dh = excluded.p256dh, auth = excluded.auth;
  delete from room.push where player = me.id and endpoint not in (   -- a player's five newest devices
    select endpoint from room.push where player = me.id order by created_at desc limit 5);
  return true;
end $$;

create or replace function public.room_push_off(p_token text, p_endpoint text)
returns boolean language plpgsql security definer set search_path = room, public, pg_temp as $$
declare me room.players := room.me(p_token);
begin
  delete from room.push where player = me.id and endpoint = p_endpoint;
  return true;
end $$;

-- The three below are for the sender alone (the "push" edge function); no page may call them.

-- The signing keys. Given a pair when none is stored, it stores that pair; either way it answers what is stored.
create or replace function public.push_keys(p_set jsonb default null)
returns jsonb language plpgsql security definer set search_path = room, public, pg_temp as $$
begin
  if p_set is not null then
    insert into room.secrets (name, value) values ('vapid', p_set) on conflict (name) do nothing;
  end if;
  return (select value from room.secrets where name = 'vapid');
end $$;

-- Who to tell, and what. The caller must be sitting at the table. p_kind is
--   turn   it has become someone's move: told only if they have stepped away
--   say    the caller said p_text: told to whoever has stepped away
--   ring   the caller is asking the others to come back: told whether they are looking or not
-- A device is not sent a turn or a line within ten seconds of its last message, nor a ring within twenty.
-- Answers {title, body, url, tag, subs: [{endpoint, p256dh, auth}]}.
create or replace function public.push_job(p_code text, p_token text, p_kind text, p_text text default null)
returns jsonb language plpgsql security definer set search_path = room, public, pg_temp as $$
declare me room.players := room.me(p_token); t room.tables; v_subs jsonb; v_body text; v_text text;
begin
  select * into t from room.tables where code = room.code(p_code);
  if not found or not (me.id = any(t.seats)) then raise exception 'You are not sitting at this table'; end if;
  if p_kind is null or p_kind not in ('turn', 'say', 'ring') then raise exception 'Unknown kind of notification'; end if;
  v_text := left(btrim(regexp_replace(coalesce(p_text, ''), '[[:cntrl:]]+', ' ', 'g')), 140);
  if p_kind = 'say' and v_text = '' then return jsonb_build_object('subs', '[]'::jsonb); end if;
  with picked as (
    select s.endpoint from room.push s join room.players p on p.id = s.player
    where s.player = any(t.seats) and s.player <> me.id and t.status <> 'closed'
      and (p_kind = 'ring' or p.seen_at < now() - interval '40 seconds')
      and (p_kind <> 'turn' or t.turn = s.player)
      and (s.last_at is null or s.last_at < now() - case when p_kind = 'ring' then interval '20 seconds' else interval '10 seconds' end)
  ), marked as (
    update room.push s set last_at = now() from picked where s.endpoint = picked.endpoint
    returning s.endpoint, s.p256dh, s.auth
  )
  select coalesce(jsonb_agg(jsonb_build_object('endpoint', endpoint, 'p256dh', p256dh, 'auth', auth)), '[]') into v_subs from marked;
  v_body := case p_kind when 'turn' then 'Your turn. ' || me.name || ' is waiting.'
                        when 'say' then me.name || ': ' || v_text
                        else me.name || ' is waiting for you at the table.' end;
  return jsonb_build_object('title', case t.game when 'gin' then 'gin/rummy' else 'game/room' end, 'body', v_body,
    'url', '/games/' || t.game || '/?t=' || t.code, 'tag', t.code, 'subs', v_subs);
end $$;

-- A device that no longer takes messages (it was reset, or notifications were turned off there).
create or replace function public.push_gone(p_endpoint text)
returns boolean language sql security definer set search_path = room, public, pg_temp as $$
  delete from room.push where endpoint = p_endpoint returning true
$$;

do $$
declare f record; r text;
begin
  for f in select p.oid::regprocedure as sig from pg_proc p join pg_namespace n on n.oid = p.pronamespace
           where n.nspname = 'public' and p.proname in ('push_keys', 'push_job', 'push_gone') loop
    execute format('revoke all on function %s from public', f.sig);
    foreach r in array array['anon', 'authenticated'] loop
      if exists (select 1 from pg_roles where rolname = r) then execute format('revoke all on function %s from %I', f.sig, r); end if;
    end loop;
    if exists (select 1 from pg_roles where rolname = 'service_role') then
      execute format('grant execute on function %s to service_role', f.sig);
    end if;
  end loop;
end $$;

do $$
declare f record;
begin
  for f in select p.oid::regprocedure as sig from pg_proc p join pg_namespace n on n.oid = p.pronamespace
           where n.nspname = 'public' and p.proname like 'room\_%' loop
    execute format('revoke all on function %s from public', f.sig);
    if exists (select 1 from pg_roles where rolname = 'anon') then
      execute format('grant execute on function %s to anon, authenticated', f.sig);
    end if;
  end loop;
end $$;
