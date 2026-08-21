# Deploying fair_online to PythonAnywhere (fairmodel.net)

This folder is a complete, self-contained Flask application, also published
at [github.com/chrisroadmap/fair_online](https://github.com/chrisroadmap/fair_online).
Everything it needs — the FaIR model, the calibrated climate parameters, and
the emissions data — is bundled inside `data/` and `static/`, so it does not
need internet access at runtime.

Paths below assume PythonAnywhere username `chrisroadmap` and that the repo
is cloned to `/home/chrisroadmap/fair_online` — adjust if you put it
somewhere else.

## 1. Get the code onto PythonAnywhere

Since your domain already points at a placeholder web app, you'll be
replacing that app's code rather than creating a new one. Because this is
now a real git repo, cloning it directly is cleaner than uploading a zip —
it also makes step 5 (updating later) a one-line `git pull`.

1. Log in to [pythonanywhere.com](https://www.pythonanywhere.com) and open a
   **Bash console** (Dashboard → New console → Bash).
2. Clone the repo:

   ```bash
   cd ~
   git clone https://github.com/chrisroadmap/fair_online.git
   ```

> **Note on old files in this repo:** if `fair_online/` also still has an
> older `flask_app.py` / `config.cfg` / RCP-and-matplotlib prototype in it
> from before, that's harmless — the WSGI file below imports specifically
> from `app.py` (the current Flask app in this bundle), so the old files
> just sit there unused. Worth deleting them at some point to avoid future
> confusion, but not required for this to work.

## 2. Create a virtualenv and install dependencies

`fair` (the climate model package) supports Python 3.8–3.12, so pick a
3.10/3.11/3.12 interpreter when creating the virtualenv (check what's
available with `python3.11 --version`, etc.).

**Use the built-in `venv` module rather than `mkvirtualenv`** —
`virtualenvwrapper`'s `mkvirtualenv` has been producing broken environments
on PythonAnywhere recently (pip failing with an `ImportError` on
`_posixsubprocess` before it even gets to installing anything, which isn't
related to this app — it means the environment itself didn't set up right):

```bash
python3.11 -m venv ~/.virtualenvs/fair_online-env
source ~/.virtualenvs/fair_online-env/bin/activate
pip install --upgrade pip
pip install -r /home/chrisroadmap/fair_online/requirements.txt
```

This installs Flask, the `fair` model, numpy, scipy and pandas. It should
take a minute or two. If you still hit the same `_posixsubprocess` error
here, run `python3.11 -c "import subprocess"` on its own first — if *that*
fails too, the base `python3.11` on your account is the problem, and it's
worth trying `python3.10` or `python3.12` instead, or reaching out to
PythonAnywhere support.

## 3. Point your web app at this code

1. Go to the **Web** tab in the PythonAnywhere dashboard and open the web app
   that's already configured for **fairmodel.net**.
2. Under **Virtualenv**, enter:
   `/home/chrisroadmap/.virtualenvs/fair_online-env`
3. Under **Code**, set:
   - **Source code**: `/home/chrisroadmap/fair_online`
   - **Working directory**: `/home/chrisroadmap/fair_online`
4. Click the **WSGI configuration file** link (still on the Web tab) and
   replace its entire contents with:

   ```python
   import sys

   path = '/home/chrisroadmap/fair_online'
   if path not in sys.path:
       sys.path.insert(0, path)

   from app import app as application
   ```

5. Under **Static files**, add an entry mapping URL `/static/` to directory
   `/home/chrisroadmap/fair_online/static` — this lets PythonAnywhere serve
   `plotly.min.js`, `style.css` and `app.js` directly (faster than going
   through Flask), though the app works fine without this too.
6. Click the big green **Reload** button at the top of the Web tab.

## 4. Check it

Visit **https://fairmodel.net** — you should see the dashboard load, and
clicking "Run scenario" should populate the charts within a second or two.

If something goes wrong, the **Error log** and **Server log** links on the
Web tab are the first place to look. Common issues:

- **Import error for `fair`, `flask`, `numpy` etc.** — the virtualenv path
  on the Web tab doesn't match where you ran `pip install`. Re-check step 3.
- **`_posixsubprocess` / pip crashes while installing** — see the note at
  the end of step 2; recreate the venv with `python3.11 -m venv` rather than
  `mkvirtualenv`.
- **"iirf_0 nan" or similar model errors** — make sure the whole `data/`
  folder made it into the clone (it should contain
  `species_configs_properties.csv`, `central_config.csv`,
  `emissions.csv`, `natural_forcing.csv`, `climate_meta.json`).
- **Blank page / static files 404** — double-check the static files mapping
  in step 3.5, or just make sure `templates/` and `static/` sit directly
  inside `/home/chrisroadmap/fair_online`.
- **WSGI file imports the wrong app** — if there's an old `flask_app.py`
  prototype still in the repo, make sure the WSGI file says
  `from app import app as application`, not `from flask_app import ...`.

## 5. Updating later

To ship a code change: `git pull` inside `/home/chrisroadmap/fair_online`,
then click **Reload** on the Web tab. No need to touch the WSGI file or
virtualenv again unless you add a new Python dependency (in which case
`pip install` it into `fair_online-env` first).

## About the data bundled in this app

- `data/species_configs_properties.csv`, `data/central_config.csv` — species
  and climate parameters from the **fair-calibrate v1.6.0** ensemble
  ("FASTMIP Phase 1"; CMIP7 historical forcing 1750–2023; IGCC 2024
  temperature constraints), https://doi.org/10.5281/zenodo.18828694. The
  "central" configuration is the
  per-parameter **median** across the full 841-member ensemble (each column
  of `calibrated_constrained_parameters.csv` taken at its own median,
  rather than picking one real ensemble member), which comes out to
  ECS ≈ 3.02°C, TCR ≈ 1.76°C. All `forcing_scale[...]` columns (the
  structural scaling factors on each species' forcing formula — CO2, CH4,
  N2O, the halogenated/minor GHGs, Land use, Irrigation, Volcanic, Solar)
  are forced to exactly 1.0 in this file rather than using their (typically
  close-to-but-not-exactly-1) medians, so the default run applies no
  additional forcing scaling beyond the app's own sliders.
- `data/species_defaults_merged.csv` — the per-species carbon-cycle/lifetime
  parameters (g0, g1, unperturbed lifetime, iirf terms, radiative
  efficiencies, etc.) that aren't part of the calibration ensemble. This is
  the real v1.6.0 `species_configs_properties.csv` values (verified
  complete and non-NaN for every species that needs them — CH4, N2O, all
  halogenated gases, CO2 itself), with FaIR's own bundled AR6-default file
  filling in any genuinely missing cell as a fallback (none expected in
  practice). **This replaced a real bug**: an earlier build of this pipeline
  used only FaIR's older AR6-default file for this step (carried over from
  the v1.4.1 build, where fair-calibrate's own species file left these
  blank), which silently ran every non-CO2 species on stale AR6/CMIP6-era
  lifetime parameters instead of the v1.6.0-calibrated ones — this is why
  modelled CH4 concentrations were coming out well below the observed IGCC
  2025 series (up to ~250 ppb low by 2023). Fixed now; CH4 tracks observed
  concentrations within a few percent throughout the historical record.
- `data/emissions.csv` — the 7 ScenarioMIP-CMIP7 scenario categories (VL,
  LN, L, ML, M, H, HL) used in the v1.6.0 calibration, trimmed to 1750–2100
  and converted to FaIR's native species names/units.
- `data/natural_forcing.csv` — per-scenario CMIP7 forcing timeseries for all
  four "forcing"-input-mode species in the v1.6.0 species list: Volcanic and
  Solar (scenario-invariant, reused from the v1.4.1 build), and **Land use**
  and **Irrigation** (CMIP7 per-scenario series, supplied directly by Chris).
- `data/observed_gmst.csv`, `data/observed_ghg_concentrations.csv` — the
  black observed-data overlays on the temperature and concentration charts,
  from **Indicators of Global Climate Change 2025** (Climate Indicator
  Project, https://github.com/ClimateIndicator/data): global mean surface
  temperature 1850–2025 (already baselined to the 1850–1900 mean, matching
  this app's own convention, so no rebaselining needed) and CO2/CH4/N2O
  concentrations 1750–2025 (note: only a single 1750 pre-industrial
  reference point exists before the continuous annual series picks up in
  1850 — there's a straight-line interpolation across that gap on the chart).

No external network access is required at runtime — everything the model
needs is in these bundled files.
