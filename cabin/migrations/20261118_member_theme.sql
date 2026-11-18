-- Run once in the existing Supabase project's SQL editor.
-- Gives each member somewhere to keep their app theme (light/dark and accent color) so it follows their login to every device.
-- The existing "members edit own" policy already lets a member change only their own row, so nothing else is needed.
alter table public.members
  add column if not exists theme jsonb check (theme is null or length(theme::text) < 400);
