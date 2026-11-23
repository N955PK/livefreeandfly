-- game/room, part 1 of 2: the room itself. Run this, then 2_gin.sql, in the Supabase project's SQL editor.
-- Both files are the whole current definition and are safe to run again at any time; they upgrade what's there
-- in place and keep every table in play.
--
-- The room is everything the games share: who a player is, which tables exist, who sits where, the list of open
-- tables, sitting down and leaving. Each game keeps its own cards and rules in its own schema (gin, so far) and hangs
-- them off a row in room.tables. Nothing here is reachable through the API except the public room_* functions.
--
-- A player is a browser, not an account: the page keeps a long random key and sends it with every call. The
-- member_id column is where a ski/lease member will be attached once the two are joined up; nothing reads it yet.

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
  delete from room.players p where p.seen_at < now() - interval '180 days'
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
  return jsonb_build_object('token', me.key, 'name', me.name, 'avatar', me.avatar, 'color', me.color);
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
  if other.id is null or other.id = me.id then return jsonb_build_object('moved', 0); end if;
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
