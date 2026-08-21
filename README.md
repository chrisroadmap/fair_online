# fair_online

Interactive web dashboard for the [FaIR](https://github.com/OMS-NetZero/FAIR)
simple climate model. Pick an emissions scenario, adjust climate parameters
(ECS, ocean heat uptake, forcing scales), run FaIR, and view/download the
resulting temperature and forcing pathways.

Live at [fairmodel.net](https://fairmodel.net).

## Layout

- `app.py` — Flask app (current entry point; also what `wsgi.py` serves in production)
- `fair_engine.py` — wraps `fair` v2.2.4 model runs
- `templates/index.html`, `static/{app.js,style.css,plotly.min.js}` — frontend
- `data/` — bundled calibration and emissions data (no network access needed at runtime)

`flask_app.py` and `templates/fair.html` are an older FaIR v1.x prototype,
superseded by `app.py`, and unused by `wsgi.py`.

## Local development

```bash
uv venv --python 3.12 .venv
uv pip install -r requirements.txt --python .venv/bin/python
.venv/bin/python app.py
```

Visit http://127.0.0.1:5050.

## Deployment

See [`DEPLOY.md`](DEPLOY.md) for the full PythonAnywhere setup and update procedure.

## Data & attribution

Bundled calibration data are from the **fair-calibrate v1.6.0** ensemble
("FASTMIP Phase 1" release, March 2025 — 841-member posterior, CMIP7
historical forcing through 2023, IGCC 2024 temperature constraints),
https://doi.org/10.5281/zenodo.18828694, following the
calibration/constraining methodology of Smith et al. (2024,
https://doi.org/10.5194/egusphere-2024-708),
[github.com/chrisroadmap/fair-calibrate](https://github.com/chrisroadmap/fair-calibrate).
Emissions data are the seven ScenarioMIP-CMIP7 categories (VL, LN, L, ML, M,
H, HL) from Van Vuuren et al. (2026), "The Scenario Model Intercomparison
Project for CMIP7 (ScenarioMIP-CMIP7)," *Geoscientific Model Development*,
19, 2627–2656, https://doi.org/10.5194/gmd-19-2627-2026. Climate simulation
uses the **FaIR** simple climate model
([OMS-NetZero/FAIR](https://github.com/OMS-NetZero/FAIR), `fair` package
v2.2.4).
