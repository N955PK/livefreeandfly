-- Run once in the existing Supabase project's SQL editor.
-- Occupancy is informational; retain only the nonnegative guest-count check.
begin;
alter table public.stays drop constraint if exists stays_guests_check;
alter table public.stays add constraint stays_guests_check check (guests >= 0);
commit;
