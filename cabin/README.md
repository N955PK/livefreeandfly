# ski/lease

A small web app for the Tahoe ski lease: who is sleeping at the house on which nights, how many guests they are bringing, and who owes whom for house bills. It lives at `livefreeandfly.org/cabin/` and replaces the spreadsheet.

## Who it is for

The lease members, roughly six to twelve people, on their phones, about once a week during the season. Everyone has a name, an email, and a phone number on file. Nobody else can see anything.

## Principles

- **Calendar first.** Open a night to join, or pick several nights by tapping or dragging on the month calendar.
- **Light upkeep.** A few admins look after members, fees, and house settings. Everything else, like nights, expenses, and payments, any member can add, and each person looks after what they added.
- **Fits the repo.** One self-contained `index.html`, no build step, same look as the rest of the site.

## What it does (v1, built)

### Calendar

- A month calendar. Each night shows a dot per member and a headcount. Your nights are marked in red.
- Tap any night to see who is in, set how many guests you are bringing, and leave a short note (“arriving late”).
- Headcount includes guests. Occupancy text is normal for 0–7 people, amber for 8–11, and red for 12 or more. Night details say “Getting crowded” or “Very crowded.” These are informational: there is no occupancy or per-member guest cap.
- Ikon blackout nights are striped. They're the dates the Ikon Base and Ikon Session passes are blacked out at Palisades Tahoe (the full Ikon Pass has none), from ikonpass.com. The list is `IKON_BLACKOUTS` near the top of the calendar code in `index.html`; update it each season. Opening a striped night says so.
- Holidays (MLK Day, Valentine's, Presidents' Day, Mardi Gras, St. Patrick's Day, Easter, and a few more) show a soft emoji on the night and are named when you open it. They're worked out for any year, so there's nothing to update.
- The month arrows sit either side of the month title, which leaves out the year when it's the lease's own year.
- **Who can change a night.** You can add, change, or remove only your own nights, and only inside the lease dates; an admin can change anyone's. The member who collects can mark another member's guests as paid, and nothing else on that night. The nightly guest fee is stamped by the database from House Info, so it can't be set from the browser, and a night keeps the rate it was first booked at (`migrations/20261119_tighten_rules.sql`).
- **Who can change an entry.** Whoever enters an expense has to be the payer or one of the people it's split between, and whoever enters a payment has to be the one paying or being paid, so nobody can put a charge on two other people. An entry can be edited only by the person who entered it or by an admin; the member who collects can also look after pot expenses. Anyone named in an ordinary entry can also delete it, so a wrong charge on you doesn't have to wait for an admin: tapping it shows the details and a Delete button (`migrations/20261119_entry_parties.sql`). In the app, entries you can't change simply aren't tappable. In the database (`migrations/20261118_entry_owners.sql`) the owner is stamped from the sign-in and can't be faked or reassigned. Entries made before that update have no recorded owner, so only admins can change those.
- **Season totals** is the private table at the bottom of the Money tab, in place of the old Due back section. It lists the total paid up front, a bold line, your share of the lease, your share of house bills (which adds to what you pay), your total refund with its two sources indented beneath it (in a lighter weight) (security deposit and your share of guest fees and leases, shown as negatives because they make up the refund rather than add to it), another bold line, and a bottom line, **Your total season cost**: your final individual share (your share of the lease plus house bills, less the refund). Every number is hidden behind dots until you tap one; one tap shows all of them and another hides them all, and they hide again whenever the page redraws. Full-time members see the refund lines; part-timers see just the total and their share; until the pot is paid out, the guest-fee share reads "At payout" for everyone but admins and the collector. The lease itself stays out of the payment history: an admin ticks which expenses and payments belong to it with **Choose entries** in Season costs, a section of The pot and leases (admins only). That section shows just the total paid up front and one green check, "All full-time members paid their share"; if someone hasn't, only the people who owe are named, not everyone's payments. The "Includes …" line under the total reads rent, fixed utilities, security deposit, booking fee, or follows a saved breakdown. Entries are only tagged, never deleted or changed, so everyone's balance is exactly the same before and after, and untagging puts them straight back in the history. Only admins can tag, untag, or edit them, in the app and in the database (`migrations/20261118_season_costs.sql`).
- **App theme** is in your profile (tap your name at the top), below Save and Cancel. Each person picks light, dark, or auto, and an accent color: Tech (the original), Powder, Pine, Sunset, Bubblegum, Grape, Aurora, Lemonade, Hot Cocoa, Slate, Disco (which drifts through every color), or Custom, which opens a color wheel with a brightness slider and a hex box. The skier is filled with the exact accent color. Changes apply right away. The theme is saved on your member row (the `theme` column, from `migrations/20261118_member_theme.sql`), so it follows your login to every device; the account's copy wins whenever you sign in, and this device keeps a copy only so the page is themed before sign-in. Until the migration has been run, the theme stays on the device and the profile says so. Button text switches between white and black, and link colors are nudged, so text stays readable for every accent in both light and dark (checked for the built-in colors and for a sweep of 216 custom colors).
- Swipe the calendar sideways to change month. The next month follows your finger and settles into place, and you can grab it or swipe again while it's still moving to keep scrolling through months. The arrow buttons under the calendar do the same, quickly. In "pick several nights" mode, dragging selects nights instead, and the arrows change the month.
- The house has lease dates. Nights outside the lease are greyed out and can’t be booked, and the calendar opens on the lease’s first month until it starts.
- A date always means the night you sleep there, so “Saturday” is Saturday night into Sunday.
- Several nights can be picked at once from the calendar and booked together, for yourself, guests, or both. In “Pick several nights,” tap individual dates or drag across a range (mouse, touch, or pen). Start on a selected night to deselect a range. Dragging back shrinks the range; dates outside your booking window are skipped. On phones, scroll outside the calendar while selecting. To cancel existing bookings, select the nights, tap Continue, then Remove my nights. If guests are booked, choose whether to keep them or remove them too; other members are unaffected.
- A member can send guests on a night they aren't staying themselves.
- Guests are added by name on the night they stay. Each costs a nightly fee, $60 by default and editable under House Info. Each night keeps the rate it was booked at.
- Guests pay one member, chosen by the admin, directly. The guest ledger, a detail panel, lists every guest with their sponsor, nights, and amount, a Venmo pay link to send them, and a received mark that the admin or the collecting member can set.
- The admin marks each member full time or part time from that member's Manage button in House Info (an admin's own row has one too, for their own role). A part-timer pays a lease, set per person, to the collecting member, can only book nights inside the dates the admin gives them, and is left out of new expenses by default.
- Each full-time member paid a security deposit up front ($445 by default). It comes back through the pot, less anything withheld, which comes off everyone equally.
- There can be more than one admin; an admin can make another member an admin.
- An admin or the collecting member can mark an expense as coming out of the pot, for utilities and other house bills. It is split between everyone on the lease in the month of its date. A part-timer's share is charged to them right away; a full-timer's share waits and comes off what they get back at payout.
- Guest fees and leases that have been received sit in the pot. Nothing in it affects balances until the admin pays it out; then it is split equally between full-time members and the collecting member settles up with them.

### Offline

The page and its files stay on the phone (`sw.js`, a service worker), and the page keeps a copy of the last house data it loaded. With no signal it still opens and shows the calendar, door code, and Wi-Fi, with a note saying when the data is from. Nothing can be saved until the connection comes back, and then it refreshes on its own. On a weak signal it waits a few seconds for a fresh copy before using the saved one. Signing out wipes the saved data from that phone.

### Live updates

When anyone books a night, adds an expense, or changes the house, everyone else's open page refreshes within a second or so (Supabase realtime, turned on by `migrations/20261119_live_updates.sql`). It waits while you have a panel open or a finger on the calendar, so nothing moves under you. Row-level security still decides who hears about what.

### Calendar feed

In your profile, **Calendar** makes a private link that your phone's calendar subscribes to. **Add to Apple Calendar** (iPhone and Mac) and **Add to Google Calendar** each add it in one tap; **Copy link** is for anything else, like Outlook. Your nights show up as events (one per run of nights in a row), with who else is there each night, your guests, and your note, and the calendar checks for changes every few hours. The link holds a random token only you can see; **New link** replaces it and stops the old one working. The feed comes from a small Supabase edge function, `supabase/functions/calendar/index.ts`; the section appears once `migrations/20261119_calendar_feed.sql` has been run.

### Money

- Add an expense: what, how much, who paid, the date, and who it is split between. The split is even. New expenses start with nobody selected; choose the people to include before saving.
- Your balance at the top: you are owed, you owe, or you are settled up.
- Each person has a Settle up button that shows only their own payments, worked out so the house needs as few payments as possible. If the person you owe has a Venmo username on file, Pay on Venmo opens Venmo with the amount and a note filled in; the app then asks you to confirm so the balances update. People who are owed get a Request on Venmo link.
- Balances for every member, and a running list of expenses and payments. Tap one to edit or delete it.
- Amounts are stored in cents. Leftover pennies from an uneven division are handed out one at a time so the books always sum to zero.

### House Info

- Address, door code, Wi-Fi, bed count, and house notes. Every member can see them; only admins can change them.
- The member list with call, text, and email links.
- Only an admin can add a member, with name, email, and phone. After that, a profile (name, picture, phone, Venmo) can only be edited by its owner.
- Admins can correct a sign-in email, remove a member, and set the guest fee. Removing someone keeps their past expenses on the books.

### Snow

- A fourth tab shows the Sierra Snow forecast (`livefreeandfly.org/snow/`) in a frame between the header and the tabs. It is the public page itself, opened as `../snow/?embed`, which drops that page's own title; its loading animation still plays while the forecast and map load.
- The forecast's controls and highlights (the chosen region, the storm slider, the favorite star) take this app's accent color and follow it when it changes. Snow amounts keep the forecast's own colors, since those carry meaning.
- The frame sits outside `main`, so the app's redraws never reload it, and it loads the first time the tab is opened.
- It needs a signal. Offline, the tab says so and loads when the connection returns; the rest of the app keeps working from its saved copy.

## Left out on purpose

Uneven or percentage splits, receipt photos, expense categories, approvals, per-member permissions, and in-app payments. Each adds upkeep. They can come later if the house asks for them.

## How it is built

The site is static files on GitHub Pages, one folder per app, so this follows the same shape rather than the Next.js app first proposed.

| Piece | Choice | Why |
|---|---|---|
| Page | `cabin/index.html`, plain HTML, CSS, and JavaScript | Matches `fog/`, `burnoff/`, `drive/`. No build, no dependencies to update. |
| Shared data | Supabase (hosted Postgres) | A static page needs somewhere shared to keep data. Called straight from the browser. |
| Sign-in | Google, through Supabase Auth | No passwords to manage. People stay signed in on their phone. |
| Calendar feed | One Supabase edge function | Calendar apps can't sign in, so a private token in the link stands in for it. |
| Privacy | Postgres row-level security | The repo and the public key are both public, so the database itself enforces “members only”. |

The page and `sw.js` are the whole front end. The page has two modes. With the two config values at the top of the file left blank it runs on sample data stored in the browser, which is what the preview shows. With them filled in it reads and writes Supabase and asks people to sign in.

### Data model

| Table | Fields |
|---|---|
| `members` | name, email (unique), phone, color, Venmo, picture, theme, active, admin, full or part time, a part-timer's lease and dates |
| `stays` | member, night, guest names, which guests have paid, the guest rate, whether the member is there themselves, note. One row per member per night. |
| `expenses` | description, amount in cents, paid by, split among (list of members), date, from the pot, season cost, who entered it |
| `payments` | from, to, amount in cents, date, note, season cost, who entered it |
| `house` | one row: name, address, door code, Wi-Fi, beds, notes, guest fee, collecting member, lease dates, deposit, pot payout |
| `calendar_tokens` | member, token. Only you can see yours. |

Balances are never stored. They are computed from expenses and payments each time, so an edit or a delete can never leave them stale.

### Who can see what

A signed-in person counts as a member when their email is on the active member list. Members can read everything, and the database itself enforces who can change what: your own profile and nights, the entries you made, and, for admins, the house settings and everything else. Everyone else, including someone who signs in with an email that is not on the list, gets empty results. The door code and Wi-Fi password are covered by the same rule.

## Going live

1. Create a free Supabase project.
2. Open the SQL editor, paste `cabin/schema.sql`, change the seed row at the bottom to your own name, email, and phone, and run it.
3. Under Authentication, turn on the Google provider and turn off the Email provider (every rule trusts the sign-in's email address, and Google proves it; leave "Allow new users to sign up" on so newly added members can sign in the first time), set the site URL to `https://livefreeandfly.org/cabin/`, and add it to the allowed redirect URLs.
4. Copy the project URL and the anon key into `CONFIG` at the top of the script in `cabin/index.html`.
5. Deploy the calendar function (see below).
6. Commit and push. Sign in, then add everyone else from the House tab.

Two things to check on Supabase’s current free plan before relying on it: whether idle projects are paused (weekly use in season should keep it awake, summer may not), and how many realtime connections the plan allows (a house this size is far under it).

### Updating an existing database

For the occupancy indicators and removal of the guest cap, run `cabin/migrations/20261117_remove_guest_cap.sql` in the Supabase SQL editor. Updating the static site alone does not remove the old database constraint. Fresh databases use the updated `schema.sql`.

For a theme that follows each person's login to every device, run `cabin/migrations/20261118_member_theme.sql` in the Supabase SQL editor (it adds one column to `members`).

For season costs, run `cabin/migrations/20261118_season_costs.sql` in the Supabase SQL editor. It adds a few columns and tightens one rule. Until it's run, the Season costs button is replaced by a note for admins; members still see their Season totals, built from the pot, without the lease lines.

To make sure only the person who entered an expense or payment, or an admin, can change or delete it, run `cabin/migrations/20261118_entry_owners.sql` in the Supabase SQL editor (after the season costs one). Entries made before then have no recorded owner, so only admins can change those. Until it's run, any member can still change any entry.

To close the house and nights rules (only admins can add or remove the house row, members change only their own nights, and the guest fee comes from House Info), run `cabin/migrations/20261119_tighten_rules.sql`. Before it, any member could delete the house row or book guests at no charge by talking to the database directly.

For the entry and lease-date rules, run `cabin/migrations/20261119_entry_parties.sql` (after the tighten rules one).

For live updates, run `cabin/migrations/20261119_live_updates.sql`. Until then the page still refreshes when you come back to it.

For the calendar feed, run `cabin/migrations/20261119_calendar_feed.sql` (after the tighten rules one), then deploy the function:

- **From the dashboard:** Edge Functions, Deploy a new function, Via editor. Name it `calendar`, paste in `cabin/supabase/functions/calendar/index.ts`, and deploy. Then open its settings and turn off **Verify JWT** (calendar apps can't sign in; the token in the link is checked instead).
- **Or with the Supabase CLI,** from the `cabin/` folder: `supabase functions deploy calendar --project-ref <project ref>`. `supabase/config.toml` already turns JWT checking off for it.

The function reads with the service role key Supabase gives every edge function, so nothing needs to be set up by hand.

### Updating the page

`sw.js` fetches the page fresh whenever there's signal, so pushes show up on the next open. If you change `sw.js` itself or the files it keeps, bump `VERSION` at its top. If you bump the supabase-js version, update `SUPABASE_JS` and `SUPABASE_SRI` in `index.html` and `SUPABASE_JS` in `sw.js` together; the browser refuses the file if the hash doesn't match. The spreadsheet library works the same way (`XLSX_JS` and `XLSX_SRI`).

## Next (not built)

1. **Weekly digest.** A scheduled GitHub Action that reads the weekend’s stays and open balances and emails the group on Thursday. It needs a mail service and a Supabase service key stored as a repo secret. Email first; texting through Twilio means carrier registration, which is more setup than a group this size wants.
2. **Uneven splits.** By amount or by nights stayed, for bills like utilities.
3. **Payment confirmations.** The person paid ticks "received" before a logged payment counts.

## Open questions for the house

- Crowding indicators are informational only; busy nights remain bookable.
- Do rent and the deposit go through this, or only running costs?
- Should removing a member require their balance to be zero?
- Is `/cabin/` linked from the home page, or reachable only by people who have the link? The data is private either way.

## Type

One type scale, defined once at the top of the stylesheet in `cabin/index.html` (the `--t-…` variables). The rule is simple: mono is for titles, labels, tabs, and codes; sans is for everything you read. Every screen and panel uses these jobs and nothing else, and the privacy page matches.

| Job | Font | Size and weight |
|---|---|---|
| Page title | mono | 24, semibold |
| Panel title | mono | 17, semibold |
| Calendar month title | mono | 15, semibold |
| Section label (every heading inside a page or panel, and guest group labels) | mono | 14, semibold, capitals, grey |
| Body (names, values, form text) | sans | 16 |
| Amounts | sans | 16, semibold (the big balance at the top is 36, bold) |
| Secondary text | sans | 14, grey |
| Captions and field labels | sans | 13, grey |
| Buttons | sans | 15 semibold (quiet buttons 500); small buttons 13 semibold (quiet 500) |
| Codes (door code, Wi-Fi password) | mono | 16, spaced |

When adding something new, pick the job it does and use that style rather than choosing a size.
