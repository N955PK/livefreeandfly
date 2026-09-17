# WingRock (repo: acroReplay)

WingRock is a live 3D view of your aerobatic flight in the box, driven by the OnFlight
Hub's Wi-Fi data stream — on an iPhone in the cockpit (see `ios/`) or in a browser via the
Python bridge — so you can see what the judges see and fix the figure on the next pass.

Status: phase 0 (protocol decode) done — the Hub's 50 Hz UDP INS stream,
identity message, WebSocket status frame, and HTTP config API are documented
in [docs/PROTOCOL.md](docs/PROTOCOL.md) with decoders in `onflight/` and
real-frame fixtures in `tests/`. Plan, decisions, and next phases are in
[PLAN.md](PLAN.md).

## Run it

```bash
pip install -r requirements.txt
python3 run_bridge.py --replay tests/fixtures/udp2000_moving.bin   # recorded frames, loops
python3 run_bridge.py                                              # live: Mac on the Hub's Wi-Fi
```

Then open `http://<this machine's IP>:8645/` on the iPhone (same Wi-Fi network —
on the Hub's network that's the Mac's 192.168.23.x address). Add to Home Screen
for full-screen.

```bash
python3 -m pytest tests            # decoders and frame math against real captured frames
```

## Replay a real flight from the SD card

```bash
python3 -m onflight.acrowrx_log sample_logs/data16.acrowrx sessions/data16.bin   # starts airborne by default
python3 run_bridge.py --replay sessions/data16.bin
```

The ground is aerial imagery fetched live (Esri / USGS). For the cockpit, where the phone has
no internet, bundle tiles once: `python3 tools/fetch_tiles.py --lat 36.936 --lon -121.790`
(≈400 tiles / 10 MB into `web/tiles/`, gitignored, picked up automatically and bundled into
the iOS app). The aircraft models in `web/models/` (Christen Eagle, Extra 330SC, RV-7; picked under
Box → Settings) are licensed assets and are also not in git.

## Quickstart (when the OnFlight Hub is on the bench)

1. Power the Hub outdoors (or with sky view) and wait for a solid status LED.
2. Join the Mac to the "OnFlight Hub" Wi-Fi network (you'll be offline).
3. Run the capture kit and follow its prompts:

```bash
python3 capture_onflight.py
```

4. Reconnect to normal Wi-Fi and analyze `captures/<timestamp>/`
   (see PLAN.md §6 for the decode methodology).
