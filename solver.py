"""Solve the MILP for cost min, emissions min, epsilon-constraint sweep, and
the carbon-price sweep. Detects structural thresholds.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pulp

from . import params as P
from .data_loader import MILPData
from .model import build_model


# ---------------------------------------------------------------------------
# Solution container
# ---------------------------------------------------------------------------

@dataclass
class Config:
    cost: float
    emissions: float
    open_sites: tuple
    open_dcs: tuple
    tkm_by_mode: dict
    tonne_km_total: float
    road_share: float
    rail_share: float
    nev_share: float
    flows: dict = field(default_factory=dict)   # (arc_type, o, d, m) -> tonnes
    carbon_price: float = 0.0
    objective_label: str = ""

    def signature(self):
        """Coarse fingerprint used for de-duplication of Pareto points."""
        return (
            self.open_sites,
            self.open_dcs,
            round(self.road_share, 3),
            round(self.rail_share, 3),
            round(self.nev_share, 3),
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _arc_distance(data: MILPData, o: str, d: str, mode: str) -> float:
    return data.distance_rail[(o, d)] if mode == "rail" else data.distance_road[(o, d)]


def _extract_config(vars_, data: MILPData,
                    carbon_price: float = 0.0,
                    objective_label: str = "") -> Config:
    y, x = vars_["y"], vars_["x"]
    q, p, r = vars_["q"], vars_["p"], vars_["r"]

    open_sites = tuple(sorted(j for j, var in y.items()
                              if (var.value() or 0) > 0.5))
    open_dcs   = tuple(sorted(k for k, var in x.items()
                              if (var.value() or 0) > 0.5))

    tkm = {m: 0.0 for m in P.MODES}
    flows = {}

    def add(arc_type, flow_dict):
        for (o, d, m), v in flow_dict.items():
            flow = v.value() or 0.0
            if flow <= 0:
                continue
            dist = _arc_distance(data, o, d, m)
            tkm[m] += flow * dist
            flows[(arc_type, o, d, m)] = flow

    add("supplier_to_prod", q)
    add("prod_to_dc",       p)
    add("dc_to_demand",     r)

    total_tkm = sum(tkm.values())
    if total_tkm > 0:
        road = tkm["road_diesel"] / total_tkm
        rail = tkm["rail"]        / total_tkm
        nev  = tkm["nev_road"]    / total_tkm
    else:
        road = rail = nev = 0.0

    return Config(
        cost=pulp.value(vars_["total_cost"]),
        emissions=pulp.value(vars_["total_emissions"]),
        open_sites=open_sites,
        open_dcs=open_dcs,
        tkm_by_mode=tkm,
        tonne_km_total=total_tkm,
        road_share=road,
        rail_share=rail,
        nev_share=nev,
        flows=flows,
        carbon_price=carbon_price,
        objective_label=objective_label,
    )


def _solver():
    return pulp.PULP_CBC_CMD(msg=0)


# ---------------------------------------------------------------------------
# Public solve entry points
# ---------------------------------------------------------------------------

def solve(data: MILPData,
          objective: str,
          carbon_price: float = 0.0,
          eps_emissions: float | None = None,
          label: str = "") -> Config | None:
    prob, vars_ = build_model(
        data,
        objective=objective,
        carbon_price=carbon_price,
        eps_emissions=eps_emissions,
    )
    status = prob.solve(_solver())
    if pulp.LpStatus[status] != "Optimal":
        return None
    return _extract_config(
        vars_, data,
        carbon_price=carbon_price,
        objective_label=label or objective,
    )


# ---------------------------------------------------------------------------
# Pareto epsilon-constraint sweep
# ---------------------------------------------------------------------------

def epsilon_sweep(data: MILPData, n_levels: int | None = None) -> list[Config]:
    n = n_levels or P.PARETO_N_LEVELS
    cost_min = solve(data, "cost",      label="cost_min")
    em_min   = solve(data, "emissions", label="emissions_min")
    if cost_min is None or em_min is None:
        raise RuntimeError("Endpoint solves failed")

    e_max = cost_min.emissions
    e_min = em_min.emissions

    results = [cost_min]
    if n > 2 and e_max > e_min + 1e-6:
        for k in range(1, n - 1):
            e_k = e_min + k * (e_max - e_min) / (n - 1)
            cfg = solve(data, "epsilon",
                        eps_emissions=e_k,
                        label=f"eps_{k}")
            if cfg is not None:
                results.append(cfg)
    results.append(em_min)
    results.sort(key=lambda c: c.emissions)
    return results


def deduplicate_pareto(points: list[Config]) -> list[Config]:
    """Remove duplicate network configurations and dominated points."""
    seen = set()
    unique = []
    for p in points:
        sig = p.signature()
        if sig in seen:
            continue
        seen.add(sig)
        unique.append(p)
    # Filter dominated points (lower cost AND lower emissions exists).
    front = []
    for p in unique:
        dominated = False
        for q in unique:
            if q is p:
                continue
            if q.cost <= p.cost and q.emissions <= p.emissions \
                    and (q.cost < p.cost or q.emissions < p.emissions):
                dominated = True
                break
        if not dominated:
            front.append(p)
    front.sort(key=lambda c: c.emissions)
    return front


# ---------------------------------------------------------------------------
# Carbon-price sweep + threshold detection
# ---------------------------------------------------------------------------

def carbon_price_sweep(data: MILPData,
                       grid: list[int] | None = None) -> list[Config]:
    grid = list(grid) if grid is not None else P.CARBON_PRICE_GRID
    results = []
    for price in grid:
        cfg = solve(data, "weighted",
                    carbon_price=price,
                    label=f"weighted_p{price}")
        if cfg is not None:
            results.append(cfg)
    return results


def is_structural_jump(prev: Config, new: Config,
                       threshold: float | None = None) -> tuple[bool, list[str]]:
    threshold = threshold if threshold is not None else P.STRUCTURAL_MODAL_THRESHOLD
    reasons = []
    if prev.open_sites != new.open_sites:
        reasons.append(f"sites {prev.open_sites} -> {new.open_sites}")
    if prev.open_dcs != new.open_dcs:
        reasons.append(f"dcs {prev.open_dcs} -> {new.open_dcs}")
    if abs(new.rail_share - prev.rail_share) > threshold:
        reasons.append(f"rail {prev.rail_share:.2f}->{new.rail_share:.2f}")
    if abs(new.road_share - prev.road_share) > threshold:
        reasons.append(f"road {prev.road_share:.2f}->{new.road_share:.2f}")
    if abs(new.nev_share - prev.nev_share) > threshold:
        reasons.append(f"nev {prev.nev_share:.2f}->{new.nev_share:.2f}")
    return bool(reasons), reasons


def detect_thresholds(sweep: list[Config]) -> list[dict]:
    """Return a list of {carbon_price, reasons} for every structural jump."""
    jumps = []
    for i in range(1, len(sweep)):
        is_jump, reasons = is_structural_jump(sweep[i - 1], sweep[i])
        if is_jump:
            jumps.append({
                "carbon_price": sweep[i].carbon_price,
                "reasons": reasons,
            })
    return jumps
