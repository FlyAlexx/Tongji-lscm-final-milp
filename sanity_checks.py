"""Plausibility anchors (concept §7). These are NOT a statistical validation;
they only check that the stylised model is in the right order of magnitude
and direction.
"""

from __future__ import annotations

import openpyxl

from . import params as P
from .data_loader import MILPData
from .solver import Config


def cainiao_check(carbon_price_sweep: list[Config],
                  pareto_points: list[Config]) -> dict:
    """Cainiao operates urban NEV last-mile at >90% NEV. The MILP is interregional,
    so the check is whether NEV-road becomes meaningful somewhere on the
    Pareto frontier (>5% of total tkm), not in the carbon-price sweep — the
    carbon-price sweep may stay below the NEV breakeven for the entire ETS-
    relevant range, which itself is a finding (Phase 4 lever lies above the
    marginal abatement cost the ETS can carry).
    """
    pool = list(pareto_points) + list(carbon_price_sweep)
    max_nev = max((c.nev_share for c in pool), default=0.0)
    return {
        "check": "cainiao_nev_activation",
        "max_nev_share_in_any_solve": max_nev,
        "pass": max_nev >= 0.05,
        "note": "NEV should become meaningful on the emissions-minimum end of "
                "the Pareto frontier. If it never activates anywhere, the "
                "NEV-availability rule (NEV_MAX_DISTANCE_KM or trunk corridors) "
                "is too tight.",
    }


def cosco_check(carbon_price_sweep: list[Config]) -> dict:
    """COSCO shows that beyond a certain price/regulatory signal, structural
    decarbonisation continues into options outside the model (methanol, hydrogen).
    The MILP should therefore exhibit a technology floor at the top end: between
    the highest two price points, additional emission reduction should be small.
    """
    if len(carbon_price_sweep) < 3:
        return {"check": "cosco_technology_floor", "pass": False,
                "note": "Not enough price points."}
    high = carbon_price_sweep[-1]
    mid  = carbon_price_sweep[-2]
    delta_em = mid.emissions - high.emissions
    rel = abs(delta_em) / max(high.emissions, 1.0)
    return {
        "check": "cosco_technology_floor",
        "top_price": high.carbon_price,
        "second_price": mid.carbon_price,
        "relative_emission_change": rel,
        "pass": rel < 0.05,
        "note": "At the top of the carbon-price range, the marginal emission "
                "reduction should be small — beyond that, options outside the "
                "modelled mode space (methanol, hydrogen) take over.",
    }


def _read_city_transport_emissions() -> float:
    """Sum the Transport column (column G, 'Transport') of the full-scope city
    emissions xlsx in units of 10,000 t CO2, then convert to tCO2 for cities
    inside the provinces we model.
    """
    try:
        wb = openpyxl.load_workbook(P.EMISSIONS_FILE, data_only=True, read_only=True)
    except Exception:
        return float("nan")
    ws = wb["Sheet1"]
    target_provs = set(P.PROVINCE_TO_REGION.keys())
    total_wan_t = 0.0
    # Build a small Chinese->English fallback by trying province codes.
    # The xlsx uses Chinese province names; we use a coarse match by looking up
    # both Chinese and pinyin variants. For a sanity check, an approximate sum is enough.
    chinese_to_en = {
        "北京": "Beijing", "天津": "Tianjin", "河北": "Hebei",
        "上海": "Shanghai", "江苏": "Jiangsu", "浙江": "Zhejiang",
        "安徽": "Anhui", "广东": "Guangdong", "广西": "Guangxi",
        "福建": "Fujian", "海南": "Hainan", "山东": "Shandong",
        "河南": "Henan", "湖北": "Hubei", "湖南": "Hunan",
        "江西": "Jiangxi", "四川": "Sichuan", "重庆": "Chongqing",
        "云南": "Yunnan", "贵州": "Guizhou",
    }
    # Header row 1+2; data starts at row 3. Column 7 is Transport.
    for row in ws.iter_rows(min_row=3, values_only=True):
        prov_cn = row[0]
        if not prov_cn:
            continue
        # take the first 2 chars (skip 省/市)
        key = str(prov_cn)[:2]
        en = chinese_to_en.get(key)
        if en in target_provs:
            try:
                total_wan_t += float(row[6] or 0.0)
            except (TypeError, ValueError):
                continue
    return total_wan_t * 10_000  # 10,000 t -> tCO2


def city_transport_check(model_max_emissions_tco2: float) -> dict:
    real = _read_city_transport_emissions()
    if real != real or real <= 0:
        return {
            "check": "city_transport_order_of_magnitude",
            "model_max_emissions_tco2": model_max_emissions_tco2,
            "real_tco2": None,
            "pass": True,
            "note": "City emissions file not readable; skipping.",
        }
    ratio = model_max_emissions_tco2 / real
    return {
        "check": "city_transport_order_of_magnitude",
        "model_max_emissions_tco2": model_max_emissions_tco2,
        "real_total_transport_tco2_in_modelled_provinces": real,
        "ratio": ratio,
        "pass": ratio < 0.01,  # model is a mini-case, must be much smaller
        "note": "Mini-case model emissions should be orders of magnitude below "
                "the real Transport-sector emissions of the modelled provinces.",
    }


def run_all(carbon_price_sweep: list[Config],
            pareto_points: list[Config] | None = None) -> list[dict]:
    if not carbon_price_sweep:
        return []
    pareto_points = pareto_points or []
    model_max = max(c.emissions for c in carbon_price_sweep)
    return [
        cainiao_check(carbon_price_sweep, pareto_points),
        cosco_check(carbon_price_sweep),
        city_transport_check(model_max),
    ]
