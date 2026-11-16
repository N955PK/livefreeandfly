-- ski/lease: Supabase schema. Paste into the SQL editor and run once.
-- Edit the seed row at the bottom first so you can sign in.

create extension if not exists pgcrypto;

create table members (
  id         uuid primary key default gen_random_uuid(),
  name       text not null,
  email      text not null,
  phone      text not null,
  color      text,
  venmo      text,
  avatar     text check (avatar is null or length(avatar) < 60000),  -- small inline picture or 'emoji:…'
  active     boolean not null default true,
  pool_share boolean not null default true,          -- gets a cut of guest fees (admin sets this)
  is_admin   boolean not null default false,        -- can remove members, fix emails, set the guest fee
  created_at timestamptz not null default now()
);
create unique index members_email_key on members (lower(email));

create table stays (
  id         uuid primary key default gen_random_uuid(),
  member_id  uuid not null references members(id) on delete cascade,
  night      date not null,                       -- the night slept at the house
  guests     int  not null default 0 check (guests between 0 and 12),
  guest_names text[] not null default '{}',        -- one name per guest; guests = how many
  guest_paid  text[] not null default '{}',        -- guests whose fee for this night has been received
  guest_fee_cents int,                            -- per-guest rate when this night was booked
  note       text,
  created_at timestamptz not null default now(),
  unique (member_id, night)
);
create index stays_night_idx on stays (night);

create table expenses (
  id           uuid primary key default gen_random_uuid(),
  description  text not null,
  amount_cents int  not null check (amount_cents > 0),
  paid_by      uuid not null references members(id),
  split_among  uuid[] not null check (cardinality(split_among) > 0),  -- even split
  spent_on     date not null default current_date,
  created_at   timestamptz not null default now()
);

create table payments (
  id           uuid primary key default gen_random_uuid(),
  from_member  uuid not null references members(id),
  to_member    uuid not null references members(id),
  amount_cents int  not null check (amount_cents > 0),
  paid_on      date not null default current_date,
  note         text,
  created_at   timestamptz not null default now(),
  check (from_member <> to_member)
);

create table house (
  id            int primary key default 1 check (id = 1),   -- one row
  name          text,
  address       text,
  door_code     text,
  wifi_name     text,
  wifi_password text,
  beds          int not null default 8,
  guest_fee_cents int not null default 6000,     -- nightly fee per guest
  guest_collector uuid references members(id),   -- the member guests pay directly
  listing_url   text,                            -- the rental listing, for general information
  lease_start   date,                            -- first night of the lease
  lease_end     date,                            -- move-out day; the last night is the one before
  notes         text
);
insert into house (id, name) values (1, 'Tahoe house');

-- Who counts as a member: the signed-in email is on the active list.
-- security definer so the check can read members without tripping its own policy.
create or replace function is_member() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from members
    where lower(email) = lower(auth.jwt() ->> 'email') and active
  );
$$;

-- Trust model: any member can read and change anything, like a shared
-- spreadsheet. Everyone else, signed in or not, sees nothing.
do $$
declare t text;
begin
  foreach t in array array['members','stays','expenses','payments','house'] loop
    execute format('alter table %I enable row level security', t);
    execute format(
      'create policy "members only" on %I for all to authenticated using (is_member()) with check (is_member())', t);
  end loop;
end $$;

-- Profiles belong to their owner. Any member can add someone, but only you
-- can edit your own row; the admin can also correct an email or remove a member.
create or replace function is_admin() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from members
    where lower(email) = lower(auth.jwt() ->> 'email') and active and is_admin
  );
$$;

drop policy if exists "members only" on members;
drop policy if exists "members read" on members;
drop policy if exists "members add" on members;
drop policy if exists "members edit own" on members;
create policy "members read" on members for select to authenticated using (is_member());
create policy "members add"  on members for insert to authenticated with check (is_member());
create policy "members edit own" on members for update to authenticated
  using (is_admin() or lower(email) = lower(auth.jwt() ->> 'email'))
  with check (is_member());

-- Signed-in non-admins cannot change who is an admin, anyone's sign-in email,
-- whether someone is active, or who shares guest money. (Edits made in the Supabase dashboard are not affected.)
create or replace function members_guard() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if coalesce(auth.jwt() ->> 'email', '') <> '' and not is_admin() then
    if tg_op = 'INSERT' then
      new.is_admin := false; new.active := true; new.pool_share := true;
    else
      new.is_admin := old.is_admin; new.email := old.email; new.active := old.active; new.pool_share := old.pool_share;
    end if;
  end if;
  return new;
end $$;
drop trigger if exists members_guard on members;
create trigger members_guard before insert or update on members
  for each row execute function members_guard();

-- Only the admin can change the guest fee, the lease dates, and who guests pay.
create or replace function house_guard() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if coalesce(auth.jwt() ->> 'email', '') <> '' and not is_admin() then
    new.guest_fee_cents := old.guest_fee_cents;
    new.lease_start := old.lease_start; new.lease_end := old.lease_end;
    new.guest_collector := old.guest_collector;
  end if;
  return new;
end $$;
drop trigger if exists house_guard on house;
create trigger house_guard before update on house
  for each row execute function house_guard();

-- Only the admin or the member guests pay can mark a guest as paid.
create or replace function stays_guard() returns trigger
language plpgsql security definer set search_path = public as $$
declare me text := lower(coalesce(auth.jwt() ->> 'email', ''));
begin
  if me <> '' and not is_admin() and not exists (
    select 1 from house h join members m on m.id = h.guest_collector where lower(m.email) = me and m.active
  ) then
    if tg_op = 'INSERT' then new.guest_paid := '{}'; else new.guest_paid := old.guest_paid; end if;
  end if;
  return new;
end $$;
drop trigger if exists stays_guard on stays;
create trigger stays_guard before insert or update on stays
  for each row execute function stays_guard();

-- New Supabase projects no longer expose tables to the browser API by
-- default, so grant signed-in users access explicitly. Row-level security
-- above still decides which rows they get. Nothing is granted to anon.
grant select, insert, update, delete on members, stays, expenses, payments, house to authenticated;
grant execute on function is_member() to authenticated;
grant execute on function is_admin() to authenticated;

-- Seed yourself, then add everyone else from the House tab.
insert into members (name, email, phone, color, is_admin)
values ('Your Name', 'you@example.com', '(530) 555-0100', '#39d0a4', true);
