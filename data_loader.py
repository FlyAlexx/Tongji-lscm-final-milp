"""Build the MILP input data structure.

Responsibilities
----------------
* great-circle distance matrix per mode (with circuity factors)
* mode availability per (arc_type, origin, destination, mode)
* demand weights per region from city-level census population
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from math import asin, cos, radians, sin, sqrt

from . import params as P

ARC_TYPES = ("supplier_to_prod", "prod_to_dc", "dc_to_demand")


# ---------------------------------------------------------------------------
# Data container
# ---------------------------------------------------------------------------

@dataclass
class MILPData:
    suppliers: list
    production: list
    dcs: list
    demand_regions: list
    coords: dict           # node_id -> (lon, lat)
    demand: dict           # demand_region -> tonnes / year
    fixed_prod: dict       # production node -> RMB/year
    fixed_dc: dict         # dc node -> RMB/year
    cap_prod: float
    cap_dc: float
    distance_road: dict    # (origin, destination) -> km (road)
    distance_rail: dict    # (origin, destination) -> km (rail)
    mode_allowed: dict     # (arc_type, origin, destination, mode) -> bool
    population_by_region: dict = field(default_factory=dict)  # for the record


# ---------------------------------------------------------------------------
# Geo helpers
# ---------------------------------------------------------------------------

def haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Great-circle distance in kilometres."""
    R = 6371.0
    lon1, lat1, lon2, lat2 = map(radians, (lon1, lat1, lon2, lat2))
    dlon, dlat = lon2 - lon1, lat2 - lat1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * R * asin(sqrt(a))


def _collect_coords() -> dict:
    coords = {}
    for table in (P.SUPPLIERS, P.PRODUCTION, P.DCS, P.DEMAND_REGIONS):
        for nid, info in table.items():
            coords[nid] = (info["lon"], info["lat"])
    return coords


def _all_arcs():
    arcs = []
    for i in P.SUPPLIERS:
        for j in P.PRODUCTION:
            arcs.append(("supplier_to_prod", i, j))
    for j in P.PRODUCTION:
        for k in P.DCS:
            arcs.append(("prod_to_dc", j, k))
    for k in P.DCS:
        for l in P.DEMAND_REGIONS:
            arcs.append(("dc_to_demand", k, l))
    return arcs


def _compute_distances(coords, arcs):
    distance_road, distance_rail = {}, {}
    for _atype, o, d in arcs:
        gcd = haversine_km(*coords[o], *coords[d])
        distance_road[(o, d)] = gcd * P.CIRCUITY["road"]
        distance_rail[(o, d)] = gcd * P.CIRCUITY["rail"]
    return distance_road, distance_rail


# ---------------------------------------------------------------------------
# Mode availability
# ---------------------------------------------------------------------------

def _mode_allowed(arcs, distance_road, distance_rail) -> dict:
    """Implements concept §2.4.

    road_diesel  : always available on every arc
    rail         : in RAIL_TRUNK_CORRIDORS AND distance_rail >= RAIL_MIN_DISTANCE_KM
                   (uniform across all arc types; last-mile arcs fall out
                    automatically through the distance threshold)
    nev_road     : only on prod_to_dc and dc_to_demand arcs with distance_road
                   <= NEV_MAX_DISTANCE_KM
    """
    allowed = {}
    for atype, o, d in arcs:
        d_road = distance_road[(o, d)]
        d_rail = distance_rail[(o, d)]

        allowed[(atype, o, d, "road_diesel")] = True

        allowed[(atype, o, d, "rail")] = (
            (o, d) in P.RAIL_TRUNK_CORRIDORS
            and d_rail >= P.RAIL_MIN_DISTANCE_KM
        )

        allowed[(atype, o, d, "nev_road")] = (
            atype in ("prod_to_dc", "dc_to_demand")
            and d_road <= P.NEV_MAX_DISTANCE_KM
        )

    return allowed


# ---------------------------------------------------------------------------
# Demand from census
# ---------------------------------------------------------------------------

def _load_population_by_region() -> dict:
    """Aggregate `popu_2020` from the city census file into demand regions.

    The census file lists each city with its province code. We translate the
    province code to English via `GB_PROVINCE_CODE_TO_EN` and then aggregate
    using `PROVINCE_TO_REGION`. Provinces not in the mapping are ignored.
    """
    pops = {r: 0.0 for r in P.DEMAND_REGIONS}
    with open(P.CENSUS_FILE, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                prov_code = int(row["province_code"])
                popu_2020 = float(row["popu_2020"])
            except (ValueError, KeyError):
                continue
            en_name = P.GB_PROVINCE_CODE_TO_EN.get(prov_code)
            if not en_name:
                continue
            region = P.PROVINCE_TO_REGION.get(en_name)
            if not region:
                continue
            pops[region] += popu_2020
    return pops


def _demand_from_population(pops: dict, total_demand: float) -> dict:
    total_pop = sum(pops.values())
    if total_pop <= 0:
        raise RuntimeError("Census aggregation returned zero population")
    return {r: total_demand * pop / total_pop for r, pop in pops.items()}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def load() -> MILPData:
    P.assert_feasibility()

    coords = _collect_coords()
    arcs = _all_arcs()
    distance_road, distance_rail = _compute_distances(coords, arcs)
    mode_allowed = _mode_allowed(arcs, distance_road, distance_rail)

    pops = _load_population_by_region()
    demand = _demand_from_population(pops, P.TOTAL_DEMAND)

    return MILPData(
        suppliers=list(P.SUPPLIERS),
        production=list(P.PRODUCTION),
        dcs=list(P.DCS),
        demand_regions=list(P.DEMAND_REGIONS),
        coords=coords,
        demand=demand,
        fixed_prod=P.FIXED_COST_PRODUCTION,
        fixed_dc=P.FIXED_COST_DC,
        cap_prod=P.CAPACITY_PRODUCTION,
        cap_dc=P.CAPACITY_DC,
        distance_road=distance_road,
        distance_rail=distance_rail,
        mode_allowed=mode_allowed,
        population_by_region=pops,
    )
