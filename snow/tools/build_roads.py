"""Build the 3D map's highway lines from OpenStreetMap via Overpass (ODbL; no key).

Writes data/roads.json for Tahoe and data/roads-<region>.json for the others, over the box of that region's
terrain file: [{"route": "I-80", "lines": [[[lon, lat], ...], ...]}, ...]. python tools/build_roads.py [region].
Route names match the Caltrans chain-control feed (I-80, US-50, SR-89, ...).
Run once per region, after build_terrain.py; the output is committed.
"""
import json
import re
import sys
import time
from pathlib import Path
from xml.etree import ElementTree

import numpy as np
import requests

ROOT = Path(__file__).resolve().parent.parent
SERVERS = ["https://overpass.kumi.systems/api/interpreter", "https://overpass-api.de/api/interpreter",
           "https://overpass.private.coffee/api/interpreter"]
ROUTES = {
    "tahoe": {"I 80": "I-80", "US 50": "US-50", "CA 89": "SR-89", "CA 28": "SR-28", "CA 267": "SR-267",
              "CA 88": "SR-88", "CA 4": "SR-4", "CA 20": "SR-20", "CA 49": "SR-49", "NV 431": "NV-431",
              "NV 207": "NV-207", "NV 28": "NV-28", "US 395": "US-395", "I 580": "I-580"},
    "mammoth": {"US 395": "US-395", "CA 203": "SR-203", "CA 158": "SR-158", "CA 120": "SR-120", "CA 108": "SR-108",
                "CA 167": "SR-167", "CA 168": "SR-168", "CA 182": "SR-182", "CA 270": "SR-270", "US 6": "US-6"},
    # OSM tags concurrent routes as "I 93;US 3"; the query and the split on ";" in main() already match each.
    "newengland": {"I 93": "I-93", "I 89": "I-89", "I 91": "I-91", "I 95": "I-95", "US 2": "US-2", "US 4": "US-4",
                   "US 302": "US-302", "VT 100": "VT-100", "VT 108": "VT-108", "NH 16": "NH-16", "NH 112": "NH-112",
                   "ME 26": "ME-26", "ME 27": "ME-27"},
    # OpenStreetMap writes Washington's state routes "SR 410", as Washington does; the map draws them with the plain
    # white marker (REGIONS.seattle.plainStateRoutes in the page), not California's spade.
    "seattle": {"I 5": "I-5", "I 90": "I-90", "I 405": "I-405", "US 2": "US-2", "US 12": "US-12", "US 97": "US-97",
                "US 101": "US-101", "SR 410": "SR-410", "SR 542": "SR-542", "SR 20": "SR-20", "SR 530": "SR-530",
                "SR 706": "SR-706", "SR 503": "SR-503", "SR 141": "SR-141"},
    # The roads to Jackson and over its passes: the Snake River highways, Teton Pass (WY 22) and the road to Teton
    # Village (WY 390), Togwotee Pass (US 26/287), and Idaho's side to Driggs and Grand Targhee.
    "tetons": {"US 26": "US-26", "US 89": "US-89", "US 191": "US-191", "US 287": "US-287", "WY 22": "WY-22",
               "WY 390": "WY-390", "ID 33": "ID-33", "ID 31": "ID-31", "ID 32": "ID-32"},
    # The Wasatch Front's interstates, the roads behind the range, and the canyon roads to the lifts: Little and
    # Big Cottonwood (UT 210, UT 190), Park City (UT 224), Provo Canyon and Sundance (US 189, UT 92), Ogden Canyon
    # and Snowbasin (UT 39, UT 226, UT 167) and Powder Mountain (UT 158). OpenStreetMap writes Utah's state routes
    # as "SR" on most ways and "UT" on some, so both are asked for.
    "wasatch": {"I 15": "I-15", "I 80": "I-80", "I 84": "I-84", "I 215": "I-215", "US 40": "US-40",
                "US 189": "US-189", "US 89": "US-89", "SR 210": "UT-210", "SR 190": "UT-190", "SR 224": "UT-224",
                "SR 92": "UT-92", "SR 39": "UT-39", "SR 226": "UT-226", "SR 167": "UT-167", "SR 158": "UT-158",
                "UT 210": "UT-210", "UT 190": "UT-190", "UT 224": "UT-224", "UT 92": "UT-92", "UT 39": "UT-39",
                "UT 226": "UT-226", "UT 167": "UT-167", "UT 158": "UT-158"},
    # I-70 over the Divide and Vail Pass, the roads to Winter Park and Steamboat (US 40) and over Loveland Pass
    # (US 6), to Breckenridge (CO 9) and from Copper to Leadville (CO 91), and the Colorado River road (CO 131).
    # OpenStreetMap writes Colorado's state routes as "CO" on most ways and "SH" on some, so both are asked for.
    "colorado": {"I 70": "I-70", "US 40": "US-40", "US 6": "US-6", "US 24": "US-24", "US 34": "US-34",
                 "CO 9": "CO-9", "CO 91": "CO-91", "CO 131": "CO-131", "CO 14": "CO-14",
                 "SH 9": "CO-9", "SH 91": "CO-91", "SH 131": "CO-131", "SH 14": "CO-14"},
    # I-5 through the Sacramento canyon and over Siskiyou Summit, US 97 north of Mt. Shasta, the McCloud and Lassen
    # roads (CA 89, CA 44), CA 299 across the south, CA 3 through the Trinities and the Mt. Ashland turn-off's CA 96.
    "shasta": {"I 5": "I-5", "US 97": "US-97", "CA 89": "SR-89", "CA 44": "SR-44", "CA 299": "SR-299",
               "CA 3": "SR-3", "CA 96": "SR-96", "CA 36": "SR-36", "OR 66": "OR-66"},
    # British Columbia's highways as OpenStreetMap writes them: "BC 97", the Yellowhead as "YH 5" and the
    # Trans-Canada as "TCH 1". The Okanagan's valley road (97), the Connector (97C), the roads toward Big White (33)
    # and Apex (3A), Vernon's Highway 6, and the Yellowhead and Trans-Canada through Kamloops toward Sun Peaks.
    "okanagan": {"BC 97": "BC-97", "BC 97C": "BC-97C", "BC 33": "BC-33", "BC 3A": "BC-3A", "BC 6": "BC-6",
                 "BC 97A": "BC-97A", "BC 3": "BC-3", "YH 5": "BC-5", "BC 5": "BC-5", "TCH 1": "TCH-1"},
    # The Sea-to-Sky and the Duffey Lake road (both BC 99), the Trans-Canada along the North Shore, and Vancouver
    # Island's highways to Mt. Washington, which OpenStreetMap writes both as "BC 19" and as "19".
    "bccoast": {"BC 99": "BC-99", "TCH 1": "TCH-1", "BC 19": "BC-19", "19": "BC-19", "BC 19A": "BC-19A",
                "BC 7": "BC-7", "BC 12": "BC-12"},
    # Quebec's autoroutes and routes, which OpenStreetMap writes as bare numbers: the Laurentian autoroute (15) and
    # Route 117 to Tremblant, the Townships' autoroute (10), the 40 and the 20 along the St. Lawrence, the 73 and
    # 175 to Stoneham, and the 138 to Mont-Sainte-Anne and Le Massif.
    "quebec": {"15": "A-15", "117": "R-117", "10": "A-10", "40": "A-40", "20": "A-20", "73": "A-73",
               "175": "R-175", "138": "R-138", "55": "A-55"},
    # The Trans-Canada over Rogers Pass, the Crowsnest ("CN 3") over Kootenay Pass, the Arrow Lakes road to
    # Revelstoke (23), Rossland's 3B, and the 6 and 3A through Nelson to Whitewater.
    "powderhighway": {"TCH 1": "TCH-1", "CN 3": "BC-3", "BC 23": "BC-23", "BC 3B": "BC-3B", "BC 6": "BC-6",
                      "BC 3A": "BC-3A", "BC 31": "BC-31"},
    # The Trans-Canada through Golden, the Columbia Valley road (95, with 93 from Radium), Kimberley's 95A and the
    # Crowsnest through Cranbrook and Fernie.
    "eastkootenays": {"TCH 1": "TCH-1", "BC 95": "BC-95", "BC 93": "BC-93", "BC 95A": "BC-95A", "CN 3": "BC-3"},
    # Alberta writes its highways as bare numbers: the Trans-Canada (1), the Icefields Parkway (93) and its old
    # road to Marmot (93A), the Bow Valley Parkway (1A), the Yellowhead at Jasper (16), the Kananaskis Trail to
    # Nakiska (40) and the David Thompson (11). British Columbia's side of the map writes "TCH 1" and "BC 93".
    "rockies": {"1": "TCH-1", "TCH 1": "TCH-1", "93": "AB-93", "BC 93": "BC-93", "93A": "AB-93A", "1A": "AB-1A",
                "16": "AB-16", "40": "AB-40", "11": "AB-11"},
    # The third collector's regions, each ref as it was seen on OpenStreetMap's ways (2026-11-26). The Overpass
    # servers did not answer that day, so these were built from the routes' relations (RELATIONS, ``--relations``).
    # I-90 through Bozeman and Livingston, the Gallatin Canyon (US 191) and the Big Sky spur (MT 64), the roads to
    # Bridger Bowl (MT 86), over Kings Hill to Showdown (US 89) and through Cooke City (US 212).
    "montana": {"I 90": "I-90", "US 191": "US-191", "US 89": "US-89", "US 287": "US-287", "US 20": "US-20",
                "US 212": "US-212", "US 12": "US-12", "MT 64": "MT-64", "MT 84": "MT-84", "MT 85": "MT-85",
                "MT 86": "MT-86", "MT 87": "MT-87", "MT 287": "MT-287"},
    # The Wood River road over Galena Summit to Stanley (ID 75) and its spur to Sun Valley, the Ponderosa Pine
    # byway over Banner Summit (ID 21), US 20 across the Camas Prairie to Fairfield, and US 93 and I-84 below.
    "sunvalley": {"ID 75": "ID-75", "ID 75 Spur": "ID-75", "ID 21": "ID-21", "US 20": "US-20", "US 93": "US-93",
                  "US 26": "US-26", "I 84": "I-84", "ID 46": "ID-46"},
    # Mt. Hood's roads (US 26, OR 35, the Timberline Highway OR 173, and I-84 in the Gorge), Santiam Pass
    # (US 20, OR 126, OR 22), McKenzie Pass (OR 242), US 97 through Bend, the Cascade Lakes Highway to
    # Mt. Bachelor (OR 372) and Willamette Pass (OR 58).
    "oregon": {"US 26": "US-26", "OR 35": "OR-35", "I 84": "I-84", "OR 173": "OR-173", "US 20": "US-20",
               "OR 126": "OR-126", "OR 22": "OR-22", "OR 242": "OR-242", "US 97": "US-97", "OR 372": "OR-372",
               "OR 58": "OR-58", "I 5": "I-5", "OR 281": "OR-281"},
    # The road to Taos Ski Valley (NM 150), the Enchanted Circle to Red River and Angel Fire (NM 38, US 64,
    # NM 434), the High Road and the road to Sipapu (NM 518), the Rio Grande road (NM 68), Hyde Park Road to
    # Ski Santa Fe (NM 475), and the roads to Los Alamos (NM 502, NM 501).
    "newmexico": {"NM 150": "NM-150", "NM 38": "NM-38", "NM 522": "NM-522", "NM 68": "NM-68", "US 64": "US-64",
                  "NM 434": "NM-434", "NM 518": "NM-518", "NM 475": "NM-475", "NM 502": "NM-502",
                  "NM 501": "NM-501", "US 84": "US-84", "US 285": "US-285", "I 25": "I-25"},
    # The Seward Highway (AK 1 south of Anchorage, AK 9 to Seward), the Glenn Highway (AK 1 north) and the Parks
    # (AK 3). The Alyeska Highway and the Hatcher Pass road carry no number.
    "alaska": {"AK 1": "AK-1", "AK 3": "AK-3", "AK 9": "AK-9"},
    # The roads to Aspen (CO 82) and Marble (CO 133), Crested Butte (CO 135), Monarch Pass (US 50), the Million
    # Dollar Highway over Red Mountain, Molas and Coal Bank passes (US 550), Telluride (CO 145, CO 62) and Wolf
    # Creek Pass (US 160).
    "swcolorado": {"CO 82": "CO-82", "CO 133": "CO-133", "CO 135": "CO-135", "US 50": "US-50", "US 285": "US-285",
                   "US 550": "US-550", "CO 62": "CO-62", "CO 145": "CO-145", "US 160": "US-160", "CO 149": "CO-149",
                   "I 70": "I-70"},
    # The later regions' highways, each ref as it was seen on OpenStreetMap's ways (2026-11-26); built from RELATIONS.
    "westidaho": {"I 84": "I-84", "ID 55": "ID-55", "US 95": "US-95", "ID 44": "ID-44", "US 20": "US-20",
                  "US 26": "US-26", "US 30": "US-30", "OR 237": "OR-237", "OR 7": "OR-7"},
    "wyoming": {"I 80": "I-80", "I 25": "I-25", "I 90": "I-90", "WY 130": "WY-130", "WY 251": "WY-251",
                "US 14": "US-14", "US 16": "US-16", "US 20": "US-20", "US 26": "US-26", "US 191": "US-191",
                "US 30": "US-30", "WY 232": "WY-232", "US 287": "US-287"},
    "southutah": {"I 15": "I-15", "SR 143": "UT-143", "SR 153": "UT-153", "SR 14": "UT-14", "SR 148": "UT-148",
                  "SR 20": "UT-20", "US 89": "US-89"},
    "arizona": {"I 17": "I-17", "I 40": "I-40", "US 180": "US-180", "US 89": "US-89", "AZ 260": "AZ-260",
                "AZ 273": "AZ-273", "US 60": "US-60", "AZ 77": "AZ-77", "I 10": "I-10"},
    "lasvegas": {"US 95": "US-95", "SR 156": "NV-156", "SR 157": "NV-157", "SR 158": "NV-158", "I 15": "I-15",
                 "CC 215": "CC-215", "SR 160": "NV-160"},
    "socal": {"CA 18": "CA-18", "CA 38": "CA-38", "CA 330": "CA-330", "CA 2": "CA-2", "CA 138": "CA-138",
              "I 15": "I-15", "I 10": "I-10", "I 210": "I-210", "CA 210": "CA-210", "I 215": "I-215"},
    "juneau": {"AK 7": "AK-7"},
    "valdez": {"AK 4": "AK-4"},
    "inlandnw": {"I 90": "I-90", "US 95": "US-95", "US 2": "US-2", "US 395": "US-395", "ID 200": "ID-200",
                 "SR 206": "WA-206", "ID 57": "ID-57"},
    "nwmontana": {"I 90": "I-90", "US 93": "US-93", "US 2": "US-2", "US 12": "US-12", "MT 200": "MT-200",
                  "MT 1": "MT-1", "MT 35": "MT-35", "MT 83": "MT-83", "MT 40": "MT-40", "MT 43": "MT-43"},
    "newyork": {"I 87": "I-87", "I 90": "I-90", "I 86": "I-86", "NY 73": "NY-73", "NY 86": "NY-86",
                "NY 28": "NY-28", "NY 23": "NY-23", "NY 23A": "NY-23A", "NY 30": "NY-30", "US 219": "US-219",
                "NY 64": "NY-64"},
    "midatlantic": {"I 68": "I-68", "I 76": "I-76", "I 80": "I-80", "I 81": "I-81", "I 64": "I-64",
                    "I 476": "I-476", "US 219": "US-219", "US 33": "US-33", "US 48": "US-48", "WV 32": "WV-32",
                    "WV 66": "WV-66", "PA 31": "PA-31", "VA 151": "VA-151", "PA 374": "PA-374"},
    "lakesuperior": {"MN 61": "MN-61", "I 35": "I-35", "US 2": "US-2", "US 41": "US-41", "M 26": "M-26",
                     "M 28": "M-28", "US 45": "US-45", "US 51": "US-51", "WI 29": "WI-29", "WI 77": "WI-77",
                     "WI 13": "WI-13"},
    "michigan": {"I 75": "I-75", "US 131": "US-131", "US 31": "US-31", "M 115": "M-115", "M 55": "M-55",
                 "M 37": "M-37", "M 119": "M-119", "M 75": "M-75", "M 88": "M-88", "M 32": "M-32", "M 66": "M-66",
                 "M 72": "M-72"},
    "blackhills": {"I 90": "I-90", "US 85": "US-85", "US 14A": "US-14A", "US 385": "US-385", "US 14": "US-14",
                   "US 16": "US-16", "SD 34": "SD-34"},
    "northbc": {"YH 16": "BC-16", "BC 37": "BC-37", "BC 113": "BC-113", "BC 97": "BC-97", "BC 39": "BC-39",
                "BC 29": "BC-29", "BC 62": "BC-62"},
    "ontario": {"400": "ON-400", "26": "ON-26", "11": "ON-11", "12": "ON-12", "10": "ON-10", "CR 19": "CR-19",
                "CR 22": "CR-22", "CR 124": "CR-124", "CR 42": "CR-42", "417": "ON-417", "17": "ON-17",
                "CR 508": "CR-508", "CR 511": "CR-511"},
    "gaspesie": {"132": "QC-132", "299": "QC-299", "198": "QC-198", "195": "QC-195", "298": "QC-298",
                 "234": "QC-234", "232": "QC-232", "20": "A-20"},
    "newfoundland": {"1": "TCH-1", "430": "NL-430", "440": "NL-440", "450": "NL-450", "450A": "NL-450A",
                     "480": "NL-480"},
    "yukon": {"YK 2": "YT-2", "YK 1": "YT-1", "YK 1;YK 2": "YT-1/2", "AK 98": "AK-98", "YK 8": "YT-8",
              "YK 7": "YT-7"},
}
# When no Overpass server answers, a region's roads can be read from the main OpenStreetMap API instead, one route
# relation at a time: the relations (each one state's stretch of a highway, both directions where they are mapped
# apart) by the label the route is drawn with. Found by reading a small box of the map on each road
# (``/api/0.6/map?bbox=``), whose answer lists the route relations its ways belong to.
RELATIONS = {
    "montana": {"I-90": [2328611, 2328612], "US-191": [2306279], "US-89": [1298019], "US-287": [1519971], "US-20":
                [20002033], "US-212": [324710, 2308445], "US-12": [301540], "MT-64": [1264043], "MT-84":
                [1266469], "MT-85": [5695334], "MT-86": [1266483], "MT-87": [1266574], "MT-287": [1266654]},
    "sunvalley": {"ID-75": [2512900, 12254153], "ID-21": [3344440, 3367968], "US-20": [406627], "US-93":
                  [2306282], "US-26": [2308604], "I-84": [402511, 6898994], "ID-46": [12253898]},
    "oregon": {"US-26": [2308607], "OR-35": [17662931, 17662933], "I-84": [301506, 6898773], "OR-173": [12194531],
               "US-20": [406017], "OR-126": [146232], "OR-22": [146953], "OR-242": [10554564], "US-97": [2306495],
               "OR-58": [1862451], "I-5": [2326066], "OR-281": [6714062], "OR-372": [12189406]},
    "newmexico": {"NM-150": [1485227], "NM-38": [1483000], "NM-522": [1492582], "NM-68": [1483515], "US-64":
                  [2310348], "NM-434": [1492127], "NM-518": [1492592], "NM-475": [1492140], "NM-502": [1492183],
                  "NM-501": [1492185], "US-84": [1629690], "US-285": [1628556], "I-25": [2333637, 2333638]},
    "alaska": {"AK-1": [326212, 16266162], "AK-3": [7636966, 7636967], "AK-9": [536718]},
    "swcolorado": {"CO-82": [1516311], "CO-133": [1516692], "CO-135": [1516696], "US-50": [6804642, 6804877],
                   "US-285": [1628545], "US-550": [452017, 7479051, 7479052], "CO-62": [1516090], "CO-145":
                   [1517027], "US-160": [7470608, 7470640], "CO-149": [1517030], "I-70": [84533, 6894122]},
    # The later regions, from the relation ids their research recorded.
    "westidaho": {"I-84": [301506, 402511, 6898773, 6898994], "ID-55": [2512899], "US-95": [1322940],
                  "ID-44": [2512896], "US-20": [406627], "US-26": [2308604], "US-30": [2308740, 2308743],
                  "OR-237": [12139302], "OR-7": [12212332]},
    "wyoming": {"I-80": [282374, 6902197], "I-25": [2333964, 2333965], "I-90": [178734, 6897253],
                "WY-130": [1506498], "WY-251": [1513018], "US-14": [451135], "US-16": [2308517], "US-20": [408084],
                "US-26": [2308608], "US-191": [1506357], "US-30": [443167], "WY-232": [1512949],
                "US-287": [1506356]},
    "southutah": {"I-15": [2334099, 2334100], "UT-143": [1505038], "UT-153": [1505116], "UT-14": [1504536],
                  "UT-148": [1505037], "UT-20": [1504533], "US-89": [2306246]},
    "arizona": {"I-17": [168470, 168471], "I-40": [337352, 6791956], "US-180": [1628560], "US-89": [2306244],
                "AZ-260": [1502486], "AZ-273": [1502472], "US-60": [7655460, 14395609], "AZ-77": [1501157],
                "I-10": [3332620, 3332621]},
    "lasvegas": {"US-95": [21015388, 21015389], "NV-156": [1536807], "NV-157": [1536810], "NV-158": [1536813],
                 "I-15": [2317122, 2317123], "CC-215": [19223944], "NV-160": [1536815]},
    "socal": {"CA-18": [349578], "CA-38": [2207983], "CA-330": [349574], "CA-2": [5562367, 5562601],
              "CA-138": [349640], "I-15": [2211488, 2211489], "I-10": [2396185, 2396186],
              "I-210": [157972, 157973], "CA-210": [158669, 158671], "I-215": [155016, 155025]},
    "juneau": {"AK-7": [535397]},
    "valdez": {"AK-4": [1324396]},
    "inlandnw": {"I-90": [183845, 184652, 2328611, 2328612, 6897153, 6897843], "US-95": [1322940],
                 "US-2": [2307082, 2307088], "US-395": [2306489], "ID-200": [12235168], "WA-206": [3185874],
                 "ID-57": [9986053]},
    "nwmontana": {"I-90": [2328611, 2328612], "US-93": [1343155, 2306282], "US-2": [1266683], "US-12": [301540],
                  "MT-200": [1082765], "MT-1": [1254837], "MT-35": [1113410], "MT-83": [1113409],
                  "MT-40": [1263625], "MT-43": [1261566]},
    "newyork": {"I-87": [181230], "I-90": [165109, 229716], "I-86": [318797, 318798], "NY-73": [1875647],
                "NY-86": [1295581], "NY-28": [385494], "NY-23": [182161], "NY-23A": [182155], "NY-30": [335437],
                "US-219": [1017180], "NY-64": [1074726]},
    "midatlantic": {"I-68": [1404729], "I-76": [3075336, 3075337], "I-80": [934352, 6904948],
                    "I-81": [1319518, 2297359], "I-64": [1267357, 6930415], "I-476": [932202],
                    "US-219": [2302514, 2302516], "US-33": [1593673, 1593693], "US-48": [455420],
                    "WV-32": [1538425], "WV-66": [1538505], "PA-31": [1014006], "VA-151": [1540975],
                    "PA-374": [1021160]},
    "lakesuperior": {"MN-61": [932635], "I-35": [2336021, 2336023], "US-2": [2307084, 15459560, 15459624],
                     "US-41": [2304384], "M-26": [272602], "M-28": [226345], "US-45": [2304408], "US-51": [116316],
                     "WI-29": [116321], "WI-77": [4036590], "WI-13": [1547092]},
    "michigan": {"I-75": [335614, 336890], "US-131": [253889], "US-31": [15442285, 15442286], "M-115": [279522],
                 "M-55": [239288], "M-37": [5692547], "M-119": [279540], "M-75": [277913], "M-88": [278732],
                 "M-32": [239248], "M-66": [255208], "M-72": [269922]},
    "blackhills": {"I-90": [399715, 6897262], "US-85": [1629701], "US-14A": [1937352], "US-385": [1628544],
                   "US-14": [451136], "US-16": [2308516], "SD-34": [325988]},
    "northbc": {"BC-16": [417859], "BC-37": [417860, 417862], "BC-113": [8743596], "BC-97": [7166559],
                "BC-39": [8746192], "BC-29": [8747037], "BC-62": [8746198]},
    "ontario": {"ON-400": [410040], "ON-26": [121142], "ON-11": [409993], "ON-12": [409977], "ON-10": [121141],
                "CR-19": [4232095, 4240728], "CR-22": [4232137], "CR-124": [4142223, 4234880], "CR-42": [4234870],
                "ON-417": [1607887], "ON-17": [3739959], "CR-508": [4127219], "CR-511": [4127262]},
    "gaspesie": {"QC-132": [393656, 393658, 393659], "QC-299": [393697], "QC-198": [1604992], "QC-195": [4562134],
                 "QC-298": [393760], "QC-234": [393745], "QC-232": [406216], "A-20": [406218, 20058456]},
    "newfoundland": {"TCH-1": [1732843], "NL-430": [5384079], "NL-440": [5384258], "NL-450": [5384259],
                     "NL-450A": [20173164], "NL-480": [5384277]},
    "yukon": {"YT-2": [5385974, 8747347], "YT-1": [5384759], "AK-98": [1324395], "YT-8": [5386017],
              "YT-7": [5386029]},
}
OSM_API = "https://api.openstreetmap.org/api/0.6"
TOLERANCE_DEG = 0.0004
# The Sierra crest as (lat, lon), north to south, set a little west of the passes. Mammoth's map keeps only the
# roads east of it: the page reads road status for the east side alone, and the west-side roads dead-end.
CREST = {"mammoth": [(38.46, -119.74), (38.33, -119.66), (37.91, -119.28), (37.65, -119.08), (37.21, -118.63),
                     (36.58, -118.31), (36.22, -118.12)]}


def east_of(geometry: list, crest: list) -> list:
    """The runs of a way's (lon, lat) points that lie east of the crest."""
    lats, lons = np.array(crest)[::-1].T
    points = np.array(geometry)
    keep = points[:, 0] >= np.interp(points[:, 1], lats, lons)
    runs = np.split(np.arange(len(points)), np.flatnonzero(np.diff(keep)) + 1)
    return [[geometry[i] for i in run] for run in runs if keep[run[0]] and len(run) >= 2]


def simplify(points: np.ndarray, tolerance: float) -> np.ndarray:
    """Douglas-Peucker."""
    if len(points) < 3:
        return points
    start, end = points[0], points[-1]
    segment = end - start
    length = np.hypot(*segment)
    offsets = points - start
    distance = np.hypot(*offsets.T) if length == 0 else np.abs(segment[0] * offsets[:, 1] - segment[1] * offsets[:, 0]) / length
    worst = int(distance.argmax())
    if distance[worst] <= tolerance:
        return np.array([start, end])
    return np.vstack([simplify(points[:worst + 1], tolerance)[:-1], simplify(points[worst:], tolerance)])


def chain(ways: list) -> list:
    """Join ways that share end points into longer lines."""
    lines = [list(map(tuple, way)) for way in ways]
    merged = True
    while merged:
        merged = False
        for i, a in enumerate(lines):
            for j, b in enumerate(lines):
                if i == j:
                    continue
                if a[-1] == b[0]:
                    lines[i] = a + b[1:]
                elif a[-1] == b[-1]:
                    lines[i] = a + b[-2::-1]
                elif a[0] == b[-1]:
                    lines[i] = b + a[1:]
                elif a[0] == b[0]:
                    lines[i] = b[::-1] + a[1:]
                else:
                    continue
                del lines[j]
                merged = True
                break
            if merged:
                break
    return lines


def inside_runs(geometry: list, bbox: tuple) -> list:
    """The runs of a way's (lon, lat) points that lie inside the box (south, west, north, east)."""
    south, west, north, east = bbox
    runs, run = [], []
    for lon, lat in geometry:
        if south <= lat <= north and west <= lon <= east:
            run.append((lon, lat))
        else:
            if len(run) >= 2:
                runs.append(run)
            run = []
    if len(run) >= 2:
        runs.append(run)
    return runs


def from_relations(region: str, bbox: tuple) -> dict:
    """{route label: [ways]} read from the region's route relations, each way cut to the box."""
    by_route = {}
    for route, ids in RELATIONS[region].items():
        for relation in ids:
            response = requests.get(f"{OSM_API}/relation/{relation}/full", headers={"User-Agent": "roads-builder/0.1"},
                                    timeout=180)
            response.raise_for_status()
            root = ElementTree.fromstring(response.content)
            nodes = {node.get("id"): (round(float(node.get("lon")), 5), round(float(node.get("lat")), 5))
                     for node in root.iter("node")}
            kept = 0
            for way in root.iter("way"):
                tags = {tag.get("k"): tag.get("v") for tag in way.iter("tag")}
                if not re.match(r"^(motorway|trunk|primary|secondary|tertiary)$", tags.get("highway", "")):
                    continue
                geometry = [nodes[nd.get("ref")] for nd in way.iter("nd") if nd.get("ref") in nodes]
                pieces = inside_runs(geometry, bbox)
                kept += len(pieces)
                by_route.setdefault(route, []).extend(pieces)
            print(route, "relation", relation, "->", kept, "ways in the box")
            time.sleep(1)
    return by_route


def main(region: str = "tahoe", relations: bool = False) -> None:
    suffix = "" if region == "tahoe" else f"-{region}"
    box = json.loads((ROOT / "data" / f"terrain{suffix}.json").read_text())
    BBOX = (box["lat_s"], box["lon_w"], box["lat_n"], box["lon_e"])
    routes = ROUTES[region]
    pattern = "|".join(routes)
    query = f"""[out:json][timeout:120];
way["highway"~"^(motorway|trunk|primary|secondary)$"]["ref"~"(^|;) ?({pattern})( ?;|$)"]({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});
out geom;"""
    response = None
    # ``--relations`` goes straight to the main API, for a day the Overpass servers are known to be down.
    for server in [] if relations else SERVERS:
        try:
            response = requests.post(server, data={"data": query}, headers={"User-Agent": "roads-builder/0.1"}, timeout=180)
            response.raise_for_status()
            break
        except requests.RequestException as error:
            print(server, "failed:", str(error)[:80])
            response = None
    if response is None and region not in RELATIONS:
        raise SystemExit("no Overpass server answered")
    by_route = {} if response is not None else from_relations(region, BBOX)
    for way in response.json()["elements"] if response is not None else []:
        refs = [ref.strip() for ref in way["tags"]["ref"].split(";")]
        geometry = [(round(p["lon"], 5), round(p["lat"], 5)) for p in way["geometry"]]
        pieces = east_of(geometry, CREST[region]) if region in CREST else [geometry]
        for ref in refs:
            if ref in routes:
                by_route.setdefault(routes[ref], []).extend(pieces)
    out = []
    for route, ways in sorted(by_route.items()):
        lines = [simplify(np.array(line), TOLERANCE_DEG).round(5).tolist() for line in chain(ways)]
        lines = [line for line in lines if len(line) >= 2]
        if lines:   # a route whose relation lies wholly outside the box draws nothing
            out.append({"route": route, "lines": lines})
        print(route, len(ways), "ways ->", len(lines), "lines,", sum(len(line) for line in lines), "points")
    (ROOT / "data" / f"roads{suffix}.json").write_text(json.dumps(out, separators=(",", ":")))


if __name__ == "__main__":
    main(*[arg for arg in sys.argv[1:] if arg != "--relations"][:1], relations="--relations" in sys.argv)
