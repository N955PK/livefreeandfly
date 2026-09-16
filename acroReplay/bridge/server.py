"""aiohttp app: serves the web app, fans INS samples out over a WebSocket, logs raw frames per session."""

import asyncio
import datetime
import json
import logging
from collections import deque
from pathlib import Path

from aiohttp import WSMsgType, web

from bridge import frames as fr
from onflight.records import RECORD_HEADER
from onflight.udp_ins import decode_ins

log = logging.getLogger("bridge")
ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "web"
SESSION_DIR = ROOT / "sessions"
SAMPLE_HZ = 50
HISTORY_SECONDS = 120
HISTORY_STRIDE = 5
DEFAULT_GROUND_FT = 163.0   # KWVI field elevation


def sample_from_frame(wall, f, origin):
    """Renderer-ready dict for one decoded frame; ``pos``/``quat`` are null until the INS has initialized."""
    s = {
        "wall": wall, "t": f.sys_time_s, "init": f.ins_initialized, "ok": f.ins_healthy,
        "fix": f.gnss_fix, "sats": f.gnss_num_sv, "hacc": f.horz_pos_acc_ft,
        "hdg": f.true_heading_deg, "pitch": f.pitch_deg, "roll": f.roll_deg, "nz": f.load_factor_g,
        "gs": f.ground_speed_kts, "trk": f.ground_track_deg, "vs": f.climb_rate_fpm, "alt": f.alt_msl_ft,
        "rates": [f.p_dps, f.q_dps, f.r_dps], "lat": f.lat_deg, "lon": f.lon_deg, "pos": None, "quat": None,
    }
    if f.ins_initialized and origin is not None:
        ned = fr.ned_from_lla(f.lat_deg, f.lon_deg, f.alt_msl_ft * fr.FT_TO_M, origin)
        s["pos"] = [round(v, 2) for v in fr.world_from_ned(*ned)]
        s["quat"] = [round(v, 5) for v in fr.world_quaternion(f.true_heading_deg, f.pitch_deg, f.roll_deg)]
    return s


class Broadcaster:
    """Holds connected clients, the recent-history ring, the session origin, and the raw-frame log."""

    def __init__(self, log_dir=SESSION_DIR, ground_m=DEFAULT_GROUND_FT * fr.FT_TO_M):
        self.ground_m = ground_m
        self.clients = set()
        self.history = deque(maxlen=HISTORY_SECONDS * SAMPLE_HZ)
        self.origin = None
        log_dir.mkdir(exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_path = log_dir / f"{stamp}_udp2000.bin"
        self._log = open(self.log_path, "ab")
        self.count = 0

    def _update_origin(self, f):
        """Origin = first fix horizontally, at the configured ground elevation, so altitude is absolute
        (a client joining mid-flight must not see the aircraft on the ground)."""
        if self.origin is None:
            self.origin = (f.lat_deg, f.lon_deg, self.ground_m)
            log.info("origin set at %.6f, %.6f, ground %.0f ft", f.lat_deg, f.lon_deg, self.ground_m / fr.FT_TO_M)

    async def ingest(self, wall, payload):
        self._log.write(RECORD_HEADER.pack(wall, len(payload)) + payload)
        f = decode_ins(payload)
        if f.ins_initialized:
            self._update_origin(f)
        sample = sample_from_frame(wall, f, self.origin)
        self.history.append(sample)
        self.count += 1
        if self.count % (SAMPLE_HZ * 5) == 0:
            self._log.flush()
        if self.clients:
            msg = json.dumps(sample)
            await asyncio.gather(*(ws.send_str(msg) for ws in list(self.clients)), return_exceptions=True)

    def history_message(self):
        recent = list(self.history)[::HISTORY_STRIDE]
        return json.dumps({"history": recent, "origin": self.origin})

    async def pump(self, source):
        async for wall, payload in source:
            await self.ingest(wall, payload)


async def ws_handler(request):
    ws = web.WebSocketResponse(heartbeat=10)
    await ws.prepare(request)
    bc = request.app["broadcaster"]
    bc.clients.add(ws)
    log.info("client connected (%d)", len(bc.clients))
    try:
        await ws.send_str(bc.history_message())
        async for msg in ws:
            if msg.type in (WSMsgType.CLOSE, WSMsgType.ERROR):
                break
    finally:
        bc.clients.discard(ws)
        log.info("client left (%d)", len(bc.clients))
    return ws


async def index(request):
    return web.FileResponse(WEB_DIR / "index.html")


async def save_icon(request):
    """Dev helper for web/icon.html: stores the rendered app icon as sessions/icon.png."""
    data = await request.read()
    SESSION_DIR.mkdir(exist_ok=True)
    (SESSION_DIR / "icon.png").write_bytes(data)
    log.info("icon saved (%d bytes)", len(data))
    return web.Response(text="ok")


def make_app(source, ground_ft=DEFAULT_GROUND_FT):
    app = web.Application()
    app["broadcaster"] = Broadcaster(ground_m=ground_ft * fr.FT_TO_M)
    app.add_routes([web.get("/", index), web.get("/ws", ws_handler), web.post("/dev/icon", save_icon),
                    web.static("/", WEB_DIR)])

    async def start_pump(app):
        app["pump"] = asyncio.create_task(app["broadcaster"].pump(source))

    async def stop_pump(app):
        app["pump"].cancel()

    app.on_startup.append(start_pump)
    app.on_cleanup.append(stop_pump)
    return app
