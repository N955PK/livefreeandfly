# game/room

Games for two, played over a link. It lives at `livefreeandfly.org/games/`. Gin rummy is the first one, at `/games/gin/`.

## How it works

Each game is one self-contained `index.html`, no build step, same as the rest of the site. There are no accounts: you
pick a name and an avatar (kept in your browser and shared by every game here), open a table, and send the link.

The card room runs on the same Supabase project as ski/lease. The deck, both hands, and the scoring live in the
database, in a private `gin` schema the API doesn't expose. The page can only call the `gin_*` functions, and each one
checks the caller's seat token, so a browser never receives a card it shouldn't see. Pages ask for changes every couple
of seconds, and nudge each other over a Supabase realtime channel so moves show up right away.

## Setup

Run `migrations/20261120_gin.sql` once in the Supabase project's SQL editor. It is safe to run again.

## Gin rummy house rules

- Ten cards each. One card is turned up: it starts the discard pile and sets the knock (a face card is 10, an ace 1).
- The non-dealer may take the turned-up card or pass, then the dealer may. If both pass, the non-dealer draws from the deck.
- Go down any time your deadwood is at or under the knock. No deadwood is gin.
- After a knock the other player lays off on the knocker's melds. Nothing can be laid off on gin.
- Gin scores 25 plus the other player's deadwood. A knock scores the difference.
- Undercut: if the other player ties or beats the knocker after laying off, they score 25 plus the difference.
- A game is played to 150 unless the table says otherwise (10 to 1000).
- Hollywood is three games at once: a player's first winning hand counts in game one, the second in games one and two,
  and the rest in all three. A finished game takes no more points.
- Two cards left in the deck and nobody down is a dead hand: no score, same dealer. Otherwise the loser deals next.

The page picks each player's best melds and layoffs for them; the database checks them and does the scoring.

## Tests

`tests/test_gin_sql.py` runs the migration on a throwaway local Postgres and has two bots play whole games through the
same functions the page calls.

    pip install pgserver psycopg2-binary pytest
    pytest games/tests
