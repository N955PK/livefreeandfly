# fog/west

Live fog and low cloud for the **entire West Coast** — Washington, Oregon, and California — seen from NOAA's GOES-18 (GOES-West) satellite, with live airport weather and coastal webcams pinned to the imagery.

**Live site:** https://n955pk.github.io/Foggy/

## What it does

- Animated loop of the GOES-18 **Pacific U.S. (PACUS) scan**, cropped to a coast-to-Cascades viewport from the Canadian border to Baja; new frames about every 5 minutes, auto-refreshing
- **GeoColor** by day, blended infrared at night; an **IR 3.9 µm** mode shows fog the way forecasters find it in the dark
- **Airport layer** — 20 coastal airports with live National Weather Service observations; markers are colored by reported visibility (green ≥6 sm → red <1 sm, dense fog), and tapping one shows visibility, sky, wind, and temperature
- **Webcam layer** — Oregon TripCheck coastal cameras plus California Caltrans cameras loaded live from the CWWP2 directory and filtered to within ~24 km of the coastline; icons are tinted by the visibility at the nearest airport, and tapping shows the live still
- **Zoom sharpening** — the loop plays at 2 km resolution; zoom in and pause and the current frame reloads at 1 km ("HD" appears by the frame time)
- Pinch/scroll zoom, drag pan, a Pacific-time scrubber, 2/4/8-hour spans, ½×–2× speed, and a LIVE/DELAYED freshness indicator

## How it works

One self-contained `index.html` — no build step, no dependencies, no backend, no API keys. The page reads NOAA's public CDN listing at `cdn.star.nesdis.noaa.gov` for frames, `api.weather.gov` for airport observations, and Caltrans's public CWWP2 JSON for cameras. Markers are placed with the GOES-R **ABI fixed-grid projection** (geostationary view from 137.0°W), so every airport and camera sits on its true geography at any zoom. If a data source is unreachable, its layer degrades gracefully and the satellite loop keeps running.

## Data & credits

Imagery: [NOAA / NESDIS / STAR](https://www.star.nesdis.noaa.gov/goes/) — GOES-West (GOES-18); GeoColor by CIRA & NOAA. Weather observations: [National Weather Service](https://www.weather.gov/). Cameras: Caltrans (CWWP2) and Oregon DOT TripCheck. Imagery and data are informational only — not for navigation, aviation, or safety-of-life use.

A West Coast homage to [fog.today](https://fog.today).

<!-- build 1786991261 -->
