# -*- coding: utf-8 -*-

"""
Code to run the FaIR model
"""

# --- imports

# std lib imports:
import datetime
import os
import sys

# third party imports:
import numpy as np
import pandas as pd

# fair imports:
from fair import FAIR
from fair.io import read_properties
from fair.interface import fill, initialise

# local imports:
from constants import SCENARIOS, SPECIES, DEFAULT_SPECIES

# --- global variables

# known / acceptables scenarios:
SCENARIOS = SCENARIOS
# known / acceptables species:
SPECIES = SPECIES
# default selected specie:
DEFAULT_SPECIES = DEFAULT_SPECIES
# known / acceptable input paramaters:
PARAMETERS = {
    'scenarios': {
        'default': SCENARIOS,
        'known': SCENARIOS
    },
    'species': {
        'default': DEFAULT_SPECIES,
        'known': SPECIES
    }
}

# ---

def convert_numeric(value):
    """
    Try to convert a string value to an integer or float, or return
    original value
    """
    # try int first:
    try:
        value = int(value)
    except ValueError:
        # try float:
        try:
            value = float(value)
        # otherwise use original value:
        except ValueError:
            pass
    # return value:
    return value

def parse_param(param):
    """
    Parse a parameter, convert to list / numeric as required
    """
    # strip leading / trailing space:
    param = param.strip()
    # check if this is a list:
    if param.startswith('[') and param.endswith(']'):
        # convert from string to list:
        param = [
            str(i).strip().strip('"').strip("'") for i in
            param.lstrip('[').rstrip(']').split(',')
        ]
        # try numeric convert:
        param = [convert_numeric(i) for i in param]
    # else, not a list:
    else:
        # try numeric convert:
        param = convert_numeric(param)
    # return the parameter:
    return param

def check_params(request_params):
    """
    Check supplied parameters, converting values as required

    :param request_params: POST supplied parameters
    """
    # init output dict:
    user_params = {}
    # all parameters received:
    all_params = list(request_params.keys())
    # expected / known parameters:
    known_params = list(PARAMETERS.keys())
    # check for each known parameter:
    for known_param in known_params:
        # if this parameter is present:
        if known_param in all_params:
            # get requested values:
            param_in = request_params[known_param]
            # parse parameter:
            param_out = parse_param(param_in)
            # if this is a list:
            if isinstance(param_out, list):
                # check values are acceptable:
                param_out = [
                    i for i in param_out
                    if i in PARAMETERS[known_param]['known']
                ]
                # only store unique values:
                param_out = list(set(param_out))
                # if empty, return an error:
                if not param_out:
                    err_msg = 'invalid {0} parameter'.format(known_param)
                    return False, {}, err_msg
            # store the value for this parameter:
            user_params[known_param] = param_out
        else:
            # no values present for this parameter. use defaults:
            user_params[known_param] = PARAMETERS[known_param]['default']
    # return the parameters:
    return True, user_params, None

def __run_model(user_params, data_dir, out_dp=3):
    """
    Main model running function

    :param user_params: User supplied parameters
    :param data_dir: Directory containing data files
    :param out_dp: Number of decimal places for rounding output
    """
    # Init output data:
    model_data = {}
    # Initialise FaIR
    # We want to enable the methane lifetime routine that is a function of
    # SLCFs and reactive gases, i.e. using the coefficients and feedbacks from
    # Thornhill et al. 2021 and Skeie et al. 2020. We set this option in the
    # initialiser this time:
    fair_model = FAIR(ch4_method='thornhill2021')
    # Define time horizon
    # Create world running from 1750 to 2100, at 1-year intervals:
    fair_model.define_time(1750, 2100, 1)
    # Define scenarios
    # Important that the names are consistent with those in the RCMIP
    # database:
    scenarios = user_params['scenarios']
    scenarios.sort()
    fair_model.define_scenarios(scenarios)
    # Define configs
    # Our list of configs are going to be each CMIP6 climate model's 4xCO2
    # response, which has been pre-calculated in the calibration notebooks.
    # We could also modify the response for different aerosol, ozone, methane
    # lifetime tunings etc., but not every model has this data available:
# *
    calibration_file = '4xCO2_cummins_ebm3.csv'
# *
    calibration_path = os.sep.join([
        data_dir, 'calibration', calibration_file
    ])
    calibration_df = pd.read_csv(calibration_path)
    models = calibration_df['model'].unique()
    configs = []
    for imodel, model in enumerate(models):
        runs = calibration_df.loc[calibration_df['model'] == model, 'run']
        for run in runs:
            configs.append(f'{model}_{run}')
    fair_model.define_configs(configs)
    # Define species and properties
    # FaIR contains a few helper functions that populate the model with
    # sensible defaults. One is the read_properties function that obtains
    # default species (the kitchen sink) and their properties for an
    # emissions-driven run:
    species, properties = read_properties()
    fair_model.define_species(species, properties)
    # Create input and output data:
    fair_model.allocate()
    # Fill in the data
    # Get default species configs
    # Again we read in a default list of species configs that will apply to
    # each config. If you want to change specific configs then you can still
    # use this function to set defaults and tweak what you need. We will do
    # this with the methane lifetime, which has a different value calibrated
    # for the Thornhill 2021 lifetime option.
    # I'm also going to subtract the RCMIP 1750 emissions from CH4 and N2O.
    # This is not in the default configs:
    fair_model.fill_species_configs()
    fill(
        fair_model.species_configs['unperturbed_lifetime'],
        10.8537568,
        specie='CH4'
    )
    fill(
        fair_model.species_configs['baseline_emissions'],
        19.01978312,
        specie='CH4'
    )
    fill(
        fair_model.species_configs['baseline_emissions'],
        0.08602230754,
        specie='N2O'
    )
    # Fill emissions
    # Grab emissions (+solar and volcanic forcing) from RCMIP datasets using
    # the fill_from_rcmip helper function. This function automatically selects
    # the emissions, concentration or forcing you want depending on the
    # properties for each of the SSP scenarios defined.
    # I'm then going to make one change: replace the volcanic dataset with the
    # AR6 volcanic dataset, as I want to compare the impact of monthly volcanic
    # forcing in the monthly comparison.
    # We also need to initialise the first timestep of the run in terms of its
    # per-species forcing, temperature, cumulative and airborne emissions. We
    # set these all to zero. The concentration in the first timestep will be
    # set to the baseline concentration, which are the IPCC AR6 1750 values:
# *
    forcing_file = 'volcanic_ERF_monthly_-950001-201912.csv'
# *
    forcing_path = os.sep.join([
        data_dir, 'forcing', forcing_file
    ])
    forcing_df = pd.read_csv(forcing_path, index_col='year')
    fair_model.fill_from_rcmip()
    # Overwrite volcanic forcing:
    volcanic_forcing = np.zeros(351)
    volcanic_forcing[:271] = forcing_df[1749:].groupby(
        np.ceil(forcing_df[1749:].index) // 1
    ).mean().squeeze().values
    fill(
        fair_model.forcing,
        volcanic_forcing[:, None, None],
        specie='Volcanic'
    )
    initialise(
        fair_model.concentration,
        fair_model.species_configs['baseline_concentration']
    )
    initialise(fair_model.forcing, 0)
    initialise(fair_model.temperature, 0)
    initialise(fair_model.cumulative_emissions, 0)
    initialise(fair_model.airborne_emissions, 0)
    # Fill climate configs
    # Take pre-calculated values from the Cummins et al. three layer model.
    # We will use a reproducible random seed to define the stochastic
    # behaviour:
#### *
###    calibration_file = '4xCO2_cummins_ebm3.csv'
#### *
###    calibration_path = os.sep.join([
###        data_dir, 'calibration', calibration_file
###    ])
###    calibration_df = pd.read_csv(calibration_path)
    models = calibration_df['model'].unique()
    seed = 1355763
    for config in configs:
        model, run = config.split('_')
        condition = (
            (calibration_df['model'] == model) &
            (calibration_df['run'] == run)
        )
        fill(
            fair_model.climate_configs['ocean_heat_capacity'],
            calibration_df.loc[condition, 'C1':'C3'].values.squeeze(),
            config=config
        )
        fill(
            fair_model.climate_configs['ocean_heat_transfer'],
            calibration_df.loc[condition, 'kappa1':'kappa3'].values.squeeze(),
            config=config
        )
        fill(
            fair_model.climate_configs['deep_ocean_efficacy'],
            calibration_df.loc[condition, 'epsilon'].values[0],
            config=config
        )
        fill(
            fair_model.climate_configs['gamma_autocorrelation'],
            calibration_df.loc[condition, 'gamma'].values[0],
            config=config
        )
        fill(
            fair_model.climate_configs['sigma_eta'],
            calibration_df.loc[condition, 'sigma_eta'].values[0],
            config=config
        )
        fill(
            fair_model.climate_configs['sigma_xi'],
            calibration_df.loc[condition, 'sigma_xi'].values[0],
            config=config
        )
        fill(
            fair_model.climate_configs['stochastic_run'],
            True,
            config=config
        )
        fill(
            fair_model.climate_configs['use_seed'],
            True,
            config=config
        )
        fill(
            fair_model.climate_configs['seed'],
            seed,
            config=config
        )
        seed += 399
    # Run FaIR:
    fair_model.run(progress=False)
    # The output attributes of FAIR of interest are
    # * temperature (layer=0 is surface)
    # * emissions (an output for GHGs driven with concentration)
    # * concentration (as above, vice versa)
    # * forcing: the per-species effective radiative forcing
    # * forcing_sum: the total forcing
    # * airborne_emissions: total emissions of a GHG remaining in the
    #   atmosphere
    # * airborne_fraction: the fraction of GHG emissions remaining in the
    #   atmosphere
    # * alpha_lifetime: the scaling factor to unperturbed lifetime. Mutiply
    #   the two values to get the atmospheric lifetime of a greenhouse gas
    # * cumulative_emissions
    # * ocean_heat_content_change
    # * toa_imbalance
    # * stochastic_forcing: if stochastic variability is activated, the
    #   non-deterministic part of the forcing

    # Get date information:
    model_dates = fair_model.timebounds.tolist()
    model_dates_count = len(model_dates)
    # Define dict containing data for output:
    output_data = {}
    # Add temperature data to output:
    output_data['temperature'] = {
        'name': 'temperature',
        'species': None,
        'units': 'K',
        'data': fair_model.temperature.loc[dict(layer=0)]
    }
    # Add total forcing data to output:
    output_data['forcing_sum'] = {
        'name': 'forcing_sum',
        'species': None,
        'units': 'W/m²',
        'data': fair_model.forcing_sum
    }
    # For each requested species:
    for species in user_params['species']:
        # Emissions data label:
        species_label = 'emissions_{0}'.format(species)
        # Add emissions data to output:
        output_data[species_label] = {
            'name': 'emissions',
            'species': species,
            'units': 'Gt',
            'data': fair_model.airborne_emissions.loc[dict(specie=species)]
        }
        # Concentration data label:
        species_label = 'concentration_{0}'.format(species)
        # Add concentration data to output:
        output_data[species_label] = {
            'name': 'concentration',
            'species': species,
            'units': 'ppt',
            'data': fair_model.concentration.loc[dict(specie=species)]
        }
        # Forcing data label:
        species_label = 'forcing_{0}'.format(species)
        # Add forcing data to output:
        output_data[species_label] = {
            'name': 'forcing',
            'species': species,
            'units': 'W/m²',
            'data': fair_model.forcing.loc[dict(specie=species)]
        }

    # Output data ... configs:
    model_data['configs'] = fair_model.configs
    model_data['configs_count'] = len(fair_model.configs)
    # Output variables / data types:
    model_data['data_types'] = list(output_data.keys())
    model_data['data_types_count'] = len(model_data['data_types'])

    # Loop through data types:
    for data_type in model_data['data_types']:
        # Create dict for data:
        model_data[data_type] = {}
        type_dict = model_data[data_type]
        # Store name, scenarios, species and units:
        type_dict['name'] = output_data[data_type]['name']
        type_dict['scenarios'] = scenarios
        type_dict['scenarios_count'] = len(scenarios)
        type_dict['species'] = output_data[data_type]['species']
        type_dict['units'] = output_data[data_type]['units']
        # Date series, in years:
        type_dict['date'] = model_dates
        type_dict['date_count'] = model_dates_count
        # We have data for different percentiles:
        type_dict['has_perc'] = True
        # Init min and max values:
        type_dict['min'] = 99999
        type_dict['max'] = -99999
        # Loop through scenarios:
        for scenario in scenarios:
            # Init dict for this scenario:
            type_dict[scenario] = {}
            scenario_dict = type_dict[scenario]
            # Get data for this scenario:
            scenario_data = output_data[data_type]['data'].loc[
                dict(scenario=scenario)
            ]
            # 5th percentile temperature:
            scenario_dict['perc_5'] = scenario_data.quantile(
                q=0.05, dim='config'
            ).to_numpy().round(out_dp).tolist()
            type_dict['min'] = np.nanmin([
              type_dict['min'],
              np.nanmin(scenario_dict['perc_5'])
            ])
            # replace NaN values with strings:
            scenario_dict['perc_5'] = [
              'NaN' if np.isnan(i) else i
              for i in scenario_dict['perc_5']
            ]
            # 95th percentile temperature:
            scenario_dict['perc_95'] = scenario_data.quantile(
                q=0.95, dim='config'
            ).to_numpy().round(out_dp).tolist()
            type_dict['max'] = np.nanmax([
              type_dict['max'],
              np.nanmax(scenario_dict['perc_95'])
            ])
            # replace NaN values with strings:
            scenario_dict['perc_95'] = [
              'NaN' if np.isnan(i) else i
              for i in scenario_dict['perc_95']
            ]
            # Median temperature:
            scenario_dict['median'] = scenario_data.median(
                axis=1
            ).to_numpy().round(out_dp).tolist()
            # replace NaN values with strings:
            scenario_dict['median'] = [
              'NaN' if np.isnan(i) else i
              for i in scenario_dict['median']
            ]

    # Return the data:
    return model_data

def __get_model_data(user_params, precalc_data):
    """
    Get requested data from precalculated model data

    :param user_params: User supplied parameters
    :param precalc_data: Pre-calculated data dict
    """
    # Init output data:
    model_data = {
        'configs': [],
        'configs_count': 0
    }
    # Init list for storing data types:
    data_types = []
    # Requested scenarios:
    req_scenarios = user_params['scenarios']
    req_scenarios.sort()
    # Data types we are going to try and get:
    req_data_types = ['temperature', 'forcing_sum']
    # Add per species data types:
    req_species = user_params['species']
    req_species.sort()
    # Loop through requested species:
    for req_specie in req_species:
        # For each of species specific data types:
        for species_data_type in ['emissions', 'concentration', 'forcing']:
            # Label for this species and data type:
            species_data_label = '{0}_{1}'.format(
                species_data_type, req_specie.replace(' ', '_')
            )
            # Add to requested data types:
            req_data_types.append(species_data_label)

    # For each requested data type:
    for req_data_type in req_data_types:
        # Check for the requested data in precalculated data:
        if req_data_type in precalc_data.keys():
            # Add to list of data types:
            data_types.append(req_data_type)
            # Dict of input data:
            in_dict = precalc_data[req_data_type]
            # Add to output data:
            model_data[req_data_type] = {
                'name': in_dict['name'],
                'species': in_dict['species'],
                'units': in_dict['units'],
                'date': in_dict['date'],
                'date_count': in_dict['date_count'],
                'has_perc': in_dict['has_perc'],
                'min': in_dict['min'],
                'max': in_dict['max']
            }
            out_dict = model_data[req_data_type]
            # Init list for storing scenarios for which we have data:
            my_scenarios = []
            # Loop through requested scenarios:
            for req_scenario in req_scenarios:
                # Check if data is available:
                if req_scenario in in_dict['scenarios']:
                    # Add to list of scenarios:
                    my_scenarios.append(req_scenario)
                    # Add scenario data:
                    out_dict[req_scenario] = in_dict[req_scenario]
            # Add scenarios information to output:
            out_dict['scenarios'] = my_scenarios
            out_dict['scenarios_count'] = len(my_scenarios)

    # Add data types to output:
    model_data['data_types'] = data_types
    model_data['data_types_count'] = len(data_types)

    # Return the data:
    return model_data

def run_model(request_params, precalc_data=None, data_dir=None):
    """
    Wrapper function for running model

    :param request_params: POST supplied parameters
    :param precalc_data: Pre-calculated data dict
    :param data_dir: Directory containing data files
    """
    # init result dict:
    result = {
        'status': -1,
        'message': '',
        'data': {}
    }
    # check either precalc_data or data_dir is defined:
    if not precalc_data and not data_dir:
        # updata result dict:
        result['status'] = 1
        result['message'] = 'either pre-calculated data or data directory'
        result['message'] += 'must be specified'
        # return the result:
        return result
    # check user parameters:
    status, user_params, err_msg = check_params(request_params)
    # if that failed ... :
    if not status:
        # updata result dict:
        result['status'] = 1
        result['message'] = err_msg
        # return the result:
        return result
    # try to run the model:
    try:
        # if precalculated data is provided, use that:
        if precalc_data:
            model_data = __get_model_data(user_params, precalc_data)
        else:
            model_data = __run_model(user_params, data_dir)
        result['status'] = 0
        result['message'] = 'model run suceeded'
        result['data'] = model_data
    # if that fails:
    except Exception as err_msg:
        sys.stderr.write(
            f'[{datetime.datetime.now()}] [ERROR] {err_msg}\n'
        )
        result['status'] = 1
        result['message'] = 'model run failed'
    # return the result:
    return result
