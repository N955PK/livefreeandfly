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
    # The first day of the record a season is compared against, where the earlier record is not comparable.
    season_from: str | None = None
    # Whether the forecast is corrected against this station. One that is not is shown on the page and never
    # changes a forecast number.
    corrects: bool = True
    # The station's id in the National Weather Service's hourly observations, where it reports there.
    nws: str | None = None


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
    # Whether the mountain's forecast is corrected against its station. Where it is not, the station is only shown.
    corrected: bool = True
    # The neighbour whose weather this mountain's forecast is made from, where the two are close enough that the
    # models see one place: the weather is asked for once, at the neighbour, and read at this mountain's own heights.
    weather_from: str | None = None

    @property
    def mid_m(self) -> float:
        return 0.5 * (self.base_m + self.summit_m)

    def elevations(self) -> dict:
        return {"base": self.base_m, "mid": self.mid_m, "summit": self.summit_m}


@dataclass(frozen=True)
class Region:
    key: str
    name: str
    tz: str
    # Hours behind UTC in standard time: SNOTEL reads its daily values at midnight on that clock all year.
    std_offset_h: int
    # Hours between forecast runs for the region's mountains: 24 over the number of hours in ``at``.
    every_h: int
    # The avalanche centers whose forecasts cover the region.
    avalanche: tuple[str, ...]
    # Pressure levels (hPa) read below the usual lowest one, where the region's mountains reach under it.
    low_levels: tuple[int, ...] = ()
    # The hours of the day, on the region's own clock, at which its forecast is built. Regions that share a clock
    # share their hours, so their forecasts change together.
    at: tuple[int, ...] = ()


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
        # Through the mid-2000s this gauge peaked at 1.5 to 2 times what Ward Creek, CSS Lab, and Echo Peak did
        # in the same winters; since then it has matched them. Its seasons are compared from water year 2008 on.
        Station("784:CA:SNTL", "Palisades Tahoe", 39.190, -120.266, _ft(8010), season_from="2007-10-01"),
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
# The Mount Washington Observatory's summit record, as the Regional Climate Centers publish it (ACIS, keyed
# "<id>:ACIS"; position and elevation from its metadata, 2026-11-23), with the summit's hourly weather from the
# National Weather Service. It reports snowfall, snow on the ground and the water that fell, each day, some three days
# behind; it has no snow pillow. The summit is 1,100 ft above the top of Tuckerman Ravine and scoured by wind, so its
# readings are shown for the ravine but nothing is corrected against them.
NEWENGLAND_STATIONS = {
    s.triplet: s
    for s in [
        Station("USW00014755:ACIS", "Mt. Washington summit", 44.27018, -71.30336, _ft(6272), source="acis",
                corrects=False, nws="KMWN"),
    ]
}
# SNOTEL stations paired with the Seattle region's mountains (NRCS AWDB, active 2026-11-23). Their daily values are
# stamped at midnight Pacific standard time, as California's are: at Paradise the value dated 21 November matched
# the hourly reading at midnight starting the 22nd, not the one an hour before.
SEATTLE_STATIONS = {
    s.triplet: s
    for s in [
        Station("642:WA:SNTL", "Morse Lake", 46.90585, -121.4827, _ft(5400)),
        Station("791:WA:SNTL", "Stevens Pass", 47.74607, -121.09288, _ft(3940)),
        Station("672:WA:SNTL", "Olallie Meadows", 47.37406, -121.44213, _ft(4010)),
        Station("909:WA:SNTL", "Wells Creek", 48.8661, -121.78976, _ft(4040)),
        Station("692:WA:SNTL", "Pigtail Peak", 46.62153, -121.38643, _ft(5800)),
        Station("507:WA:SNTL", "Grouse Camp", 47.28107, -120.48771, _ft(5390)),
        Station("974:WA:SNTL", "Waterhole", 47.94485, -123.42594, _ft(5010)),
        Station("679:WA:SNTL", "Paradise", 46.78266, -121.74767, _ft(5150)),
        Station("999:WA:SNTL", "Marten Ridge", 48.76292, -121.69823, _ft(3520)),
        Station("1012:WA:SNTL", "Swift Creek", 46.1638, -122.18402, _ft(4440)),
    ]
}
ALL_STATIONS = {**STATIONS, **MAMMOTH_STATIONS, **NEWENGLAND_STATIONS, **SEATTLE_STATIONS}

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
        Resort("alpine", "Alpine Meadows", 39.165, -120.238, 2085, 2588, "848:CA:SNTL", "Ikon", weak_match=True,
               weather_from="palisades"),
        Resort("homewood", "Homewood", 39.080, -120.172, 1903, 2402, "848:CA:SNTL", "Independent"),
        Resort("sugarbowl", "Sugar Bowl", 39.300, -120.335, 2108, 2550, "428:CA:SNTL", "Mountain Collective"),
        Resort("boreal", "Boreal", 39.333, -120.348, 2186, 2347, "428:CA:SNTL", "Independent",
               weather_from="sugarbowl"),
        Resort("northstar", "Northstar", 39.265, -120.133, 1921, 2625, "834:CA:SNTL", "Epic", weak_match=True),
        Resort("mtrose", "Mt. Rose", 39.320, -119.885, 2310, 2916, "652:NV:SNTL", "Independent"),
        Resort("heavenly", "Heavenly", 38.930, -119.920, 2025, 3037, "518:CA:SNTL", "Epic"),
        Resort("sierra", "Sierra-at-Tahoe", 38.795, -120.085, 2030, 2693, "463:CA:SNTL", "Ikon"),
        Resort("kirkwood", "Kirkwood", 38.680, -120.070, 2382, 2884, "1067:CA:SNTL", "Epic"),
        Resort("castle", "Castle Peak", 39.3654, -120.3494, 2200, 2774, "428:CA:SNTL", "Backcountry",
               kind="backcountry", weather_from="sugarbowl"),
        Resort("jakes", "Jakes Peak", 38.9753, -120.1243, 2067, 2800, "724:CA:SNTL", "Backcountry",
               kind="backcountry", weather_from="tallac"),
        Resort("tallac", "Mt. Tallac", 38.9059, -120.0988, 1920, 2967, "463:CA:SNTL", "Backcountry",
               kind="backcountry"),
        Resort("roundtop", "Round Top", 38.6636, -120.0015, 2613, 3164, "1067:CA:SNTL", "Backcountry",
               kind="backcountry", weather_from="kirkwood"),
        Resort("mammoth", "Mammoth Mountain", 37.635, -119.030, _ft(7953), _ft(11053), "MHP:CDEC", "Ikon",
               region="mammoth"),
        Resort("june", "June Mountain", 37.755, -119.080, _ft(7545), _ft(10090), None, "Ikon", region="mammoth"),
        Resort("sherwins", "Sherwin Ridge", 37.6043, -118.9794, 2399, 3130, "MHP:CDEC", "Backcountry",
               region="mammoth", kind="backcountry", weather_from="mammoth"),
        Resort("carsonpeak", "Carson Peak", 37.7476, -119.1242, 2204, 3324, None, "Backcountry",
               region="mammoth", kind="backcountry", weather_from="june"),
        Resort("matterhorn", "Matterhorn Peak", 38.0932, -119.3817, 2165, 3734, "SLI:CDEC", "Backcountry",
               region="mammoth", kind="backcountry", weak_match=True),
        Resort("danaplateau", "Dana Plateau", 37.9200, -119.2150, 2907, 3494, "DAN:CDEC", "Backcountry",
               region="mammoth", kind="backcountry"),
        Resort("whitney", "Mt. Whitney", 36.5786, -118.2922, 2548, 4421, None, "Backcountry",
               region="mammoth", kind="backcountry"),
        # New England has no snow sensors, so none of these has a station (Tuckerman's, below, is shown only). Elevations are from each resort's own
        # mountain-stats page where it could be read, and otherwise from the secondary source the research names
        # (Sunday River, Stratton's base and Crotched). Each point is the midpoint of the mountain's main lift in
        # OpenStreetMap, checked against the USGS elevation service (looked up 2026-11-23). Three rulings: Sugarbush
        # uses Lincoln Peak's base and summit because the forecast point is on Lincoln Peak; Stowe's summit is its
        # highest lift-served skiing, 3,625 ft, not Mt. Mansfield's 4,395 ft; and Sugarloaf's base is its summit
        # minus its stated vertical, since the resort does not publish one.
        Resort("sugarloaf", "Sugarloaf", 45.04554, -70.31476, _ft(1417), _ft(4237), None, "Ikon",
               region="newengland"),
        Resort("sundayriver", "Sunday River", 44.46334, -70.86467, _ft(800), _ft(3140), None, "Ikon",
               region="newengland"),
        Resort("loon", "Loon", 44.04715, -71.62851, _ft(860), _ft(3050), None, "Ikon",
               region="newengland"),
        Resort("killington", "Killington", 43.61127, -72.81108, _ft(1165), _ft(4241), None, "Ikon",
               region="newengland"),
        Resort("pico", "Pico", 43.64769, -72.83847, _ft(2000), _ft(3967), None, "Ikon",
               region="newengland", weather_from="killington"),          # 4.6 km from Killington
        Resort("sugarbush", "Sugarbush", 44.13197, -72.90544, _ft(1575), _ft(3975), None, "Ikon",
               region="newengland"),
        Resort("stratton", "Stratton", 43.10461, -72.91493, _ft(1872), _ft(3875), None, "Ikon",
               region="newengland"),
        Resort("stowe", "Stowe", 44.5344, -72.80087, _ft(1559), _ft(3625), None, "Epic",
               region="newengland"),
        Resort("okemo", "Okemo", 43.40547, -72.73386, _ft(1144), _ft(3344), None, "Epic",
               region="newengland"),
        Resort("mountsnow", "Mount Snow", 42.96339, -72.90724, _ft(1900), _ft(3600), None, "Epic",
               region="newengland", weather_from="stratton"),            # 15.7 km from Stratton
        Resort("wildcat", "Wildcat", 44.25667, -71.23137, _ft(1950), _ft(4062), None, "Epic",
               region="newengland"),
        Resort("attitash", "Attitash", 44.07554, -71.22543, _ft(600), _ft(2350), None, "Epic",
               region="newengland"),
        Resort("sunapee", "Mount Sunapee", 43.3222, -72.07727, _ft(1233), _ft(2743), None, "Epic",
               region="newengland"),
        Resort("crotched", "Crotched", 43.00708, -71.8781, _ft(1050), _ft(2066), None, "Epic",
               region="newengland"),
        # Tuckerman Ravine, on Mt. Washington: the skiing is in the ravine, not on the 6,288 ft summit above it. The
        # point is the ravine (OpenStreetMap), the top is the lip of the headwall, where a profile of the ground
        # toward the summit eases from 45 degrees, and the base is the Pinkham Notch trailhead; heights are read
        # from the Terrain Tiles elevation model (2026-11-23). It sits inside the Presidential Range avalanche zone.
        # It shows the summit's measured snow, which is not used to correct its forecast.
        Resort("tuckerman", "Tuckerman Ravine", 44.2619, -71.2961, 619, 1580, "USW00014755:ACIS", "Backcountry",
               region="newengland", kind="backcountry", weather_from="wildcat"),   # 5.2 km, across Pinkham Notch
        # Seattle: the Washington Cascades and Olympics resorts a Seattle skier drives to, and the Washington
        # volcanoes skied from their summits (looked up 2026-11-23). Elevations are from each resort's own page where
        # it could be read (Stevens Pass, Mt. Baker, Crystal's stats page as search engines show it, Alpental's
        # vertical) and otherwise from the secondary sources the research names. Each resort's point is the midpoint
        # of its main lift in OpenStreetMap, checked against the Terrain Tiles elevation model to sit between base and
        # summit. Alpental is its own entry: the Summit at Snoqualmie gives it its own page, report and vertical, and
        # it is a separate base area with twice the vertical. The Summit at Snoqualmie covers West, Central and East,
        # from East's base to Central's top, with its point on the Central Express. Crystal's summit is Silver King,
        # the top the resort publishes. Hurricane Ridge is the Olympics' one entry: a small area on the national
        # park's road, open weekends and Monday holidays. Left out: Loup Loup (over four hours away), Leavenworth,
        # Echo Valley and Badger Mountain (rope tows and a poma), the Spokane-area hills (eastern Washington) and
        # Mt. Hood (Oregon, Portland's).
        # Sensors are paired by the guide's rule: the nearest SNOTEL station within 10 km and 300 m of the mountain's
        # middle, or a low one within 10 km as a weak match. Stevens Pass's station sits below the base, 309 m under
        # the middle, so it is a weak match.
        Resort("crystal", "Crystal Mountain", 46.93563, -121.48776, _ft(4400), _ft(7012), "642:WA:SNTL", "Ikon",
               region="seattle"),
        Resort("stevens", "Stevens Pass", 47.73921, -121.1, _ft(4061), _ft(5845), "791:WA:SNTL", "Epic",
               region="seattle", weak_match=True),
        Resort("snoqualmie", "Summit at Snoqualmie", 47.40482, -121.41854, _ft(2610), _ft(3865), "672:WA:SNTL",
               "Ikon", region="seattle"),
        Resort("alpental", "Alpental", 47.44024, -121.43034, _ft(3140), _ft(5420), "672:WA:SNTL", "Ikon",
               region="seattle", weather_from="snoqualmie"),
        Resort("bakerskiarea", "Mt. Baker Ski Area", 48.85002, -121.65696, _ft(3500), _ft(5089), "909:WA:SNTL",
               "Independent", region="seattle"),
        Resort("whitepass", "White Pass", 46.63099, -121.38899, _ft(4500), _ft(6500), "692:WA:SNTL", "Indy",
               region="seattle"),
        Resort("missionridge", "Mission Ridge", 47.27984, -120.41786, _ft(4570), _ft(6820), "507:WA:SNTL",
               "Independent", region="seattle"),
        Resort("hurricaneridge", "Hurricane Ridge", 47.9729, -123.49516, _ft(4800), _ft(5500), "974:WA:SNTL", "Indy",
               region="seattle"),
        # The volcanoes: one entry each from the usual spring trailhead to the true summit, so Mid falls on the
        # route's middle. Each point is on the route at about that middle, on the side the route climbs; bases are
        # read from the Terrain Tiles at the trailhead and summits are the published heights (the tiles read a few
        # feet low on a sharp top). Mt. Rainier runs from Paradise to Columbia Crest, 14,410 ft; its Mid is about
        # Camp Muir, the top of the Muir Snowfield, where its point is. Mt. Baker is the volcano by the Easton
        # Glacier from Schriebers Meadow (the Park Butte trailhead), the side most often skied; the ski area is the
        # entry above. Glacier Peak is a multi-day trip from the North Fork Sauk trailhead, its point in the White
        # Chuck basin. Mt. Adams is the South Climb from Cold Springs, its point below the Lunch Counter. Mt. St.
        # Helens is the Worm Flows from Marble Mountain Sno-Park to the crater rim. The Paradise, Marten Ridge and
        # Swift Creek stations sit far below their volcano's middle, so they are weak matches; nothing reports within
        # 10 km of Glacier Peak or Mt. Adams. A correction learned at a sensor near the trailhead says nothing about a
        # summit one to three kilometres above it, and one water series feeds every height, so these three are shown
        # their sensor and not corrected against it.
        Resort("rainier", "Mt. Rainier", 46.834, -121.7329, 1653, _ft(14410), "679:WA:SNTL", "Backcountry",
               region="seattle", kind="backcountry", weak_match=True, corrected=False),
        Resort("mtbaker", "Mt. Baker", 48.7494, -121.8137, 1024, _ft(10781), "999:WA:SNTL", "Backcountry",
               region="seattle", kind="backcountry", weak_match=True, corrected=False),
        Resort("glacierpeak", "Glacier Peak", 48.082, -121.128, 630, _ft(10541), None, "Backcountry",
               region="seattle", kind="backcountry"),
        Resort("adams", "Mt. Adams", 46.179, -121.4928, 1689, _ft(12276), None, "Backcountry",
               region="seattle", kind="backcountry"),
        Resort("sthelens", "Mt. St. Helens", 46.1725, -122.188, 814, _ft(8363), "1012:WA:SNTL", "Backcountry",
               region="seattle", kind="backcountry", weak_match=True, corrected=False),
    ]
}

REGIONS = {
    r.key: r
    for r in [
        # The three western regions are built together at 5 am, 1 pm and 9 pm Pacific: before the ski day, at midday and
        # in the evening. New England is built at 4 am and 4 pm Eastern; the afternoon one falls with the West's 1 pm.
        Region("tahoe", "Tahoe", "America/Los_Angeles", 8, 8, ("SAC",), at=(5, 13, 21)),
        Region("mammoth", "Eastern Sierra", "America/Los_Angeles", 8, 8, ("ESAC", "BAC"), at=(5, 13, 21)),
        # Every lift-served foot of New England is below 850 hPa (near 1,450 m): the highest summit is Killington's
        # 1,293 m and the lowest base Attitash's 183 m, which 1000 hPa (near 110 m) covers.
        Region("newengland", "New England", "America/New_York", 5, 12, ("MWAC",),
               low_levels=(1000, 975, 950, 925, 900), at=(4, 16)),
        # 850 hPa is near 1,450 m; the Cascade passes and most of their bases are below that, down to Glacier Peak's
        # trailhead at 630 m, which 950 hPa (near 540 m) covers.
        Region("seattle", "Cascades", "America/Los_Angeles", 8, 8, ("NWAC",), low_levels=(950, 925, 900), at=(5, 13, 21)),
    ]
}


def resorts_in(region: str) -> list[Resort]:
    return [r for r in RESORTS.values() if r.region == region]


def weather_point(resort: Resort) -> Resort:
    """The mountain whose place a resort's weather is asked for at: its own, or the neighbour it shares with."""
    return RESORTS[resort.weather_from] if resort.weather_from else resort


def avalanche_centers() -> tuple[str, ...]:
    """Every region's avalanche centers, in region order, each once."""
    return tuple(dict.fromkeys(center for region in REGIONS.values() for center in region.avalanche))


# Open-Meteo model identifiers.
DET_MODELS = ["gfs_seamless", "ecmwf_ifs025", "icon_seamless", "gem_seamless"]
ENS_MODELS = {"gfs025": "gfs_seamless", "ecmwf_ifs025": "ecmwf_ifs025",
              "icon_seamless": "icon_seamless", "gem_global": "gem_seamless"}

PRESSURE_LEVELS = [850, 800, 750, 700, 650, 600, 550, 500]


def levels_for(region: str) -> list[int]:
    """The pressure levels a region's forecast reads, lowest in the air first."""
    return sorted(REGIONS[region].low_levels, reverse=True) + PRESSURE_LEVELS


# Sierra box used to gather hand-measured snowfall for snow-ratio training.
SIERRA_BBOX = (36.0, 40.5, -121.5, -118.0)
TAHOE_BBOX = (38.4, 39.7, -120.8, -119.6)
MAMMOTH_BBOX = (37.0, 38.3, -119.7, -118.4)
# Around the Seattle region's ten snow sensors, Swift Creek in the south to Wells Creek in the north.
SEATTLE_BBOX = (46.0, 49.0, -123.6, -120.3)
