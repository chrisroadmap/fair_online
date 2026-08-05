"""Core simulation engine wrapping the FaIR simple climate model.

Loads the bundled fair-calibrate v1.4.1 data once at import time, and exposes
a single `run_scenario()` function that the Flask app calls per request.
"""
import json
import os

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
EMISSIONS_FILE = os.path.join(DATA_DIR, "emissions.csv")
NATURAL_FORCING_FILE = os.path.join(DATA_DIR, "natural_forcing.csv")
CLIMATE_META_FILE = os.path.join(DATA_DIR, "climate_meta.json")

YEAR_START = 1750
YEAR_END = 2100

SCENARIOS = {
    "verylow": {
        "label": "Very low emissions",
        "subtitle": "Rapid mitigation — roughly SSP1-1.9-like",
        "approx_2100_warming": "~1.7°C",
    },
    "verylow-overshoot": {
        "label": "Very low, temporary overshoot",
        "subtitle": "Peaks then declines faster than Very Low",
        "approx_2100_warming": "~2.0°C",
    },
    "low": {
        "label": "Low emissions",
        "subtitle": "Strong mitigation — roughly SSP1-2.6-like",
        "approx_2100_warming": "~2.1°C",
    },
    "medium-overshoot": {
        "label": "Medium emissions",
        "subtitle": "Roughly SSP2-4.5-like, emissions decline from mid-century",
        "approx_2100_warming": "~3.1°C",
    },
    "high-overshoot": {
        "label": "High emissions",
        "subtitle": "Limited mitigation — roughly SSP3-7.0-like",
        "approx_2100_warming": "~3.8°C",
    },
}
# "medium-extension" and "high-extension" are also in the underlying
# fair-calibrate data (identical to their "-overshoot" siblings through 2100,
# diverging only afterwards) but are omitted from the UI list since this
# dashboard's default time horizon ends in 2100.

# Species users are allowed to hand-edit emissions trajectories for.
EDITABLE_SPECIES = ["CO2 FFI", "CO2 AFOLU", "CH4", "N2O", "Sulfur"]
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


def _emergent_ecs_tcr(kappa, capacity, epsilon, forcing_4co2):
    ebm = EnergyBalanceModel(
        ocean_heat_capacity=capacity,
        ocean_heat_transfer=kappa,
        deep_ocean_efficacy=epsilon,
        forcing_4co2=forcing_4co2,
    )
    ebm.emergent_parameters()
    return float(ebm.ecs), float(ebm.tcr)


def solve_kappa0_for_ecs(target_ecs):
    """Return the scale factor on the base (multi-model) kappa[0] that gives
    the requested equilibrium climate sensitivity, holding kappa[1], kappa[2],
    ocean heat capacities and deep-ocean efficacy fixed at their central
    (fair-calibrate v1.4.1 median) values."""

    def f(scale):
        ecs, _ = _emergent_ecs_tcr([_BASE_K[0] * scale, _BASE_K[1], _BASE_K[2]], _BASE_C, _BASE_EPS, _BASE_F4)
        return ecs - target_ecs

    return brentq(f, 0.05, 12, xtol=1e-6)


def climate_config_from_params(ecs=None, ocean_heat_uptake_scale=1.0, advanced=None):
    """Build the final (kappa, capacity, epsilon, forcing_4co2) tuple plus the
    resulting emergent ECS/TCR, from either the simple sliders (ecs +
    ocean_heat_uptake_scale) or an `advanced` dict overriding raw parameters
    directly. `advanced`, if given, takes precedence."""
    kappa = list(_BASE_K)
    capacity = list(_BASE_C)
    epsilon = _BASE_EPS
    f4 = _BASE_F4

    if ecs is not None:
        scale = solve_kappa0_for_ecs(ecs)
        kappa[0] = _BASE_K[0] * scale
    capacity[0] = _BASE_C[0] * ocean_heat_uptake_scale

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


def run_scenario(
    scenario,
    ecs=None,
    ocean_heat_uptake_scale=1.0,
    co2_forcing_scale=1.0,
    aerosol_forcing_scale=1.0,
    advanced=None,
    emissions_overrides=None,
    year_end=YEAR_END,
):
    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown scenario '{scenario}'")
    emissions_overrides = emissions_overrides or {}

    climate = climate_config_from_params(ecs=ecs, ocean_heat_uptake_scale=ocean_heat_uptake_scale, advanced=advanced)

    f = FAIR(ch4_method="thornhill2021")
    f.define_time(YEAR_START, year_end, 1)
    f.define_scenarios([scenario])
    f.define_configs(["run"])
    f.define_species(_SPECIES, _PROPERTIES)
    f.allocate()

    # Start from fair's own bundled AR6 default species configs (this is the
    # file that has sensible numeric values for every species, including the
    # iirf/lifetime-feedback terms the fair-calibrate metadata file leaves
    # blank). The fair-calibrate central-ensemble-member values applied next
    # override CO2's carbon-cycle feedback, aerosol radiative efficiencies,
    # and the climate response parameters on top of this baseline.
    f.fill_species_configs()
    # apply the central-ensemble-member species-level params (radiative
    # efficiencies, iirf, aci params etc.) to our single "run" config
    for col in _CENTRAL_ROW.index:
        if "[" in col:
            param_name, idx = col.split("[")
            idx = idx[:-1]
        else:
            param_name, idx = col, None
        if param_name in ("gamma_autocorrelation", "ocean_heat_capacity", "ocean_heat_transfer", "deep_ocean_efficacy", "sigma_eta", "sigma_xi", "forcing_4co2"):
            continue  # handled below via climate dict
        if idx is not None and idx not in _SPECIES:
            continue
        try:
            if idx is not None:
                fill(f.species_configs[param_name], _CENTRAL_ROW[col], specie=idx, config="run")
            else:
                fill(f.species_configs[param_name], _CENTRAL_ROW[col], config="run")
        except (KeyError, ValueError):
            pass

    fill(f.climate_configs["ocean_heat_capacity"], climate["capacity"], config="run")
    fill(f.climate_configs["ocean_heat_transfer"], climate["kappa"], config="run")
    fill(f.climate_configs["deep_ocean_efficacy"], climate["epsilon"], config="run")
    fill(f.climate_configs["forcing_4co2"], climate["forcing_4co2"], config="run")
    fill(f.climate_configs["gamma_autocorrelation"], _CENTRAL_ROW["gamma_autocorrelation"], config="run")
    fill(f.climate_configs["sigma_eta"], _CENTRAL_ROW["sigma_eta"], config="run")
    fill(f.climate_configs["sigma_xi"], _CENTRAL_ROW["sigma_xi"], config="run")
    fill(f.climate_configs["stochastic_run"], False, config="run")

    fill(f.species_configs["forcing_scale"], co2_forcing_scale, specie="CO2", config="run")
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

    for specie, rcname in [("Volcanic", "Volcanic"), ("Solar", "Solar")]:
        row = _NATURAL_DF[(_NATURAL_DF["Scenario"] == scenario) & (_NATURAL_DF["Variable"] == rcname)]
        vals = row[_NAT_YEAR_COLS].values.squeeze().astype(float)
        interp = np.interp(f.timebounds, _NAT_YEARS, vals)
        fill(f.forcing, interp[:, None], specie=specie, scenario=scenario)

    # Every species that carries a tracked atmospheric concentration (all
    # greenhouse gases, plus the derived EESC index used in ozone/CH4
    # chemistry) needs its pre-industrial concentration set as the t=0
    # boundary condition, or its forward integration is undefined (NaN) from
    # the very first step. Species without a concentration state (aerosols,
    # forcing-driven categories) have baseline_concentration == NaN and are
    # correctly skipped.
    baseline_conc = f.species_configs["baseline_concentration"].sel(config="run")
    for specie in _SPECIES:
        val = float(baseline_conc.sel(specie=specie).values)
        if not np.isnan(val):
            initialise(f.concentration, val, specie=specie)
    initialise(f.forcing, 0)
    initialise(f.temperature, 0)
    initialise(f.cumulative_emissions, 0)
    initialise(f.airborne_emissions, 0)

    f.run(progress=False)

    years = f.timebounds
    baseline_mask = (years >= 1850) & (years <= 1900)
    temperature = f.temperature.sel(scenario=scenario, config="run", layer=0).values
    baseline = temperature[baseline_mask].mean()
    temp_anomaly = temperature - baseline

    forcing_total = f.forcing_sum.sel(scenario=scenario, config="run").values
    conc_co2 = f.concentration.sel(scenario=scenario, config="run", specie="CO2").values
    conc_ch4 = f.concentration.sel(scenario=scenario, config="run", specie="CH4").values
    conc_n2o = f.concentration.sel(scenario=scenario, config="run", specie="N2O").values

    def forcing_of(specie):
        return f.forcing.sel(scenario=scenario, config="run", specie=specie).values

    forcing_co2 = forcing_of("CO2")
    forcing_ch4 = forcing_of("CH4")
    forcing_n2o = forcing_of("N2O")
    forcing_aerosol = forcing_of("Aerosol-radiation interactions") + forcing_of("Aerosol-cloud interactions")
    forcing_other = forcing_total - forcing_co2 - forcing_ch4 - forcing_n2o - forcing_aerosol

    result = {
        "years": years.tolist(),
        "temperature_anomaly": temp_anomaly.tolist(),
        "forcing_total": forcing_total.tolist(),
        "forcing_co2": forcing_co2.tolist(),
        "forcing_ch4": forcing_ch4.tolist(),
        "forcing_n2o": forcing_n2o.tolist(),
        "forcing_aerosol": forcing_aerosol.tolist(),
        "forcing_other": forcing_other.tolist(),
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


def list_scenarios():
    return SCENARIOS


def default_emissions_control_points(scenario, specie):
    """Return sensible default control-point years/values for the emissions
    editor, initialised from the selected preset scenario."""
    base_vals = _base_emissions_series(scenario, specie)
    control_years = [2030, 2040, 2050, 2060, 2075, 2100]
    return [[y, float(np.interp(y, _EMIS_YEARS, base_vals))] for y in control_years]
