# Dashboard v2: ensemble uncertainty, 2150 horizon, forcing regroup, custom uploads

**Status:** Active
**Date:** 2026-08-21
**Type:** new-feature
**Scope:** Implements the seven items in `wishlist.md` (OneDrive project folder), covering `fair_engine.py`, `app.py`, `static/app.js`, `templates/index.html`, and new bundled `data/` files.

## Testing Strategy

**Approach:** manual-verification (no test suite in this repo; verify each item against the running local dev server, comparing chart/table output before and after).

Test cases (Given/When/Then):

- **Given** the default scenario and climate response, **when** the user runs it, **then** the temperature chart shows a shaded 5th–95th percentile band in addition to the central line, and no other chart gains uncertainty bands.
- **Given** any of the 7 presets, **when** run, **then** the x-axis extends to 2150 with a physically continuous trajectory (no discontinuity at 2100).
- **Given** the aerosol slider at its default position, **when** the user reads its value, **then** it displays an absolute W/m² figure consistent with the 2005–2014 modelled average at scale=1.0, not a unitless multiplier.
- **Given** the single forcing-strength slider, **when** moved, **then** it scales CO2 forcing and all other-GHG forcing together (not CO2 alone).
- **Given** a completed run, **when** viewing the forcing breakdown chart, **then** exactly 5 series are shown (CO2, other GHGs, aerosols, other anthropogenic, natural) and they sum to the total forcing line.
- **Given** a CSV in the documented upload format, **when** the user uploads it, **then** the run uses that trajectory in place of the preset, and a malformed upload is rejected with a specific error rather than a silent fallback.
- **Given** the footer, **when** viewed, **then** it links to docs.fairmodel.net.

---

## Problem

`wishlist.md` (uploaded to the OneDrive project folder, `fair-climate-dashboard/wishlist.md`) lists seven asks for the next development stage. They range from small (a documentation link) to substantial (ensemble uncertainty, a new scenario time horizon, a file upload feature). Several require bundled data the app doesn't currently have, so this spec exists to pin down feasibility and design before touching code.

## Design

### 1. Temperature uncertainty band (5th/95th percentile)

- The bundled `data/central_config.csv` is a single per-parameter-median row — not real ensemble members, so no percentile spread can be computed from it today.
- Verified via the v1.6.0 Zenodo record (`10.5281/zenodo.18828694`) that `calibrated_constrained_parameters.csv` (the real 841-member posterior, 1.4 MB) **is** available there — the "Zenodo unreachable" blocker noted in `fair_engine.py`'s old comments no longer applies.
- Plan: bundle a subsample of that file as `data/ensemble_members.csv` (see Open Questions for size), load it alongside `central_config.csv`, and add a second FaIR run across the `config` dimension using those members (FaIR's `xr` backend already vectorizes multi-config runs — this is the intended usage pattern, not N sequential runs).
- Compute 5th/95th percentile of `temperature` across the ensemble dimension only; leave every other output (forcing, concentrations) as the single central-estimate run, per the wishlist's explicit "other variables do not need uncertainties."
- `/api/run` response gains `temperature_p5` / `temperature_p95` arrays. `app.js`'s temperature chart adds a shaded Plotly band trace between them.

### 2. Extend all scenarios to 2150

- Confirmed via the ScenarioMIP-CMIP7 paper (Van Vuuren et al., 2026) that all seven categories have a mandated extension protocol to at least 2150, using differentiated per-category methodology rather than IAM output — this is a real, citable dataset, not an extrapolation we'd be inventing ourselves.
- Not yet located: the specific published file(s) containing that 2100–2150 extension data (emissions and/or concentrations) in a form convertible to this app's existing wide CSV format. This is the one item where I stopped short of guessing — see Open Questions.
- Once sourced: extend `data/emissions.csv` and `data/natural_forcing.csv` with 2101–2150 columns per scenario, bump `YEAR_END` to 2150, and confirm the observed-data overlays (which stop at 2025) don't need special-casing on the chart's new right edge.

### 3. Aerosol forcing slider in W/m² (2005–2014 mean)

- Aerosol ERF depends only on (historical, scenario-independent) aerosol-precursor emissions and the aerosol forcing formula itself — not on ECS/TCR/OHU — so the 2005–2014 mean at `aerosol_forcing_scale=1.0` is a single fixed reference value, computable once at import time from the existing central run.
- Slider UI changes from a unitless 0.3–2.0× multiplier to an absolute W/m² range (computed as reference × [0.3, 2.0]); `app.js` converts the displayed W/m² value back to a scale factor before sending it to `/api/run`, so the wire format (`aerosol_forcing_scale`) is unchanged.

### 4. Merge the CO2 forcing slider into an all-GHG slider

- Today `co2_forcing_scale` only multiplies CO2's `forcing_scale`. Change: rename the concept (keep the wire param name `co2_forcing_scale` to avoid an unnecessary API break, or rename to `ghg_forcing_scale` — see Open Questions) and apply the same scale factor to CO2's `forcing_scale` *and* every "other greenhouse gas" species from item 5's grouping (CH4, N2O, all halogenated/minor GHGs) in one `fill()` call instead of just CO2's.
- One slider, one label ("Greenhouse gas forcing strength"), same 0.8–1.2× range as today's CO2 slider.

### 5. Regroup the forcing breakdown chart into 5 categories

- Species-to-category mapping, derived from `species_configs_properties.csv`'s full species list:
  - **CO2** — `CO2` (as today).
  - **Other greenhouse gases** — `CH4`, `N2O`, all halogenated species (`CFC-*`, `HCFC-*`, `HFC-*`, `C2F6`...`C8F18`, `NF3`, `SF6`, `SO2F2`, `CCl4`, `CHCl3`, `CH2Cl2`, `CH3Cl`, `CH3CCl3`, `CH3Br`, `Halon-*`).
  - **Aerosols** — `Aerosol-radiation interactions` + `Aerosol-cloud interactions` (unchanged from today's `forcing_aerosol`).
  - **Other anthropogenic** — `Ozone`, `Stratospheric water vapour`, `Land use`, `Irrigation`, `Light absorbing particles on snow and ice` (per the wishlist's explicit note that ozone and stratospheric water vapour belong here).
  - **Natural** — `Solar`, `Volcanic`.
  - `Equivalent effective stratospheric chlorine` is an input diagnostic (feeds the Ozone forcing calculation), not itself a forcing series in `f.forcing` — excluded from the sum, and worth a quick assertion in code that the 5 categories sum to `forcing_sum` within floating-point tolerance.
- `/api/run` response replaces `forcing_co2`/`forcing_ch4`/`forcing_n2o`/`forcing_other` with `forcing_co2`, `forcing_other_ghg`, `forcing_aerosol` (kept), `forcing_other_anthro`, `forcing_natural`. `app.js`'s forcing chart and CSV download header update to match.

### 6. User-uploadable custom emissions CSV

- "The format FaIR currently uses" is this app's own bundled `data/emissions.csv` shape: wide CSV with `scenario, region, variable, unit` columns followed by one column per year, `variable` values matching FaIR's species names (`CO2 FFI`, `CH4`, etc.) — the natural thing for a FaIR user to already have on hand, since it's the same shape as the calibration input data and RCMIP-style emissions files people already use with FaIR.
- New `POST /api/upload-emissions` accepts a CSV in that shape, validates: required species present (at minimum the 5 `EDITABLE_SPECIES`; others fall back to the selected preset), year columns parseable and covering at least `EDIT_ANCHOR_YEAR`–2100 (2150 once item 2 lands), values numeric. Returns a specific error message per failure (missing species / bad year column / non-numeric cell), never a silent fallback to defaults.
- Parsed trajectory is stored server-side keyed by a short-lived token (or round-tripped to the client and replayed in the `/api/run` body) and substituted for the preset's base emissions in `run_scenario`, upstream of the existing 2023-onward manual-edit control points (which still apply on top, if the user also drags sliders after uploading).
- Frontend: a file input in the "Custom emissions" section, next to the existing per-species edit controls.

### 7. Link to docs.fairmodel.net

- Add a link in `templates/index.html`'s header or footer to `https://docs.fairmodel.net/`. The longer-term "mini-site hosted at fairmodel.net" framing is a deployment/IA goal, not a discrete task — no code change beyond the link itself belongs in this spec; worth a one-line note in `DEPLOY.md`'s "About the data" or a new "Roadmap" section instead.

## Architecture

```
data/
  ensemble_members.csv          new — subsample of the 841-member posterior, for item 1
  emissions.csv                 extended with 2101-2150 columns, for item 2 (pending source)
  natural_forcing.csv           extended with 2101-2150 columns, for item 2 (pending source)
fair_engine.py
  run_scenario()                 add ensemble config dimension, 5-category forcing split, custom-emissions override path
  FORCING_CATEGORIES             new — species->category mapping for item 5
app.py
  /api/upload-emissions          new endpoint for item 6
static/app.js
  temperature chart               shaded p5-p95 band
  forcing chart                   5 series instead of 4
  aerosol slider                  W/m² display <-> scale-factor wire format
  ghg slider                      relabelled, same wiring
  upload UI                       new file input + error surfacing
templates/index.html
  footer                          docs.fairmodel.net link
  custom-emissions section        file upload control
```

## Out of scope

- Actually moving/rehosting the dashboard onto a `fairmodel.net` mini-site information architecture — item 7 only asks for a documentation link; the hosting/IA change is a separate future decision, not implemented here.
- Uncertainty bands on forcing or concentration charts — wishlist explicitly limits this to temperature.
- Running the full 2500 AD long-term extension some ScenarioMIP-CMIP7 modelling groups are asked to provide — wishlist asks for 2150, not 2500.

## Decisions (resolved 2026-08-21)

- **Ensemble size (item 1):** small subsample, ~30–50 members drawn from the 841-member posterior — not the full ensemble.
- **2150 extension data (item 2):** Chris has the data or knows the source; he'll point the agent at it before this item starts. Until then, item 2 is deferred — implement the other 6 items first.
- **Wire parameter naming (item 4):** rename `co2_forcing_scale` → `ghg_forcing_scale`.

## Implementation order

Agreed with Chris to build and check in one item at a time rather than all at once:

1. Item 7 — docs.fairmodel.net link (smallest, warm-up)
2. Item 3 — aerosol forcing in W/m²
3. Item 4 — merge CO2 slider into `ghg_forcing_scale`
4. Item 5 — 5-category forcing regroup
5. Item 1 — temperature ensemble uncertainty band (~30–50 members)
6. Item 6 — custom emissions CSV upload
7. Item 2 — extend to 2150 (once the data source is confirmed)
