# acroReplay

Real-time aerobatic figure replay: a live 3D recreation of the aircraft driven
by an OnFlight Hub's Wi-Fi data stream, so the pilot can review each figure
right after flying it — during the repositioning leg — and iterate efficiently.

Status: planning / pre-hardware. Everything known, unknown, and planned is in
[PLAN.md](PLAN.md).

## Quickstart (when the OnFlight Hub is on the bench)

1. Power the Hub outdoors (or with sky view) and wait for a solid status LED.
2. Join the Mac to the "OnFlight Hub" Wi-Fi network (you'll be offline).
3. Run the capture kit and follow its prompts:

```bash
python3 capture_onflight.py
```

4. Reconnect to normal Wi-Fi and analyze `captures/<timestamp>/`
   (see PLAN.md §6 for the decode methodology).
