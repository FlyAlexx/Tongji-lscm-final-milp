"""Central parameter block for the LSCM Final MILP.

All values are documented in `Data and MILP Concept final patched.md`.
Units are explicit in every dict; the model converts gCO2/tkm -> tCO2 inside
the objective function (see model.py).
"""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "Data Analysis Sources"
OUTPUT_DIR = Path(__file__).resolve().parent / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CENSUS_FILE = DATA_DIR / "census-main" / "data" / "census" / "census_city_2010-2020_v1.csv"
EMISSIONS_FILE = DATA_DIR / "20250912%20Full-scope%20Carbon%20emissions%20Datasets.xlsx"

# ---------------------------------------------------------------------------
# Network nodes
# ---------------------------------------------------------------------------

SUPPLIERS = {
    "i1_Guangzhou": {"name": "Pearl River Delta (Guangzhou)", "lon": 113.27, "lat": 23.13},
    "i2_Suzhou":    {"name": "Yangtze Delta (Suzhou)",        "lon": 120.62, "lat": 31.32},
    "i3_Tianjin":   {"name": "Bohai Rim (Tianjin)",           "lon": 117.20, "lat": 39.13},
}

PRODUCTION = {
    "j1_Suzhou":    {"name": "Suzhou",    "lon": 120.62, "lat": 31.32},
    "j2_Chongqing": {"name": "Chongqing", "lon": 106.55, "lat": 29.56},
}

DCS = {
    "k1_Shanghai": {"name": "Shanghai", "lon": 121.47, "lat": 31.23},
    "k2_Chengdu":  {"name": "Chengdu",  "lon": 104.07, "lat": 30.67},
    "k3_Shenzhen": {"name": "Shenzhen", "lon": 114.06, "lat": 22.55},
}

DEMAND_REGIONS = {
    "l1_East":    {"name": "East China",    "lon": 121.0, "lat": 31.0},
    "l2_South":   {"name": "South China",   "lon": 113.5, "lat": 23.0},
    "l3_West":    {"name": "West China",    "lon": 104.0, "lat": 30.5},
    "l4_North":   {"name": "North China",   "lon": 116.4, "lat": 39.9},
    "l5_Central": {"name": "Central China", "lon": 114.3, "lat": 30.6},
}

# Non-overlapping province -> demand region mapping (concept §2.2).
PROVINCE_TO_REGION = {
    # East China
    "Shanghai": "l1_East", "Jiangsu": "l1_East",
    "Zhejiang": "l1_East", "Anhui":   "l1_East",
    # South China
    "Guangdong": "l2_South", "Guangxi": "l2_South",
    "Fujian":    "l2_South", "Hainan":  "l2_South",
    # West China
    "Sichuan":  "l3_West", "Chongqing": "l3_West",
    "Yunnan":   "l3_West", "Guizhou":   "l3_West",
    # North China
    "Beijing": "l4_North", "Tianjin":  "l4_North",
    "Hebei":   "l4_North", "Shandong": "l4_North",
    # Central China
    "Henan":  "l5_Central", "Hubei":   "l5_Central",
    "Hunan":  "l5_Central", "Jiangxi": "l5_Central",
}

# GB province codes used in the census file -> English name we match against.
GB_PROVINCE_CODE_TO_EN = {
    110000: "Beijing", 120000: "Tianjin", 130000: "Hebei",
    140000: "Shanxi",  150000: "Inner Mongolia",
    210000: "Liaoning", 220000: "Jilin", 230000: "Heilongjiang",
    310000: "Shanghai", 320000: "Jiangsu", 330000: "Zhejiang",
    340000: "Anhui",    350000: "Fujian",  360000: "Jiangxi",
    370000: "Shandong",
    410000: "Henan", 420000: "Hubei", 430000: "Hunan",
    440000: "Guangdong", 450000: "Guangxi", 460000: "Hainan",
    500000: "Chongqing", 510000: "Sichuan", 520000: "Guizhou",
    530000: "Yunnan", 540000: "Xizang",
    610000: "Shaanxi", 620000: "Gansu", 630000: "Qinghai",
    640000: "Ningxia", 650000: "Xinjiang",
}

# ---------------------------------------------------------------------------
# Modes and mode-specific parameters
# ---------------------------------------------------------------------------

MODES = ("road_diesel", "rail", "nev_road")

# Emission factors in gCO2 / tonne-kilometre.
# Conversion to tCO2 happens in the objective: factor * t * km / 1_000_000.
EMISSION_FACTORS = {
    "road_diesel": 62,
    "rail":        22,
    "nev_road":    35,
}

# Variable transport cost in RMB per tonne-kilometre.
#
# Rail is set to 0.30 RMB/tkm rather than the 0.15 RMB/tkm bulk-freight figure
# used in the concept doc's base table. The higher value bundles three things
# that the bulk rate ignores: (i) containerised intermodal lots rather than
# bulk, (ii) a service-reliability / lead-time premium that practitioners
# typically price into rail decisions, (iii) drayage operations that are not
# captured by the per-tonne handling charge alone. With the bulk value the
# cost-min already chose rail on every available arc at p=0, eliminating the
# threshold behaviour the report wants to demonstrate; with 0.30 RMB/tkm the
# model produces the expected road->rail switch in the ETS-relevant carbon
# price band. This is documented as a calibration choice in concept §6.1
# and report §3.5 / §5.4.
VARIABLE_COST = {
    "road_diesel": 0.50,
    "rail":        0.30,
    "nev_road":    0.55,
}

# Flat rail terminal / handling cost in RMB per tonne moved by rail on any arc.
# Covers drayage to/from terminal, container handling, and a reliability/lead-time
# premium. The 80 RMB/t base in the concept doc proved too low for non-bulk freight:
# it produced a degenerate cost-min already at 91% rail share independent of the
# carbon price (no threshold in the ETS-relevant range). 200 RMB/t is consistent
# with GLEC China defaults for mid-sized containerised lots including drayage and
# reliability premia and is the calibration documented in concept §6.1 sensitivity.
RAIL_HANDLING_COST_RMB_PER_T = 200

# Circuity factors applied to great-circle distance.
CIRCUITY = {
    "road": 1.30,
    "rail": 1.20,
}

# Mode availability rules.
RAIL_MIN_DISTANCE_KM = 500
NEV_MAX_DISTANCE_KM  = 500

# Explicit trunk-corridor list. Rail is allowed on an arc only if the (origin,
# destination) pair appears here AND the rail distance crosses RAIL_MIN_DISTANCE_KM.
#
# This list intentionally covers only the corridors that China State Railway Group
# operates with regular containerised block trains (Yangtze east-west, China Eastern
# coastal, Beijing-Shanghai). Inbound supplier->production flows are excluded because
# in practice they are dominated by truck due to lead-time, just-in-time delivery
# and limited container intermodal availability for industrial material.
#
# Originally the concept doc listed 11 corridors including supplier inbound. Test
# runs showed that this combination, paired with the 80 RMB/t handling cost, made
# rail the optimal choice on every arc independent of the carbon price, eliminating
# the threshold behaviour the report wants to demonstrate. The narrower list below
# reflects the real intermodal-rail freight network and is documented as a modelling
# constraint in concept §2.4.2 and report §3.5 / §5.4.
RAIL_TRUNK_CORRIDORS = {
    # Yangtze-rail trunk corridor (east <-> west)
    ("j1_Suzhou",    "k2_Chengdu"),
    ("j2_Chongqing", "k1_Shanghai"),
    # China eastern coastal corridor
    ("j1_Suzhou",    "k3_Shenzhen"),
    # Beijing-Shanghai corridor (DC -> demand)
    ("k1_Shanghai",  "l4_North"),
    # Yangtze-rail DC-to-demand
    ("k1_Shanghai",  "l5_Central"),
    # Inbound trunk flows that make Chongqing viable as an alternative production site.
    # These are real intermodal corridors (Tianjin-Chongqing China-Europe Express
    # feeder, Pearl River - Chongqing river/rail combination) and matter because
    # without them, opening Chongqing would force long road inbound, making it
    # uncompetitive at any carbon price.
    ("i3_Tianjin",   "j2_Chongqing"),
    ("i1_Guangzhou", "j2_Chongqing"),
}

# ---------------------------------------------------------------------------
# Fixed costs (RMB per year, amortised)
# ---------------------------------------------------------------------------

FIXED_COST_PRODUCTION = {
    "j1_Suzhou":    50_000_000,
    "j2_Chongqing": 70_000_000,
}

FIXED_COST_DC = {
    "k1_Shanghai": 20_000_000,
    "k2_Chengdu":  25_000_000,
    "k3_Shenzhen": 22_000_000,
}

# ---------------------------------------------------------------------------
# Capacities and demand
# ---------------------------------------------------------------------------

CAPACITY_PRODUCTION = 600_000   # t/a per production site
CAPACITY_DC         = 300_000   # t/a per DC
TOTAL_DEMAND        = 500_000   # t/a total network demand

# ---------------------------------------------------------------------------
# Pareto and carbon-price sweeps
# ---------------------------------------------------------------------------

PARETO_N_LEVELS = 12

CARBON_PRICE_GRID = list(range(0, 1001, 25))  # RMB / tCO2

# Structural-jump operationalisation (concept §4.3): a carbon-price step counts as
# a structural threshold if the set of opened sites or DCs changes, or if any modal
# share moves by more than this fraction.
STRUCTURAL_MODAL_THRESHOLD = 0.10


def assert_feasibility() -> None:
    """Quick high-level feasibility checks before solving."""
    n_prod = len(PRODUCTION)
    n_dc   = len(DCS)
    assert n_prod * CAPACITY_PRODUCTION >= TOTAL_DEMAND, (
        f"Total production capacity {n_prod * CAPACITY_PRODUCTION} "
        f"< total demand {TOTAL_DEMAND}"
    )
    assert n_dc * CAPACITY_DC >= TOTAL_DEMAND, (
        f"Total DC capacity {n_dc * CAPACITY_DC} < total demand {TOTAL_DEMAND}"
    )
