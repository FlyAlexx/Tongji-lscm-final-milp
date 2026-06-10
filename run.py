"""Entry point — runs the full pipeline and writes every output file.

Usage from `02 Projekte/LSCM final/`:

    python -m lscm_milp.run
"""

from __future__ import annotations

import time

from . import data_loader, sanity_checks, outputs
from .solver import (
    Config,
    carbon_price_sweep,
    deduplicate_pareto,
    detect_thresholds,
    epsilon_sweep,
)


def main() -> None:
    t0 = time.time()
    print("[1/5] Loading data ...")
    data = data_loader.load()
    print(f"      demand total = {sum(data.demand.values()):.0f} t/a "
          f"across {len(data.demand)} regions")

    print("[2/5] Epsilon-constraint Pareto sweep ...")
    pareto_all = epsilon_sweep(data)
    pareto = deduplicate_pareto(pareto_all)
    print(f"      {len(pareto_all)} raw points -> {len(pareto)} unique non-dominated")
    for p in pareto:
        print(f"      {p.objective_label:>14}  "
              f"cost={p.cost/1e6:>7.1f}M  em={p.emissions:>9.1f}  "
              f"sites={p.open_sites}  dcs={p.open_dcs}  "
              f"shares road={p.road_share:.2f} rail={p.rail_share:.2f} nev={p.nev_share:.2f}")

    print("[3/5] Carbon-price sweep ...")
    sweep = carbon_price_sweep(data)
    print(f"      {len(sweep)} price points")
    jumps = detect_thresholds(sweep)
    print(f"      {len(jumps)} structural jumps")
    for j in jumps[:10]:
        print(f"        p={j['carbon_price']:>5}  {'; '.join(j['reasons'])}")

    print("[4/5] Sanity checks ...")
    sanity = sanity_checks.run_all(sweep, pareto)
    for s in sanity:
        print(f"      {s['check']:>34}  pass={s['pass']}")

    print("[5/5] Writing outputs ...")
    outputs.write_pareto_csv(pareto_all)
    outputs.write_pareto_csv(pareto, path=outputs.OUT / "pareto_frontier_unique.csv")
    outputs.write_carbon_sweep_csv(sweep)
    outputs.write_thresholds_json(jumps)
    outputs.write_report_table(pareto, sweep, jumps)
    outputs.plot_pareto_frontier(pareto, jumps=jumps)
    outputs.plot_carbon_price_sensitivity(sweep, jumps=jumps)

    # Build the 3-panel network plot using cost-min, first-threshold (if any),
    # and emissions-min as the three representative configurations.
    cost_min = pareto[-1]
    em_min   = pareto[0]
    panels: list[tuple[str, Config]] = [("Zone 1 — cost minimum", cost_min)]
    if jumps:
        first_price = jumps[0]["carbon_price"]
        for cfg in sweep:
            if cfg.carbon_price == first_price:
                panels.append((f"Zone 2 — after first structural jump (p={first_price})", cfg))
                break
    panels.append(("Zone 3 — emissions minimum", em_min))
    outputs.plot_network_3panel(data, panels)

    outputs.write_model_log(data, pareto, sweep, jumps, sanity)

    print(f"Done in {time.time() - t0:.1f}s. Outputs in {outputs.OUT}")


if __name__ == "__main__":
    main()
