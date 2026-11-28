# Ace

Games for two, played over a link. It lives at `livefreeandfly.org/games/`. Gin rummy is the first one, at `/games/gin/`.

## The look

Ace has a look of its own (the mark is a spade in outline with a gunsight where its heart would be, drawn in `icons/mark.svg` from the owner's own picture and dressed for the app icon in `icons/icon.svg`; the name is the card and the pilot) and follows the
same rules as Turbo Snow: the phone's own lettering, a page and its surfaces in the phone's light or dark, one accent
(green), hairline borders, and everything that can be tapped a pill that dips under the finger and springs back.
Pop-ups are sheets that rise from the bottom. Copy is plain whole sentences. The one place with colors of its own
is a game's table, which is cloth: there everything is light on dark whatever the phone's setting, tapped things are
dark glass pills of a few fixed heights, and gold is the single highlight (whose turn it is, what is chosen, the
thing to do next). `room.css` holds the shared pieces and the colors; a game's page adds only its table.

## The score pad

`score/` is a gin rummy score sheet for a game played with real cards, for two or three players. It talks to no
server: the sheet is kept on the device. Tap who won the hand, type the points, add. The games of a Hollywood match
sit side by side, each with a column for every player, and each hand is a row showing the running total where it
counted. It works out which games a hand counts in, closes a game at the target, counts the boxes, and settles each
finished game by the same convention as the online table (game bonus, boxes, shutout, money a point), pair by pair
when there are three. Points can be taken away with the + / − switch, the last line undone, or any line tapped to
take it off; the sheet is always added up again from its lines.

## How it works

You pick a name and a face, open a table, and send the link (or list the table in the room so anyone there can sit
down). A player is a browser: the first time it does anything, the room hands it a long random key, and that key goes
with every call after. "Play on another device" hands the same key to a second phone or laptop by link or QR code,
so both sit in your seat at every table.

An account is optional: a login name and a password attached to that player. Logging in on any phone or computer
hands it the account's key, so your tables and your record are there; anything played in that browser as a guest
is folded into the account. The leaderboard lists players with accounts by games won, and counts only games in
which both players have accounts. The room keeps a salted, stretched hash of the password, never the password, and
locks a login name for five minutes after five wrong tries. There is no email, so a forgotten password cannot be
reset.

The room runs on the same Supabase project as ski/lease, in two layers:

- **The room** (`sql/1_room.sql`, `room.js`, `room.css`) is everything games share: players, tables, who sits where,
  the list of open tables, your tables and whose turn it is, sitting down, leaving, a record of finished games, live
  nudges between two pages, and sound.
- **A game** (`sql/2_gin.sql`, `gin/index.html`) keeps its own cards and rules in its own schema and hangs them off a
  row in `room.tables`.

The deck, both hands, and the scoring live in the database, in schemas the API doesn't expose. A page can only call
the public `room_*` and `gin_*` functions, and each one checks the caller's seat, so a browser never receives a card
it shouldn't see. Pages ask for changes every couple of seconds, and nudge each other over a Supabase realtime
channel so moves show up right away.

A table is swept out after 45 days without a move, and a player after 180 days without a visit.

## Setup

Run `sql/1_room.sql`, then `sql/2_gin.sql`, in the Supabase project's SQL editor. Both are the whole current
definition and are safe to run again at any time: they upgrade what's there in place and keep every table in play.
Run them before publishing a page that needs something new from them; the calls an older page makes keep working.

## Gin rummy

House rules:

- Ten cards each. One card is turned up: it starts the discard pile and sets the knock (a face card is 10, an ace 1).
- The non-dealer may take the turned-up card or pass, then the dealer may. If both pass, the non-dealer draws from the deck.
- Go down any time your deadwood is at or under the knock. No deadwood is gin.
- After a knock the other player lays off on the knocker's melds. Nothing can be laid off on gin.
- Gin scores 25 plus the other player's deadwood. A knock scores the difference.
- Undercut: if the other player ties or beats the knocker after laying off, they score 25 plus the difference.
- A game is played to 150 unless the table says otherwise (10 to 1000).
- Settling up, by the usual convention: when a game ends the winner adds 100 for the game and each player adds 25 for
  every hand they won (a box); the loser pays the difference at a penny a point. If the loser never scored, the game
  bonus is doubled. Whoever opens the table sets the money a point (or none) and can change the game bonus, the box,
  the gin and undercut bonuses, and what a shutout pays. Hollywood settles its three games one by one. The scoresheet
  shows what each match came to and the book between the two of you: every match you have finished, what it paid,
  and the running total after it. The running total also sits beside the score at the top of the table. The app only
  keeps the tally; no money moves through it.
- Hollywood is three games at once: a player's first winning hand counts in game one, the second in games one and two,
  and the rest in all three. A finished game takes no more points.
- You may throw back the card you just took off the discard pile.
- Two cards left in the deck and nobody down is a dead hand: no score, same dealer. Otherwise the winner deals next,
  so the loser is offered the turned-up card first.

At the table:

- **Your hand is yours to arrange.** Drag a card anywhere along it and it stays there, through draws and throws and
  a reload. A card you draw lands on the right end. The Sort buttons put the whole hand in order by meld, suit, or
  rank whenever you want a fresh start.
- Tap a card and then Throw it, or drag it onto the discard pile.
- Going down is the gold circle beside the piles, not a button next to Throw, so it is never tapped by mistake.
- When the other player has stepped away, a Ring them button by their name sends a notification to their phone.
  If they have not turned notifications on, it opens your phone's Messages instead, with a reminder and the table's
  link already written; you pick who it goes to.
  A player with an account can add a phone number (the Phone number link under their name); the text is then
  already addressed to it. Only players sitting at a table with them can use the number.
- The box in the bottom row, beside your avatar, is always there to type in; send with the keyboard's send key or the button beside it. With
  the box empty, that button slides up a dozen faces that send on one tap (the tray stays up for more), ready lines,
  and your own last six. A face reaches the other player even when the live channel is down.
- Notifications: a player turns them on per device (the 🔔 link under their name, or the table's settings). A device
  is told when it is its owner's turn and they have stepped away, when the other player says something while they
  are away, and when they are rung. On an iPhone this needs the page added to the Home Screen and opened from there.
- "Cards and table" in the table's settings picks the suit colors (classic, green clubs, or four colors; the suits are drawn so a club and a spade differ in shape), the
  backs of the cards (six, or a picture of your own) and the cloth. They are kept on your device and are yours alone.
- Melds are colored and deadwood counted for you; "Show my melds" in the table's settings turns that off.
- The page picks each player's best melds and layoffs when someone goes down; the database checks them and scores.
- The scoresheet also keeps the tally of every game the two of you have finished, across tables.
- Leaving a table ends the game for both players, with the scores left as they stand.

## Adding a game

1. `sql/3_<game>.sql`: a schema with the game's state keyed by `code references room.tables`, and public
   `<game>_*` functions that take `p_token` and use `room.me`, `room.new_table`, `room.sit`, and `room.seat`. Keep
   `room.tables.status`, `turn`, and `summary` current (gin does it with a trigger) so the lists can say whose turn
   it is.
2. `<game>/index.html`: load `../room.css` and `../room.js` and build the table. `Room.call` makes a call as the
   player, `Room.live` is the nudge channel, and the profile, device, and table-list pieces are ready to use.
3. Add the game to `GAMES` in `room.js` (its name, path, and how to describe a table) and a tile to `index.html`.
4. Teach `dev/server.py` the new function prefix.

## Next: ski/lease members

Nothing here knows about ski/lease yet. The pieces left for that step:

- `room.players.member_id` is reserved for the lease member a player is. Signing in to ski/lease would attach it
  (and could fold a browser's existing key into the member with `room_adopt`, so tables carry over).
- A listed table is visible to anyone who opens the room. Lease-only tables would add a column on `room.tables` for
  who may see and join, checked in `room_lobby` and `room.sit`.
- Names and faces could come from the member's lease profile instead of the picker.

## Working on it

`dev/server.py` is a local stand-in for Supabase: it serves the site and answers the calls from a throwaway Postgres
loaded with `sql/`. The pages use it automatically on localhost.

    pip install pgserver psycopg2-binary pytest
    python3 games/dev/server.py        # http://localhost:8766/games/ ; second player on http://127.0.0.1:8766/games/
    pytest games/tests

`tests/test_gin_sql.py` has two bots play whole games through the same functions the page calls, checks the room
(lists, leaving, a second device), and upgrades a copy of the first version of gin to make sure tables in play
survive it.

## Notifications: setting up the sender

Notifications need one more piece on the Supabase project, once:

1. Run `sql/1_room.sql` again (it adds the list of devices and the sender's functions).
2. In Supabase, open Edge Functions, deploy a new function through the editor, name it `push`, and paste in
   `push/index.ts`. Turn "Verify JWT" off for it: the pages call it with the publishable key, and it checks every
   request against the card room itself.

There is no key to make or paste. The sender makes its signing key pair the first time it runs and keeps it in the
database (`room.secrets`), where no page can read it. Who is told, and what, is decided in the database
(`public.push_job`); the function only seals each message for its device and hands it to Apple, Google or Mozilla.
`sw.js` is what shows the notification on the phone, and `manifest.webmanifest` is what lets an iPhone add the room
to its Home Screen as an app.
