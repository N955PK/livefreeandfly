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
    source: str = "snotel"
    live: bool = True
    depth: bool = True


@dataclass(frozen=True)
class Resort:
    key: str
    name: str
    lat: float
    lon: float
    base_m: float
    summit_m: float
    station: str | None
    pass_group: str
    region: str = "tahoe"
    kind: str = "resort"
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

# Snow sensors along the crest around Mammoth, for that region's water correction: California Data Exchange
# Center pillows (keyed "<id>:CDEC"; positions and elevations from CDEC's station pages, 2026-11-19) and the
# one SNOTEL site. Gem Pass and Volcanic Knob stopped reporting in 2023 but their record still counts.
# Mammoth Pass's depth gauge reports a few hours a day and sat at one value through a storm that added four
# inches of water (2026-11-19), so only its pillow is used.
# Rock Creek Lakes is left out because CDEC and NRCS disagree on where it is, and Green Mountain because its
# pillow was dead for the 2022 winter and jumps by half a meter of water in a day.
MAMMOTH_STATIONS = {
    s.triplet: s
    for s in [
        Station("MHP:CDEC", "Mammoth Pass", 37.6124, -119.0317, _ft(9300), source="cdec", depth=False),
        Station("GEM:CDEC", "Gem Pass", 37.7800, -119.1700, _ft(10750), source="cdec", live=False),
        Station("DAN:CDEC", "Dana Meadows", 37.8980, -119.2588, _ft(9760), source="cdec"),
        Station("TUM:CDEC", "Tuolumne Meadows", 37.8762, -119.3500, _ft(8500), source="cdec"),
        Station("TNY:CDEC", "Tenaya Lake", 37.8373, -119.4502, _ft(8070), source="cdec"),
        Station("SLI:CDEC", "Slide Canyon", 38.0912, -119.4319, _ft(9200), source="cdec"),
        Station("VLC:CDEC", "Volcanic Knob", 37.3879, -118.9050, _ft(10050), source="cdec", live=False),
        Station("SLK:CDEC", "South Lake", 37.1759, -118.5627, _ft(9600), source="cdec"),
        Station("SWM:CDEC", "Sawmill", 37.1620, -118.5626, _ft(10200), source="cdec"),
        Station("846:CA:SNTL", "Virginia Lakes Ridge", 38.0730, -119.2343, _ft(9400)),
    ]
}
ALL_STATIONS = {**STATIONS, **MAMMOTH_STATIONS}

# Resort elevations from OpenSkiMap statistics (ODbL), Mammoth and June from the resorts' published figures;
# resort coordinates are mid-mountain. For backcountry spots the summit is the peak and the base is the usual
# winter trailhead, both read from the Terrain Tiles elevation model (2026-11-19). Mammoth Mountain and Sherwin
# Ridge pair with the Mammoth Pass pillow, 2 km south of the summit. Nothing that still reports sits near June
# (Gem Pass and Agnew Pass went quiet), so June Mountain and Carson Peak have no station and no correction.
# Matterhorn Peak (base at Twin Lakes) pairs with Slide Canyon, 4 km west across the crest, and Dana Plateau
# (the rim above the chutes; base at Ellery Lake on the Tioga Road) with Dana Meadows, 5 km southwest.
# Mt. Whitney (base at Whitney Portal; published elevations) is far south of every sensor the Mammoth correction
# was fitted to, so it has no station either.
RESORTS = {
    r.key: r
    for r in [
        Resort("palisades", "Palisades Tahoe", 39.197, -120.245, 1890, 2665, "784:CA:SNTL", "Ikon"),
        Resort("alpine", "Alpine Meadows", 39.165, -120.238, 2085, 2588, "848:CA:SNTL", "Ikon", weak_match=True),
        Resort("homewood", "Homewood", 39.080, -120.172, 1903, 2402, "848:CA:SNTL", "Independent"),
        Resort("sugarbowl", "Sugar Bowl", 39.300, -120.335, 2108, 2550, "428:CA:SNTL", "Mountain Collective"),
        Resort("boreal", "Boreal", 39.333, -120.348, 2186, 2347, "428:CA:SNTL", "Independent"),
        Resort("northstar", "Northstar", 39.265, -120.133, 1921, 2625, "834:CA:SNTL", "Epic", weak_match=True),
        Resort("mtrose", "Mt. Rose", 39.320, -119.885, 2310, 2916, "652:NV:SNTL", "Independent"),
        Resort("heavenly", "Heavenly", 38.930, -119.920, 2025, 3037, "518:CA:SNTL", "Epic"),
        Resort("sierra", "Sierra-at-Tahoe", 38.795, -120.085, 2030, 2693, "463:CA:SNTL", "Ikon"),
        Resort("kirkwood", "Kirkwood", 38.680, -120.070, 2382, 2884, "1067:CA:SNTL", "Epic"),
        Resort("castle", "Castle Peak", 39.3654, -120.3494, 2200, 2774, "428:CA:SNTL", "Backcountry",
               kind="backcountry"),
        Resort("jakes", "Jakes Peak", 38.9753, -120.1243, 2067, 2800, "724:CA:SNTL", "Backcountry",
               kind="backcountry"),
        Resort("tallac", "Mt. Tallac", 38.9059, -120.0988, 1920, 2967, "463:CA:SNTL", "Backcountry",
               kind="backcountry"),
        Resort("roundtop", "Round Top", 38.6636, -120.0015, 2613, 3164, "1067:CA:SNTL", "Backcountry",
               kind="backcountry"),
        Resort("mammoth", "Mammoth Mountain", 37.635, -119.030, _ft(7953), _ft(11053), "MHP:CDEC", "Ikon",
               region="mammoth"),
        Resort("june", "June Mountain", 37.755, -119.080, _ft(7545), _ft(10090), None, "Ikon", region="mammoth"),
        Resort("sherwins", "Sherwin Ridge", 37.6043, -118.9794, 2399, 3130, "MHP:CDEC", "Backcountry",
               region="mammoth", kind="backcountry"),
        Resort("carsonpeak", "Carson Peak", 37.7476, -119.1242, 2204, 3324, None, "Backcountry",
               region="mammoth", kind="backcountry"),
        Resort("matterhorn", "Matterhorn Peak", 38.0932, -119.3817, 2165, 3734, "SLI:CDEC", "Backcountry",
               region="mammoth", kind="backcountry", weak_match=True),
        Resort("danaplateau", "Dana Plateau", 37.9200, -119.2150, 2907, 3494, "DAN:CDEC", "Backcountry",
               region="mammoth", kind="backcountry"),
        Resort("whitney", "Mt. Whitney", 36.5786, -118.2922, 2548, 4421, None, "Backcountry",
               region="mammoth", kind="backcountry"),
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
MAMMOTH_BBOX = (37.0, 38.3, -119.7, -118.4)
