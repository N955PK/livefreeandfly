"""A local stand-in for Supabase, for working on the games without touching the live card room.

    pip install pgserver psycopg2-binary
    python3 games/dev/server.py            # then open http://localhost:8766/games/

Serves the site and answers /rest/v1/rpc/<function> from a throwaway Postgres loaded with games/sql. The game pages
talk to this instead of Supabase whenever they're opened on localhost. To play both seats, open the second player
on http://127.0.0.1:8766 so it gets its own browser storage. There are no live nudges here; pages poll instead.
"""
import json
import re
import sys
import tempfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pgserver
import psycopg2

REPO = Path(__file__).resolve().parents[2]
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8766
DATA = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(tempfile.mkdtemp(prefix="gameroom-"))

server = pgserver.get_server(DATA)
conn = psycopg2.connect(server.get_uri())
conn.autocommit = True
lock = threading.Lock()
with conn.cursor() as cur:
    cur.execute("do $$ begin create role anon nologin; create role authenticated nologin; "
                "exception when duplicate_object then null; end $$")
    for sql in sorted((REPO / "games" / "sql").glob("*.sql")):
        cur.execute(sql.read_text())


class Handler(SimpleHTTPRequestHandler):
    def do_POST(self):
        found = re.fullmatch(r"/rest/v1/rpc/((?:room|gin)_[a-z_]+)", self.path)
        args = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        if not found or not all(re.fullmatch(r"p_[a-z_]+", k) for k in args):
            return self.reply(404, {"code": "PGRST202", "message": "no such function"})
        names = ", ".join(f"{k} => %s" for k in args)
        vals = [json.dumps(v) if isinstance(v, (list, dict)) else v for v in args.values()]
        try:
            with lock, conn.cursor() as cur:
                cur.execute(f"select public.{found.group(1)}({names})", vals)
                self.reply(200, cur.fetchone()[0])
        except psycopg2.Error as e:
            self.reply(400, {"code": e.pgcode, "message": e.diag.message_primary or str(e)})

    def reply(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *a):
        pass


print(f"game room on http://localhost:{PORT}/games/  (second player: http://127.0.0.1:{PORT}/games/)", flush=True)
ThreadingHTTPServer(("127.0.0.1", PORT), partial(Handler, directory=str(REPO))).serve_forever()
