"""Resorts, stations, model names, and paths."""
import os
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
    # The collector that builds and publishes the region (see COLLECTOR below), and the country the region menu
    # lists it under.
    collector: str = "main"
    country: str = "USA"


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
# SNOTEL stations around the Tetons (NRCS AWDB, active 2026-11-24): the three paired with the region's places first
# (Grand Targhee, Phillips Bench above Teton Pass, Togwotee Pass), then seven neighbours from the Snake River's
# headwaters to the Gros Ventre that the region's water correction is also fitted to. Wyoming's daily values are
# stamped on the Pacific standard clock too, an hour off the mountains' own: at Phillips Bench the value dated
# 17 November matched the hourly reading stamped midnight starting the 18th, and the station list gives every one of
# these a data time zone of UTC-8.
TETONS_STATIONS = {
    s.triplet: s
    for s in [
        Station("1082:WY:SNTL", "Grand Targhee", 43.7793, -110.9278, _ft(9260)),
        Station("689:WY:SNTL", "Phillips Bench", 43.5169, -110.9126, _ft(8170)),
        Station("822:WY:SNTL", "Togwotee Pass", 43.749, -110.0578, _ft(9590)),
        Station("499:WY:SNTL", "Grassy Lake", 44.126, -110.8343, _ft(7330)),
        Station("577:WY:SNTL", "Lewis Lake Divide", 44.2086, -110.6663, _ft(7880)),
        Station("764:WY:SNTL", "Snake River Station", 44.1336, -110.6692, _ft(6900)),
        Station("314:WY:SNTL", "Base Camp", 43.9402, -110.4454, _ft(7040)),
        Station("695:ID:SNTL", "Pine Creek Pass", 43.57, -111.2116, _ft(6710)),
        Station("497:WY:SNTL", "Granite Creek", 43.343, -110.435, _ft(6770)),
        Station("506:WY:SNTL", "Gros Ventre Summit", 43.3894, -110.1294, _ft(8760)),
    ]
}
# SNOTEL stations in the central and northern Wasatch (NRCS AWDB, active 2026-11-24): the six paired with the
# region's mountains first, then four between them and Ben Lomond that a water correction can also be fitted to.
# Atwater and Powder Mountain began in 2022 and 2021. Utah's daily values are stamped on the Pacific standard clock,
# as Wyoming's are: at Snowbird the value dated 17 November matched the hourly reading stamped midnight starting the
# 18th, on each of ten days, and the station list gives all of Utah's a data time zone of UTC-8.
WASATCH_STATIONS = {
    s.triplet: s
    for s in [
        Station("766:UT:SNTL", "Snowbird", 40.56914, -111.65852, _ft(9170)),
        Station("366:UT:SNTL", "Brighton", 40.59936, -111.58167, _ft(8790)),
        Station("814:UT:SNTL", "Thaynes Canyon", 40.6235, -111.53322, _ft(9260)),
        Station("1308:UT:SNTL", "Atwater", 40.59124, -111.63775, _ft(8750)),
        Station("1300:UT:SNTL", "Powder Mountain", 41.37428, -111.76673, _ft(8490)),
        Station("820:UT:SNTL", "Timpanogos Divide", 40.42817, -111.61633, _ft(8180)),
        Station("628:UT:SNTL", "Mill-D North", 40.65883, -111.63683, _ft(8940)),
        Station("596:UT:SNTL", "Lookout Peak", 40.83731, -111.70965, _ft(8150)),
        Station("474:UT:SNTL", "Farmington", 40.97462, -111.80975, _ft(7920)),
        Station("332:UT:SNTL", "Ben Lomond Peak", 41.37603, -111.94405, _ft(7690)),
    ]
}
# SNOTEL stations along Colorado's I-70 corridor and above Steamboat (NRCS AWDB, active 2026-11-24): the eight
# paired with the region's mountains first, then four more between Vail and Berthoud Pass, then three more in the
# Park Range by Steamboat, which is 100 km north of the rest and lower. Colorado's daily values are stamped on the
# Pacific standard clock, as Wyoming's and Utah's are: at Vail Mountain the value dated D matched the hourly reading
# stamped midnight starting D+1 on each of fourteen days, and the station list gives every one a zone of UTC-8.
COLORADO_STATIONS = {
    s.triplet: s
    for s in [
        Station("842:CO:SNTL", "Vail Mountain", 39.61765, -106.38019, _ft(10290)),
        Station("1040:CO:SNTL", "McCoy Park", 39.60231, -106.544, _ft(9500)),
        Station("505:CO:SNTL", "Grizzly Peak", 39.64646, -105.8694, _ft(11110)),
        Station("602:CO:SNTL", "Loveland Basin", 39.67428, -105.90264, _ft(11410)),
        Station("415:CO:SNTL", "Copper Mountain", 39.48917, -106.17154, _ft(10500)),
        Station("335:CO:SNTL", "Berthoud Summit", 39.80364, -105.77786, _ft(11300)),
        Station("457:CO:SNTL", "Dry Lake", 40.5337, -106.7814, _ft(8240)),
        Station("1041:CO:SNTL", "Beaver Creek Village", 39.59871, -106.51113, _ft(8530)),
        Station("485:CO:SNTL", "Fremont Pass", 39.38014, -106.19784, _ft(11310)),
        Station("531:CO:SNTL", "Hoosier Pass", 39.36092, -106.05999, _ft(11600)),
        Station("935:CO:SNTL", "Jackwhacker Gulch", 39.57096, -105.80355, _ft(11030)),
        Station("970:CO:SNTL", "Jones Pass", 39.7645, -105.90655, _ft(10430)),
        Station("1186:CO:SNTL", "Fool Creek", 39.86866, -105.86765, _ft(11130)),
        Station("709:CO:SNTL", "Rabbit Ears", 40.36735, -106.74118, _ft(9390)),
        Station("825:CO:SNTL", "Tower", 40.5374, -106.67655, _ft(10610)),
        Station("408:CO:SNTL", "Columbine", 40.39591, -106.60437, _ft(9170)),
    ]
}
# California's snow pillows around Mt. Shasta and Lassen (CDEC, reporting 2026-11-24); there is no SNOTEL station
# north of the Sierra near them. The two paired with the region's mountains first: Sand Flat, the only pillow on
# Mt. Shasta, and Lower Lassen Peak, which went quiet for most of the last two winters. Then seven more with full
# winters on record, from the Trinity and Scott mountains west of I-5 to Blacks Mountain east of Lassen, that a
# water correction could be fitted to; only Sand Flat among them is on Shasta itself.
SHASTA_STATIONS = {
    s.triplet: s
    for s in [
        Station("SDF:CDEC", "Sand Flat", 41.350239, -122.246529, _ft(6750), source="cdec"),
        Station("LLP:CDEC", "Lower Lassen Peak", 40.466602, -121.50811, _ft(8338), source="cdec"),
        Station("PET:CDEC", "Peterson Flat", 41.302219, -122.527779, _ft(7150), source="cdec"),
        Station("HIG:CDEC", "Highland Lakes", 41.09186, -122.49239, _ft(5830), source="cdec"),
        Station("SLT:CDEC", "Slate Creek", 41.04398, -122.479893, _ft(5560), source="cdec"),
        Station("STM:CDEC", "Stouts Meadow", 41.169275, -121.939465, _ft(5200), source="cdec"),
        Station("SNM:CDEC", "Snow Mountain", 40.778809, -121.782677, _ft(5950), source="cdec"),
        Station("HRK:CDEC", "Harkness Flat", 40.418, -121.275, _ft(6200), source="cdec"),
        Station("BLA:CDEC", "Blacks Mountain", 40.76984, -121.199783, _ft(7050), source="cdec"),
    ]
}
# Canada's snow stations (reporting 2026-11-24). British Columbia's automated snow weather stations (keyed
# "<id>:BCASWS"; positions and elevations from the province's own station list) and one Alberta River Basins snow
# pillow ("<id>:ABRIVERS"; its elevation is SRTM's at the listed spot, as Alberta publishes none). A region's table
# is the stations its water correction is fitted to: each has a snow pillow and a precipitation gauge with at least
# four winters on record since 2020, and the ones paired with a mountain come first. A station between two regions
# is in both. ``corrects=False`` marks one that is only shown.


def _bc(station_id: str, name: str, lat: float, lon: float, elev_m: float, **more) -> Station:
    return Station(f"{station_id}:BCASWS", name, lat, lon, elev_m, source="bcasws", **more)


# The Okanagan's highlands, Trout Creek west of the lake to Park Mountain in the Monashees' foothills. Silver Star
# Mountain is on SilverStar; nothing reports within 20 km of Big White, Sun Peaks or Apex.
OKANAGAN_STATIONS = {
    s.triplet: s
    for s in [
        _bc("2F10P", "Silver Star Mountain", 50.37136, -119.06211, 1840),
        _bc("2F05P", "Mission Creek", 49.94467, -118.94970, 1780),
        _bc("2E07P", "Grano Creek", 49.55197, -118.67730, 1870),
        _bc("1F03P", "Park Mountain", 50.44961, -118.61856, 1890),
        _bc("2F19P", "Oyama Lake", 50.11633, -119.27900, 1360),
        _bc("1F04P", "Enderby", 50.65302, -118.92690, 1950),
        _bc("2F08P", "Greyback Reservoir", 49.61634, -119.42268, 1550),
        _bc("2F01AP", "Trout Creek West", 49.74017, -120.18910, 1420),
        _bc("2F18P", "Brenda Mine", 49.86236, -119.98211, 1460),
        _bc("2F09P", "Whiterocks Mountain", 50.01669, -119.74610, 1800),
    ]
}
# The south Coast Mountains and Vancouver Island: the North Shore, the Sea to Sky, the Lillooet's headwaters and
# the dry side by Bralorne. Mount Strachan, on Cypress itself, measures depth and no water and has no long record,
# so it is only shown.
BCCOAST_STATIONS = {
    s.triplet: s
    for s in [
        _bc("3A09P", "Palisade Lake", 49.45444, -123.03194, 900),
        _bc("3A30P", "Mount Strachan", 49.40432, -123.19151, 1215, corrects=False),
        _bc("3A20P", "Callaghan Creek", 50.13706, -123.10289, 1017),
        _bc("3A25P", "Squamish River Upper", 50.15430, -123.43610, 1360),
        _bc("3A28P", "Tetrahedron", 49.59785, -123.60499, 1420),
        _bc("1D06P", "Tenquille Lake", 50.53625, -122.92996, 1680),
        _bc("1C05P", "McGillivray Pass", 50.69856, -122.62538, 1718, depth=False),
        _bc("1D08P", "Lamont Creek Upper", 49.58191, -122.31428, 1208),
        _bc("3B17P", "Wolf River Upper", 49.70414, -125.67925, 1490, depth=False),
        _bc("1C14P", "Bralorne", 50.77519, -122.78882, 1382),
        _bc("1C18P", "Mission Ridge", 50.76256, -122.20769, 1850, depth=False),
        _bc("1C12P", "Green Mountain", 50.79563, -122.92454, 1780, depth=False),
    ]
}
# The Selkirks and Monashees, Kootenay Lake to the Big Bend. Rogers Pass's station is in the valley; Mount
# Revelstoke's is across the Illecillewaet from the resort.
POWDERHIGHWAY_STATIONS = {
    s.triplet: s
    for s in [
        _bc("2A34P", "Rogers Pass", 51.27012, -117.50942, 1182),
        _bc("2A06P", "Mount Revelstoke", 51.03634, -118.15160, 1850, depth=False),
        _bc("2D14P", "Redfish Creek", 49.69008, -117.08650, 2100),
        _bc("2A31P", "Caribou Creek", 51.10903, -117.22842, 2201, depth=False),
        _bc("2A30P", "Colpitti Creek", 51.60772, -117.61086, 2131),
        _bc("2D10P", "Gray Creek Upper", 49.61656, -116.65890, 1930),
        _bc("2A18P", "Keystone Creek", 51.41129, -118.36066, 1840, depth=False),
        _bc("2B08P", "St. Leon Creek", 50.43417, -117.70121, 1800, depth=False),
        _bc("2B06P", "Barnes Creek", 50.06855, -118.35112, 1620, depth=False),
    ]
}
# The Purcells and the Rockies' west slope, the Flathead to Golden.
EASTKOOTENAYS_STATIONS = {
    s.triplet: s
    for s in [
        _bc("2C09Q", "Morrissey Ridge", 49.44722, -114.975, 1860),
        _bc("2C10P", "Moyie Mountain", 49.25150, -115.77390, 1835),
        _bc("2D08P", "East Creek", 50.63960, -116.92973, 2030, depth=False),
        _bc("2C14P", "Floe Lake", 51.05992, -116.13712, 2090),
        _bc("2A31P", "Caribou Creek", 51.10903, -117.22842, 2201, depth=False),
        _bc("2D10P", "Gray Creek Upper", 49.61656, -116.65890, 1930),
    ]
}
# The Rockies' British Columbia side, which is all that has a record: Alberta publishes five days of readings and
# no more, so Sunshine Village's pillow is only shown and has no usual year to be told against.
ROCKIES_STATIONS = {
    s.triplet: s
    for s in [
        _bc("2A32P", "Wildcat Creek", 51.6963, -116.62941, 2122, depth=False),
        _bc("2C14P", "Floe Lake", 51.05992, -116.13712, 2090),
        _bc("1A01P", "Yellowhead Lake", 52.90622, -118.54750, 1860),
        _bc("2A21P", "Molson Creek", 52.22056, -118.22583, 1935),
        Station("05BB803:ABRIVERS", "Sunshine Village", 51.07745, -115.78159, 2192, source="abrivers", depth=False,
                corrects=False),
    ]
}
CANADA_STATIONS = {**OKANAGAN_STATIONS, **BCCOAST_STATIONS, **POWDERHIGHWAY_STATIONS, **EASTKOOTENAYS_STATIONS,
                   **ROCKIES_STATIONS}
# SNOTEL stations around southwest Montana: Big Sky and the Gallatin, Bridger, Little Belt and Beartooth ranges (NRCS
# AWDB, active 2026-11-26): the ones paired
# with the region's mountains first, then every other within 25 km of one that has reported since before 2022,
# which the region's water correction is also fitted to. The station list gives every one a data time zone of UTC-8.
MONTANA_STATIONS = {
    s.triplet: s
    for s in [
        Station("590:MT:SNTL", "Lone Mountain", 45.27412, -111.42692, _ft(8820)),
        Station("929:MT:SNTL", "Sacajawea", 45.87395, -110.92783, _ft(6610)),
        Station("781:MT:SNTL", "Spur Park", 46.77962, -110.62165, _ft(8080)),
        Station("754:MT:SNTL", "Shower Falls", 45.40125, -110.95758, _ft(8060)),
        Station("480:MT:SNTL", "Fisher Creek", 45.06235, -109.94488, _ft(9110)),
        Station("365:MT:SNTL", "Brackett Creek", 45.89107, -110.93851, _ft(7370)),
        Station("437:MT:SNTL", "Deadman Creek", 46.79279, -110.67545, _ft(6440)),
        Station("578:MT:SNTL", "Lick Creek", 45.50410, -110.96625, _ft(6880)),
        Station("670:MT:SNTL", "Northeast Entrance", 45.00568, -110.01411, _ft(7420)),
        Station("1008:MT:SNTL", "Onion Park", 46.91348, -110.85360, _ft(7420)),
        Station("1009:MT:SNTL", "Stringer Creek", 46.92690, -110.90198, _ft(6550)),
        Station("862:MT:SNTL", "White Mill", 45.04575, -109.90987, _ft(8730)),
    ]
}
# SNOTEL stations around Sun Valley, the Soldier Mountains and the Sawtooths (NRCS AWDB, active 2026-11-26): the ones
# paired
# with the region's mountains first, then every other within 25 km of one that has reported since before 2022,
# which the region's water correction is also fitted to. The station list gives every one a data time zone of UTC-8.
SUNVALLEY_STATIONS = {
    s.triplet: s
    for s in [
        Station("769:ID:SNTL", "Soldier R.S.", 43.48407, -114.82692, _ft(5780)),
        Station("490:ID:SNTL", "Galena Summit", 43.87497, -114.71363, _ft(8790)),
        Station("312:ID:SNTL", "Banner Summit", 44.30342, -115.23447, _ft(7040)),
        Station("895:ID:SNTL", "Chocolate Gulch", 43.76850, -114.41812, _ft(6310)),
        Station("1306:ID:SNTL", "Couch Summit", 43.51762, -114.80214, _ft(6780)),
        Station("450:ID:SNTL", "Dollarhide Summit", 43.60250, -114.67417, _ft(8390)),
        Station("489:ID:SNTL", "Galena", 43.87722, -114.67250, _ft(7470)),
        Station("537:ID:SNTL", "Hyndman", 43.71077, -114.15894, _ft(7590)),
        Station("601:ID:SNTL", "Lost-Wood Divide", 43.82441, -114.26404, _ft(7870)),
        Station("792:ID:SNTL", "Stickney Mill", 43.86117, -114.20902, _ft(7440)),
        Station("845:ID:SNTL", "Vienna Mine", 43.79942, -114.85273, _ft(8930)),
    ]
}
# SNOTEL stations around Oregon's Cascades, Mt. Hood to Willamette Pass (NRCS AWDB, active 2026-11-26): the ones paired
# with the region's mountains first, then every other within 25 km of one that has reported since before 2022,
# which the region's water correction is also fitted to. The station list gives every one a data time zone of UTC-8.
OREGON_STATIONS = {
    s.triplet: s
    for s in [
        Station("651:OR:SNTL", "Mt Hood Test Site", 45.32097, -121.71580, _ft(5380)),
        Station("655:OR:SNTL", "Mud Ridge", 45.25362, -121.73673, _ft(4070)),
        Station("712:OR:SNTL", "Red Hill", 45.46430, -121.70428, _ft(4410)),
        Station("526:OR:SNTL", "Hogg Pass", 44.42042, -121.85655, _ft(4800)),
        Station("388:OR:SNTL", "Cascade Summit", 43.59042, -122.06010, _ft(5100)),
        Station("1166:OR:SNTL", "Bear Grass", 44.32530, -122.09380, _ft(4720)),
        Station("351:OR:SNTL", "Blazed Alder", 45.42870, -121.85605, _ft(3660)),
        Station("398:OR:SNTL", "Clackamas Lake", 45.09658, -121.75443, _ft(3400)),
        Station("401:OR:SNTL", "Clear Lake", 45.18832, -121.69160, _ft(3810)),
        Station("434:OR:SNTL", "Daly Lake", 44.52147, -122.08718, _ft(3690)),
        Station("504:OR:SNTL", "Greenpoint", 45.62237, -121.70415, _ft(3320)),
        Station("545:OR:SNTL", "Irish Taylor", 43.80368, -121.94793, _ft(5540)),
        Station("552:OR:SNTL", "Jump Off Joe", 44.38605, -122.16683, _ft(3530)),
        Station("614:OR:SNTL", "Marion Forks", 44.59397, -121.97365, _ft(2590)),
        Station("619:OR:SNTL", "Mckenzie", 44.21030, -121.87292, _ft(4770)),
        Station("660:OR:SNTL", "New Crescent Lake", 43.51185, -121.97982, _ft(4910)),
        Station("710:OR:SNTL", "Railroad Overpass", 43.65887, -122.21272, _ft(2680)),
        Station("729:OR:SNTL", "Salt Creek Falls", 43.61193, -122.11758, _ft(4220)),
        Station("733:OR:SNTL", "Santiam Jct.", 44.43503, -121.94502, _ft(3740)),
        Station("1167:OR:SNTL", "Smith Ridge", 44.30325, -122.04053, _ft(3270)),
        Station("801:OR:SNTL", "Summit Lake", 43.44907, -122.13808, _ft(5610)),
        Station("815:OR:SNTL", "Three Creeks Meadow", 44.14425, -121.64095, _ft(5680)),
    ]
}
# SNOTEL stations around northern New Mexico: the Sangre de Cristo and Jemez mountains (NRCS AWDB, active 2026-11-26):
# the ones paired
# with the region's mountains first, then every other within 25 km of one that has reported since before 2022,
# which the region's water correction is also fitted to. The station list gives every one a data time zone of UTC-8.
NEWMEXICO_STATIONS = {
    s.triplet: s
    for s in [
        Station("1168:NM:SNTL", "Taos Powderhorn", 36.58195, -105.45617, _ft(11020)),
        Station("715:NM:SNTL", "Red River Pass #2", 36.69935, -105.34145, _ft(9840)),
        Station("1170:NM:SNTL", "Palo", 36.40869, -105.33038, _ft(9330)),
        Station("1083:NM:SNTL", "Tres Ritos", 36.12790, -105.52706, _ft(8740)),
        Station("922:NM:SNTL", "Santa Fe", 35.77154, -105.78487, _ft(11480)),
        Station("708:NM:SNTL", "Quemazon", 35.92195, -106.39179, _ft(9500)),
        Station("921:NM:SNTL", "Elk Cabin", 35.70730, -105.80584, _ft(8220)),
        Station("491:NM:SNTL", "Gallegos Peak", 36.19418, -105.55742, _ft(9460)),
        Station("1173:NM:SNTL", "Garita Peak", 36.00469, -106.54805, _ft(10100)),
        Station("1254:NM:SNTL", "Rio Santa Barbara", 36.07196, -105.62949, _ft(10640)),
        Station("1169:NM:SNTL", "Shuree", 36.78765, -105.23920, _ft(10070)),
        Station("1307:NM:SNTL", "Taos Pueblo", 36.54099, -105.35944, _ft(10990)),
        Station("934:NM:SNTL", "Tolby", 36.47498, -105.19534, _ft(10210)),
        Station("854:NM:SNTL", "Wesner Springs", 35.77584, -105.54337, _ft(11110)),
    ]
}
# SNOTEL stations around Southcentral Alaska: Girdwood, Turnagain Pass, Summit Lake, Anchorage and Hatcher Pass (NRCS
# AWDB, active 2026-11-26): the ones paired
# with the region's mountains first, then every other within 25 km of one that has reported since before 2022,
# which the region's water correction is also fitted to. Alaska stamps its daily values an hour later than the other
# states, on its own standard clock (a data time zone of UTC-9 in the station list).
ALASKA_STATIONS = {
    s.triplet: s
    for s in [
        Station("1103:AK:SNTL", "Mt. Alyeska", 60.95842, -149.08858, _ft(1500)),
        Station("641:AK:SNTL", "Frostbite Bottom", 61.74699, -149.26769, _ft(2690)),
        Station("954:AK:SNTL", "Turnagain Pass", 60.78043, -149.18325, _ft(1860)),
        Station("955:AK:SNTL", "Summit Creek", 60.61713, -149.53128, _ft(1340)),
        Station("1091:AK:SNTL", "Independence Mine", 61.79001, -149.28390, _ft(3450)),
        Station("1070:AK:SNTL", "Anchorage Hillside", 61.11315, -149.68345, _ft(1910)),
        Station("956:AK:SNTL", "Grandview", 60.60832, -149.06313, _ft(1070)),
        Station("946:AK:SNTL", "Indian Pass", 61.06577, -149.48543, _ft(2400)),
        Station("2044:AK:SNTL", "Spring Creek", 61.65653, -149.12926, _ft(590)),
    ]
}
# SNOTEL stations around southwest Colorado: the Elk Mountains, the Sawatch at Monarch and the San Juans (NRCS AWDB,
# active 2026-11-26): the ones paired
# with the region's mountains first, then every other within 25 km of one that has reported since before 2022,
# which the region's water correction is also fitted to. The station list gives every one a data time zone of UTC-8.
SWCOLORADO_STATIONS = {
    s.triplet: s
    for s in [
        Station("380:CO:SNTL", "Butte", 38.89435, -106.95327, _ft(10190)),
        Station("701:CO:SNTL", "Porphyry Creek", 38.48864, -106.33967, _ft(10790)),
        Station("1344:CO:SNTL", "Alta Lakes", 37.88929, -107.84484, _ft(11290)),
        Station("713:CO:SNTL", "Red Mountain Pass", 37.89168, -107.71389, _ft(11060)),
        Station("387:CO:SNTL", "Cascade #2", 37.65751, -107.80287, _ft(8990)),
        Station("874:CO:SNTL", "Wolf Creek Summit", 37.47903, -106.80234, _ft(10930)),
        Station("780:CO:SNTL", "Spud Mountain", 37.69883, -107.77841, _ft(10660)),
        Station("669:CO:SNTL", "North Lost Trail", 39.07818, -107.14388, _ft(9190)),
        Station("327:CO:SNTL", "Beartown", 37.71433, -107.51240, _ft(11580)),
        Station("1101:CO:SNTL", "Chapman Tunnel", 39.26210, -106.62944, _ft(10090)),
        Station("465:CO:SNTL", "El Diente Peak", 37.78607, -108.02235, _ft(10210)),
        Station("1058:CO:SNTL", "Grayback", 37.47051, -106.53790, _ft(11620)),
        Station("538:CO:SNTL", "Idarado", 37.93389, -107.67620, _ft(9780)),
        Station("542:CO:SNTL", "Independence Pass", 39.07543, -106.61154, _ft(10570)),
        Station("556:CO:SNTL", "Kiln", 39.31720, -106.61501, _ft(9610)),
        Station("580:CO:SNTL", "Lily Pond", 37.38028, -106.54823, _ft(11070)),
        Station("586:CO:SNTL", "Lizard Head Pass", 37.79895, -107.92475, _ft(10190)),
        Station("618:CO:SNTL", "Mc Clure Pass", 39.12899, -107.28834, _ft(8760)),
        Station("629:CO:SNTL", "Mineral Creek", 37.84737, -107.72657, _ft(10030)),
        Station("632:CO:SNTL", "Molas Lake", 37.74929, -107.68933, _ft(10610)),
        Station("658:CO:SNTL", "Nast Lake", 39.29695, -106.60786, _ft(8710)),
        Station("1100:CO:SNTL", "Saint Elmo", 38.69985, -106.36805, _ft(10420)),
        Station("1128:CO:SNTL", "Sargents Mesa", 38.28560, -106.37085, _ft(11490)),
        Station("737:CO:SNTL", "Schofield Pass", 39.01467, -107.04933, _ft(10640)),
        Station("739:CO:SNTL", "Scotch Creek", 37.64562, -108.00833, _ft(9160)),
        Station("797:CO:SNTL", "Stump Lakes", 37.47647, -107.63348, _ft(11230)),
        Station("840:CO:SNTL", "Upper San Juan", 37.48563, -106.83528, _ft(10140)),
        Station("1141:CO:SNTL", "Upper Taylor", 38.99071, -106.74504, _ft(10710)),
    ]
}
# The regions added after the third collector's first six keep their sensors in one table, by region: the SNOTEL
# stations paired with a region's mountains first, then every other within 25 km of one that has reported since
# before 2022 (NRCS AWDB, active 2026-11-26). Every state's stations but Alaska's keep the Pacific standard clock.
MORE_STATIONS = {
    # Western Idaho: Bogus Basin above Boise, Brundage and Tamarack by McCall, and Anthony Lakes across the Snake
    # in Oregon's Elkhorns.
    "westidaho": {s.triplet: s for s in [
        Station("978:ID:SNTL", "Bogus Basin", 43.76377, -116.09685, _ft(6370)),
        Station("370:ID:SNTL", "Brundage Reservoir", 45.04315, -116.13253, _ft(6280)),
        Station("319:ID:SNTL", "Bear Basin", 44.95222, -116.14293, _ft(5350)),
        Station("1016:ID:SNTL", "Long Valley", 44.78835, -116.08878, _ft(4890)),
        Station("782:ID:SNTL", "Puhi Flat", 44.77091, -116.24805, _ft(6240)),
        Station("740:ID:SNTL", "Secesh Summit", 45.18848, -115.97152, _ft(6530)),
        Station("855:ID:SNTL", "West Branch", 45.07220, -116.45413, _ft(5590)),
        Station("331:OR:SNTL", "Beaver Reservoir", 45.14532, -118.21900, _ft(5140)),
        Station("361:OR:SNTL", "Bourne", 44.83052, -118.18787, _ft(5850)),
        Station("464:OR:SNTL", "Eilertson Meadows", 44.86887, -118.11387, _ft(5510)),
        Station("494:OR:SNTL", "Gold Center", 44.76380, -118.31170, _ft(5400)),
        Station("873:OR:SNTL", "Wolf Creek", 45.06704, -118.15185, _ft(5730)),
    ]},
    # Wyoming outside Jackson: the Snowy Range, Casper Mountain, the Bighorns, Cody's Sleeping Giant, Pinedale's
    # White Pine and Cokeville's Pine Creek.
    "wyoming": {s.triplet: s for s in [
        Station("367:WY:SNTL", "Brooklyn Lake", 41.36038, -106.23038, _ft(10250)),
        Station("807:WY:SNTL", "Sylvan Road", 44.47825, -110.03808, _ft(7140)),
        Station("468:WY:SNTL", "Elkhart Park G.S.", 43.00657, -109.75893, _ft(9410)),
        Station("389:WY:SNTL", "Casper Mtn.", 42.73362, -106.31789, _ft(7940)),
        Station("703:WY:SNTL", "Powder River Pass", 44.16188, -107.12622, _ft(9480)),
        Station("358:WY:SNTL", "Bone Springs Div", 44.67881, -107.58110, _ft(9340)),
        Station("350:WY:SNTL", "Blackwater", 44.37667, -109.79333, _ft(9830)),
        Station("377:WY:SNTL", "Burgess Junction", 44.78765, -107.52917, _ft(7910)),
        Station("1046:WY:SNTL", "Cinnabar Park", 41.23843, -106.23101, _ft(9670)),
        Station("451:WY:SNTL", "Dome Lake", 44.57462, -107.29537, _ft(8890)),
        Station("472:WY:SNTL", "Evening Star", 44.65258, -109.78422, _ft(9030)),
        Station("509:WY:SNTL", "Hams Fork", 42.14600, -110.67833, _ft(7860)),
        Station("512:WY:SNTL", "Hanson Sawmill", 44.25602, -106.97983, _ft(8360)),
        Station("554:WY:SNTL", "Kelley R.S.", 42.26554, -110.80181, _ft(8240)),
        Station("1196:WY:SNTL", "Med Bow", 41.37833, -106.34697, _ft(10500)),
        Station("661:WY:SNTL", "New Fork Lake", 43.11265, -109.94947, _ft(8380)),
        Station("668:WY:SNTL", "North French Creek", 41.33087, -106.37558, _ft(10150)),
        Station("731:WY:SNTL", "Sand Lake", 41.46250, -106.28100, _ft(10080)),
        Station("751:WY:SNTL", "Shell Creek", 44.50012, -107.42947, _ft(9570)),
        Station("798:WY:SNTL", "Sucker Creek", 44.72279, -107.40035, _ft(8840)),
        Station("806:WY:SNTL", "Sylvan Lake", 44.47764, -110.15651, _ft(8440)),
        Station("818:WY:SNTL", "Tie Creek", 44.81243, -107.41017, _ft(7050)),
    ]},
    # Southern Utah: Brian Head, and Eagle Point and Delano Peak in the Tushars.
    "southutah": {s.triplet: s for s in [
        Station("1154:UT:SNTL", "Brian Head", 37.67994, -112.85674, _ft(10040)),
        Station("339:UT:SNTL", "Big Flat", 38.30183, -112.35672, _ft(10320)),
        Station("390:UT:SNTL", "Castle Valley", 37.66098, -112.74093, _ft(9600)),
        Station("557:UT:SNTL", "Kimberly Mine", 38.48383, -112.39273, _ft(9110)),
        Station("621:UT:SNTL", "Merchant Valley", 38.30285, -112.43637, _ft(8710)),
        Station("626:UT:SNTL", "Midway Valley", 37.56933, -112.83849, _ft(9830)),
        Station("1148:UT:SNTL", "Panguitch Lake RS", 37.70463, -112.65037, _ft(8300)),
        Station("1248:UT:SNTL", "Suu Ranch", 37.59711, -112.92949, _ft(8050)),
        Station("853:UT:SNTL", "Webster Flat", 37.57500, -112.90155, _ft(9150)),
        Station("1197:UT:SNTL", "Yankee Reservoir", 37.74797, -112.77495, _ft(8680)),
    ]},
    # Arizona: Snowbowl and Humphreys Peak on the San Francisco Peaks, and Sunrise in the White Mountains, 250 km
    # south-east.
    "arizona": {s.triplet: s for s in [
        Station("927:AZ:SNTL", "Snowslide Canyon", 35.34179, -111.65084, _ft(9720)),
        Station("310:AZ:SNTL", "Baldy", 33.97845, -109.50357, _ft(9210)),
        Station("1121:AZ:SNTL", "Fort Valley", 35.26773, -111.74479, _ft(7360)),
        Station("1271:AZ:SNTL", "Hawley Lake", 33.97121, -109.76531, _ft(8290)),
        Station("617:AZ:SNTL", "Maverick Fork", 33.92123, -109.45872, _ft(9210)),
    ]},
    # Lee Canyon in the Spring Mountains above Las Vegas.
    "lasvegas": {s.triplet: s for s in [
        Station("1350:NV:SNTL", "Lee Canyon Upper", 36.29604, -115.68430, _ft(9390)),
        Station("1111:NV:SNTL", "Bristlecone Trail", 36.31575, -115.69543, _ft(8900)),
        Station("1112:NV:SNTL", "Lee Canyon", 36.30537, -115.67508, _ft(8620)),
        Station("1110:NV:SNTL", "Rainbow Canyon", 36.24930, -115.62972, _ft(7840)),
    ]},
    # Valdez: Thompson Pass's backcountry, the Odyssey side from the pass summit and Girls Mountain across the
    # highway. The Upper Tsaina River sensor, 6 km off and 600 m below, is shown but corrects nothing.
    "valdez": {s.triplet: s for s in [
        Station("1055:AK:SNTL", "Upper Tsaina River", 61.19112, -145.64807, _ft(1730)),
    ]},
    # Inland Northwest.
    "inlandnw": {s.triplet: s for s in [
        Station("738:ID:SNTL", "Schweitzer Basin", 48.37428, -116.63917, _ft(6090)),
        Station("594:ID:SNTL", "Lookout", 47.45749, -115.70457, _ft(5180)),
        Station("707:WA:SNTL", "Quartz Peak", 47.87927, -117.08938, _ft(4710)),
        Station("535:ID:SNTL", "Humboldt Gulch", 47.53178, -115.77643, _ft(4260)),
        Station("1081:ID:SNTL", "Ragged Mountain", 47.85583, -117.03667, _ft(4210)),
        Station("803:ID:SNTL", "Sunset", 47.55545, -115.82422, _ft(5570)),
    ]},
    # Northwest Montana.
    "nwmontana": {s.triplet: s for s in [
        Station("1144:MT:SNTL", "Blacktail Mtn", 47.98317, -114.35443, _ft(5660)),
        Station("901:MT:SNTL", "Stuart Mountain", 46.99521, -113.92667, _ft(7270)),
        Station("850:MT:SNTL", "Warm Springs", 46.27368, -113.16400, _ft(7840)),
        Station("727:MT:SNTL", "Saddle Mtn.", 45.69259, -113.96828, _ft(7890)),
        Station("664:MT:SNTL", "Noisy Basin", 48.15668, -113.94630, _ft(6070)),
        Station("313:MT:SNTL", "Barker Lakes", 46.09713, -113.13038, _ft(8250)),
        Station("349:MT:SNTL", "Black Pine", 46.41400, -113.43095, _ft(7170)),
        Station("930:MT:SNTL", "Peterson Meadows", 46.12588, -113.30792, _ft(7190)),
        Station("638:ID:SNTL", "Moose Creek", 45.67008, -113.95315, _ft(6170)),
    ]},
    # Black Hills.
    "blackhills": {s.triplet: s for s in [
        Station("920:SD:SNTL", "North Rapid Creek", 44.20617, -103.78758, _ft(6150)),
    ]},
}

ALL_STATIONS = {**STATIONS, **MAMMOTH_STATIONS, **NEWENGLAND_STATIONS, **SEATTLE_STATIONS, **TETONS_STATIONS,
                **WASATCH_STATIONS, **COLORADO_STATIONS, **SHASTA_STATIONS, **CANADA_STATIONS, **MONTANA_STATIONS,
                **SUNVALLEY_STATIONS, **OREGON_STATIONS, **NEWMEXICO_STATIONS, **ALASKA_STATIONS, **SWCOLORADO_STATIONS,
                **{triplet: station for stations in MORE_STATIONS.values() for triplet, station in stations.items()}}

# Resort elevations from OpenSkiMap statistics (ODbL), Mammoth and June from the resorts' published figures;
# resort coordinates are mid-mountain. For backcountry spots the summit is the peak and the base is the usual
# winter trailhead, both read from the Terrain Tiles elevation model (2026-11-19). Mammoth Mountain and Sherwin
# Ridge pair with the Mammoth Pass pillow, 2 km south of the summit. Nothing that still reports sits near June
# (Gem Pass and Agnew Pass went quiet), so June Mountain and Carson Peak have no station and no correction.
# Matterhorn Peak (base at Twin Lakes) pairs with Slide Canyon, 4 km west across the crest, and Dana Plateau
# (the rim above the chutes; base at Ellery Lake on the Tioga Road) with Dana Meadows, 5 km southwest.
# Mt. Whitney (base at Whitney Portal; published elevations) is far south of every sensor the Mammoth correction
# was fitted to, so it has no station either.
ALL_RESORTS = {
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
        # New England has no snow sensors, so none of these has a station (Tuckerman's, below, is shown only).
        # Elevations are from each resort's own
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
        # The rest of New England's larger mountains (looked up 2026-11-24). Each point is the midpoint of a main
        # lift in OpenStreetMap, checked against the USGS elevation service; for Cannon, Bretton Woods and
        # Saddleback it is the lift from the base, since the one to the top starts mid-mountain. Elevations are the
        # resort's own or the Indy Pass's figures, except where those do not match the ground: Jay Peak's summit is
        # its tram's top, Bolton Valley's base is the Timberline lift's, and Saddleback, Cranmore and Black
        # Mountain's summit are read at the ends of their lifts. Most take a neighbour's weather; Jay Peak, Burke,
        # Bretton Woods and Saddleback have no neighbour near enough and ask for their own.
        Resort("jaypeak", "Jay Peak", 44.93161, -72.51601, _ft(1815), _ft(3823), None, "Indy",
               region="newengland"),
        Resort("smugglers", "Smugglers' Notch", 44.56721, -72.76681, _ft(1030), _ft(3640), None, "Indy",
               region="newengland", weather_from="stowe"),               # 4.5 km from Stowe
        Resort("bolton", "Bolton Valley", 44.41768, -72.84166, _ft(1560), _ft(3150), None, "Indy",
               region="newengland", weather_from="stowe"),               # 13 km from Stowe
        Resort("madriverglen", "Mad River Glen", 44.19682, -72.92455, _ft(1600), _ft(3637), None, "Independent",
               region="newengland", weather_from="sugarbush"),           # 7 km from Sugarbush
        Resort("burke", "Burke", 44.57798, -71.89843, _ft(1210), _ft(3267), None, "Indy",
               region="newengland"),
        Resort("bromley", "Bromley", 43.22020, -72.93758, _ft(1950), _ft(3284), None, "Independent",
               region="newengland", weather_from="stratton"),            # 13 km from Stratton
        Resort("magic", "Magic Mountain", 43.19703, -72.76516, _ft(1350), _ft(2850), None, "Indy",
               region="newengland", weather_from="stratton"),            # 16 km from Stratton
        Resort("cannon", "Cannon", 44.17026, -71.69910, _ft(1900), _ft(4080), None, "Indy",
               region="newengland", weather_from="loon"),                # 15 km from Loon
        Resort("waterville", "Waterville Valley", 43.96268, -71.53846, _ft(1820), _ft(3840), None, "Indy",
               region="newengland", weather_from="loon"),                # 12 km from Loon
        Resort("brettonwoods", "Bretton Woods", 44.25233, -71.46541, _ft(1600), _ft(3100), None, "Independent",
               region="newengland"),
        # Cranmore gives two days on the full Ikon pass only, so it is not counted as an Ikon mountain.
        Resort("cranmore", "Cranmore", 44.05756, -71.10110, _ft(553), _ft(1667), None, "Independent",
               region="newengland", weather_from="attitash"),            # 10 km from Attitash
        Resort("blackmountain", "Black Mountain", 44.17199, -71.16709, _ft(1250), _ft(2258), None, "Indy",
               region="newengland", weather_from="attitash"),            # 12 km from Attitash
        Resort("saddleback", "Saddleback", 44.94152, -70.52148, _ft(2143), _ft(4002), None, "Indy",
               region="newengland"),
        # Mt. Mansfield above Stowe's lifts: the point and top are the summit (the Chin), and the base is the Hell
        # Brook trailhead on Route 108. No avalanche center forecasts it.
        Resort("mansfield", "Mt. Mansfield", 44.54395, -72.81431, 560, 1339, None, "Backcountry",
               region="newengland", kind="backcountry", weather_from="stowe"),     # 1.5 km from Stowe
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
        # Tetons: the three lift-served mountains around Jackson and the two passes skied from the road (looked up
        # 2026-11-24). Jackson Hole's base and summit are from its own statistics page, Grand Targhee's from its
        # own (the main base area and the top of Fred's Mountain, its highest lift), Snow King's from Wikipedia
        # (its own site refused to be read). Each resort's point is the middle of its main lift in OpenStreetMap:
        # Jackson Hole's tram, Targhee's Dreamcatcher, Snow King's Summit Gondola. Jackson Hole is also on the
        # Mountain Collective; Snow King's place on the Indy Pass this winter is disputed, so it is Independent.
        # Teton Pass runs from the lot at the top of the pass (8,431 ft) to Mount Glory's higher, south summit
        # (10,086 ft), its point half way up the bootpack. Togwotee Pass is Breccia Peak (11,007 ft), the tour the
        # guides call the most accessible, from its pull-out a kilometre north of the pass, which the Terrain Tiles
        # put at 2,886 m, below the pass itself; its point is on the way up at about the middle height.
        # Sensors by the guide's rule: Phillips Bench is 9.8 km from Jackson Hole's point and 64 m under its middle;
        # it is 3.6 km from Teton Pass's but 330 m under that middle, below the pass itself, so a weak match there.
        # Nothing reports within 10 km of Snow King.
        Resort("jacksonhole", "Jackson Hole", 43.59236, -110.84913, _ft(6311), _ft(10450), "689:WY:SNTL", "Ikon",
               region="tetons"),
        Resort("targhee", "Grand Targhee", 43.78795, -110.94568, _ft(7851), _ft(9862), "1082:WY:SNTL",
               "Mountain Collective", region="tetons"),
        Resort("snowking", "Snow King", 43.4678, -110.76167, _ft(6237), _ft(7808), None, "Independent",
               region="tetons"),
        Resort("tetonpass", "Teton Pass", 43.5022, -110.9526, _ft(8431), _ft(10086), "689:WY:SNTL", "Backcountry",
               region="tetons", kind="backcountry", weak_match=True),
        Resort("togwotee", "Togwotee Pass", 43.7822, -110.0715, 2886, _ft(11007), "822:WY:SNTL", "Backcountry",
               region="tetons", kind="backcountry"),
        # The Wasatch (looked up 2026-11-24). Each resort's point is the midpoint of a main lift from its base in
        # OpenStreetMap, checked against the USGS elevation service. Bases are the resorts' own figures (Alta's and
        # Sundance's from Ski Utah). A summit is the top of the highest lift where the published one is a peak
        # reached on foot: Alta's is the Sugarloaf lift's (not Mt. Baldy, 11,068 ft), Solitude's the Summit
        # Express's, Park City's the Jupiter lift's, Snowbasin's the Allen Peak tram's and Powder Mountain's
        # Lightning Ridge's (not James Peak). The Ikon mountains that are also on the Mountain Collective are Ikon.
        # Four pairs are close enough to share weather, none across the main crest; Alta and Brighton are 5 km
        # apart but over the divide between the Cottonwood canyons, so each asks for its own.
        # Sensors by the guide's rule. Alta and Mt. Superior take Snowbird's: Atwater is nearer but 320 m under
        # their middles. Thaynes Canyon is 3 km from Park City and 258 m above its middle; it is 369 m above Deer
        # Valley's, which is taken with it because the two share one reading of the weather. Timpanogos Divide is
        # 347 m under Mt. Timpanogos's middle, a weak match. Nothing reports within 10 km of Snowbasin.
        Resort("alta", "Alta", 40.57979, -111.63715, _ft(8530), _ft(10556), "766:UT:SNTL", "Ikon",
               region="wasatch"),
        Resort("snowbird", "Snowbird", 40.57104, -111.65074, _ft(7760), _ft(11000), "766:UT:SNTL", "Ikon",
               region="wasatch", weather_from="alta"),                   # 1.5 km from Alta
        Resort("brighton", "Brighton", 40.59049, -111.58015, _ft(8755), _ft(10500), "366:UT:SNTL", "Ikon",
               region="wasatch"),
        Resort("solitude", "Solitude", 40.61639, -111.5978, _ft(7994), _ft(10010), "366:UT:SNTL", "Ikon",
               region="wasatch", weather_from="brighton"),               # 3.2 km from Brighton
        Resort("parkcity", "Park City", 40.64296, -111.50814, _ft(6800), _ft(9977), "814:UT:SNTL", "Epic",
               region="wasatch"),
        Resort("deervalley", "Deer Valley", 40.6315, -111.4821, _ft(6530), _ft(9570), "814:UT:SNTL", "Ikon",
               region="wasatch", weather_from="parkcity"),               # 2.5 km from Park City
        Resort("snowbasin", "Snowbasin", 41.20469, -111.86577, _ft(6450), _ft(9366), None, "Ikon",
               region="wasatch"),
        Resort("powdermountain", "Powder Mountain", 41.37722, -111.76249, _ft(6900), _ft(9005), "1300:UT:SNTL",
               "Independent", region="wasatch"),
        Resort("sundance", "Sundance", 40.38668, -111.58493, _ft(6100), _ft(8250), "820:UT:SNTL", "Independent",
               region="wasatch"),
        # Backcountry. Each point is on the way up at about the middle height: Mt. Superior's on its east ridge,
        # Cardiff Peak's on the Cardiff Pass trail, both from the trailhead in Alta (2,631 m), and Mt. Timpanogos's
        # on the trail from Aspen Grove (2,099 m). Summits are OpenStreetMap's peaks, checked against USGS.
        Resort("superior", "Mt. Superior", 40.59391, -111.65865, 2631, 3364, "766:UT:SNTL", "Backcountry",
               region="wasatch", kind="backcountry", weather_from="alta"),          # 2.4 km from Alta
        Resort("cardiff", "Cardiff Peak", 40.59335, -111.64418, 2631, 3132, "1308:UT:SNTL", "Backcountry",
               region="wasatch", kind="backcountry", weather_from="alta"),          # 1.6 km from Alta
        Resort("timpanogos", "Mt. Timpanogos", 40.39824, -111.63013, 2099, 3581, "820:UT:SNTL", "Backcountry",
               region="wasatch", kind="backcountry", weak_match=True, weather_from="sundance"),   # 4 km
        # Colorado: the I-70 corridor from Beaver Creek to Loveland, Winter Park and Berthoud Pass, and Steamboat
        # (looked up 2026-11-24). Each resort's point is the midpoint of a main lift from its base in
        # OpenStreetMap, checked against the USGS elevation service; Breckenridge's is the Colorado SuperChair's,
        # from the Peak 8 base. Bases are the resorts' own figures (A-Basin's, Copper's and Steamboat's from
        # secondary sources that match the ground). A summit is the top of the highest lift where the published
        # one is reached on foot: Breckenridge's Imperial chair, Keystone's Bergman, A-Basin's Lenawee, Loveland's
        # Lift 9, Copper's Three Bears, Winter Park's Panoramic and Steamboat's Morningside.
        # Sharing: A-Basin takes Keystone's weather (7.8 km, both west of the Divide), Loveland Pass takes
        # Loveland's (2.6 km), Vail Pass takes Copper's (7.4 km, across West Tenmile Creek, not the Divide) and
        # Berthoud Pass takes Winter Park's (9.3 km; the pass is on the Divide, but nothing else is near). Loveland
        # and A-Basin are 4.9 km apart across the Divide and Breckenridge and Copper 7 km across the Tenmile
        # Range, so each asks for its own.
        # Sensors by the guide's rule. Breckenridge's only one within 10 km is Copper Mountain's, across the
        # Tenmile crest, so it has none. Winter Park takes Berthoud Summit, level with Fool Creek by distance but
        # on record since 1963 and shared with the pass. Loveland Pass and Vail Pass sit more than 300 m above
        # theirs, weak matches.
        Resort("vail", "Vail", 39.62698, -106.37096, _ft(8120), _ft(11570), "842:CO:SNTL", "Epic", region="colorado"),
        Resort("beavercreek", "Beaver Creek", 39.59273, -106.51323, _ft(8100), _ft(11440), "1040:CO:SNTL", "Epic",
               region="colorado"),
        Resort("breckenridge", "Breckenridge", 39.47582, -106.07661, _ft(9600), _ft(12840), None, "Epic",
               region="colorado"),
        Resort("keystone", "Keystone", 39.59276, -105.94115, _ft(9280), _ft(12277), "505:CO:SNTL", "Epic",
               region="colorado"),
        Resort("abasin", "Arapahoe Basin", 39.63778, -105.87148, _ft(10780), _ft(12479), "505:CO:SNTL", "Ikon",
               region="colorado", weather_from="keystone"),              # 7.8 km from Keystone
        Resort("loveland", "Loveland", 39.67672, -105.89713, _ft(10800), _ft(12700), "602:CO:SNTL", "Indy",
               region="colorado"),
        Resort("copper", "Copper Mountain", 39.49158, -106.15617, _ft(9712), _ft(12322), "415:CO:SNTL", "Ikon",
               region="colorado"),
        Resort("winterpark", "Winter Park", 39.88023, -105.76915, _ft(9000), _ft(11988), "335:CO:SNTL", "Ikon",
               region="colorado"),
        Resort("steamboat", "Steamboat", 40.45519, -106.78864, _ft(6900), _ft(10543), "457:CO:SNTL", "Ikon",
               region="colorado"),
        # Backcountry, each from its pass's lot to the summit most skied from it, the point half way up: Colorado
        # Mines Peak above Berthoud Pass, the Divide ridge east of Loveland Pass below Mt. Sniktau, and Uneva Peak
        # from Vail Pass. Heights are USGS's.
        Resort("berthoud", "Berthoud Pass", 39.7964, -105.76994, 3448, 3805, "335:CO:SNTL", "Backcountry",
               region="colorado", kind="backcountry", weather_from="winterpark"),            # 9.3 km
        Resort("lovelandpass", "Loveland Pass", 39.6722, -105.8668, 3655, 3938, "602:CO:SNTL", "Backcountry",
               region="colorado", kind="backcountry", weak_match=True, weather_from="loveland"),   # 2.6 km
        Resort("vailpass", "Vail Pass", 39.5475, -106.2035, 3232, 3813, "415:CO:SNTL", "Backcountry",
               region="colorado", kind="backcountry", weak_match=True, weather_from="copper"),     # 7.4 km
        # Shasta: Mt. Shasta and the mountains a day's drive around it, from Mt. Ashland in Oregon to Lassen Peak
        # (looked up 2026-11-24). The Ski Park's point is the midpoint of its Douglas chair and Mt. Ashland's of its
        # Ariel chair, in OpenStreetMap, checked against the USGS elevation service. The Ski Park's summit is its
        # stated base plus its stated vertical, which is where the Gray Butte chair ends; Mt. Ashland's is the top
        # of the Ariel chair, 55 ft under the peak. Mt. Shasta runs from Bunny Flat up Avalanche Gulch, its point at
        # Helen Lake; Lassen Peak from the Kohm Yah-mah-nee visitor center, where the road is closed in winter;
        # Castle Lake from the lot at the lake to Middle Peak, the tour the avalanche center's observers make there.
        # Nobody shares weather: the Ski Park is on Shasta's own flank, 1,360 m under the mountain's point, and the
        # rest are 19 km apart or more.
        # Sensors: Sand Flat is 5 km from the Ski Park and near its middle height; it is the nearest to Mt. Shasta
        # too, but 1,158 m under that mountain's middle, so there it is shown and corrects nothing. Lower Lassen
        # Peak is on Lassen. Nothing reports within 10 km of Castle Lake or of Mt. Ashland (Big Red Mountain is
        # 12 km along the crest).
        Resort("shastaskipark", "Mt. Shasta Ski Park", 41.32316, -122.19807, _ft(5500), _ft(7536), "SDF:CDEC", "Indy",
               region="shasta"),
        Resort("ashland", "Mt. Ashland", 42.08402, -122.71416, _ft(6344), _ft(7478), None, "Independent",
               region="shasta"),
        Resort("shasta", "Mt. Shasta", 41.38988, -122.21016, 2109, 4322, "SDF:CDEC", "Backcountry",
               region="shasta", kind="backcountry", weak_match=True, corrected=False),
        Resort("castlelake", "Castle Lake", 41.22132, -122.38332, 1659, 2016, None, "Backcountry",
               region="shasta", kind="backcountry"),
        Resort("lassen", "Lassen Peak", 40.47685, -121.50608, 2051, 3187, "LLP:CDEC", "Backcountry",
               region="shasta", kind="backcountry"),
        # ---- Canada: built by the second collector (see COLLECTOR). Heights are metres as the resorts publish
        # them, checked against OpenTopoData's SRTM, the USGS service having nothing north of the border. None has a
        # station yet: British Columbia's and Alberta's snow stations need a reader of their own.
        # The Okanagan (looked up 2026-11-24). Each point is the midpoint of a main lift in OpenStreetMap: Big
        # White's Bullet Express, SilverStar's Comet Express, Sun Peaks' Sunburst Express and Apex's Quickdraw.
        # Summits are the top of the highest lift where the published one is a peak no lift reaches (Big White's
        # Alpine T-Bar, 34 m under the peak; Sun Peaks' West Bowl Express, below Mt. Tod). SilverStar's base is its
        # summit less its stated vertical, where the Putnam chair starts; Apex's is the foot of its lowest chair,
        # 30 m above the published figure. Nobody shares weather: the nearest two are 71 km apart. Sun Peaks is
        # also on the Mountain Collective, and is counted as Ikon.
        Resort("bigwhite", "Big White", 49.73055, -118.92684, 1508, 2285, None, "Indy", region="okanagan"),
        Resort("silverstar", "SilverStar", 50.36381, -119.05471, 1155, 1915, "2F10P:BCASWS", "Ikon",
               region="okanagan"),                                       # the station is 1 km off, near the top
        Resort("sunpeaks", "Sun Peaks", 50.89223, -119.8983, 1198, 2093, None, "Ikon", region="okanagan"),
        Resort("apex", "Apex", 49.38404, -119.90579, 1607, 2178, None, "Indy", region="okanagan"),
        # The BC Coast (looked up 2026-11-24). Each resort's point is the midpoint of a main lift in OpenStreetMap:
        # Whistler's Village Gondola, which serves for Blackcomb too (their gondolas are 2.6 km apart across
        # Fitzsimmons Creek), Cypress's Lions Express, Grouse's Screaming Eagle, Seymour's Mystery Peak Express and
        # Mt. Washington's Eagle Express. Whistler's base is Creekside and its top Blackcomb's 7th Heaven; its
        # figures and Cypress's are Wikipedia's, Vail's own site being behind a waiting room. Grouse publishes no
        # ski base, so its base is the foot of its lowest chair. Grouse is only a two-day bonus on the Ikon pass, so
        # it is Independent. Cypress and Seymour take Grouse's weather: 9 and 10 km along the one North Shore
        # front, with valleys and no crest between.
        Resort("whistler", "Whistler Blackcomb", 50.09129, -122.95018, 653, 2240, None, "Epic", region="bccoast"),
        Resort("cypress", "Cypress", 49.40067, -123.19927, 826, 1440, "3A30P:BCASWS", "Ikon",
               region="bccoast", weather_from="grouse"),                 # 9.1 km from Grouse
        Resort("grouse", "Grouse", 49.37568, -123.07964, 865, 1231, "3A09P:BCASWS", "Independent",
               region="bccoast"),                                        # Palisade Lake, 9.4 km north
        Resort("seymour", "Mt. Seymour", 49.37252, -122.94576, 935, 1265, None, "Independent",
               region="bccoast", weather_from="grouse"),                 # 9.7 km from Grouse
        Resort("mtwashington", "Mt. Washington", 49.74717, -125.30003, 1083, 1588, None, "Indy", region="bccoast"),
        # Backcountry. The Spearhead is Decker Mountain from the top of Blackcomb's lifts, its point on the Decker
        # Glacier and its base Decker Lake, the tour's low point; it is 7.7 km from Whistler's point but over the
        # Spearhead crest and 950 m higher, so it asks for its own weather. The Duffey is Mount Chief Pascall from
        # the pull-out east of Cayoosh Pass. Paul Ridge is Round Mountain from the Diamond Head lot, its point at
        # the Red Heather shelter.
        Resort("spearhead", "Spearhead", 50.07236, -122.84629, 1988, 2421, None, "Backcountry",
               region="bccoast", kind="backcountry"),
        Resort("duffey", "Duffey Lake", 50.36998, -122.46033, 1261, 2204, None, "Backcountry",
               region="bccoast", kind="backcountry"),
        Resort("paulridge", "Paul Ridge", 49.76275, -123.03811, 975, 1646, None, "Backcountry",
               region="bccoast", kind="backcountry"),
        # Quebec (looked up 2026-11-24): the Laurentians, the Eastern Townships, and Québec City and Charlevoix.
        # Each point is the midpoint of a main lift in OpenStreetMap. Only Bromont's and Mont Orford's own pages
        # gave heights; the rest are Wikipedia's or the Indy Pass's, each checked against the lifts' ends. Mont
        # Orford's base and Owl's Head's base and top are read at the ends of their lifts, the published figures
        # sitting 50 m under and 20 m under and 48 m over them. Le Massif is on the Ikon pass and the Mountain
        # Collective, and is counted as Ikon. Mont Blanc takes Tremblant's weather, 14 km across the one plateau;
        # everything else is 21 km apart or more. Nothing here reports snow water: three climate stations report
        # depth alone, so no mountain has a station.
        Resort("tremblant", "Tremblant", 46.21673, -74.56864, 230, 875, None, "Ikon", region="quebec"),
        Resort("montblanc", "Mont Blanc", 46.10553, -74.48358, 346, 556, None, "Indy",
               region="quebec", weather_from="tremblant"),               # 14 km from Tremblant
        Resort("saintsauveur", "Mont Saint-Sauveur", 45.88143, -74.14762, 203, 416, None, "Independent",
               region="quebec"),
        Resort("bromont", "Bromont", 45.29512, -72.63725, 192, 550, None, "Mountain Collective", region="quebec"),
        Resort("sutton", "Mont Sutton", 45.09892, -72.56068, 400, 860, None, "Indy", region="quebec"),
        Resort("orford", "Mont Orford", 45.3154, -72.23078, 315, 850, None, "Independent", region="quebec"),
        Resort("owlshead", "Owl's Head", 45.06831, -72.29791, 238, 708, None, "Indy", region="quebec"),
        Resort("stoneham", "Stoneham", 47.02946, -71.39479, 248, 593, None, "Independent", region="quebec"),
        Resort("montsainteanne", "Mont-Sainte-Anne", 47.08071, -70.92012, 175, 800, None, "Independent",
               region="quebec"),
        Resort("lemassif", "Le Massif", 47.28086, -70.5914, 36, 806, None, "Ikon", region="quebec"),
        # Interior British Columbia's Powder Highway (looked up 2026-11-24), as two regions, because its east keeps
        # Alberta's clock and its west the coast's: the Powder Highway proper (Revelstoke, Rogers Pass, RED,
        # Whitewater, Kootenay Pass) and the East Kootenays (Kicking Horse, Panorama, Kimberley, Fernie). Each
        # resort's point is the midpoint of a main lift in OpenStreetMap, its height checked against SRTM and
        # Canada's own elevation model. A base or top is read at a lift's end where the published figure is not
        # where the lifts are: Kicking Horse's base (its three base lifts start 80 m above the published 1,190 m)
        # and top (the Stairway to Heaven chair's, not the ridge above), Panorama's top (the Summit Quad's),
        # Kimberley's top (the Easter chair's, 80 m under the published one), RED's top (the Grey Mountain chair's)
        # and Whitewater's base (the Glory Ridge chair's, 240 m under the lodge) and top (the Raven chair's).
        # Nobody shares weather: the nearest two are 35 km apart. Revelstoke and Panorama are also on the Mountain
        # Collective and are counted as Ikon; Kicking Horse, Fernie and Kimberley give Epic holders seven days
        # between them and are counted as Epic.
        Resort("revelstoke", "Revelstoke", 50.95989, -118.14335, 512, 2225, "2A06P:BCASWS", "Ikon",
               region="powderhighway"),                                  # Mount Revelstoke, 8.5 km north
        Resort("redmountain", "RED Mountain", 49.10237, -117.84281, 1185, 2037, None, "Ikon",
               region="powderhighway"),
        Resort("whitewater", "Whitewater", 49.43994, -117.15131, 1389, 2063, None, "Independent",
               region="powderhighway"),
        # Rogers Pass is Ursus Minor up Connaught Creek from the Discovery Centre; Kootenay Pass is Cornice Ridge
        # from the lot at Bridal Lake, its point on the ridge's ski trail.
        Resort("rogerspass", "Rogers Pass", 51.30095, -117.56427, 1318, 2738, "2A34P:BCASWS", "Backcountry",
               region="powderhighway", kind="backcountry", weak_match=True),   # the station is in the valley
        Resort("kootenaypass", "Kootenay Pass", 49.06455, -117.0482, 1775, 2111, None, "Backcountry",
               region="powderhighway", kind="backcountry"),
        Resort("kickinghorse", "Kicking Horse", 51.28638, -117.06322, 1266, 2415, None, "Epic",
               region="eastkootenays"),
        Resort("panorama", "Panorama", 50.45075, -116.23403, 1150, 2365, None, "Ikon", region="eastkootenays"),
        Resort("kimberley", "Kimberley", 49.68391, -116.01971, 1230, 1905, None, "Epic", region="eastkootenays"),
        Resort("fernie", "Fernie", 49.45083, -115.09335, 1052, 2134, "2C09Q:BCASWS", "Epic",
               region="eastkootenays"),                                  # Morrissey Ridge, 8.6 km east
        # The Canadian Rockies in Alberta (looked up 2026-11-24): Banff's three hills, Nakiska in Kananaskis, Marmot
        # Basin at Jasper, and two tours off the Icefields Parkway. Each resort's point is the midpoint of a main
        # lift in OpenStreetMap; Sunshine's is the Super Angel chair's, up in the village where the skiing is, not
        # the gondola's in the valley below it. Bases and tops are the published ones, but Norquay's are the pair
        # that agree with its own vertical (1,630 and 2,133 m) and Marmot's top is the Knob chair's, not the peak
        # above it that is reached on foot. Nobody shares weather: Sunshine and Norquay, the nearest two, are 19 km
        # apart across the Bow Valley. Castle Mountain is left out: it is 190 km south of Nakiska and would double
        # the map. Banff's three are on Ikon; Nakiska gives Epic holders days, like the East Kootenays' three;
        # Marmot is on the Mountain Collective alone.
        Resort("lakelouise", "Lake Louise", 51.44796, -116.14336, 1646, 2637, None, "Ikon", region="rockies"),
        Resort("sunshine", "Sunshine Village", 51.07645, -115.77166, 1658, 2730, "05BB803:ABRIVERS", "Ikon",
               region="rockies"),
        Resort("norquay", "Norquay", 51.20909, -115.60912, 1630, 2133, None, "Ikon", region="rockies"),
        Resort("nakiska", "Nakiska", 50.9484, -115.16551, 1525, 2260, None, "Epic", region="rockies"),
        Resort("marmot", "Marmot Basin", 52.7997, -118.09919, 1698, 2498, None, "Independent", region="rockies"),
        # Bow Summit is the slopes west of the highway, from the Peyto Lake lot up the old fire road to the
        # lookout; Parker Ridge is the ridge above its trailhead on the Parkway.
        Resort("bowsummit", "Bow Summit", 51.71076, -116.50407, 2088, 2362, "2A32P:BCASWS", "Backcountry",
               region="rockies", kind="backcountry"),
        Resort("parkerridge", "Parker Ridge", 52.186, -117.10894, 2020, 2350, None, "Backcountry",
               region="rockies", kind="backcountry"),
        # ---- The third collector's regions (see COLLECTOR): the USA's regions added once the first
        # collector's plan was
        # full. Each point is the midpoint of the mountain's main lift in OpenStreetMap (a point on the skied slope
        # for a backcountry spot), checked against the USGS elevation service; bases and summits are the resorts'
        # published figures, or the USGS height at the lift's end where the two disagree; passes are for 2026-27 from
        # search results of the passes' lists, which could not be opened directly (looked up 2026-11-26).
        # Southwest Montana: Big Sky and the Gallatin, Bridger, Little Belt and Beartooth ranges.
        Resort("bigsky", "Big Sky", 45.27922, -111.41698, _ft(6800), _ft(11166), "590:MT:SNTL", "Ikon",
               region="montana"),
        Resort("bridger", "Bridger Bowl", 45.81606, -110.91982, _ft(6100), _ft(8700), "929:MT:SNTL", "Independent",
               region="montana"),
        Resort("showdown", "Showdown", 46.83705, -110.70830, _ft(6800), _ft(8200), "781:MT:SNTL", "Indy",
               region="montana"),
        Resort("blackmore", "Mt. Blackmore", 45.44675, -110.98957, _ft(6725), _ft(10156), "754:MT:SNTL", "Backcountry",
               region="montana", kind="backcountry"),
        Resort("beehive", "Beehive Basin", 45.34399, -111.39733, _ft(7926), _ft(10742), "590:MT:SNTL", "Backcountry",
               region="montana", kind="backcountry", weather_from="bigsky"),
        Resort("lulupass", "Lulu Pass", 45.06200, -109.95000, _ft(7590), _ft(10308), "480:MT:SNTL", "Backcountry",
               region="montana", kind="backcountry"),
        # Sun Valley, the Soldier Mountains and the Sawtooths.
        Resort("sunvalley", "Sun Valley", 43.67186, -114.40345, _ft(5750), _ft(9150), None, "Ikon",
               region="sunvalley"),
        Resort("dollar", "Dollar Mountain", 43.68628, -114.34653, _ft(5943), _ft(6582), None, "Ikon",
               region="sunvalley", weather_from="sunvalley"),
        Resort("soldier", "Soldier Mountain", 43.48434, -114.83576, _ft(5798), _ft(7177), "769:ID:SNTL", "Indy",
               region="sunvalley"),
        Resort("galena", "Galena Summit", 43.85200, -114.71200, _ft(8706), _ft(10112), "490:ID:SNTL", "Backcountry",
               region="sunvalley", kind="backcountry"),
        Resort("banner", "Banner Summit", 44.32750, -115.20610, _ft(7050), _ft(8976), "312:ID:SNTL", "Backcountry",
               region="sunvalley", kind="backcountry"),
        Resort("williams", "Williams Peak", 44.15290, -114.98760, _ft(6400), _ft(10635), None, "Backcountry",
               region="sunvalley", kind="backcountry"),
        # Oregon's Cascades, Mt. Hood to Willamette Pass.
        Resort("hoodmeadows", "Mt. Hood Meadows", 45.33849, -121.66854, _ft(4523), _ft(7300), "651:OR:SNTL", "Indy",
               region="oregon"),
        Resort("timberline", "Timberline", 45.32425, -121.71875, _ft(4850), _ft(7000), "651:OR:SNTL", "Independent",
               region="oregon"),
        Resort("skibowl", "Mt. Hood Skibowl", 45.29648, -121.77463, _ft(3600), _ft(5027), "655:OR:SNTL", "Independent",
               region="oregon"),
        Resort("cooperspur", "Cooper Spur", 45.41067, -121.60668, _ft(3931), _ft(4265), "712:OR:SNTL", "Indy",
               region="oregon"),
        Resort("hoodoo", "Hoodoo", 44.40548, -121.87731, _ft(4668), _ft(5703), "526:OR:SNTL", "Indy",
               region="oregon"),
        Resort("bachelor", "Mt. Bachelor", 43.99621, -121.68242, _ft(5700), _ft(9065), None, "Ikon",
               region="oregon"),
        Resort("willamettepass", "Willamette Pass", 43.60369, -122.02757, _ft(5120), _ft(6683), "388:OR:SNTL",
               "Independent",
               region="oregon"),
        Resort("hoodsouth", "Mt. Hood", 45.36000, -121.70450, _ft(5884), _ft(11243), "651:OR:SNTL", "Backcountry",
               region="oregon", kind="backcountry", weak_match=True, corrected=False),
        Resort("tillyjane", "Tilly Jane", 45.39150, -121.65500, _ft(3899), _ft(8489), "651:OR:SNTL", "Backcountry",
               region="oregon", kind="backcountry"),
        Resort("tumalo", "Tumalo Mountain", 44.00350, -121.64800, _ft(6349), _ft(7779), None, "Backcountry",
               region="oregon", kind="backcountry", weather_from="bachelor"),
        Resort("southsister", "South Sister", 44.08500, -121.76700, _ft(5453), _ft(10354), None, "Backcountry",
               region="oregon", kind="backcountry"),
        # Northern New Mexico: the Sangre de Cristo and Jemez mountains.
        Resort("taos", "Taos Ski Valley", 36.58925, -105.45102, _ft(9350), _ft(12481), "1168:NM:SNTL", "Ikon",
               region="newmexico"),
        Resort("redriver", "Red River", 36.70140, -105.40923, _ft(8645), _ft(10275), "715:NM:SNTL", "Independent",
               region="newmexico"),
        Resort("angelfire", "Angel Fire", 36.38130, -105.25470, _ft(8554), _ft(10677), "1170:NM:SNTL", "Independent",
               region="newmexico"),
        Resort("sipapu", "Sipapu", 36.15059, -105.55122, _ft(8200), _ft(9255), "1083:NM:SNTL", "Independent",
               region="newmexico"),
        Resort("skisantafe", "Ski Santa Fe", 35.79074, -105.79884, _ft(10350), _ft(12075), "922:NM:SNTL", "Independent",
               region="newmexico"),
        Resort("pajarito", "Pajarito", 35.89118, -106.39400, _ft(9000), _ft(10440), "708:NM:SNTL", "Independent",
               region="newmexico"),
        Resort("wheelerpeak", "Wheeler Peak", 36.55700, -105.42350, _ft(10217), _ft(13159), "1168:NM:SNTL",
               "Backcountry",
               region="newmexico", kind="backcountry", weather_from="taos"),
        Resort("goldhill", "Gold Hill", 36.62250, -105.44900, _ft(9468), _ft(12703), "1168:NM:SNTL", "Backcountry",
               region="newmexico", kind="backcountry", weather_from="taos"),
        Resort("lakepeak", "Lake Peak", 35.79850, -105.77450, _ft(10271), _ft(12372), "922:NM:SNTL", "Backcountry",
               region="newmexico", kind="backcountry"),
        # Southcentral Alaska: Girdwood, Turnagain Pass, Summit Lake, Anchorage and Hatcher Pass.
        Resort("alyeska", "Alyeska", 60.96596, -149.08792, _ft(250), _ft(2750), "1103:AK:SNTL", "Ikon",
               region="alaska"),
        Resort("arcticvalley", "Arctic Valley", 61.24805, -149.51985, _ft(2500), _ft(3900), None, "Indy",
               region="alaska"),
        Resort("skeetawk", "Skeetawk", 61.74265, -149.23781, _ft(1450), _ft(1750), "641:AK:SNTL", "Indy",
               region="alaska"),
        Resort("tincan", "Tincan", 60.78805, -149.16976, _ft(1043), _ft(3810), "954:AK:SNTL", "Backcountry",
               region="alaska", kind="backcountry"),
        Resort("sunburst", "Sunburst", 60.75880, -149.19400, _ft(810), _ft(3780), "954:AK:SNTL", "Backcountry",
               region="alaska", kind="backcountry", weather_from="tincan"),
        Resort("manitoba", "Manitoba Mountain", 60.68400, -149.43300, _ft(1285), _ft(3668), "955:AK:SNTL",
               "Backcountry",
               region="alaska", kind="backcountry", weak_match=True),
        Resort("hatcherpass", "Hatcher Pass", 61.77312, -149.25781, _ft(2700), _ft(4694), "1091:AK:SNTL", "Backcountry",
               region="alaska", kind="backcountry"),
        # Southwest Colorado: the Elk Mountains, the Sawatch at Monarch and the San Juans.
        Resort("aspen", "Aspen Mountain", 39.16887, -106.81882, _ft(7945), _ft(11212), None, "Ikon",
               region="swcolorado"),
        Resort("highlands", "Aspen Highlands", 39.16983, -106.86064, _ft(8040), _ft(11574), None, "Ikon",
               region="swcolorado", weather_from="aspen"),
        Resort("buttermilk", "Buttermilk", 39.19401, -106.86787, _ft(7870), _ft(9900), None, "Ikon",
               region="swcolorado", weather_from="aspen"),
        Resort("snowmass", "Snowmass", 39.19799, -106.96113, _ft(8104), _ft(12510), None, "Ikon",
               region="swcolorado"),
        Resort("crestedbutte", "Crested Butte", 38.89317, -106.95461, _ft(9375), _ft(11879), "380:CO:SNTL", "Epic",
               region="swcolorado"),
        Resort("monarch", "Monarch", 38.50790, -106.33519, _ft(10790), _ft(11804), "701:CO:SNTL", "Independent",
               region="swcolorado"),
        Resort("telluride", "Telluride", 37.93005, -107.83809, _ft(8725), _ft(12515), "1344:CO:SNTL", "Epic",
               region="swcolorado"),
        Resort("silverton", "Silverton", 37.88062, -107.65989, _ft(10400), _ft(12072), "713:CO:SNTL", "Independent",
               region="swcolorado"),
        Resort("purgatory", "Purgatory", 37.62329, -107.82267, _ft(8793), _ft(10822), "387:CO:SNTL", "Independent",
               region="swcolorado"),
        Resort("wolfcreek", "Wolf Creek", 37.46726, -106.79799, _ft(10300), _ft(11763), "874:CO:SNTL", "Independent",
               region="swcolorado"),
        Resort("redmountainpass", "Red Mountain Pass", 37.90050, -107.69800, _ft(11018), _ft(12890), "713:CO:SNTL",
               "Backcountry",
               region="swcolorado", kind="backcountry"),
        Resort("coalbankpass", "Coal Bank Pass", 37.69950, -107.79500, _ft(10640), _ft(12968), "780:CO:SNTL",
               "Backcountry",
               region="swcolorado", kind="backcountry", weak_match=True),
        Resort("marble", "Marble", 39.04500, -107.18900, _ft(7984), _ft(11314), "669:CO:SNTL", "Backcountry",
               region="swcolorado", kind="backcountry"),
        # Western Idaho: Bogus Basin above Boise, Brundage and Tamarack by McCall, and Anthony Lakes across
        # the Snake in Oregon's Elkhorns.
        Resort("bogusbasin", "Bogus Basin", 43.75920, -116.09950, _ft(5800), _ft(7582), "978:ID:SNTL", "Independent",
               region="westidaho"),
        Resort("brundage", "Brundage", 45.00530, -116.14500, _ft(5882), _ft(7604), "370:ID:SNTL", "Indy",
               region="westidaho"),
        Resort("tamarack", "Tamarack", 44.67780, -116.13590, _ft(4900), _ft(7700), None, "Indy",
               region="westidaho"),
        Resort("anthonylakes", "Anthony Lakes", 44.96120, -118.23970, _ft(7100), _ft(8000), None, "Independent",
               region="westidaho"),
        Resort("jughandle", "Jughandle Mountain", 44.84800, -115.96000, _ft(6220), _ft(8309), None, "Backcountry",
               region="westidaho", kind="backcountry"),
        Resort("granitemountain", "Granite Mountain", 45.09850, -116.19500, _ft(6449), _ft(8474), "370:ID:SNTL",
               "Backcountry",
               region="westidaho", kind="backcountry", weak_match=True),
        # Wyoming outside Jackson: the Snowy Range, Casper Mountain, the Bighorns, Cody's Sleeping Giant,
        # Pinedale's White Pine and Cokeville's Pine Creek. Sleeping Giant may not run its lifts this winter;
        # it is kept until that is known.
        Resort("snowyrange", "Snowy Range", 41.33800, -106.18550, _ft(8798), _ft(9663), "367:WY:SNTL", "Independent",
               region="wyoming"),
        Resort("sleepinggiant", "Sleeping Giant", 44.49080, -109.94650, _ft(6619), _ft(7428), "807:WY:SNTL",
               "Independent",
               region="wyoming"),
        Resort("whitepine", "White Pine", 42.97260, -109.75310, _ft(8400), _ft(9334), "468:WY:SNTL", "Indy",
               region="wyoming"),
        Resort("hogadon", "Hogadon", 42.74740, -106.34110, _ft(7400), _ft(8000), "389:WY:SNTL", "Independent",
               region="wyoming"),
        Resort("meadowlark", "Meadowlark", 44.16160, -107.22000, _ft(8500), _ft(9267), "703:WY:SNTL", "Indy",
               region="wyoming"),
        Resort("antelopebutte", "Antelope Butte", 44.60660, -107.51430, _ft(8400), _ft(9400), "358:WY:SNTL", "Indy",
               region="wyoming"),
        Resort("pinecreek", "Pine Creek", 42.09880, -110.82340, _ft(6801), _ft(8225), None, "Independent",
               region="wyoming"),
        # Southern Utah: Brian Head, and Eagle Point and Delano Peak in the Tushars.
        Resort("brianhead", "Brian Head", 37.68825, -112.84146, _ft(9600), _ft(10920), "1154:UT:SNTL", "Independent",
               region="southutah"),
        Resort("eaglepoint", "Eagle Point", 38.31669, -112.38052, _ft(9330), _ft(10600), "339:UT:SNTL", "Indy",
               region="southutah"),
        Resort("delano", "Delano Peak", 38.36500, -112.38300, _ft(9940), _ft(12169), "339:UT:SNTL", "Backcountry",
               region="southutah", kind="backcountry", weather_from="eaglepoint"),
        # Arizona: Snowbowl and Humphreys Peak on the San Francisco Peaks, and Sunrise in the White Mountains,
        # 250 km south-east. Mt. Lemmon, 330 km further south and open a handful of days a winter, is left
        # out.
        Resort("azsnowbowl", "Snowbowl", 35.32828, -111.69541, _ft(9200), _ft(11500), "927:AZ:SNTL", "Independent",
               region="arizona"),
        Resort("humphreys", "Humphreys Peak", 35.33800, -111.69300, _ft(9275), _ft(12633), "927:AZ:SNTL", "Backcountry",
               region="arizona", kind="backcountry", weak_match=True, weather_from="azsnowbowl"),
        Resort("sunrisepark", "Sunrise", 33.96413, -109.56131, _ft(9360), _ft(10900), "310:AZ:SNTL", "Indy",
               region="arizona"),
        # Lee Canyon in the Spring Mountains above Las Vegas.
        Resort("leecanyon", "Lee Canyon", 36.29983, -115.68207, _ft(8660), _ft(9370), "1350:NV:SNTL", "Independent",
               region="lasvegas"),
        # Southern California: Bear Mountain, Snow Summit and Snow Valley in the San Bernardinos, and Mountain
        # High and Mt. Baldy in the San Gabriels. There are no snow sensors here, so none has a station. Mt.
        # Baldy's point is on Chair 1, the lift from the road.
        Resort("bearmountain", "Bear Mountain", 34.22016, -116.86398, _ft(7140), _ft(8805), None, "Ikon",
               region="socal"),
        Resort("snowsummit", "Snow Summit", 34.22829, -116.88971, _ft(7000), _ft(8200), None, "Ikon",
               region="socal", weather_from="bearmountain"),
        Resort("snowvalley", "Snow Valley", 34.21767, -117.03523, _ft(6800), _ft(7841), None, "Ikon",
               region="socal"),
        Resort("mountainhigh", "Mountain High", 34.37188, -117.69132, _ft(6600), _ft(8200), None, "Indy",
               region="socal"),
        Resort("mtbaldy", "Mt. Baldy", 34.27213, -117.61611, _ft(6500), _ft(8600), None, "Independent",
               region="socal"),
        # Juneau: Eaglecrest on Douglas Island and the two peaks toured from it, Mt. Troy and Mt. Ben Stewart.
        # No snow sensor is within 40 km.
        Resort("eaglecrest", "Eaglecrest", 58.26788, -134.51230, _ft(1200), _ft(2600), None, "Indy",
               region="juneau"),
        Resort("mttroy", "Mt. Troy", 58.26740, -134.48750, _ft(1195), _ft(3005), None, "Backcountry",
               region="juneau", kind="backcountry", weather_from="eaglecrest"),
        Resort("benstewart", "Mt. Ben Stewart", 58.26400, -134.53400, _ft(1195), _ft(3438), None, "Backcountry",
               region="juneau", kind="backcountry", weather_from="eaglecrest"),
        # Valdez: Thompson Pass's backcountry, the Odyssey side from the pass summit and Girls Mountain across
        # the highway. The Upper Tsaina River sensor, 6 km off and 600 m below, is shown but corrects nothing.
        Resort("thompsonpass", "Thompson Pass", 61.14000, -145.70500, _ft(2669), _ft(4565), "1055:AK:SNTL",
               "Backcountry",
               region="valdez", kind="backcountry", weak_match=True, corrected=False),
        Resort("girlsmountain", "Girls Mountain", 61.18021, -145.74712, _ft(2117), _ft(6134), "1055:AK:SNTL",
               "Backcountry",
               region="valdez", kind="backcountry", weak_match=True, corrected=False, weather_from="thompsonpass"),
        # The Inland Northwest: Schweitzer above Sandpoint, 49 Degrees North and Mt. Spokane in Washington,
        # and Silver Mountain, Lookout Pass and Stevens Peak along I-90 in the Silver Valley. Lookout Pass's
        # pass could not be confirmed and is given as Independent.
        Resort("schweitzer", "Schweitzer", 48.37459, -116.62898, _ft(4000), _ft(6400), "738:ID:SNTL", "Ikon",
               region="inlandnw"),
        Resort("lookoutpass", "Lookout Pass", 47.45523, -115.70152, _ft(4500), _ft(6150), "594:ID:SNTL", "Independent",
               region="inlandnw"),
        Resort("silvermountain", "Silver Mountain", 47.49234, -116.12317, _ft(4100), _ft(6300), None, "Indy",
               region="inlandnw"),
        Resort("fortyninenorth", "49 Degrees North", 48.29298, -117.56779, _ft(3923), _ft(5774), None, "Indy",
               region="inlandnw"),
        Resort("mtspokane", "Mt. Spokane", 47.91948, -117.10592, _ft(3818), _ft(5889), "707:WA:SNTL", "Independent",
               region="inlandnw"),
        Resort("stevenspeak", "Stevens Peak", 47.42620, -115.76400, _ft(4725), _ft(6838), "594:ID:SNTL", "Backcountry",
               region="inlandnw", kind="backcountry", weather_from="lookoutpass"),
        # Northwest Montana: Whitefish and Blacktail by Flathead Lake, Jewel Basin in the Swan Range, Snowbowl
        # above Missoula, Discovery by Anaconda, and Lost Trail and Gash Point in the Bitterroot. Discovery's
        # pass could not be confirmed and is given as Independent.
        Resort("whitefish", "Whitefish", 48.49326, -114.34774, _ft(4464), _ft(6817), None, "Independent",
               region="nwmontana"),
        Resort("blacktail", "Blacktail", 48.02026, -114.36619, _ft(5236), _ft(6780), "1144:MT:SNTL", "Indy",
               region="nwmontana"),
        Resort("montanasnowbowl", "Snowbowl", 47.02142, -114.00132, _ft(5000), _ft(7600), "901:MT:SNTL", "Indy",
               region="nwmontana"),
        Resort("discovery", "Discovery", 46.25631, -113.24395, _ft(5770), _ft(8158), "850:MT:SNTL", "Independent",
               region="nwmontana"),
        Resort("losttrail", "Lost Trail", 45.69076, -113.95704, _ft(6400), _ft(8200), "727:MT:SNTL", "Indy",
               region="nwmontana"),
        Resort("jewelbasin", "Jewel Basin", 48.15150, -113.93000, _ft(5742), _ft(7528), "664:MT:SNTL", "Backcountry",
               region="nwmontana", kind="backcountry"),
        Resort("gashpoint", "Gash Point", 46.42450, -114.29800, _ft(5781), _ft(8886), None, "Backcountry",
               region="nwmontana", kind="backcountry"),
        # New York: Whiteface and Gore in the Adirondacks, West Mountain by Glens Falls, Hunter, Windham,
        # Belleayre and Plattekill in the Catskills, and Holiday Valley and Bristol in the west. There are no
        # snow sensors in the East, so none has a station.
        Resort("whiteface", "Whiteface", 44.35469, -73.87658, _ft(1220), _ft(4386), None, "Mountain Collective",
               region="newyork"),
        Resort("gore", "Gore", 43.67528, -74.02094, _ft(998), _ft(3600), None, "Independent",
               region="newyork"),
        Resort("hunter", "Hunter", 42.20275, -74.22128, _ft(1600), _ft(3200), None, "Epic",
               region="newyork"),
        Resort("windham", "Windham", 42.29140, -74.26107, _ft(1707), _ft(3053), None, "Independent",
               region="newyork"),
        Resort("belleayre", "Belleayre", 42.13443, -74.50963, _ft(2025), _ft(3429), None, "Independent",
               region="newyork"),
        Resort("plattekill", "Plattekill", 42.28762, -74.65824, _ft(2340), _ft(3314), None, "Independent",
               region="newyork"),
        Resort("westmountain", "West Mountain", 43.28534, -73.73291, _ft(460), _ft(1470), None, "Indy",
               region="newyork"),
        Resort("holidayvalley", "Holiday Valley", 42.25957, -78.67618, _ft(1500), _ft(2250), None, "Independent",
               region="newyork"),
        Resort("bristol", "Bristol", 42.74416, -77.41239, _ft(1000), _ft(2200), None, "Independent",
               region="newyork"),
        # The Mid-Atlantic: Snowshoe, Timberline and Canaan Valley in West Virginia, Wisp in Maryland, Seven
        # Springs, Blue Mountain, Camelback and Elk Mountain in Pennsylvania, and Wintergreen and Massanutten
        # in Virginia.
        Resort("snowshoe", "Snowshoe", 38.41300, -79.98915, _ft(3261), _ft(4786), None, "Ikon",
               region="midatlantic"),
        Resort("timberlinewv", "Timberline WV", 39.03737, -79.39780, _ft(3268), _ft(4268), None, "Independent",
               region="midatlantic"),
        Resort("canaanvalley", "Canaan Valley", 39.00339, -79.43592, _ft(3430), _ft(4280), None, "Indy",
               region="midatlantic", weather_from="timberlinewv"),
        Resort("wisp", "Wisp", 39.55321, -79.36699, _ft(2415), _ft(3115), None, "Indy",
               region="midatlantic"),
        Resort("sevensprings", "Seven Springs", 40.02268, -79.30286, _ft(2240), _ft(2994), None, "Epic",
               region="midatlantic"),
        Resort("bluemountainpa", "Blue Mountain", 40.81537, -75.51204, _ft(460), _ft(1540), None, "Ikon",
               region="midatlantic"),
        Resort("camelback", "Camelback", 41.04750, -75.34796, _ft(1250), _ft(2047), None, "Ikon",
               region="midatlantic"),
        Resort("elkmountain", "Elk Mountain", 41.72038, -75.55945, _ft(1690), _ft(2690), None, "Independent",
               region="midatlantic"),
        Resort("wintergreen", "Wintergreen", 37.92220, -78.94044, _ft(2512), _ft(3515), None, "Indy",
               region="midatlantic"),
        Resort("massanutten", "Massanutten", 38.39554, -78.76542, _ft(1750), _ft(2833), None, "Indy",
               region="midatlantic"),
        # Lake Superior's shores and the north woods: Lutsen and Spirit Mountain in Minnesota, Whitecap and
        # Granite Peak in Wisconsin, and Snowriver, Big Powderhorn and Mount Bohemia in Michigan's Upper
        # Peninsula. Mount Bohemia keeps Eastern time, an hour ahead of the rest.
        Resort("lutsen", "Lutsen", 47.65089, -90.72637, _ft(906), _ft(1688), None, "Ikon",
               region="lakesuperior"),
        Resort("spiritmtn", "Spirit Mountain", 46.71615, -92.21343, _ft(720), _ft(1298), None, "Indy",
               region="lakesuperior"),
        Resort("bohemia", "Mount Bohemia", 47.38934, -88.01689, _ft(651), _ft(1458), None, "Independent",
               region="lakesuperior"),
        Resort("snowriver", "Snowriver", 46.50453, -89.97089, _ft(1212), _ft(1750), None, "Ikon",
               region="lakesuperior"),
        Resort("bigpowderhorn", "Big Powderhorn", 46.50609, -90.09516, _ft(1218), _ft(1637), None, "Indy",
               region="lakesuperior"),
        Resort("granitepeak", "Granite Peak", 44.92535, -89.68637, _ft(1242), _ft(1883), None, "Ikon",
               region="lakesuperior"),
        Resort("whitecap", "Whitecap", 46.40790, -90.39872, _ft(1449), _ft(1750), None, "Indy",
               region="lakesuperior"),
        # Northern lower Michigan: Boyne Mountain, The Highlands, Nub's Nob, Schuss Mountain, Crystal Mountain
        # and Caberfae.
        Resort("boynemountain", "Boyne Mountain", 45.16280, -84.93583, _ft(715), _ft(1155), None, "Ikon",
               region="michigan"),
        Resort("boynehighlands", "The Highlands", 45.46946, -84.94146, _ft(773), _ft(1325), None, "Ikon",
               region="michigan"),
        Resort("nubsnob", "Nub's Nob", 45.46928, -84.90273, _ft(911), _ft(1338), None, "Indy",
               region="michigan", weather_from="boynehighlands"),
        Resort("crystalmi", "Crystal Mountain", 44.52182, -85.99549, _ft(794), _ft(1132), None, "Indy",
               region="michigan"),
        Resort("caberfae", "Caberfae", 44.24132, -85.71846, _ft(1172), _ft(1545), None, "Independent",
               region="michigan"),
        Resort("schuss", "Schuss Mountain", 44.94219, -85.13559, _ft(829), _ft(1173), None, "Indy",
               region="michigan"),
        # Terry Peak in South Dakota's Black Hills. South Dakota's two SNOTEL stations are both further than
        # 10 km off, so it has no station.
        Resort("terrypeak", "Terry Peak", 44.33293, -103.82963, _ft(5900), _ft(6990), None, "Indy",
               region="blackhills"),
        # Northern British Columbia: Shames by Terrace, Hudson Bay Mountain and the Hankin-Evelyn backcountry
        # by Smithers, and Powder King at Pine Pass, 300 km east. No snow station is paired yet: the
        # province's station list could not be read the day these were added.
        Resort("shames", "Shames", 54.48982, -128.96089, 700, 1189, None, "Indy",
               region="northbc"),
        Resort("hudsonbay", "Hudson Bay Mountain", 54.77452, -127.24716, 1142, 1650, None, "Indy",
               region="northbc"),
        Resort("powderking", "Powder King", 55.36421, -122.62165, 935, 1525, None, "Independent",
               region="northbc"),
        Resort("hankinevelyn", "Hankin-Evelyn", 54.88032, -127.51847, 900, 1546, None, "Backcountry",
               region="northbc", kind="backcountry"),
        # Ontario: Blue Mountain at Collingwood, Mount St. Louis Moonstone and Horseshoe north of Barrie, and
        # Calabogie Peaks in the Ottawa Valley.
        Resort("bluemountain", "Blue Mountain", 44.49968, -80.31718, 230, 450, None, "Ikon",
               region="ontario"),
        Resort("mountstlouis", "Mount St. Louis", 44.62498, -79.67057, 217, 354, None, "Independent",
               region="ontario"),
        Resort("horseshoe", "Horseshoe", 44.54735, -79.67544, 269, 392, None, "Independent",
               region="ontario"),
        Resort("calabogie", "Calabogie Peaks", 45.26910, -76.78417, 154, 366, None, "Indy",
               region="ontario"),
        # The Gaspé: the Chic-Chocs' backcountry (Mont Albert, Mont Hog's Back and the Champs-de-Mars), Mont
        # Miller at Murdochville, Val-d'Irène, Pin Rouge on the Baie des Chaleurs, and Mont-Comi by Rimouski.
        Resort("montalbert", "Mont Albert", 48.91592, -66.15176, 221, 1070, None, "Backcountry",
               region="gaspesie", kind="backcountry"),
        Resort("hogsback", "Mont Hog's Back", 48.86130, -66.10852, 387, 830, None, "Backcountry",
               region="gaspesie", kind="backcountry"),
        Resort("champsdemars", "Champs-de-Mars", 48.87577, -66.08146, 324, 700, None, "Backcountry",
               region="gaspesie", kind="backcountry", weather_from="hogsback"),
        Resort("montmiller", "Mont Miller", 48.96333, -65.48581, 548, 836, None, "Independent",
               region="gaspesie"),
        Resort("valdirene", "Val-d'Irène", 48.47553, -67.57721, 444, 684, None, "Indy",
               region="gaspesie"),
        Resort("montcomi", "Mont-Comi", 48.46744, -68.20176, 283, 570, None, "Independent",
               region="gaspesie"),
        Resort("pinrouge", "Pin Rouge", 48.31907, -65.71973, 50, 500, None, "Independent",
               region="gaspesie"),
        # Newfoundland: Marble Mountain by Corner Brook and White Hills by Clarenville, 290 km apart. Marble
        # Mountain's summit is the top of its lift, 470 m; the 546 m it publishes is the top of Mount Musgrave
        # above.
        Resort("marblemountain", "Marble Mountain", 48.94058, -57.83263, 10, 470, None, "Indy",
               region="newfoundland"),
        Resort("whitehills", "White Hills", 48.16187, -54.05107, 200, 357, None, "Independent",
               region="newfoundland"),
        # The Yukon: Mount Sima at Whitehorse and Log Cabin in the White Pass, on the Klondike Highway.
        Resort("mountsima", "Mount Sima", 60.60817, -135.05439, 853, 1180, None, "Independent",
               region="yukon"),
        Resort("logcabin", "Log Cabin", 59.75100, -134.98900, 889, 1700, None, "Backcountry",
               region="yukon", kind="backcountry"),
        # ---- Mountains added to earlier regions on 2026-11-26, looked up the same way as the later regions'.
        # Colorado's: Eldora and Ski Cooper in the Colorado region and Sunlight and Powderhorn in Southwest
        # Colorado. Ski Cooper takes the Fremont Pass sensor, 9 km off and at its height; the Lake Eldora
        # sensor beside Eldora and Mesa Lakes above Powderhorn are not among the stations those regions'
        # corrections were fitted to, so those mountains have none until the fits are run again.
        Resort("eldora", "Eldora", 39.93713, -105.59074, _ft(9200), _ft(10600), None, "Ikon",
               region="colorado"),
        Resort("skicooper", "Ski Cooper", 39.35553, -106.29276, _ft(10500), _ft(11700), "485:CO:SNTL", "Independent",
               region="colorado"),
        Resort("sunlight", "Sunlight", 39.38901, -107.33941, _ft(8141), _ft(9895), None, "Indy",
               region="swcolorado"),
        Resort("powderhorn", "Powderhorn", 39.06235, -108.14439, _ft(8200), _ft(9850), None, "Indy",
               region="swcolorado"),
        # The Sierra's west slope and its passes, in the Eastern Sierra's region (Sean, 2026-11-26): Bear
        # Valley, Dodge Ridge, China Peak and Badger Pass, and Sonora and Ebbetts passes. None is paired with
        # a sensor: the region's correction is fitted to the crest's pillows around Mammoth, 30 km and more
        # from each, and adding stations would change Mammoth's numbers.
        Resort("bearvalley", "Bear Valley", 38.48990, -120.04908, _ft(6600), _ft(8500), None, "Indy",
               region="mammoth"),
        Resort("dodgeridge", "Dodge Ridge", 38.18543, -119.95259, _ft(6600), _ft(8200), None, "Indy",
               region="mammoth"),
        Resort("chinapeak", "China Peak", 37.22813, -119.15464, _ft(7030), _ft(8709), None, "Indy",
               region="mammoth"),
        Resort("badgerpass", "Badger Pass", 37.65761, -119.66163, _ft(7200), _ft(7800), None, "Independent",
               region="mammoth"),
        Resort("sonorapass", "Sonora Pass", 38.31200, -119.64000, _ft(9624), _ft(11572), None, "Backcountry",
               region="mammoth", kind="backcountry"),
        Resort("ebbettspass", "Ebbetts Pass", 38.52700, -119.79200, _ft(8727), _ft(9964), None, "Backcountry",
               region="mammoth", kind="backcountry"),
        # Canada's: Manning Park and Sasquatch on the BC Coast, and Castle Mountain, in Alberta, with the East
        # Kootenays.
        Resort("manning", "Manning Park", 49.07374, -120.91377, 1357, 1789, None, "Indy",
               region="bccoast"),
        Resort("sasquatch", "Sasquatch", 49.38589, -121.93475, 980, 1317, None, "Indy",
               region="bccoast"),
        Resort("castlemountain", "Castle Mountain", 49.31749, -114.42278, 1425, 2295, None, "Indy",
               region="eastkootenays"),
        # Quebec's: Mont-Édouard and Le Valinouët in the Saguenay.
        Resort("montedouard", "Mont-Édouard", 48.15963, -70.28602, 182, 628, None, "Indy",
               region="quebec"),
        Resort("valinouet", "Le Valinouët", 48.65017, -70.88923, 440, 789, None, "Independent",
               region="quebec"),
    ]
}

ALL_REGIONS = {
    r.key: r
    for r in [
        # The three western regions are built together at 5 am, 1 pm and 9 pm Pacific: before the ski day, at midday and
        # in the evening. New England is built at 4 am and 4 pm Eastern; the afternoon one falls with the West's 1 pm.
        Region("tahoe", "Tahoe", "America/Los_Angeles", 8, 8, ("SAC",), at=(5, 13, 21)),
        Region("mammoth", "Central Sierras", "America/Los_Angeles", 8, 8, ("ESAC", "BAC"), at=(5, 13, 21)),
        # Every lift-served foot of New England is below 850 hPa (near 1,450 m): the highest summit is Killington's
        # 1,293 m and the lowest base Attitash's 183 m, which 1000 hPa (near 110 m) covers.
        Region("newengland", "New England", "America/New_York", 5, 12, ("MWAC",),
               low_levels=(1000, 975, 950, 925, 900), at=(4, 16)),
        # 850 hPa is near 1,450 m; the Cascade passes and most of their bases are below that, down to Glacier Peak's
        # trailhead at 630 m, which 950 hPa (near 540 m) covers.
        Region("seattle", "Cascades", "America/Los_Angeles", 8, 8, ("NWAC",), low_levels=(950, 925, 900), at=(5, 13, 21)),
        # Built at the West's hours on its own clock, 5 am, 1 pm and 9 pm Mountain, an hour before the West's.
        # Wyoming's SNOTEL stations keep the Pacific standard clock (see TETONS_STATIONS), so the sensor offset is
        # 8, not Mountain time's 7. The lowest ground is Snow King's base at 1,901 m, well above 850 hPa: no lower
        # levels are read.
        Region("tetons", "Tetons", "America/Denver", 8, 8, ("BTAC",), at=(5, 13, 21)),
        # The Tetons' hours and clocks: Utah's SNOTEL stations keep the Pacific standard clock too (see
        # WASATCH_STATIONS). The lowest ground is Sundance's base at 1,859 m: no lower levels are read.
        Region("wasatch", "Wasatch", "America/Denver", 8, 8, ("UAC",), at=(5, 13, 21)),
        # The same hours and clocks again: Colorado's SNOTEL stations keep the Pacific standard clock (see
        # COLORADO_STATIONS). The lowest ground is Steamboat's base at 2,103 m: no lower levels are read.
        # Built by the third collector since 2026-11-26, to leave the first room for the Sierra's west slope.
        Region("colorado", "Colorado", "America/Denver", 8, 8, ("CAIC",), at=(5, 13, 21), collector="west"),
        # Built twice a day, at 5 am and 5 pm Pacific, to keep the day's calls under the service's limit (Sean's
        # choice, 2026-11-24). The lowest ground is Castle Lake's lot at 1,659 m: no lower levels are read.
        Region("shasta", "Shasta", "America/Los_Angeles", 8, 12, ("MSAC",), at=(5, 17)),
        # ---- Canada, the second collector's. Built at the West's hours on each region's own clock. Avalanche
        # Canada's forecasts are not on avalanche.org, so no center is named here; the page reads them itself.
        # SilverStar's and Sun Peaks' bases are near 1,150 to 1,200 m, under 850 hPa, so 900 hPa (near 990 m) is read.
        Region("okanagan", "Okanagan", "America/Vancouver", 8, 8, (), low_levels=(900,), at=(5, 13, 21),
               collector="canada", country="Canada"),
        # Whistler's Creekside base is at 653 m, which 950 hPa (near 540 m) covers.
        Region("bccoast", "BC Coast", "America/Vancouver", 8, 8, (), low_levels=(950, 925, 900), at=(5, 13, 21),
               collector="canada", country="Canada"),
        # Like New England, every lift-served metre is below 850 hPa (Le Massif's gondola starts at 36 m), and it is
        # built at New England's hours on the same clock.
        Region("quebec", "Quebec", "America/Toronto", 5, 12, (), low_levels=(1000, 975, 950, 925, 900), at=(4, 16),
               collector="canada", country="Canada"),
        # Revelstoke's base is at 512 m, just under the 950 hPa level, so 975 hPa (near 320 m) is read too.
        Region("powderhighway", "Powder Highway", "America/Vancouver", 8, 8, (), low_levels=(975, 950, 925, 900),
               at=(5, 13, 21), collector="canada", country="Canada"),
        # Golden, Invermere, Kimberley and Fernie keep Alberta's clock. Fernie's base, the lowest, is at 1,052 m.
        Region("eastkootenays", "East Kootenays", "America/Edmonton", 7, 8, (), low_levels=(900,), at=(5, 13, 21),
               collector="canada", country="Canada"),
        # Nakiska's base, the lowest, is at 1,525 m, above the lowest level every pull already reads.
        Region("rockies", "Canadian Rockies", "America/Edmonton", 7, 8, (), at=(5, 13, 21),
               collector="canada", country="Canada"),
        # ---- The third collector's: the USA's regions added once the first collector's plan was full. Built at the
        # West's hours on each region's own clock. Every state's SNOTEL stations but Alaska's keep the Pacific
        # standard clock, so the sensor offset is 8; Alaska's keep Alaska standard time, 9.
        # The lowest ground is Bridger Bowl's base at 1,859 m, well above 850 hPa: no lower levels are read.
        Region("montana", "Montana", "America/Denver", 8, 8, ("GNFAC",), at=(5, 13, 21), collector="west"),
        # Ketchum keeps Mountain time. The lowest ground is Sun Valley's River Run base at 1,753 m.
        Region("sunvalley", "Sun Valley", "America/Boise", 8, 8, ("SNFAC",), at=(5, 13, 21), collector="west"),
        # Mt. Hood is the Northwest Avalanche Center's (the Cascades' center, named there already) and the central
        # Cascades the Central Oregon Avalanche Center's, "COAA" on avalanche.org. Skibowl's base is at 1,097 m and
        # Tilly Jane's trailhead at 1,188 m, under 850 hPa, so 900 hPa (near 990 m) is read.
        Region("oregon", "Oregon", "America/Los_Angeles", 8, 8, ("NWAC", "COAA"), low_levels=(900,), at=(5, 13, 21),
               collector="west"),
        # The lowest ground is Sipapu's base at 2,499 m: no lower levels are read.
        Region("newmexico", "New Mexico", "America/Denver", 8, 8, ("TAC",), at=(5, 13, 21), collector="west"),
        # Alyeska's tram starts at 76 m and Turnagain Pass's lots are near 300 m: every level down to 1000 hPa is
        # read, as in New England.
        Region("alaska", "Alaska", "America/Anchorage", 9, 8, ("CNFAIC", "HPAC"),
               low_levels=(1000, 975, 950, 925, 900), at=(5, 13, 21), collector="west"),
        # Colorado's clocks and center. The lowest ground is Buttermilk's base at 2,399 m: no lower levels are read.
        Region("swcolorado", "Southwest Colorado", "America/Denver", 8, 8, ("CAIC",), at=(5, 13, 21),
               collector="west"),
        # The fourth collector's regions (see COLLECTOR), built at the West's hours on each region's own
        # clock. Western Idaho: the Payette center forecasts McCall's mountains and the Wallowa center the
        # Elkhorns. Tamarack's base, the lowest, is at 1,494 m, above the lowest level every pull reads.
        Region("westidaho", "Western Idaho", "America/Boise", 8, 8, ("PAC", "WAC"), at=(5, 13, 21), collector="north"),
        # Wyoming's seven are spread over 380 km. The Eastern Wyoming Avalanche Information Center covers the
        # Snowy Range and the Bighorns but posts no rated forecast, so no center is named. The lowest base is
        # Sleeping Giant's at 2,017 m.
        Region("wyoming", "Wyoming", "America/Denver", 8, 8, (), at=(5, 13, 21), collector="north"),
        # Southern Utah is the Utah center's Southwest zone. The lowest ground is Eagle Point's lowest lift at
        # 2,844 m.
        Region("southutah", "Southern Utah", "America/Denver", 8, 8, ("UAC",), at=(5, 13, 21), collector="north"),
        # Arizona keeps Mountain standard time all year. The Kachina Peaks center forecasts the San Francisco
        # Peaks. The lowest base is Snowbowl's at 2,804 m.
        Region("arizona", "Arizona", "America/Phoenix", 8, 8, ("KPAC",), at=(5, 13, 21), collector="north"),
        # Las Vegas is Lee Canyon alone, base 2,640 m; no avalanche center covers the Spring Mountains.
        Region("lasvegas", "Las Vegas", "America/Los_Angeles", 8, 8, (), at=(5, 13, 21), collector="north"),
        # Southern California has no snow sensors and no avalanche center. The lowest base is Mt. Baldy's at
        # 1,981 m.
        Region("socal", "Southern California", "America/Los_Angeles", 8, 8, (), at=(5, 13, 21), collector="north"),
        # Juneau is the Coastal Alaska center's Douglas Island zone. Eaglecrest's base is at 366 m, which 975
        # hPa (near 320 m) covers; Alaska's sensors keep Alaska standard time.
        Region("juneau", "Juneau", "America/Juneau", 9, 8, ("CAAC",), low_levels=(975, 950, 925, 900), at=(5, 13,
               21), collector="north"),
        # Valdez is the Valdez center's Intermountain zone. Girls Mountain's trailhead is at 645 m, which 950
        # hPa (near 540 m) covers.
        Region("valdez", "Valdez", "America/Anchorage", 9, 8, ("VAC",), low_levels=(950, 925, 900), at=(5, 13, 21),
               collector="north"),
        # The Inland Northwest keeps Pacific time (Lookout Pass sits on the Montana line). The Idaho Panhandle
        # center forecasts the Selkirks and the Silver Valley. Mt. Spokane's base is at 1,164 m, under 850
        # hPa, so 900 hPa (near 990 m) is read.
        Region("inlandnw", "Inland Northwest", "America/Los_Angeles", 8, 8, ("IPAC",), low_levels=(900,), at=(5, 13,
               21), collector="north"),
        # Northwest Montana is the Flathead center's ground in the north and the West Central Montana center's
        # around Missoula and the Bitterroot. Whitefish's base is at 1,361 m, under 850 hPa, so 900 hPa is
        # read.
        Region("nwmontana", "Northwest Montana", "America/Denver", 8, 8, ("FAC", "WCMAC"), low_levels=(900,), at=(5,
               13, 21), collector="north"),
        # The fifth collector's regions (see COLLECTOR): the East and the Midwest, built at New England's
        # hours on each region's own clock and, like New England, read all the way down to 1000 hPa. New
        # York's lowest base is West Mountain's at 140 m.
        Region("newyork", "New York", "America/New_York", 5, 12, (), low_levels=(1000, 975, 950, 925, 900), at=(4,
               16), collector="east"),
        # The Mid-Atlantic runs 420 km from Elk Mountain to Wintergreen. Its lowest base is Blue Mountain's at
        # 140 m.
        Region("midatlantic", "Mid-Atlantic", "America/New_York", 5, 12, (), low_levels=(1000, 975, 950, 925, 900),
               at=(4, 16), collector="east"),
        # Lake Superior keeps Central time (Mount Bohemia, on the Keweenaw, is an hour ahead). Its lowest base
        # is Mount Bohemia's at 198 m.
        Region("lakesuperior", "Lake Superior", "America/Chicago", 6, 12, (), low_levels=(1000, 975, 950, 925, 900),
               at=(4, 16), collector="east"),
        # Michigan's lowest base is Boyne Mountain's at 218 m.
        Region("michigan", "Michigan", "America/Detroit", 5, 12, (), low_levels=(1000, 975, 950, 925, 900), at=(4,
               16), collector="east"),
        # The Black Hills are Terry Peak alone, base 1,798 m, so no lower levels are read.
        Region("blackhills", "Black Hills", "America/Denver", 8, 12, (), at=(4, 16), collector="east"),
        # More of Canada, the second collector's. Northern BC spans 405 km, Terrace to Pine Pass. Shames's
        # base is at 700 m, which 950 hPa (near 540 m) covers.
        Region("northbc", "Northern BC", "America/Vancouver", 8, 8, (), low_levels=(950, 925, 900), at=(5, 13, 21),
               collector="canada", country="Canada"),
        # Ontario is built at New England's hours and read down to 1000 hPa: Calabogie's base is at 154 m.
        Region("ontario", "Ontario", "America/Toronto", 5, 12, (), low_levels=(1000, 975, 950, 925, 900), at=(4, 16),
               collector="canada", country="Canada"),
        # The Gaspé's Chic-Chocs are forecast by Avalanche Québec, which Avalanche Canada's feed carries. Pin
        # Rouge's base is at 50 m.
        Region("gaspesie", "Gaspé", "America/Toronto", 5, 12, (), low_levels=(1000, 975, 950, 925, 900), at=(4, 16),
               collector="canada", country="Canada"),
        # Newfoundland keeps its own half-hour clock. Marble Mountain's base is at 10 m.
        Region("newfoundland", "Newfoundland", "America/St_Johns", 4, 12, (), low_levels=(1000, 975, 950, 925, 900),
               at=(4, 16), collector="canada", country="Canada"),
        # The Yukon's White Pass is forecast by Avalanche Canada with the Yukon Avalanche Association. Mount
        # Sima's base is at 853 m, which 925 hPa (near 760 m) covers.
        Region("yukon", "Yukon", "America/Whitehorse", 7, 8, (), low_levels=(925, 900), at=(5, 13, 21),
               collector="canada", country="Canada"),
    ]
}

# Which collector this process is. Each collector is a workflow of its own (snow-collect.yml is "main",
# snow-collect-canada.yml is "canada", snow-collect-west.yml is "west", snow-collect-north.yml is "north",
# snow-collect-east.yml is "east"): it builds only its own regions, publishes
# them on a data branch of its own
# with its own index, and keeps its own ledger of calls. Everything that walks REGIONS or RESORTS therefore sees one
# collector's share; ALL_REGIONS and ALL_RESORTS are every region and mountain there is.
COLLECTOR = os.environ.get("SNOW_COLLECTOR", "main")
REGIONS = {key: region for key, region in ALL_REGIONS.items() if region.collector == COLLECTOR}
RESORTS = {key: resort for key, resort in ALL_RESORTS.items() if resort.region in REGIONS}


def resorts_in(region: str) -> list[Resort]:
    return [r for r in RESORTS.values() if r.region == region]


def weather_point(resort: Resort) -> Resort:
    """The mountain whose place a resort's weather is asked for at: its own, or the neighbour it shares with."""
    return RESORTS[resort.weather_from] if resort.weather_from else resort


def avalanche_centers() -> tuple[str, ...]:
    """Every region's avalanche centers, in region order, each once. Every collector's regions are here: the
    avalanche file is the first collector's work whoever forecasts the region."""
    return tuple(dict.fromkeys(center for region in ALL_REGIONS.values() for center in region.avalanche))


# Open-Meteo model identifiers.
DET_MODELS = ["gfs_seamless", "ecmwf_ifs025", "icon_seamless", "gem_seamless"]
ENS_MODELS = {"gfs025": "gfs_seamless", "ecmwf_ifs025": "ecmwf_ifs025",
              "icon_seamless": "icon_seamless", "gem_global": "gem_seamless"}

PRESSURE_LEVELS = [850, 800, 750, 700, 650, 600, 550, 500]


def levels_for(region: str) -> list[int]:
    """The pressure levels a region's forecast reads, lowest in the air first."""
    return sorted(ALL_REGIONS[region].low_levels, reverse=True) + PRESSURE_LEVELS


# Sierra box used to gather hand-measured snowfall for snow-ratio training.
SIERRA_BBOX = (36.0, 40.5, -121.5, -118.0)
TAHOE_BBOX = (38.4, 39.7, -120.8, -119.6)
MAMMOTH_BBOX = (37.0, 38.3, -119.7, -118.4)
# Around the Seattle region's ten snow sensors, Swift Creek in the south to Wells Creek in the north.
SEATTLE_BBOX = (46.0, 49.0, -123.6, -120.3)
# Around the Tetons: Yellowstone's south edge to the Wyoming Range, the Big Holes to the Wind Rivers' north end.
TETONS_BBOX = (43.0, 44.4, -111.6, -109.8)
# Around the Wasatch's ten snow sensors, Timpanogos Divide in the south to Ben Lomond Peak in the north.
WASATCH_BBOX = (40.2, 41.5, -112.1, -111.4)
# Around Colorado's sixteen snow sensors: Hoosier Pass in the south to Tower above Steamboat in the north. The four
# by Steamboat sit apart, in (40.3, 40.6, -106.85, -106.55); the twelve along I-70 are in (39.3, 39.9, -106.6, -105.75).
COLORADO_BBOX = (39.3, 40.6, -106.85, -105.75)
# Around Shasta's nine snow pillows, Harkness Flat by Lassen to Sand Flat on Mt. Shasta.
SHASTA_BBOX = (40.4, 41.6, -122.9, -121.19)
# Around each Canadian region's stations and mountains.
OKANAGAN_BBOX = (49.3, 51.0, -120.3, -118.5)
BCCOAST_BBOX = (49.3, 50.9, -125.8, -122.1)
POWDERHIGHWAY_BBOX = (49.0, 51.7, -118.5, -116.6)
EASTKOOTENAYS_BBOX = (49.0, 51.3, -117.3, -114.8)
ROCKIES_BBOX = (50.9, 53.0, -118.7, -115.0)
# Around southwest Montana: Big Sky and the Gallatin, Bridger, Little Belt and Beartooth ranges: its mountains and the
# sensors its correction is fitted to.
MONTANA_BBOX = (44.86, 47.08, -111.63, -109.71)
# Around Sun Valley, the Soldier Mountains and the Sawtooths: its mountains and the sensors its correction is fitted to.
SUNVALLEY_BBOX = (43.33, 44.48, -115.43, -113.96)
# Around Oregon's Cascades, Mt. Hood to Willamette Pass: its mountains and the sensors its correction is fitted to.
OREGON_BBOX = (43.3, 45.77, -122.41, -121.41)
# Around northern New Mexico: the Sangre de Cristo and Jemez mountains: its mountains and the sensors its correction
# is fitted to.
NEWMEXICO_BBOX = (35.56, 36.94, -106.75, -105.0)
# Around Southcentral Alaska: Girdwood, Turnagain Pass, Summit Lake, Anchorage and Hatcher Pass: its mountains and the
# sensors its correction is fitted to.
ALASKA_BBOX = (60.46, 61.94, -149.88, -148.86)
# Around southwest Colorado: the Elk Mountains, the Sawatch at Monarch and the San Juans: its mountains and the
# sensors its correction is fitted to.
SWCOLORADO_BBOX = (37.23, 39.47, -108.22, -106.14)
# The later regions' boxes, by region: each holds the region's mountains and the sensors its correction is fitted to.
MORE_BBOX = {
    "westidaho": (43.61, 45.34, -118.51, -115.76),
    "wyoming": (41.09, 44.96, -111.02, -105.99),
    "southutah": (37.42, 38.63, -113.13, -112.16),
    "arizona": (33.77, 35.49, -111.94, -109.26),
    "lasvegas": (36.1, 36.47, -115.9, -115.43),
    "socal": (34.07, 34.52, -117.89, -116.66),
    "juneau": (58.11, 58.42, -134.73, -134.29),
    "valdez": (60.99, 61.34, -145.95, -145.45),
    "inlandnw": (47.28, 48.52, -117.77, -115.5),
    "nwmontana": (45.52, 48.64, -114.57, -112.93),
    "newyork": (41.98, 44.5, -78.88, -73.53),
    "midatlantic": (37.77, 41.87, -80.19, -75.15),
    "lakesuperior": (44.78, 47.8, -92.41, -87.82),
    "michigan": (44.09, 45.62, -86.2, -84.7),
    "blackhills": (44.06, 44.48, -104.03, -103.59),
    "northbc": (54.34, 55.51, -129.16, -122.42),
    "ontario": (44.35, 45.42, -80.52, -76.58),
    "gaspesie": (48.17, 49.11, -68.4, -65.29),
    "newfoundland": (48.01, 49.09, -58.03, -53.85),
    "yukon": (59.6, 60.76, -135.25, -134.79),
}
# The later regions that have sensors to fit to: the states its SNOTEL stations are listed under, and the lowest
# hand-measured station (m) taken for its snow ratio.
FIT_BOXES = {
    "westidaho": (("ID", "OR"), 1200.0),
    "wyoming": ("WY", 1500.0),
    "southutah": ("UT", 1500.0),
    "arizona": ("AZ", 1500.0),
    "lasvegas": ("NV", 1500.0),
    "inlandnw": (("ID", "WA", "MT"), 600.0),
    "nwmontana": (("MT", "ID"), 900.0),
}
