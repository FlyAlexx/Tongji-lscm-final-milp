# LSCM Final MILP

A multi-objective Mixed-Integer-Linear-Program for Green Supply Chain Network
Design under China's Dual Carbon goals. Built for the Tongji University course
*Logistics and Supply Chain Management* (Prof. Zhang Jun), final project 2026.

The model traces a Pareto frontier between total supply chain cost and CO2
emissions, sweeps carbon prices in the China-ETS-relevant band, and detects
the structural thresholds at which network configuration changes.

## Result in one line

The calibrated mini-case finds a first structural threshold at **p = 25 RMB/tCO2**:
modal share moves from 26% road / 74% rail to 11% / 89%, emissions drop by 20%,
total cost rises by 0.02%. The current China-ETS-Secondary-Market spot of about
76 RMB/tCO2 (Jan 2026) sits just above this threshold. Further structural
change requires emission caps or policy acceleration, not carbon prices in the
ETS-relevant range.

## Install and run

```bash
git clone https://github.com/<your-username>/lscm-final-milp.git
cd lscm-final-milp
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m lscm_milp.run
```

Outputs land in `lscm_milp/outputs/`. To regenerate the report-ready Excel and
all figures (Pareto frontier, broken-axis carbon-price sweeps, and three
single-zone network plots), run:

```bash
python -m lscm_milp.build_excel_and_charts
```

Generated files appear in `lscm_milp/outputs/report/`.

## Module layout

```
lscm_milp/
├── params.py                   # all calibration constants
├── data_loader.py              # distances, demand from census, mode availability
├── model.py                    # PuLP MILP, both objectives + epsilon constraint
├── solver.py                   # cost-min, em-min, eps-sweep, carbon-price sweep, threshold detect
├── sanity_checks.py            # Cainiao / COSCO / city-transport plausibility anchors
├── outputs.py                  # CSVs, basic plots, model log
├── build_excel_and_charts.py   # report-ready Excel workbook + final PNG charts
├── run.py                      # entry point — runs the full pipeline
└── outputs/                    # generated outputs (gitignored if you prefer)
```

## Calibration choices

The numerical mini-case is data-grounded where open Chinese data exists and
stylised otherwise. The key calibration choices and their justifications are
in `params.py` as inline comments, and the report itself documents them in
Sections 3.5 and 5.4. Briefly:

- Demand weights come from Dong, Du & Liu (2022) China Census, mapped one-to-one
  to five non-overlapping regional clusters.
- Transport distances are great-circle distances with road circuity 1.30 and
  rail circuity 1.20.
- Emission factors follow GLEC 3.0 China defaults (road-diesel 62, rail 22,
  NEV-road 35 gCO2/tonne-km), with NEV-road derived from the 2024 China grid
  factor of 550 gCO2/kWh and a 0.06 kWh/tonne-km consumption assumption.
- Carbon prices come from ICAP for the China National ETS Secondary Market.
- Rail handling cost is set to 200 RMB/t and rail variable cost to 0.30
  RMB/tonne-km (rather than the bulk-freight defaults) to capture drayage,
  terminal access and a service-reliability premium typical for containerised
  non-bulk freight in China.
- Rail availability is restricted to seven explicit China State Railway Group
  block-train corridors (Yangtze east-west, China eastern coastal,
  Beijing-Shanghai, and two China-Europe-Express feeders into Chongqing).
- NEV-road is restricted to distances under 500 km.

## Pareto endpoints (final calibration)

| Configuration   | Cost (M RMB/year) | Emissions (tCO2/year) | Sites              | DCs | Road | Rail | NEV |
|-----------------|---:|---:|---|---|---:|---:|---:|
| Cost minimum    | 387 | 19,584 | Suzhou           | 3 | 26% | 74% |  0% |
| After threshold | 387 | 15,658 | Suzhou           | 3 | 11% | 89% |  0% |
| Low-carbon      | 390 | 14,481 | Suzhou           | 3 |  4% | 89% |  7% |
| Emissions min   | 458 | 13,971 | Suzhou+Chongqing | 3 |  3% | 83% | 15% |

## License

MIT — see `LICENSE`. The model and code may be reused, but please cite the
underlying report if you build on it in academic work.

## Citation

> Kuhne, A. (2026). *From Compliance to Competitive Edge: Green Supply Chain
> Network Design Under China's Dual Carbon Goals*. Final project, Logistics
> and Supply Chain Management, Tongji University.
