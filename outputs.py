"""Write CSVs and plots that the report can pull from directly."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

from . import params as P
from .data_loader import MILPData
from .solver import Config

OUT = P.OUTPUT_DIR


# ---------------------------------------------------------------------------
# CSV writers
# ---------------------------------------------------------------------------

PARETO_COLUMNS = [
    "label", "carbon_price", "cost_rmb", "emissions_tco2",
    "open_sites", "open_dcs",
    "road_share", "rail_share", "nev_share",
    "tonne_km_total",
]


def _config_row(cfg: Config) -> dict:
    return {
        "label":           cfg.objective_label,
        "carbon_price":    cfg.carbon_price,
        "cost_rmb":        round(cfg.cost, 2),
        "emissions_tco2":  round(cfg.emissions, 3),
        "open_sites":      "+".join(cfg.open_sites),
        "open_dcs":        "+".join(cfg.open_dcs),
        "road_share":      round(cfg.road_share, 4),
        "rail_share":      round(cfg.rail_share, 4),
        "nev_share":       round(cfg.nev_share, 4),
        "tonne_km_total":  round(cfg.tonne_km_total, 0),
    }


def write_csv(path: Path, rows: list[dict], cols: list[str]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})


def write_pareto_csv(points: list[Config], path: Path | None = None) -> Path:
    path = path or (OUT / "pareto_frontier.csv")
    write_csv(path, [_config_row(p) for p in points], PARETO_COLUMNS)
    return path


def write_carbon_sweep_csv(sweep: list[Config], path: Path | None = None) -> Path:
    path = path or (OUT / "carbon_price_sensitivity.csv")
    write_csv(path, [_config_row(p) for p in sweep], PARETO_COLUMNS)
    return path


def write_thresholds_json(jumps: list[dict], path: Path | None = None) -> Path:
    path = path or (OUT / "thresholds.json")
    structural = [j["carbon_price"] for j in jumps]
    payload = {
        "first_threshold_RMB_per_tCO2":  structural[0] if structural else None,
        "second_threshold_RMB_per_tCO2": structural[1] if len(structural) >= 2 else None,
        "all_jumps": jumps,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return path


REPORT_COLS = [
    "scenario", "carbon_price", "cost_rmb", "emissions_tco2",
    "cost_increase_vs_baseline_pct", "emission_reduction_vs_baseline_pct",
    "open_sites", "open_dcs",
    "road_share", "rail_share", "nev_share",
]


def write_report_table(pareto_points: list[Config],
                       sweep: list[Config],
                       jumps: list[dict],
                       path: Path | None = None) -> Path:
    """Build the four-line summary table referenced in concept §5.2."""
    path = path or (OUT / "report_results_table.csv")
    if not pareto_points:
        write_csv(path, [], REPORT_COLS)
        return path

    cost_min = pareto_points[-1]  # highest emissions == cost-minimum endpoint
    em_min   = pareto_points[0]   # lowest emissions == emission-minimum endpoint

    # First-threshold scenario: configuration after first structural jump
    first_threshold_cfg = None
    if jumps:
        target_price = jumps[0]["carbon_price"]
        for cfg in sweep:
            if cfg.carbon_price == target_price:
                first_threshold_cfg = cfg
                break

    # Low-carbon network: near em_min on the Pareto frontier (penultimate point)
    low_carbon_cfg = pareto_points[1] if len(pareto_points) >= 2 else em_min

    cost_base = cost_min.cost
    em_base   = cost_min.emissions

    rows = []

    def add_row(scenario: str, cfg: Config | None):
        if cfg is None:
            return
        rows.append({
            "scenario":          scenario,
            "carbon_price":      cfg.carbon_price,
            "cost_rmb":          round(cfg.cost, 2),
            "emissions_tco2":    round(cfg.emissions, 3),
            "cost_increase_vs_baseline_pct":
                round(100 * (cfg.cost - cost_base) / cost_base, 2) if cost_base else None,
            "emission_reduction_vs_baseline_pct":
                round(100 * (em_base - cfg.emissions) / em_base, 2) if em_base else None,
            "open_sites":  "+".join(cfg.open_sites),
            "open_dcs":    "+".join(cfg.open_dcs),
            "road_share":  round(cfg.road_share, 4),
            "rail_share":  round(cfg.rail_share, 4),
            "nev_share":   round(cfg.nev_share, 4),
        })

    add_row("Cost minimum",     cost_min)
    add_row("First threshold",  first_threshold_cfg)
    add_row("Low-carbon network", low_carbon_cfg)
    add_row("Emissions minimum", em_min)

    write_csv(path, rows, REPORT_COLS)
    return path


# ---------------------------------------------------------------------------
# Plots
# ---------------------------------------------------------------------------

def plot_pareto_frontier(points: list[Config],
                         jumps: list[dict] | None = None,
                         path: Path | None = None) -> Path:
    path = path or (OUT / "pareto_frontier.png")
    fig, ax = plt.subplots(figsize=(7, 5))

    xs = [p.cost / 1e6 for p in points]
    ys = [p.emissions for p in points]
    ax.plot(xs, ys, "-o", color="#1f4e79", linewidth=2, markersize=6, label="Pareto frontier")

    # Annotate endpoints
    if points:
        ax.annotate(f" cost min\n {points[-1].emissions:.0f} tCO2",
                    (xs[-1], ys[-1]),
                    fontsize=8, va="bottom", ha="left")
        ax.annotate(f"em min\n {points[0].emissions:.0f} tCO2 ",
                    (xs[0], ys[0]),
                    fontsize=8, va="top", ha="right")

    ax.set_xlabel("Total cost (million RMB / year)")
    ax.set_ylabel("Total emissions (tCO2 / year)")
    ax.set_title("Pareto frontier — cost vs CO2 (calibrated mini-case)")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper right")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def plot_carbon_price_sensitivity(sweep: list[Config],
                                  jumps: list[dict] | None = None,
                                  path: Path | None = None) -> Path:
    path = path or (OUT / "carbon_price_sensitivity.png")
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 7), sharex=True)

    prices    = [c.carbon_price for c in sweep]
    emissions = [c.emissions for c in sweep]
    road      = [c.road_share for c in sweep]
    rail      = [c.rail_share for c in sweep]
    nev       = [c.nev_share for c in sweep]

    ax1.plot(prices, emissions, "-o", color="#1f4e79", markersize=4)
    ax1.set_ylabel("Emissions (tCO2 / year)")
    ax1.set_title("Carbon-price sweep")
    ax1.grid(True, alpha=0.3)

    ax2.stackplot(prices, road, rail, nev,
                  labels=["Road diesel", "Rail", "NEV road"],
                  colors=["#b85450", "#5b8c5a", "#446ca8"], alpha=0.85)
    ax2.set_xlabel("Carbon price (RMB / tCO2)")
    ax2.set_ylabel("Modal share (tonne-km)")
    ax2.set_ylim(0, 1)
    ax2.legend(loc="upper right")
    ax2.grid(True, alpha=0.3)

    # Mark structural jumps on both panels
    if jumps:
        for j in jumps:
            for ax in (ax1, ax2):
                ax.axvline(j["carbon_price"], color="grey", linestyle="--", alpha=0.7)

    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def plot_network_3panel(data: MILPData,
                        zone_configs: list[tuple[str, Config]],
                        path: Path | None = None) -> Path:
    path = path or (OUT / "network_transition_3panel.png")
    if len(zone_configs) < 1:
        return path

    fig, axes = plt.subplots(1, len(zone_configs),
                             figsize=(5.2 * len(zone_configs), 5),
                             sharex=True, sharey=True)
    if len(zone_configs) == 1:
        axes = [axes]

    node_color = {
        "supplier":  "#888",
        "prod":      "#446ca8",
        "dc":        "#b85450",
        "demand":    "#5b8c5a",
    }
    mode_color = {
        "road_diesel": "#b85450",
        "rail":        "#446ca8",
        "nev_road":    "#5b8c5a",
    }

    def node_type(nid: str) -> str:
        if nid in data.suppliers: return "supplier"
        if nid in data.production: return "prod"
        if nid in data.dcs: return "dc"
        return "demand"

    for ax, (label, cfg) in zip(axes, zone_configs):
        # Draw nodes
        for nid, (lon, lat) in data.coords.items():
            t = node_type(nid)
            active = (
                t == "supplier"
                or (t == "prod"   and nid in cfg.open_sites)
                or (t == "dc"     and nid in cfg.open_dcs)
                or (t == "demand")
            )
            alpha = 1.0 if active else 0.25
            ax.scatter([lon], [lat], s=120, c=node_color[t],
                       edgecolor="black", alpha=alpha, zorder=3)
            ax.annotate(nid.split("_", 1)[-1], (lon, lat),
                        textcoords="offset points", xytext=(6, 6),
                        fontsize=7, alpha=alpha)

        # Draw flows
        max_flow = max((v for v in cfg.flows.values()), default=1.0)
        for (atype, o, d, m), flow in cfg.flows.items():
            x1, y1 = data.coords[o]
            x2, y2 = data.coords[d]
            lw = 0.5 + 2.5 * flow / max_flow
            ax.plot([x1, x2], [y1, y2],
                    color=mode_color[m], alpha=0.7, linewidth=lw, zorder=2)

        ax.set_title(f"{label}\n"
                     f"cost {cfg.cost/1e6:.0f} M RMB · "
                     f"em {cfg.emissions:.0f} tCO2",
                     fontsize=10)
        ax.set_xlabel("Longitude")
        ax.grid(True, alpha=0.3)
        ax.set_xlim(95, 125)
        ax.set_ylim(18, 42)

    axes[0].set_ylabel("Latitude")

    handles = [
        mpatches.Patch(color=mode_color["road_diesel"], label="Road diesel"),
        mpatches.Patch(color=mode_color["rail"],        label="Rail"),
        mpatches.Patch(color=mode_color["nev_road"],    label="NEV road"),
    ]
    fig.legend(handles=handles, loc="lower center",
               ncol=3, bbox_to_anchor=(0.5, -0.02),
               frameon=False)
    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


# ---------------------------------------------------------------------------
# Model log
# ---------------------------------------------------------------------------

def write_model_log(data: MILPData,
                    pareto_points: list[Config],
                    sweep: list[Config],
                    jumps: list[dict],
                    sanity_results: list[dict],
                    path: Path | None = None) -> Path:
    path = path or (OUT / "model_log.txt")
    lines = []
    lines.append("LSCM Final MILP model log")
    lines.append("=========================")
    lines.append("")
    lines.append("Units: cost in RMB/year; emissions in tCO2/year; "
                 "carbon price in RMB/tCO2; tonne-km totalled over all flows.")
    lines.append("")
    lines.append(f"Nodes: {len(data.suppliers)} suppliers, "
                 f"{len(data.production)} production sites, "
                 f"{len(data.dcs)} DCs, {len(data.demand_regions)} demand regions.")
    lines.append(f"Total demand: {sum(data.demand.values()):.0f} t/a")
    lines.append("Demand by region: " + ", ".join(
        f"{r}={int(t)}" for r, t in data.demand.items()))
    lines.append("")

    n_road = sum(1 for k, v in data.mode_allowed.items() if k[3] == "road_diesel" and v)
    n_rail = sum(1 for k, v in data.mode_allowed.items() if k[3] == "rail" and v)
    n_nev  = sum(1 for k, v in data.mode_allowed.items() if k[3] == "nev_road"  and v)
    lines.append(f"Mode availability: road={n_road}, rail={n_rail}, nev={n_nev} arcs.")
    lines.append("")

    if pareto_points:
        lines.append("Pareto endpoints:")
        cm, em = pareto_points[-1], pareto_points[0]
        lines.append(f"  cost min     cost {cm.cost:>14,.0f}  em {cm.emissions:>10.1f}  "
                     f"sites {cm.open_sites}  dcs {cm.open_dcs}")
        lines.append(f"  emissions min cost {em.cost:>14,.0f}  em {em.emissions:>10.1f}  "
                     f"sites {em.open_sites}  dcs {em.open_dcs}")
        lines.append("")

    lines.append(f"Carbon-price sweep: {len(sweep)} points over "
                 f"{sweep[0].carbon_price}..{sweep[-1].carbon_price} RMB/tCO2"
                 if sweep else "Carbon-price sweep: none")
    lines.append(f"Structural jumps detected: {len(jumps)}")
    for j in jumps[:10]:
        lines.append(f"  p={j['carbon_price']:>5}  {'; '.join(j['reasons'])}")
    lines.append("")

    lines.append("Sanity checks (plausibility anchors, not validation):")
    for r in sanity_results:
        lines.append(f"  - {r['check']}: pass={r['pass']}  {r.get('note','')}")
    lines.append("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return path
