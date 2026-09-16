# acroReplay

Real-time aerobatic figure replay: a live 3D recreation of the aircraft driven
by an OnFlight Hub's Wi-Fi data stream, so the pilot can review each figure
right after flying it — during the repositioning leg — and iterate efficiently.

Status: phase 0 (protocol decode) done — the Hub's 50 Hz UDP INS stream,
identity message, WebSocket status frame, and HTTP config API are documented
in [docs/PROTOCOL.md](docs/PROTOCOL.md) with decoders in `onflight/` and
real-frame fixtures in `tests/`. Plan, decisions, and next phases are in
[PLAN.md](PLAN.md).

```bash
python3 -m pytest tests            # decoders against real captured frames
```

## Quickstart (when the OnFlight Hub is on the bench)

1. Power the Hub outdoors (or with sky view) and wait for a solid status LED.
2. Join the Mac to the "OnFlight Hub" Wi-Fi network (you'll be offline).
3. Run the capture kit and follow its prompts:

```bash
python3 capture_onflight.py
```

4. Reconnect to normal Wi-Fi and analyze `captures/<timestamp>/`
   (see PLAN.md §6 for the decode methodology).
