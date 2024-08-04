# -*- coding: utf-8 -*-

"""
FaIR web application
"""

# --- imports

# std lib imports:
import json
import os

# third party imports:
from flask import Flask, render_template, request
import netCDF4 as nc
import numpy as np

# local imports:
from model import run_model
from constants import SCENARIOS, SPECIES, DEFAULT_SPECIES

# --- global variables

# define flask application:
app = Flask(__name__)
# define site root:
SITE_ROOT = os.path.realpath(app.root_path)
# define data directory:
DATA_DIR = os.sep.join([SITE_ROOT, 'data'])
# scenarios which can be selected on model pages:
SCENARIOS = [{'name': i, 'checked': True} for i in SCENARIOS]
# species which can be selected on model pages:
SPECIES = SPECIES
# default selected specie:
DEFAULT_SPECIES = DEFAULT_SPECIES
# pre-calculated data is stored here:
PRECALC_DATA = {}
# pre-calculated data directory:
PRECALC_DIR = os.sep.join([DATA_DIR, 'pre-calc'])
# pre-calculated data files:
PRECALC_FILES = {
    'temperature': {
        'path': 'ssp_temperature.nc',
        'units': 'K',
        'data_key': 'temperature'
    },
    'emissions': {
        'path': 'ssp_emissions.nc',
        'units': 'Gt',
        'data_key': 'emissions'
    },
    'concentration': {
        'path': 'ssp_concentration.nc',
        'units': 'ppt',
        'data_key': 'concentration'
    },
    'forcing': {
        'path': 'ssp_forcing.nc',
        'units': 'W/m2',
        'data_key': 'forcing'
    },
    'forcing_sum': {
        'path': 'ssp_forcing_sum.nc',
        'units': 'W/m2',
        'data_key': 'forcing'
    }
}
# years for which pre-calculated data should be read in (greater than /
# less than):
PRECALC_START = 1699
PRECALC_END = 2301

# define path to config and read:
CONFIG_FILE = os.sep.join([SITE_ROOT, 'config.json'])
with open(CONFIG_FILE, 'r', encoding='utf-8') as CONFIG_JSON:
    APP_CONFIG = json.load(CONFIG_JSON)
# define flask app secret key:
app.secret_key = APP_CONFIG['secret_key']

# ---

# how many decimal places to use for rounding:
DATA_DP = 3
# init data types dictionary:
DATA_TYPES = {}

# load precalculated data on start up.
# loop through precalculated files:
for data_type, precalc_dict in PRECALC_FILES.items():
    # get data type details:
    data_path = precalc_dict['path']
    data_units = precalc_dict['units']
    data_key = precalc_dict['data_key']
    # data file path:
    data_file = os.sep.join([
        PRECALC_DIR, data_path
    ])
    # load the data:
    data = nc.Dataset(data_file)
    # get data dimensions:
    data_dims = data.dimensions.keys()
    # get data variables:
    data_vars = data.variables.keys()
    # get data scenarios:
    data_scenarios = data['scenario'][:].tolist()
    data_scenarios_count = len(data_scenarios)
    # get date dimension, either 'timepoints' or 'timebounds':
    if 'timebounds' in data_dims:
        date_key = 'timebounds'
    else:
        date_key = 'timepoints'
    # get indexes for required dates:
    date_indexes = np.where(
        (data[date_key][:] > PRECALC_START) &
        (data[date_key][:] < PRECALC_END)
    )
    # get data dates:
    data_date = data[date_key][date_indexes].tolist()
    data_date_count = len(data_date)
    # check if there is a percentile dimension:
    has_perc = bool('percentile' in data_dims)
    # if this data does not have a specie dimension:
    if not 'specie' in data_dims:
        # init dict for this data:
        DATA_TYPES[data_type] = {
            'name': data_type,
            'scenarios': data_scenarios,
            'scenarios_count': data_scenarios_count,
            'species': None,
            'units': precalc_dict['units'],
            'date': data_date,
            'date_count': data_date_count,
            'data': data[data_key][date_indexes].round(DATA_DP),
            'has_perc': has_perc
        }
    # else, there is a species dimension:
    else:
        # loop through species:
        for i, specie in enumerate(data['specie'][:]):
            # data type key is data type + species name:
            data_type_key = '{0}_{1}'.format(
                data_type, specie.replace(' ', '_')
            )
            # if this data has units:
            if 'units' in data_vars:
                specie_units = data['units'][i]
            else:
                specie_units = precalc_dict['units']
            # if this data has percentiles:
            if has_perc:
                species_data = data[data_key][date_indexes][:, :, :, i].round(DATA_DP)
            else:
                species_data = data[data_key][date_indexes][:, :, i].round(DATA_DP)
            # init dict for this data:
            DATA_TYPES[data_type_key] = {
                'name': data_type,
                'scenarios': data_scenarios,
                'scenarios_count': data_scenarios_count,
                'species': specie,
                'units': specie_units,
                'date': data_date,
                'date_count': data_date_count,
                'data': species_data,
                'has_perc': has_perc
            }

# loop through all data types:
for data_type, type_dict in DATA_TYPES.items():
    # scenarios for this type:
    scenarios = type_dict['scenarios']
    # data for this type:
    type_data = type_dict['data']
    # init precalc dict for this data:
    PRECALC_DATA[data_type] = {
        'name': type_dict['name'],
        'scenarios': type_dict['scenarios'],
        'scenarios_count': type_dict['scenarios_count'],
        'species': type_dict['species'],
        'units': type_dict['units'],
        'date': type_dict['date'],
        'date_count': type_dict['date_count'],
        'has_perc': type_dict['has_perc']
    }
    data_dict = PRECALC_DATA[data_type]
    # init min and max values:
    data_dict['min'] = 999999
    data_dict['max'] = -999999
    # loop through scenarios:
    for i, scenario in enumerate(scenarios):
        # dict for this scenario:
        data_dict[scenario] = {}
        scenario_dict = data_dict[scenario]
        # if this data has percentiles:
        if type_dict['has_perc']:
            # 5th percentile values:
            scenario_dict['perc_5'] = (
                type_data[:, i, 0].tolist()
            )
            # update min value:
            data_dict['min'] = np.nanmin([
                data_dict['min'],
                np.nanmin(scenario_dict['perc_5'])
            ])
            # replace NaN values with strings:
            scenario_dict['perc_5'] = [
              'NaN' if np.isnan(j) else j
              for j in scenario_dict['perc_5']
            ]
            # 95th percentile values:
            scenario_dict['perc_95'] = (
                type_data[:, i, 2].tolist()
            )
            # update max value:
            data_dict['max'] = np.nanmax([
                data_dict['max'],
                np.nanmax(scenario_dict['perc_95'])
            ])
            # replace NaN values with strings:
            scenario_dict['perc_95'] = [
              'NaN' if np.isnan(j) else j
              for j in scenario_dict['perc_95']
            ]
            # median values:
            scenario_dict['median'] = (
                type_data[:, i, 1].tolist()
            )
            # replace NaN values with strings:
            scenario_dict['median'] = [
              'NaN' if np.isnan(j) else j
              for j in scenario_dict['median']
            ]
        # else, no percentiles:
        else:
            # data values:
            scenario_dict['data'] = (
                type_data[:, i].tolist()
            )
            # update min value:
            data_dict['min'] = np.nanmin([
                data_dict['min'],
                np.nanmin(scenario_dict['data'])
            ])
            # update max value:
            data_dict['max'] = np.nanmax([
                data_dict['max'],
                np.nanmax(scenario_dict['data'])
            ])
            # replace NaN values with strings:
            scenario_dict['data'] = [
              'NaN' if np.isnan(j) else j
              for j in scenario_dict['data']
            ]

# done with DATA_TYPES:
del DATA_TYPES

# ---

# home:
@app.route('/', methods=['GET'])
def render_home():
    """
    Render home page
    """
    # return rendered home page:
    return render_template(
        'home.html.j2', current_page='home', header_img=True
    )

# model page:
@app.route('/model', methods=['GET'])
def render_model():
    """
    Render model page
    """
    # return rendered model page:
    return render_template(
        'model.html.j2', current_page='model', header_img=False,
        scenarios=SCENARIOS, species=SPECIES, default_species=DEFAULT_SPECIES
    )

# model runnning:
@app.route('/run', methods=['POST'])
def run():
    """
    Run the model
    """
    # get POST data:
    request_params = request.form
    # run the model:
    result = run_model(request_params, data_dir=DATA_DIR)
    # return the result:
    return result

# get precalculated model data:
@app.route('/get', methods=['POST'])
def get():
    """
    Get precalculated model data
    """
    # get POST data:
    request_params = request.form
    # get the model data:
    result = run_model(request_params, precalc_data=PRECALC_DATA)
    # return the result:
    return result

# about:
@app.route('/about', methods=["GET"])
def render_contact():
    """
    Render about page
    """
    # return rendered contact page:
    return render_template(
        'about.html.j2', current_page='about', header_img=False
    )

# error:
@app.errorhandler(Exception)
def handle_exception(error):
    """
    Handle errors
    """
    return render_template(
        'error.html.j2', current_page='error', error=error.description
    ), error.code

if __name__ == '__main__':
    app.run(debug=True)
