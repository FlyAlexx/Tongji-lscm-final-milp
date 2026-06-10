"""Build the multi-objective MILP in PuLP.

The model returns the LpProblem plus a dict of decision variables and the two
objective expressions (cost RMB/a, emissions tCO2/a) so the solver can build
either an epsilon-constraint or a weighted-sum formulation.
"""

from __future__ import annotations

import pulp

from . import params as P
from .data_loader import MILPData


def build_model(
    data: MILPData,
    objective: str = "cost",
    carbon_price: float = 0.0,
    eps_emissions: float | None = None,
):
    """Return (problem, vars_dict).

    objective in {"cost", "emissions", "epsilon", "weighted"}.
    - "cost"      : minimise total cost only
    - "emissions" : minimise total emissions, plus a tiny cost tiebreaker
    - "epsilon"   : minimise cost subject to total emissions <= eps_emissions
    - "weighted"  : minimise cost + carbon_price * emissions
    """
    if objective not in {"cost", "emissions", "epsilon", "weighted"}:
        raise ValueError(f"Unknown objective {objective!r}")

    prob = pulp.LpProblem("GSCND_DualCarbon", pulp.LpMinimize)

    # ------------------------------------------------------------------
    # Decision variables
    # ------------------------------------------------------------------
    y = {j: pulp.LpVariable(f"y_{j}", cat="Binary") for j in data.production}
    x = {k: pulp.LpVariable(f"x_{k}", cat="Binary") for k in data.dcs}

    # Flow vars only for allowed (arc, mode) combinations.
    q, p_var, r = {}, {}, {}

    for i in data.suppliers:
        for j in data.production:
            for m in P.MODES:
                if data.mode_allowed[("supplier_to_prod", i, j, m)]:
                    q[(i, j, m)] = pulp.LpVariable(f"q_{i}_{j}_{m}", lowBound=0)

    for j in data.production:
        for k in data.dcs:
            for m in P.MODES:
                if data.mode_allowed[("prod_to_dc", j, k, m)]:
                    p_var[(j, k, m)] = pulp.LpVariable(f"p_{j}_{k}_{m}", lowBound=0)

    for k in data.dcs:
        for l in data.demand_regions:
            for m in P.MODES:
                if data.mode_allowed[("dc_to_demand", k, l, m)]:
                    r[(k, l, m)] = pulp.LpVariable(f"r_{k}_{l}_{m}", lowBound=0)

    # ------------------------------------------------------------------
    # Cost and emissions expressions
    # ------------------------------------------------------------------
    fixed_cost = (
        pulp.lpSum(data.fixed_prod[j] * y[j] for j in data.production)
        + pulp.lpSum(data.fixed_dc[k] * x[k] for k in data.dcs)
    )

    var_cost_terms = []
    emissions_terms = []

    def arc_distance(o: str, d: str, mode: str) -> float:
        return data.distance_rail[(o, d)] if mode == "rail" else data.distance_road[(o, d)]

    def add_flow(flow_dict):
        for (o, d, m), v in flow_dict.items():
            dist = arc_distance(o, d, m)
            var_cost_terms.append(P.VARIABLE_COST[m] * dist * v)
            if m == "rail":
                var_cost_terms.append(P.RAIL_HANDLING_COST_RMB_PER_T * v)
            # gCO2/tkm * t * km = g; / 1e6 -> tCO2
            emissions_terms.append(P.EMISSION_FACTORS[m] * dist * v / 1_000_000)

    add_flow(q)
    add_flow(p_var)
    add_flow(r)

    total_cost = fixed_cost + pulp.lpSum(var_cost_terms)
    total_emissions = pulp.lpSum(emissions_terms)

    # ------------------------------------------------------------------
    # Set objective
    # ------------------------------------------------------------------
    if objective == "cost":
        prob += total_cost, "MinTotalCost"
    elif objective == "emissions":
        # Tiny cost penalty breaks ties so opening status is well-defined.
        prob += total_emissions + 1e-9 * total_cost, "MinTotalEmissions"
    elif objective == "epsilon":
        if eps_emissions is None:
            raise ValueError("epsilon objective requires eps_emissions")
        prob += total_cost, "MinCostEpsilon"
        prob += total_emissions <= eps_emissions, "EpsilonConstraint"
    else:  # weighted
        prob += total_cost + carbon_price * total_emissions, "Weighted"

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------

    # Demand satisfaction
    for l in data.demand_regions:
        prob += (
            pulp.lpSum(r[(k, l, m)] for k in data.dcs for m in P.MODES if (k, l, m) in r)
            >= data.demand[l],
            f"Demand_{l}",
        )

    # Flow balance at production: total inbound == total outbound (alpha = 1)
    for j in data.production:
        inbound = pulp.lpSum(
            q[(i, j, m)] for i in data.suppliers for m in P.MODES if (i, j, m) in q
        )
        outbound = pulp.lpSum(
            p_var[(j, k, m)] for k in data.dcs for m in P.MODES if (j, k, m) in p_var
        )
        prob += inbound == outbound, f"Bal_prod_{j}"

    # Flow balance at DC: total inbound == total outbound
    for k in data.dcs:
        inbound = pulp.lpSum(
            p_var[(j, k, m)] for j in data.production for m in P.MODES if (j, k, m) in p_var
        )
        outbound = pulp.lpSum(
            r[(k, l, m)] for l in data.demand_regions for m in P.MODES if (k, l, m) in r
        )
        prob += inbound == outbound, f"Bal_dc_{k}"

    # Production capacity (and activation): outbound <= cap * y_j
    for j in data.production:
        outbound = pulp.lpSum(
            p_var[(j, k, m)] for k in data.dcs for m in P.MODES if (j, k, m) in p_var
        )
        prob += outbound <= data.cap_prod * y[j], f"Cap_prod_{j}"

    # DC capacity (and activation): outbound <= cap * x_k
    for k in data.dcs:
        outbound = pulp.lpSum(
            r[(k, l, m)] for l in data.demand_regions for m in P.MODES if (k, l, m) in r
        )
        prob += outbound <= data.cap_dc * x[k], f"Cap_dc_{k}"

    vars_ = {
        "y": y, "x": x, "q": q, "p": p_var, "r": r,
        "total_cost": total_cost,
        "total_emissions": total_emissions,
    }
    return prob, vars_
