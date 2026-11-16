-- cabin/time: Supabase schema. Paste into the SQL editor and run once.
-- Edit the seed row at the bottom first so you can sign in.

create extension if not exists pgcrypto;

create table members (
  id         uuid primary key default gen_random_uuid(),
  name       text not null,
  email      text not null,
  phone      text not null,
  color      text,
  active     boolean not null default true,
  created_at timestamptz not null default now()
);
create unique index members_email_key on members (lower(email));

create table stays (
  id         uuid primary key default gen_random_uuid(),
  member_id  uuid not null references members(id) on delete cascade,
  night      date not null,                       -- the night slept at the house
  guests     int  not null default 0 check (guests between 0 and 12),
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

-- Seed yourself, then add everyone else from the House tab.
insert into members (name, email, phone, color)
values ('Your Name', 'you@example.com', '(530) 555-0100', '#39d0a4');
