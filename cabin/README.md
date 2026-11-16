# ski/lease

A small web app for the Tahoe ski lease: who is sleeping at the house on which nights, how many guests they are bringing, and who owes whom for house bills. It lives at `livefreeandfly.org/cabin/` and replaces the spreadsheet.

## Who it is for

The lease members, roughly six to twelve people, on their phones, about once a week during the season. Everyone has a name, an email, and a phone number on file. Nobody else can see anything.

## Principles

- **One tap for the common thing.** Saying “I’m up Saturday” is a single tap from the first screen.
- **No maintenance.** No admin role, no approvals, no categories to curate. Any member can add or fix anything, the way a shared spreadsheet works.
- **Fits the repo.** One self-contained `index.html`, no build step, same look as the rest of the site.

## What it does (v1, built)

### Calendar

- A strip for the current weekend (Friday, Saturday, Sunday nights). Tap a night to add or remove yourself.
- A month calendar. Each night shows a dot per member and a headcount. Your nights are marked in red.
- Tap any night to see who is in, set how many guests you are bringing, and leave a short note (“arriving late”).
- Headcount includes guests and is compared to the number of beds. A night over capacity is flagged; nothing is blocked.
- The house has lease dates. Nights outside the lease are greyed out and can’t be booked, and the calendar opens on the lease’s first month until it starts.
- A date always means the night you sleep there, so “Saturday” is Saturday night into Sunday.
- Guests are added by name on the night they stay. Each costs a nightly fee, $60 by default and editable under House Info. Each night keeps the rate it was booked at.
- Guests pay one member, chosen by the admin, directly. A detail panel lists every guest with their sponsor, nights, and amount, a Venmo pay link to send them, and a paid mark that the admin or the collecting member can set.
- The admin marks each member full time or part time. A part-timer pays a lease, set per person, to the collecting member, and is left out of new expenses by default.
- Guest money and leases that have been received sit in a season pot. Nothing in it affects balances until the admin pays it out; then it is split equally between full-time members and the collecting member settles up with them.

### Money

- Add an expense: what, how much, who paid, the date, and who it is split between. The split is even and defaults to everyone.
- Your balance at the top: you are owed, you owe, or you are settled up.
- Each person has a Settle up button that shows only their own payments, worked out so the house needs as few payments as possible. If the person you owe has a Venmo username on file, Pay on Venmo opens Venmo with the amount and a note filled in; the app then asks you to confirm so the balances update. People who are owed get a Request on Venmo link.
- Balances for every member, and a running list of expenses and payments. Tap one to edit or delete it.
- Amounts are stored in cents. Leftover pennies from an uneven division are handed out one at a time so the books always sum to zero.

### House Info

- Address, door code, Wi-Fi, bed count, and house notes, editable by any member.
- The member list with call, text, and email links.
- Any member can add a member with name, email, and phone. After that, a profile (name, picture, phone, Venmo) can only be edited by its owner.
- One member is the admin. The admin can correct a sign-in email, remove a member, and set the guest fee. Removing someone keeps their past expenses on the books.

## Left out on purpose

Uneven or percentage splits, receipt photos, expense categories, approvals, per-member permissions, and in-app payments. Each adds upkeep. They can come later if the house asks for them.

## How it is built

The site is static files on GitHub Pages, one folder per app, so this follows the same shape rather than the Next.js app first proposed.

| Piece | Choice | Why |
|---|---|---|
| Page | `cabin/index.html`, plain HTML, CSS, and JavaScript | Matches `fog/`, `burnoff/`, `drive/`. No build, no dependencies to update. |
| Shared data | Supabase (hosted Postgres) | A static page needs somewhere shared to keep data. Called straight from the browser. |
| Sign-in | Supabase magic link by email | No passwords to manage. People stay signed in on their phone. |
| Privacy | Postgres row-level security | The repo and the public key are both public, so the database itself enforces “members only”. |

The page has two modes. With the two config values at the top of the file left blank it runs on sample data stored in the browser, which is what the preview shows. With them filled in it reads and writes Supabase and asks people to sign in.

### Data model

| Table | Fields |
|---|---|
| `members` | name, email (unique), phone, color, active |
| `stays` | member, night, guests, note. One row per member per night. |
| `expenses` | description, amount in cents, paid by, split among (list of members), date |
| `payments` | from, to, amount in cents, date, note |
| `house` | one row: name, address, door code, Wi-Fi, beds, notes |

Balances are never stored. They are computed from expenses and payments each time, so an edit or a delete can never leave them stale.

### Who can see what

A signed-in person counts as a member when their email is on the active member list. Members can read and change everything. Everyone else, including someone who signs in with an email that is not on the list, gets empty results. The door code and Wi-Fi password are covered by the same rule.

## Going live

1. Create a free Supabase project.
2. Open the SQL editor, paste `cabin/schema.sql`, change the seed row at the bottom to your own name, email, and phone, and run it.
3. Under Authentication, set the site URL to `https://livefreeandfly.org/cabin/` and add it to the allowed redirect URLs.
4. Copy the project URL and the anon key into `CONFIG` at the top of the script in `cabin/index.html`.
5. Commit and push. Sign in, then add everyone else from the House tab.

Two things to check on Supabase’s current free plan before relying on it: whether idle projects are paused (weekly use in season should keep it awake, summer may not), and how many sign-in emails per hour the built-in mailer allows. If the email limit is tight, connecting an email service such as Resend fixes it.

## Next (not built)

1. **Weekly digest.** A scheduled GitHub Action that reads the weekend’s stays and open balances and emails the group on Thursday. It needs a mail service and a Supabase service key stored as a repo secret. Email first; texting through Twilio means carrier registration, which is more setup than a group this size wants.
2. **Guest fee.** An optional nightly charge per guest that posts to the money tab automatically.
3. **Uneven splits.** By amount or by nights stayed, for bills like utilities.
4. **Calendar feed.** A subscribe link so nights show up in everyone’s phone calendar.
5. **Live updates.** Today the page refreshes when you return to it. Supabase can push changes as they happen.

## Open questions for the house

- Is there a rule for busy nights, such as a guest cap or members-first on holiday weekends? The app flags over-capacity nights but does not stop them.
- Do rent and the deposit go through this, or only running costs?
- Should removing a member require their balance to be zero?
- Is `/cabin/` linked from the home page, or reachable only by people who have the link? The data is private either way.
