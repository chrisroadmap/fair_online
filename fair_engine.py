"""Core simulation engine wrapping the FaIR simple climate model.

Loads the bundled fair-calibrate v1.6.0 data once at import time, and exposes
a single `run_scenario()` function that the Flask app calls per request.
"""
import json
import os
from functools import lru_cache

import numpy as np
import pandas as pd
from scipy.optimize import brentq

from fair import FAIR
from fair.io import read_properties
from fair.interface import fill, initialise
from fair.energy_balance_model import EnergyBalanceModel

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

SPECIES_FILE = os.path.join(DATA_DIR, "species_configs_properties.csv")
CENTRAL_CONFIG_FILE = os.path.join(DATA_DIR, "central_config.csv")
# 41-member subsample of the real fair-calibrate v1.6.0 constrained posterior
# (calibrated_constrained_parameters.csv, 841 members, Zenodo 10.5281/
# zenodo.18828694), used for the temperature ensemble uncertainty band (item
# 1 of dashboard-v2-wishlist.md). Member 1140683 (CENTRAL_CONFIG_FILE's
# "central" row is an exact match to this member) is force-included, plus 40
# more chosen by random draw (numpy Generator, seed 788525, applied to the
# 840 remaining member IDs) -- an earlier stride-21 draw looked
# representative on forcing_4co2 alone but, checked against the full
# posterior's ECS/TCR after the fact, was biased ~5% cool on median ECS and
# ~24% too narrow on ECS spread (both feed the temperature band directly).
# This seed was picked (from 2000 candidates) as the closest match to the
# full 841-member posterior's ECS and TCR median+spread simultaneously --
# resulting median/std within 1% of the true posterior on both ECS and TCR.
ENSEMBLE_MEMBERS_FILE = os.path.join(DATA_DIR, "ensemble_members.csv")
EMISSIONS_FILE = os.path.join(DATA_DIR, "emissions.csv")
NATURAL_FORCING_FILE = os.path.join(DATA_DIR, "natural_forcing.csv")
CLIMATE_META_FILE = os.path.join(DATA_DIR, "climate_meta.json")
# The species_configs "defaults" file used to seed every non-calibration-
# ensemble parameter (carbon-cycle/lifetime terms, radiative efficiencies,
# etc.): the real v1.6.0 species_configs_properties.csv values, with FaIR's
# own bundled AR6-default file filling in any genuinely missing cell (see
# prep_v160.py section 5). Species introduced in v1.6.0 that aren't in
# FaIR's older AR6 defaults (currently just "Irrigation") get an all-NaN
# fallback where the v1.6.0 file itself is also NaN -- harmless, since
# Irrigation is forcing-driven and those NaN cells are for parameters (iirf,
# radiative efficiency, etc.) that only apply to emissions/concentration-
# driven species.
SPECIES_DEFAULTS_FILE = os.path.join(DATA_DIR, "species_defaults_merged.csv")
# Observed reference series from "Indicators of Global Climate Change 2025"
# (Climate Indicator Project, https://github.com/ClimateIndicator/data),
# overplotted on the temperature and concentration charts. GMST is annual
# mean surface temperature 1850-2025, already anomalised against the
# 1850-1900 mean (verified: the mean of 1850-1900 in this file is ~0.00C),
# matching this app's own temperature baseline exactly, so no rebaselining
# is needed. Concentrations cover CO2/CH4/N2O 1750-2025, with a gap between
# the single 1750 pre-industrial reference point and the continuous annual
# series from 1850 onward (no annual data in between is published).
OBSERVED_GMST_FILE = os.path.join(DATA_DIR, "observed_gmst.csv")
OBSERVED_GHG_FILE = os.path.join(DATA_DIR, "observed_ghg_concentrations.csv")

YEAR_START = 1750
YEAR_END = 2100

SCENARIOS = {
    "VL": {
        "label": "Very Low emission scenario (VL)",
        "subtitle": "Rapid, deep mitigation, net-negative CO2 well before 2100 — roughly SSP1-1.9-like",
        "approx_2100_warming": "~1.4°C",
    },
    "LN": {
        "label": "Low-to-Negative emission scenario (LN)",
        "subtitle": "Emissions persist near mid-century, then a rapid switch to strong net-negative CO2 pulls the trajectory back down by 2100",
        "approx_2100_warming": "~1.6°C",
    },
    "L": {
        "label": "Low emission scenario (L)",
        "subtitle": "Strong mitigation, net-negative CO2 by end of century — roughly SSP1-2.6-like",
        "approx_2100_warming": "~1.7°C",
    },
    "ML": {
        "label": "Medium-to-Low emission scenario (ML)",
        "subtitle": "Substantial near-term emissions declining to net-negative CO2 by 2100",
        "approx_2100_warming": "~2.2°C",
    },
    "M": {
        "label": "Medium emission scenario (M)",
        "subtitle": "Roughly SSP2-4.5-like; emissions plateau and only decline modestly this century",
        "approx_2100_warming": "~2.8°C",
    },
    "H": {
        "label": "High emission scenario (H)",
        "subtitle": "Limited mitigation, emissions keep rising through 2100 — roughly SSP3-7.0-like",
        "approx_2100_warming": "~3.3°C",
    },
    "HL": {
        "label": "High-to-Low emission scenario (HL)",
        "subtitle": "Emissions stay high (comparable to the High pathway) through mid-century, then fall sharply toward net-zero CO2 by 2100 — a high-legacy, late-overshoot pathway",
        "approx_2100_warming": "~2.7°C",
    },
}
# Codes, ordering, and labels follow the seven ScenarioMIP-CMIP7 categories
# exactly as named in:
#   Van Vuuren, D. P., O'Neill, B. C., Tebaldi, C., et al. (2026). "The
#   Scenario Model Intercomparison Project for CMIP7 (ScenarioMIP-CMIP7)."
#   Geoscientific Model Development, 19, 2627-2656.
#   https://doi.org/10.5194/gmd-19-2627-2026
# (VL, LN, L, ML, M, H, HL), replacing the AR6 WG3 scenario names used with
# fair-calibrate v1.4.1. The "approx_2100_warming" figures are this app's own
# central-estimate run (default climate response, no user overrides) for
# each scenario, so they stay internally consistent with what the app
# actually shows -- they are not independently sourced literature values.
# Subtitles are written from inspecting each scenario's actual CO2 emissions
# trajectory (see prep_v160.py's SCENARIO_MAP), since some of the category
# names (e.g. "HL" / high-legacy) describe a near-term emissions profile
# rather than the end-of-century warming ranking -- HL's late-century
# drawdown to near net-zero CO2 by 2100 means it ends up cooler by 2100 than
# the continuously-rising "H" pathway, despite higher emissions mid-century.

# Species users are allowed to hand-edit emissions trajectories for.
EDITABLE_SPECIES = ["CO2 FFI", "CO2 AFOLU", "CH4", "N2O", "Sulfur"]
# "Other greenhouse gases" grouping used by the ghg_forcing_scale slider,
# matching the wishlist's item 5 category (CH4, N2O, and every halogenated
# species) -- kept alongside CO2 here so a single forcing_scale slider covers
# all well-mixed GHGs in one fill() call.
OTHER_GHG_SPECIES = [
    "CH4", "N2O",
    "CFC-11", "CFC-12", "CFC-113", "CFC-114", "CFC-115",
    "HCFC-22", "HCFC-141b", "HCFC-142b",
    "CCl4", "CHCl3", "CH2Cl2", "CH3Cl", "CH3CCl3", "CH3Br",
    "Halon-1211", "Halon-1301", "Halon-2402",
    "CF4", "C2F6", "C3F8", "c-C4F8", "C4F10", "C5F12", "C6F14", "C7F16", "C8F18",
    "NF3", "SF6", "SO2F2",
    "HFC-125", "HFC-134a", "HFC-143a", "HFC-152a", "HFC-227ea", "HFC-23",
    "HFC-236fa", "HFC-245fa", "HFC-32", "HFC-365mfc", "HFC-4310mee",
]
# Forcing-chart category groupings for item 5 of dashboard-v2-wishlist.md.
# "Equivalent effective stratospheric chlorine" is an input diagnostic that
# feeds the Ozone forcing calculation, not itself a forcing series in
# f.forcing -- deliberately excluded from every category below.
AEROSOL_SPECIES = ["Aerosol-radiation interactions", "Aerosol-cloud interactions"]
OTHER_ANTHRO_SPECIES = [
    "Ozone", "Stratospheric water vapour", "Land use", "Irrigation",
    "Light absorbing particles on snow and ice",
]
NATURAL_SPECIES = ["Solar", "Volcanic"]
EMISSIONS_UNITS = {
    "CO2 FFI": "Gt CO2/yr",
    "CO2 AFOLU": "Gt CO2/yr",
    "CH4": "Mt CH4/yr",
    "N2O": "Mt N2O/yr",
    "Sulfur": "Mt SO2/yr",
}
# The last year of the "common history" before scenarios diverge / user edits
# are allowed to take effect.
EDIT_ANCHOR_YEAR = 2023

with open(CLIMATE_META_FILE) as fh:
    CLIMATE_META = json.load(fh)

# ---- module-level cached data (loaded once per process) ----
_SPECIES, _PROPERTIES = read_properties(SPECIES_FILE)
_CENTRAL_ROW = pd.read_csv(CENTRAL_CONFIG_FILE, index_col=0).loc["central"]
_ENSEMBLE_DF = pd.read_csv(ENSEMBLE_MEMBERS_FILE, index_col=0)
_EMISSIONS_DF = pd.read_csv(EMISSIONS_FILE)
_EMISSIONS_DF.columns = [str(c) for c in _EMISSIONS_DF.columns]
_EMIS_YEAR_COLS = [c for c in _EMISSIONS_DF.columns if c not in ("scenario", "region", "variable", "unit")]
_EMIS_YEARS = np.array([float(c) for c in _EMIS_YEAR_COLS])

_NATURAL_DF = pd.read_csv(NATURAL_FORCING_FILE)
_NATURAL_DF.columns = [str(c) for c in _NATURAL_DF.columns]
_NAT_YEAR_COLS = [c for c in _NATURAL_DF.columns if c not in ("Scenario", "Variable", "Region", "Unit")]
_NAT_YEARS = np.array([float(c) for c in _NAT_YEAR_COLS])

_BASE_C = [_CENTRAL_ROW[f"ocean_heat_capacity[{i}]"] for i in range(3)]
_BASE_K = [_CENTRAL_ROW[f"ocean_heat_transfer[{i}]"] for i in range(3)]
_BASE_EPS = _CENTRAL_ROW["deep_ocean_efficacy"]
_BASE_F4 = _CENTRAL_ROW["forcing_4co2"]
_BASE_ECS = CLIMATE_META["central_ecs"]

_OBSERVED_GMST_DF = pd.read_csv(OBSERVED_GMST_FILE)
_OBSERVED_GHG_DF = pd.read_csv(OBSERVED_GHG_FILE)


def observed_data():
    """IGCC 2025 observed GMST (1850-2025, vs 1850-1900) and CO2/CH4/N2O
    concentrations (1750-2025), for overlaying on the model charts."""
    return {
        "gmst": {
            "years": _OBSERVED_GMST_DF["year"].tolist(),
            "values": _OBSERVED_GMST_DF["GMST"].tolist(),
        },
        "concentrations": {
            "co2": {
                "years": _OBSERVED_GHG_DF["year"].tolist(),
                "values": _OBSERVED_GHG_DF["CO2"].tolist(),
            },
            "ch4": {
                "years": _OBSERVED_GHG_DF["year"].tolist(),
                "values": _OBSERVED_GHG_DF["CH4"].tolist(),
            },
            "n2o": {
                "years": _OBSERVED_GHG_DF["year"].tolist(),
                "values": _OBSERVED_GHG_DF["N2O"].tolist(),
            },
        },
        "source": "Indicators of Global Climate Change 2025 (Climate Indicator Project)",
    }


def _emergent_ecs_tcr(kappa, capacity, epsilon, forcing_4co2):
    ebm = EnergyBalanceModel(
        ocean_heat_capacity=capacity,
        ocean_heat_transfer=kappa,
        deep_ocean_efficacy=epsilon,
        forcing_4co2=forcing_4co2,
    )
    ebm.emergent_parameters()
    return float(ebm.ecs), float(ebm.tcr)


def _solve_kappa0_scale_for_ecs(kappa1, kappa2, capacity, epsilon, forcing_4co2, target_ecs):
    """Return the scale factor on kappa[0] that gives `target_ecs`, holding
    kappa[1], kappa[2], capacity and epsilon fixed at the given values.
    Shared by the central "run" config (`solve_kappa0_for_ecs`, scaling from
    the selected central member's own kappa[0]) and, per ensemble member, by
    `_apply_ensemble_configs_responsive`.
    """

    def f(scale):
        ecs, _ = _emergent_ecs_tcr([_BASE_K[0] * scale, kappa1, kappa2], capacity, epsilon, forcing_4co2)
        return ecs - target_ecs

    return brentq(f, 0.05, 12, xtol=1e-6)


def solve_kappa0_for_ecs(target_ecs):
    """Return the scale factor on the base kappa[0] (from the selected
    central ensemble member) that gives the requested equilibrium climate
    sensitivity, holding kappa[1], kappa[2], ocean heat capacities and
    deep-ocean efficacy fixed at that member's values."""
    return _solve_kappa0_scale_for_ecs(_BASE_K[1], _BASE_K[2], _BASE_C, _BASE_EPS, _BASE_F4, target_ecs)


def _member_kappa0_scale_for_ecs(row, target_ecs):
    """Like `solve_kappa0_for_ecs`, but scales from one ensemble member's own
    native kappa[0] (via that member's own kappa[1,2]/capacity/epsilon/
    forcing_4co2 -- `_BASE_K[0]` above is a fixed reference the scale factor
    multiplies onto, so use the member's own kappa[0] instead)."""
    kappa1 = row["ocean_heat_transfer[1]"]
    kappa2 = row["ocean_heat_transfer[2]"]
    capacity = [row[f"ocean_heat_capacity[{i}]"] for i in range(3)]
    epsilon = row["deep_ocean_efficacy"]
    forcing_4co2 = row["forcing_4co2"]

    def f(scale):
        ecs, _ = _emergent_ecs_tcr([row["ocean_heat_transfer[0]"] * scale, kappa1, kappa2], capacity, epsilon, forcing_4co2)
        return ecs - target_ecs

    return brentq(f, 0.05, 12, xtol=1e-6)


# Each member's own native (unscaled) emergent ECS, precomputed once at
# import time from its own kappa/capacity/epsilon/forcing_4co2 -- used as
# the reference point for the relative ECS rescale in
# _apply_ensemble_configs_responsive (member_target_ecs = member_native_ecs
# * (user_ecs / _BASE_ECS), preserving each member's relative distance from
# the ensemble's central tendency rather than pinning every member to the
# same absolute ECS).
_ENSEMBLE_NATIVE_ECS = np.array([
    _emergent_ecs_tcr(
        [row["ocean_heat_transfer[0]"], row["ocean_heat_transfer[1]"], row["ocean_heat_transfer[2]"]],
        [row[f"ocean_heat_capacity[{i}]"] for i in range(3)],
        row["deep_ocean_efficacy"],
        row["forcing_4co2"],
    )[0]
    for _, row in _ENSEMBLE_DF.iterrows()
])


def climate_config_from_params(ecs=None, ocean_heat_uptake_scale=1.0, advanced=None):
    """Build the final (kappa, capacity, epsilon, forcing_4co2) tuple plus the
    resulting emergent ECS/TCR, from either the simple sliders (ecs +
    ocean_heat_uptake_scale) or an `advanced` dict overriding raw parameters
    directly. `advanced`, if given, takes precedence.

    ocean_heat_uptake_scale scales kappa[1] and kappa[2] (the surface<->mid
    and mid<->deep heat exchange coefficients), not ocean_heat_capacity.
    These set the fast-mode timescale that TCR is sensitive to and ECS is
    not, so the slider moves TCR over a wide range while leaving ECS fixed.
    Scaling capacity[0] instead (the previous approach) left TCR nearly flat
    across the slider's full range, since that timescale stayed far below
    the 70-year TCR window regardless."""
    kappa = list(_BASE_K)
    capacity = list(_BASE_C)
    epsilon = _BASE_EPS
    f4 = _BASE_F4

    if ecs is not None:
        scale = solve_kappa0_for_ecs(ecs)
        kappa[0] = _BASE_K[0] * scale
    kappa[1] = _BASE_K[1] * ocean_heat_uptake_scale
    kappa[2] = _BASE_K[2] * ocean_heat_uptake_scale

    if advanced:
        if "kappa" in advanced:
            kappa = list(advanced["kappa"])
        if "capacity" in advanced:
            capacity = list(advanced["capacity"])
        if "epsilon" in advanced:
            epsilon = advanced["epsilon"]
        if "forcing_4co2" in advanced:
            f4 = advanced["forcing_4co2"]

    ecs_out, tcr_out = _emergent_ecs_tcr(kappa, capacity, epsilon, f4)
    return {
        "kappa": kappa,
        "capacity": capacity,
        "epsilon": epsilon,
        "forcing_4co2": f4,
        "ecs": ecs_out,
        "tcr": tcr_out,
    }


def _base_emissions_series(scenario, specie):
    row = _EMISSIONS_DF[
        (_EMISSIONS_DF["scenario"] == scenario)
        & (_EMISSIONS_DF["variable"] == specie)
        & (_EMISSIONS_DF["region"] == "World")
    ]
    if len(row) == 0:
        return None
    return row[_EMIS_YEAR_COLS].values.squeeze().astype(float)


def _apply_emissions_override(base_vals, control_points):
    """Splice a user-edited future trajectory onto the historical portion.

    control_points: list of [year, value] pairs, year >= EDIT_ANCHOR_YEAR.
    The trajectory is held at the base (scenario) value up to and including
    EDIT_ANCHOR_YEAR, then piecewise-linearly interpolated through the user's
    control points from EDIT_ANCHOR_YEAR onward.
    """
    vals = base_vals.copy()
    anchor_val = np.interp(EDIT_ANCHOR_YEAR, _EMIS_YEARS, base_vals)
    pts_years = [EDIT_ANCHOR_YEAR] + [p[0] for p in control_points]
    pts_vals = [anchor_val] + [p[1] for p in control_points]
    order = np.argsort(pts_years)
    pts_years = np.array(pts_years)[order]
    pts_vals = np.array(pts_vals)[order]
    mask_future = _EMIS_YEARS >= EDIT_ANCHOR_YEAR
    vals[mask_future] = np.interp(_EMIS_YEARS[mask_future], pts_years, pts_vals)
    return vals


_CLIMATE_ROW_PARAMS = {
    "gamma_autocorrelation", "ocean_heat_capacity", "ocean_heat_transfer",
    "deep_ocean_efficacy", "sigma_eta", "sigma_xi", "forcing_4co2",
}


def _apply_config_row(f, row, config_name, climate=None):
    """Apply one calibration-ensemble row's species_configs and
    climate_configs values to a single named FAIR config.

    `climate` overrides the row's own (kappa, capacity, epsilon,
    forcing_4co2) -- used for the user-tunable "run" config, whose climate
    response comes from the ecs/ocean_heat_uptake_scale sliders rather than
    directly from `row`. Ensemble-member configs pass `climate=None` so each
    member keeps its own native, uncalibrated-by-the-user climate response.

    Single-config only -- for the ensemble (many rows, one call each) use
    `_apply_ensemble_configs` instead, which batches every row into one
    `fill()` per parameter rather than one per (row, parameter) pair.
    """
    for col in row.index:
        if "[" in col:
            param_name, idx = col.split("[")
            idx = idx[:-1]
        else:
            param_name, idx = col, None
        if param_name in _CLIMATE_ROW_PARAMS:
            continue  # handled below via the climate dict
        if idx is not None and idx not in _SPECIES:
            continue
        try:
            if idx is not None:
                fill(f.species_configs[param_name], row[col], specie=idx, config=config_name)
            else:
                fill(f.species_configs[param_name], row[col], config=config_name)
        except (KeyError, ValueError):
            pass

    if climate is None:
        climate = {
            "capacity": [row[f"ocean_heat_capacity[{i}]"] for i in range(3)],
            "kappa": [row[f"ocean_heat_transfer[{i}]"] for i in range(3)],
            "epsilon": row["deep_ocean_efficacy"],
            "forcing_4co2": row["forcing_4co2"],
        }
    fill(f.climate_configs["ocean_heat_capacity"], climate["capacity"], config=config_name)
    fill(f.climate_configs["ocean_heat_transfer"], climate["kappa"], config=config_name)
    fill(f.climate_configs["deep_ocean_efficacy"], climate["epsilon"], config=config_name)
    fill(f.climate_configs["forcing_4co2"], climate["forcing_4co2"], config=config_name)
    fill(f.climate_configs["gamma_autocorrelation"], row["gamma_autocorrelation"], config=config_name)
    fill(f.climate_configs["sigma_eta"], row["sigma_eta"], config=config_name)
    fill(f.climate_configs["sigma_xi"], row["sigma_xi"], config=config_name)
    fill(f.climate_configs["stochastic_run"], False, config=config_name)


def _apply_ensemble_configs(f, ensemble_df, member_configs):
    """Vectorized equivalent of calling `_apply_config_row` once per row of
    `ensemble_df`: one `fill()` per species/climate parameter across *all*
    member configs at once, instead of one `fill()` per (member, parameter)
    pair. Each `fill()` is an xarray label-based `.loc[]` assignment with
    per-call overhead that dominates when called thousands of times (41
    members x ~90 columns); batching cuts that to ~90 calls total.
    """
    for col in ensemble_df.columns:
        if "[" in col:
            param_name, idx = col.split("[")
            idx = idx[:-1]
        else:
            param_name, idx = col, None
        if param_name in _CLIMATE_ROW_PARAMS:
            continue  # handled below via climate_configs
        if idx is not None and idx not in _SPECIES:
            continue
        values = ensemble_df[col].to_numpy()
        try:
            if idx is not None:
                fill(f.species_configs[param_name], values, specie=idx, config=member_configs)
            else:
                fill(f.species_configs[param_name], values, config=member_configs)
        except (KeyError, ValueError):
            pass

    capacity = ensemble_df[[f"ocean_heat_capacity[{i}]" for i in range(3)]].to_numpy()
    kappa = ensemble_df[[f"ocean_heat_transfer[{i}]" for i in range(3)]].to_numpy()
    fill(f.climate_configs["ocean_heat_capacity"], capacity, config=member_configs)
    fill(f.climate_configs["ocean_heat_transfer"], kappa, config=member_configs)
    fill(f.climate_configs["deep_ocean_efficacy"], ensemble_df["deep_ocean_efficacy"].to_numpy(), config=member_configs)
    fill(f.climate_configs["forcing_4co2"], ensemble_df["forcing_4co2"].to_numpy(), config=member_configs)
    fill(f.climate_configs["gamma_autocorrelation"], ensemble_df["gamma_autocorrelation"].to_numpy(), config=member_configs)
    fill(f.climate_configs["sigma_eta"], ensemble_df["sigma_eta"].to_numpy(), config=member_configs)
    fill(f.climate_configs["sigma_xi"], ensemble_df["sigma_xi"].to_numpy(), config=member_configs)
    fill(f.climate_configs["stochastic_run"], False, config=member_configs)


def _apply_ensemble_configs_responsive(f, ensemble_df, member_configs, ecs, ocean_heat_uptake_scale, ghg_forcing_scale, aerosol_forcing_scale):
    """Like `_apply_ensemble_configs`, but rescales each member's climate
    response and forcing strength by the same relative sliders the user
    applied to the central "run" config, instead of leaving every member at
    its untouched native calibration -- so the temperature ensemble band
    moves and reshapes with the sliders rather than staying fixed. Only
    called for the simple-slider path (`advanced` is None); advanced mode's
    raw kappa/capacity/epsilon/forcing_4co2 entry has no principled way to
    map onto a per-member relative rescale, so the ensemble stays native
    there (see `_apply_ensemble_configs`).

    - ECS: each member's own native ECS is scaled by the same ratio the
      user's slider applies to the central estimate (`ecs / _BASE_ECS`),
      preserving each member's relative distance from the pack rather than
      pinning every member to one absolute ECS. Requires one `brentq` solve
      per member (~0.3ms each, ~13ms total for 41 members) since each
      member's kappa[0]->ECS mapping depends on its own kappa[1,2]/capacity/
      epsilon/forcing_4co2.
    - Ocean heat uptake: kappa[1]/kappa[2] scaled directly (mirrors "run" --
      already a relative multiply there, no solving needed).
    - GHG/aerosol forcing scale: each member's own native forcing_scale is
      multiplied by the slider (preserves inter-member calibration spread on
      this term). This intentionally differs from "run", which overwrites
      forcing_scale with the slider value outright rather than multiplying
      -- replicating that overwrite here would collapse the ensemble's
      forcing_scale spread to zero on every request (ghg_forcing_scale/
      aerosol_forcing_scale default to 1.0 and are always sent, never "off").
    """
    _apply_ensemble_configs(f, ensemble_df, member_configs)

    ecs_ratio = ecs / _BASE_ECS
    member_target_ecs = _ENSEMBLE_NATIVE_ECS * ecs_ratio
    kappa0_scales = np.array([
        _member_kappa0_scale_for_ecs(row, target_ecs)
        for (_, row), target_ecs in zip(ensemble_df.iterrows(), member_target_ecs)
    ])
    new_kappa0 = ensemble_df["ocean_heat_transfer[0]"].to_numpy() * kappa0_scales
    new_kappa12 = ensemble_df[["ocean_heat_transfer[1]", "ocean_heat_transfer[2]"]].to_numpy() * ocean_heat_uptake_scale
    new_kappa = np.column_stack([new_kappa0, new_kappa12])
    fill(f.climate_configs["ocean_heat_transfer"], new_kappa, config=member_configs)

    for specie in ["CO2"] + OTHER_GHG_SPECIES:
        native = ensemble_df[f"forcing_scale[{specie}]"].to_numpy()
        fill(f.species_configs["forcing_scale"], native * ghg_forcing_scale, specie=specie, config=member_configs)
    for aero_specie in AEROSOL_SPECIES:
        # No calibrated forcing_scale column exists for aerosol species (same
        # as the central row -- see run_scenario's `.get(..., 1.0)` fallback),
        # so every member's native base scale is 1.0, matching "run".
        fill(f.species_configs["forcing_scale"], aerosol_forcing_scale, specie=aero_specie, config=member_configs)


def run_scenario(
    scenario,
    ecs=None,
    ocean_heat_uptake_scale=1.0,
    ghg_forcing_scale=1.0,
    aerosol_forcing_scale=1.0,
    advanced=None,
    emissions_overrides=None,
    year_end=YEAR_END,
):
    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown scenario '{scenario}'")
    emissions_overrides = emissions_overrides or {}

    climate = climate_config_from_params(ecs=ecs, ocean_heat_uptake_scale=ocean_heat_uptake_scale, advanced=advanced)

    # The 41-member ensemble always runs -- there is no single-run mode. The
    # displayed central temperature line is the ensemble median (see below),
    # not "run"'s own trajectory; "run" itself is still computed and used
    # for forcing/concentration/emissions/ecs-tcr, which stay single-config
    # per the wishlist's original scope ("other variables do not need
    # uncertainties").
    member_configs = [f"ens_{member_id}" for member_id in _ENSEMBLE_DF.index]
    configs = ["run"] + member_configs

    f = FAIR(ch4_method="thornhill2021")
    f.define_time(YEAR_START, year_end, 1)
    f.define_scenarios([scenario])
    f.define_configs(configs)
    f.define_species(_SPECIES, _PROPERTIES)
    f.allocate()

    # Start from fair's own bundled AR6 default species configs (this is the
    # file that has sensible numeric values for every species, including the
    # iirf/lifetime-feedback terms the fair-calibrate metadata file leaves
    # blank), re-indexed onto our full v1.6.0 species list. The
    # fair-calibrate ensemble-member values applied next override CO2's
    # carbon-cycle feedback, aerosol radiative efficiencies, and the climate
    # response parameters on top of this baseline, per config.
    f.fill_species_configs(SPECIES_DEFAULTS_FILE)
    # Central "run" config: fair-calibrate's central-member species-level
    # params, with climate response coming from the user's ecs/
    # ocean_heat_uptake_scale/advanced sliders rather than directly from
    # _CENTRAL_ROW.
    _apply_config_row(f, _CENTRAL_ROW, "run", climate=climate)
    # Ensemble-member configs. Batched across all members at once (see
    # _apply_ensemble_configs) -- looping _apply_config_row per row was the
    # dominant cost of an ensemble run (thousands of single-value xarray
    # .loc[] assignments).
    #
    # In the simple-slider path (advanced is None, ecs given), each member's
    # climate response and forcing strength is rescaled by the same relative
    # factors applied to "run", so the ensemble (and its median) moves with
    # the sliders instead of staying fixed (see
    # _apply_ensemble_configs_responsive). In advanced mode there's no
    # principled per-member rescale for raw kappa/capacity/epsilon entry, so
    # members keep their native, untouched calibration -- real
    # fair-calibrate structural/parametric uncertainty around whatever the
    # advanced panel's climate response currently produces.
    if advanced is None and ecs is not None:
        _apply_ensemble_configs_responsive(
            f, _ENSEMBLE_DF, member_configs,
            ecs=climate["ecs"],
            ocean_heat_uptake_scale=ocean_heat_uptake_scale,
            ghg_forcing_scale=ghg_forcing_scale,
            aerosol_forcing_scale=aerosol_forcing_scale,
        )
    else:
        _apply_ensemble_configs(f, _ENSEMBLE_DF, member_configs)

    fill(f.species_configs["forcing_scale"], ghg_forcing_scale, specie=["CO2"] + OTHER_GHG_SPECIES, config="run")
    for aero_specie in ("Aerosol-radiation interactions", "Aerosol-cloud interactions"):
        base_scale = _CENTRAL_ROW.get(f"forcing_scale[{aero_specie}]", 1.0)
        fill(f.species_configs["forcing_scale"], base_scale * aerosol_forcing_scale, specie=aero_specie, config="run")

    emissions_echo = {}
    for specie in _SPECIES:
        if _PROPERTIES[specie]["input_mode"] != "emissions":
            continue
        base_vals = _base_emissions_series(scenario, specie)
        if base_vals is None:
            continue
        if specie in emissions_overrides:
            vals = _apply_emissions_override(base_vals, emissions_overrides[specie])
        else:
            vals = base_vals
        interp = np.interp(f.timepoints, _EMIS_YEARS, vals)
        fill(f.emissions, interp[:, None], specie=specie, scenario=scenario)
        if specie in EDITABLE_SPECIES:
            emissions_echo[specie] = interp.tolist()

    # FaIR requires every "forcing"-input-mode species to have a fully
    # non-NaN forcing timeseries (it raises ValueError otherwise), so every
    # such species must be explicitly filled here -- there's no "leave it
    # NaN and let nansum ignore it" option, unlike emissions/concentration
    # species. All four "forcing"-input-mode species in the v1.6.0 species
    # list -- Volcanic, Solar, Land use, and Irrigation (new in v1.6.0; Land
    # use was "calculated" from AFOLU emissions in v1.4.1, Irrigation didn't
    # exist at all) -- are covered by CMIP7 per-scenario timeseries bundled
    # in natural_forcing.csv. The zero-fill fallback below is now just a
    # safety net in case a species is ever added here without bundled data.
    for specie in _SPECIES:
        if _PROPERTIES[specie]["input_mode"] != "forcing":
            continue
        row = _NATURAL_DF[(_NATURAL_DF["Scenario"] == scenario) & (_NATURAL_DF["Variable"] == specie)]
        if len(row) == 0:
            fill(f.forcing, 0.0, specie=specie, scenario=scenario)
            continue
        vals = row[_NAT_YEAR_COLS].values.squeeze().astype(float)
        interp = np.interp(f.timebounds, _NAT_YEARS, vals)
        fill(f.forcing, interp[:, None], specie=specie, scenario=scenario)

    # Every species that carries a tracked atmospheric concentration (all
    # greenhouse gases, plus the derived EESC index used in ozone/CH4
    # chemistry) needs its pre-industrial concentration set as the t=0
    # boundary condition, or its forward integration is undefined (NaN) from
    # the very first step. Species without a concentration state (aerosols,
    # forcing-driven categories) have baseline_concentration == NaN and are
    # correctly skipped. baseline_concentration is itself a per-config
    # calibrated value (e.g. pre-industrial CO2 varies member to member), so
    # this must be set per config, not just once from "run" and broadcast.
    # Vectorized across every config and specie in one assignment -- NaN
    # entries (species with no concentration state) pass straight through,
    # since f.concentration is already all-NaN at this point (f.allocate()'s
    # default fill), so writing NaN is a no-op identical to skipping it.
    baseline_conc = f.species_configs["baseline_concentration"].sel(config=configs)
    f.concentration.loc[dict(timebounds=f.timebounds[0], scenario=scenario, config=configs)] = baseline_conc.values
    initialise(f.forcing, 0)
    initialise(f.temperature, 0)
    initialise(f.cumulative_emissions, 0)
    initialise(f.airborne_emissions, 0)

    f.run(progress=False)

    years = f.timebounds

    forcing_total = f.forcing_sum.sel(scenario=scenario, config="run").values
    conc_co2 = f.concentration.sel(scenario=scenario, config="run", specie="CO2").values
    conc_ch4 = f.concentration.sel(scenario=scenario, config="run", specie="CH4").values
    conc_n2o = f.concentration.sel(scenario=scenario, config="run", specie="N2O").values

    def forcing_of(specie):
        sel = f.forcing.sel(scenario=scenario, config="run", specie=specie)
        if isinstance(specie, list):
            sel = sel.sum("specie")
        return sel.values

    forcing_co2 = forcing_of("CO2")
    forcing_other_ghg = forcing_of(OTHER_GHG_SPECIES)
    forcing_aerosol = forcing_of(AEROSOL_SPECIES)
    forcing_other_anthro = forcing_of(OTHER_ANTHRO_SPECIES)
    forcing_natural = forcing_of(NATURAL_SPECIES)
    assert np.allclose(
        forcing_co2 + forcing_other_ghg + forcing_aerosol + forcing_other_anthro + forcing_natural,
        forcing_total,
    ), "5-category forcing breakdown does not sum to forcing_sum"

    # Central temperature line is the ensemble median, not "run"'s own
    # trajectory -- there is no single-run temperature mode. Each member's
    # anomaly is relative to its own 1850-1900 mean, matching the pre-median
    # convention used elsewhere in this app. Uncertainty band (p5/p95)
    # covers temperature only, per the wishlist's original scope; forcing
    # and concentration charts stay single-config ("run").
    member_temp = f.temperature.sel(scenario=scenario, config=member_configs, layer=0)
    member_baseline = member_temp.sel(timebounds=slice(1850, 1900)).mean("timebounds")
    member_anomaly = member_temp - member_baseline
    temp_anomaly = member_anomaly.quantile(0.50, dim="config").values
    temperature_p5 = member_anomaly.quantile(0.05, dim="config").values.tolist()
    temperature_p95 = member_anomaly.quantile(0.95, dim="config").values.tolist()

    result = {
        "years": years.tolist(),
        "temperature_anomaly": temp_anomaly.tolist(),
        "forcing_total": forcing_total.tolist(),
        "temperature_p5": temperature_p5,
        "temperature_p95": temperature_p95,
        "forcing_co2": forcing_co2.tolist(),
        "forcing_other_ghg": forcing_other_ghg.tolist(),
        "forcing_aerosol": forcing_aerosol.tolist(),
        "forcing_other_anthro": forcing_other_anthro.tolist(),
        "forcing_natural": forcing_natural.tolist(),
        "concentration_co2": conc_co2.tolist(),
        "concentration_ch4": conc_ch4.tolist(),
        "concentration_n2o": conc_n2o.tolist(),
        "emissions": emissions_echo,
        "emissions_years": f.timepoints.tolist(),
        "ecs": climate["ecs"],
        "tcr": climate["tcr"],
        "warming_2100": float(temp_anomaly[years == 2100][0]) if 2100 in years else None,
        "warming_2050": float(temp_anomaly[years == 2050][0]) if 2050 in years else None,
        "warming_2024": float(temp_anomaly[years == 2024][0]) if 2024 in years else None,
    }
    return result


@lru_cache(maxsize=1)
def aerosol_forcing_reference_wm2():
    """Mean aerosol ERF (radiation + cloud interactions) over 2005-2014 at
    aerosol_forcing_scale=1.0, used to display the aerosol slider in
    absolute W/m^2 instead of a unitless scale factor. Scenario-independent:
    aerosol-precursor emissions are identical across all 7 scenarios prior
    to 2023 (verified against data/emissions.csv), and aerosol forcing
    doesn't depend on ECS/OHU/CO2 forcing scale, so any one scenario run at
    the default climate response gives the same reference value."""
    result = run_scenario(scenario=next(iter(SCENARIOS)), aerosol_forcing_scale=1.0)
    years = np.array(result["years"])
    mask = (years >= 2005) & (years <= 2014)
    return float(np.mean(np.array(result["forcing_aerosol"])[mask]))


def list_scenarios():
    return SCENARIOS


def default_emissions_control_points(scenario, specie):
    """Return sensible default control-point years/values for the emissions
    editor, initialised from the selected preset scenario."""
    base_vals = _base_emissions_series(scenario, specie)
    control_years = [2030, 2040, 2050, 2060, 2075, 2100]
    return [[y, float(np.interp(y, _EMIS_YEARS, base_vals))] for y in control_years]
