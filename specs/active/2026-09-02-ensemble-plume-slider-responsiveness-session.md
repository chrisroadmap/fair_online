# Ensemble uncertainty band: made the plume respond to the climate sliders

**Date:** 2026-09-02
**Status:** Active
**Project:** fair_online (FaIR climate dashboard)

## Summary

Chris reported the temperature ensemble uncertainty band (item 1, `dashboard-v2-wishlist.md`) didn't move when the ECS/ocean-heat-uptake/forcing sliders were dragged — only the central "run" line responded. Traced this to `run_scenario()`: the sliders were only ever applied to the `"run"` config; all 41 ensemble members kept their own native, unmodified calibration regardless of slider position, by original design (the spec's own comment: "not 'what if' exploration of the central estimate"). Brainstormed options, then implemented the one Chris picked: fully recompute each member's climate response and forcing strength under the same relative sliders, rather than leaving the band static or just shifting it.

Also fixed the ensemble-uncertainty performance issue Chris flagged from an earlier session first (separate, smaller task): `_apply_config_row` looped per ensemble member calling `fill()` ~87 times each (~3,900 individual xarray `.loc[]` assignments); batched into one `fill()` per parameter across all 41 members. 611ms → 350ms per ensemble-enabled call; numerically identical output, verified by full-array comparison and live `/api/run` smoke test. Committed separately as `ec750d9` before the plume-responsiveness work began.

## Decisions

Grilled in two rounds; Chris's answers in bold.

- **Core behavior (full recompute, not shift-only or fixed+labeled):** each member's climate response is rescaled by the same relative sliders the user applies to "run", not just relabeled or offset.
- **ECS rescale — relative, not absolute pin:** each member's own native ECS is scaled by the same ratio the slider applies to the central estimate (`member_target_ecs = member_native_ecs * (user_ecs / central_ecs)`), preserving each member's relative distance from the pack, rather than pinning every member to one identical absolute ECS.
- **GHG/aerosol forcing-scale sliders — multiply, not overwrite:** each member's own calibrated `forcing_scale` (e.g. CO2's varies 0.91–1.16 across the ensemble, std 0.06 — not trivially ~1.0) is multiplied by the slider value. This deliberately diverges from how `"run"` handles the same slider today (`fill(..., ghg_forcing_scale, ...)` overwrites the central row's calibrated value outright) — replicating that overwrite per-member would collapse the ensemble's forcing-scale spread to a single shared value on every request, since these sliders default to 1.0 and are always sent, never "off". Not fixing `"run"`'s overwrite behavior itself — out of scope, flagged but not touched.
- **Advanced mode (raw kappa/capacity/epsilon/forcing_4co2 entry) — ensemble stays native:** no principled absolute-vs-relative answer exists for four raw parameters at once without re-opening the ECS question per-parameter. Ensemble members keep their untouched native calibration in advanced mode; only the central line responds. Revisit later if wanted.
- **Ocean heat uptake — direct multiply, uncontroversial:** `kappa[1]`/`kappa[2]` scaled by `ocean_heat_uptake_scale` per member, mirroring exactly what `"run"` already does (this slider was already a relative multiply, not a pin, so no absolute-vs-relative choice existed here).

## Implementation

- `fair_engine.py`:
  - `_BASE_ECS` — the central member's own emergent ECS (from `climate_meta.json`'s `central_ecs`), the reference denominator for the ECS ratio.
  - `_solve_kappa0_scale_for_ecs()` — factored out of `solve_kappa0_for_ecs()`, parameterized on kappa[1,2]/capacity/epsilon/forcing_4co2 so it can solve for any member, not just the central row.
  - `_member_kappa0_scale_for_ecs(row, target_ecs)` — same solve, scaling from one ensemble member's own native kappa[0].
  - `_ENSEMBLE_NATIVE_ECS` — each member's own native emergent ECS, precomputed once at import time (41 `EnergyBalanceModel.emergent_parameters()` calls, ~13ms total, paid once not per-request).
  - `_apply_ensemble_configs_responsive()` — new function: starts from `_apply_ensemble_configs()`'s native fill, then overwrites `ocean_heat_transfer` (vectorized across all 41 members in one `fill()`, using the relative-ECS-rescaled kappa[0] plus OHU-scaled kappa[1,2]) and `forcing_scale` for CO2/other-GHG species (native × `ghg_forcing_scale`) and aerosol species (`aerosol_forcing_scale`, since no calibrated aerosol `forcing_scale` column exists — same 1.0 fallback as `"run"`).
  - `run_scenario()`: dispatches to `_apply_ensemble_configs_responsive()` when `advanced is None and ecs is not None` (the simple-slider path), else falls back to the native `_apply_ensemble_configs()` (advanced mode).
- The 41 per-member `brentq` solves stay a Python-level loop (each member's kappa0->ECS mapping is independent, not vectorizable), but the resulting `fill()` calls into xarray remain batched — kept the earlier perf fix's discipline of one assignment per parameter across all members, not one per member.

## Verification

- **Correctness:** built an unambiguous slow per-member reference implementation of the same design rules (scalar `fill()` calls, one member at a time) and diffed the *entire* `species_configs`/`climate_configs` state against the vectorized `_apply_ensemble_configs_responsive()` output for a non-trivial slider combination (ECS +1.3°C, OHU 1.15×, GHG 1.08×, aerosol 0.7×) — zero mismatches across every data variable.
- **Behavior, live through `/api/run`:** ECS 5.0 vs 2.0 (scenario M) — band shifts and widens/narrows with the line (ECS 5.0: p5/run/p95 = 2.97/4.16/4.94; ECS 2.0: 1.51/2.27/2.64 — both properly centered, wider band at higher ECS as the relative rescale implies). GHG/aerosol sliders confirmed to shift the band too. Advanced-mode run confirmed the band stays exactly at the native baseline (p5/p95 identical to a no-override run) while only the line moves.
- **Performance:** ensemble-enabled call still ~0.35–0.39s (the 41 `brentq` solves add ~10-20ms, negligible next to the batched `fill()` cost already fixed this session).

## Follow-up: always-on ensemble, median as the central line

After the responsiveness fix landed, Chris asked to remove the single-run mode entirely: always compute the ensemble, and make the temperature chart's central line the ensemble median instead of `"run"`'s own trajectory. Clarified scope first (one question): median applies to the **temperature chart only** — forcing, concentration, emissions, and the ECS/TCR diagnostic readout stay driven by the single `"run"` config exactly as before, per the wishlist's original scope ("other variables do not need uncertainties").

- `fair_engine.py`: removed the `include_ensemble` parameter from `run_scenario()` — the ensemble (`_ENSEMBLE_DF`, 41 members) always runs, always through the same responsive-vs-native dispatch (simple-slider path rescales members; advanced mode keeps them native). Replaced the `"run"`-config temperature/baseline computation with the ensemble-median block: `member_anomaly.quantile(0.50, dim="config")` is now `temperature_anomaly` (and therefore `warming_2024/2050/2100` too, since those are derived from it); `temperature_p5`/`temperature_p95` are always present in the result (no more conditional). `"run"`'s own temperature is no longer read anywhere — it's still computed as part of the same FaIR integration (can't be skipped per-config) but unused.
- `app.py`: dropped `include_ensemble` from `_parse_run_request`; removed the `has_ensemble` conditional in `/api/download`'s CSV export (band columns are now unconditional); renamed the median CSV column to `temperature_anomaly_C_rel_1850-1900_ensemble_median`.
- `templates/index.html`: removed the "Show temperature uncertainty band (~41-member ensemble, slower)" checkbox.
- `static/app.js`: removed `ensemble-toggle-chk` references (`gatherRequestBody`, `resetAllControls`); temperature chart's band traces are now unconditional (was `if (result.temperature_p5 && ...)`); renamed the central-line legend entry `"This run"` → `"Ensemble median"` and the comparison overlay `"Previous run"` → `"Previous median"` for accuracy (the field it plots is now always the median, automatically, since it's the same `temperature_anomaly` field under its new definition).

**Verification:** `run_scenario('M')` with no ensemble flag returns `temperature_p5`/`temperature_p95` unconditionally, median-based `warming_2100` (2.73°C vs. the old `"run"`-line value of ~3.07°C at defaults — expected, median of 41 members isn't the same number as one particular member's own trajectory). Live-tested `/`, `/api/run` (bare `{"scenario":"M"}` body, no ensemble param), and `/api/download` (CSV header/columns correct, band always present) through the running dev server. Cost: ~0.37s per call now that every call pays the ensemble cost — already validated acceptable in the earlier perf-fix and responsiveness work this session.

## Follow-up: ensemble subsample was biased; redrawn and re-verified against ground truth

After going always-on, Chris flagged the median run looked "a little too cool historically" at default settings. Investigated rather than assuming — this surfaced a real, separate bug plus one non-bug worth documenting.

- **Real bug, fixed:** downloaded the actual 841-member fair-calibrate posterior (`calibrated_constrained_parameters.csv`, Zenodo 10.5281/zenodo.18828694) and checked the bundled 41-member subsample's ECS/TCR distribution against it. The original stride-21 draw (documented in `fair_engine.py`'s old comment as verified "unbiased" via forcing_4co2 alone) was actually biased on ECS specifically: median 5% cool (2.835 vs true 2.990), spread 24% too narrow (std 0.736 vs true 0.972) — both directly shrink and cool-shift the temperature band. Re-drew via random sampling (2000 candidate seeds scored against the full posterior's ECS+TCR median and spread jointly, central member 1140683 still force-included); selected seed 788525 lands within ~1-3% of the true posterior on both ECS and TCR. Wrote the new `data/ensemble_members.csv`; old file backed up to session scratch (not in repo). Updated `fair_engine.py`'s explanatory comment to describe the new method and document the old one's actual (not assumed) bias.
- **Verified this fix against ground truth, not just internal consistency:** ran the *full* 841-member posterior directly through FaIR (not just checking summary stats) to get the true population median trajectory. The new 41-member resample's median (1.291°C at 2024) now closely tracks the true population's own median (1.236°C) — confirming the resample is representative, not just internally self-consistent.
- **Non-bug, investigated and closed:** even the true population median (1.236°C at 2024) sits notably below the single hand-picked "central" member (1.431°C, `climate_meta.json`'s member 1140683) and observed GMST (1.511°C at 2024). Traced this to a single-year-vs-smooth-trend artifact, not a model or sampling defect: the observed 2015-2024 decadal mean (1.231°C) matches the population median almost exactly (1.236°C) — 2023-2024 were exceptionally warm *individual* observed years (El Niño peak, post-2020 shipping-aerosol cleanup, Hunga Tonga water vapor injection) that this deterministic, emissions-only model has no mechanism to reproduce. Also sanity-checked the 1850-1900 baseline computation directly (model: 0.0001°C, observed file: 0.0002°C, matching the file's own pre-verified documentation) — ruled out as a contributor. Also noted in passing (not fixed, out of scope): the GHG-forcing slider's pre-existing overwrite-not-multiply behavior on `"run"` adds ~0.06°C to the old central line vs. that member's true native calibration — a separate, small, pre-existing quirk.
- Chris's call after seeing the decadal-average match: ship as-is, no caption/tooltip needed.

## Artifacts

- Modified `fair_engine.py`, `app.py`, `templates/index.html`, `static/app.js`, `data/ensemble_members.csv` (not yet committed as of this doc — pending).
- Commit `ec750d9` on `feature/docs-link-aerosol-display` — separate, prior perf fix (`_apply_ensemble_configs` batching), already committed.

## Context

Continuation of the same session as the `ec750d9` perf fix — both address the same ensemble-uncertainty-band feature (item 1, `dashboard-v2-wishlist.md`), diagnosed and fixed back to back. `.gitignore` and the two untracked `specs/active/*.md` session files from the prior OHU-slider session remain uncommitted and unrelated to either change, per that session's own notes.
