"""Resorts, stations, model names, and paths."""
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CACHE = ROOT / ".cache"
RAW = CACHE / "raw"
TABLES = CACHE / "tables"
MODELS = ROOT / "models"
REPORTS = ROOT / "reports"
SITE = ROOT
USER_AGENT = "tahoe-snow/0.1"

MM_PER_IN = 25.4
M_PER_FT = 0.3048


@dataclass(frozen=True)
class Station:
    triplet: str
    name: str
    lat: float
    lon: float
    elev_m: float


@dataclass(frozen=True)
class Resort:
    key: str
    name: str
    lat: float
    lon: float
    base_m: float
    summit_m: float
    station: str
    weak_match: bool = False

    @property
    def mid_m(self) -> float:
        return 0.5 * (self.base_m + self.summit_m)

    def elevations(self) -> dict:
        return {"base": self.base_m, "mid": self.mid_m, "summit": self.summit_m}


def _ft(feet: float) -> float:
    return round(feet * M_PER_FT, 1)


# SNOTEL stations in the Tahoe box (NRCS AWDB, active 2026-11-19).
STATIONS = {
    s.triplet: s
    for s in [
        Station("340:NV:SNTL", "Big Meadow", 39.455, -119.942, _ft(8240)),
        Station("356:CA:SNTL", "Blue Lakes", 38.608, -119.925, _ft(8060)),
        Station("1051:CA:SNTL", "Burnside Lake", 38.719, -119.894, _ft(8180)),
        Station("1067:CA:SNTL", "Carson Pass", 38.693, -120.002, _ft(8360)),
        Station("428:CA:SNTL", "CSS Lab", 39.326, -120.368, _ft(6890)),
        Station("462:CA:SNTL", "Ebbetts Pass", 38.550, -119.805, _ft(8660)),
        Station("463:CA:SNTL", "Echo Peak", 38.849, -120.079, _ft(7650)),
        Station("473:CA:SNTL", "Fallen Leaf", 38.934, -120.055, _ft(6250)),
        Station("1049:CA:SNTL", "Forestdale Creek", 38.682, -119.960, _ft(8050)),
        Station("508:CA:SNTL", "Hagans Meadow", 38.852, -119.937, _ft(7740)),
        Station("518:CA:SNTL", "Heavenly Valley", 38.924, -119.916, _ft(8540)),
        Station("1050:CA:SNTL", "Horse Meadow", 38.837, -119.887, _ft(8580)),
        Station("539:CA:SNTL", "Independence Camp", 39.453, -120.294, _ft(6970)),
        Station("540:CA:SNTL", "Independence Creek", 39.490, -120.282, _ft(6440)),
        Station("541:CA:SNTL", "Independence Lake", 39.428, -120.313, _ft(8340)),
        Station("615:NV:SNTL", "Marlette Lake", 39.164, -119.897, _ft(7860)),
        Station("652:NV:SNTL", "Mt Rose Ski Area", 39.316, -119.895, _ft(8810)),
        Station("784:CA:SNTL", "Palisades Tahoe", 39.190, -120.266, _ft(8010)),
        Station("724:CA:SNTL", "Rubicon #2", 38.999, -120.131, _ft(7560)),
        Station("809:CA:SNTL", "Tahoe City Cross", 39.172, -120.154, _ft(6760)),
        Station("834:CA:SNTL", "Truckee #2", 39.301, -120.184, _ft(6500)),
        Station("848:CA:SNTL", "Ward Creek #3", 39.135, -120.219, _ft(6750)),
    ]
}

# Elevations from OpenSkiMap statistics (ODbL); coordinates are mid-mountain.
RESORTS = {
    r.key: r
    for r in [
        Resort("palisades", "Palisades Tahoe", 39.197, -120.245, 1890, 2665, "784:CA:SNTL"),
        Resort("alpine", "Alpine Meadows", 39.165, -120.238, 2085, 2588, "848:CA:SNTL", weak_match=True),
        Resort("homewood", "Homewood", 39.080, -120.172, 1903, 2402, "848:CA:SNTL"),
        Resort("sugarbowl", "Sugar Bowl", 39.300, -120.335, 2108, 2550, "428:CA:SNTL"),
        Resort("boreal", "Boreal", 39.333, -120.348, 2186, 2347, "428:CA:SNTL"),
        Resort("northstar", "Northstar", 39.265, -120.133, 1921, 2625, "834:CA:SNTL", weak_match=True),
        Resort("mtrose", "Mt. Rose", 39.320, -119.885, 2310, 2916, "652:NV:SNTL"),
        Resort("heavenly", "Heavenly", 38.930, -119.920, 2025, 3037, "518:CA:SNTL"),
        Resort("sierra", "Sierra-at-Tahoe", 38.795, -120.085, 2030, 2693, "463:CA:SNTL"),
        Resort("kirkwood", "Kirkwood", 38.680, -120.070, 2382, 2884, "1067:CA:SNTL"),
    ]
}

# Open-Meteo model identifiers.
DET_MODELS = ["gfs_seamless", "ecmwf_ifs025", "icon_seamless", "gem_seamless"]
ENS_MODELS = {"gfs025": "gfs_seamless", "ecmwf_ifs025": "ecmwf_ifs025",
              "icon_seamless": "icon_seamless", "gem_global": "gem_seamless"}

PRESSURE_LEVELS = [850, 800, 750, 700, 650, 600, 550, 500]

# Sierra box used to gather hand-measured snowfall for snow-ratio training.
SIERRA_BBOX = (36.0, 40.5, -121.5, -118.0)
TAHOE_BBOX = (38.4, 39.7, -120.8, -119.6)
