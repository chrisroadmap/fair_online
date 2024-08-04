'use strict';

/* --- global variables: --- */

/* url for running model: */
var model_url = '/get';

/* model parameters: */
var model_params = {
  'scenarios': ['ssp119', 'ssp126', 'ssp245', 'ssp370', 'ssp585'],
  'species': ['CO2']
};
/* variable to indicate if parameters are o.k.: */
var model_params_ok = true;

/* input elements: */
var input_els = {
  'scenarios': document.getElementsByClassName('scenarios_input_checkbox'),
  'scenarios_error': document.getElementById('scenarios_input_error'),
  'species': document.getElementsByClassName('species_input_checkbox'),
  'species_error': document.getElementById('species_input_error'),
  'run_button': document.getElementById('run_model_button'),
  'run_button_display': null
};

/* plot config: */
var plot_vars = {
  /* main plot container element: */
  'plot_container_el': document.getElementById('content_plots'),
  'plot_container_el_display': null,
  /* model spinner element: */
  'model_spinner': document.getElementById('content_model_spinner'),
  /* time series plots parent element: */
  'ts_parent_el': document.getElementById('content_ts_plots'),
  /* time series plot types configurations: */
  'data_types': {
    'temperature': {
      'title': 'temperature anomaly',
      'x_title': 'year',
      'y_title': 'temperature anomaly'
    },
    'forcing_sum': {
      'title': 'total forcing',
      'x_title': 'year',
      'y_title': 'forcing'
    },
    'emissions': {
      'title': 'airborne emissions',
      'x_title': 'year',
      'y_title': 'emissions'
    },
    'concentration': {
      'title': 'concentration',
      'x_title': 'year',
      'y_title': 'concentration'
    },
    'forcing': {
      'title': 'forcing',
      'x_title': 'year',
      'y_title': 'forcing'
    }
  },
  /* scenarios plot configurations: */
  'scenarios': {
    'ssp119': {
      'name': 'ssp119',
      'color': '#00a9cf',
      'fill': 'rgba(0, 169, 207, 0.1)'
    },
    'ssp126': {
      'name': 'ssp126',
      'color': '#003466',
      'fill': 'rgba(0, 52, 102, 0.1)'
    },
    'ssp245': {
      'name': 'ssp245',
      'color': '#f69320',
      'fill': 'rgba(246, 147, 32, 0.1)'
    },
    'ssp370': {
      'name': 'ssp370',
      'color': '#df0000',
      'fill': 'rgba(223, 0, 0, 0.1)'
    },
    'ssp585': {
      'name': 'ssp585',
      'color': '#980002',
      'fill': 'rgba(152, 0, 2, 0.1)'
    }
  }
};

/* model data: */
var model_data = null;

/* --- --- */

/* checkbox element input validation function: */
function validate_checkbox_input() {

  /* presume all o.k.: */
  model_params_ok = true;

  /* scenarios: */

  /* error element: */
  var scenarios_error_element = input_els['scenarios_error'];
  scenarios_error_element.innerHTML = '';
  /* model scenario checkbox elements: */
  var scenarios_elements = input_els['scenarios'];
  /* wipe out scenarios parameter: */
  model_params['scenarios'] = [];
  /* loop through elements: */
  for (var i = 0; i < scenarios_elements.length; i++) {
    /* if checked, store the values: */
    if (scenarios_elements[i].checked == true) {
      model_params['scenarios'].push(scenarios_elements[i].value);
    };
  };
  /* check at least one scenario is checked: */
  if (model_params['scenarios'].length < 1) {
    /* if not, display an error message: */
    model_params_ok = false;
    scenarios_error_element.innerHTML = 'At least one scenario must be selected';
    scenarios_error_element.style.display = 'inline';
  } else {
    /* else, remove any error message: */
    scenarios_error_element.style.display = 'none';
  };
  /* if parameters o.k., enable button: */
  var input_run_button = input_els['run_button'];
  if (model_params_ok == true) {
    input_run_button.removeAttribute('disabled');
  } else {
    input_run_button.setAttribute('disabled', true);
  };

  /* species: */

  /* error element: */
  var species_error_element = input_els['species_error'];
  species_error_element.innerHTML = '';
  /* model scenario checkbox elements: */
  var species_elements = input_els['species'];
  /* wipe out species parameter: */
  model_params['species'] = [];
  /* loop through elements: */
  for (var i = 0; i < species_elements.length; i++) {
    /* if checked, store the values: */
    if (species_elements[i].checked == true) {
      model_params['species'].push(species_elements[i].value);
    };
  };
  /* check at least one scenario is checked: */
  if (model_params['species'].length < 1) {
    /* if not, display an error message: */
    model_params_ok = false;
    species_error_element.innerHTML = 'At least one species must be selected';
    species_error_element.style.display = 'inline';
  } else {
    /* else, remove any error message: */
    species_error_element.style.display = 'none';
  };
  /* if parameters o.k., enable button: */
  var input_run_button = input_els['run_button'];
  if (model_params_ok == true) {
    input_run_button.removeAttribute('disabled');
  } else {
    input_run_button.setAttribute('disabled', true);
  };

};

/* add input listeners: */
function add_listeners() {
  /* model scenario checkbox elements listener: */
  var scenarios_elements = input_els['scenarios'];
  /* loop through elements: */
  for (var i = 0; i < scenarios_elements.length; i++) {
    /* add listener: */
    scenarios_elements[i].addEventListener('click', validate_checkbox_input);
  };
  /* model species checkbox elements listener: */
  var species_elements = input_els['species'];
  /* loop through elements: */
  for (var i = 0; i < species_elements.length; i++) {
    /* add listener: */
    species_elements[i].addEventListener('click', validate_checkbox_input);
  };
  /* add run button listener: */
  var input_run_button = input_els['run_button'];
  /* add click listener: */
  input_run_button.addEventListener('click', run_model);
};

/* element hiding function: */
function hide_elements() {
  /* plot containiner element: */
  var plot_container_el = plot_vars['plot_container_el'];
  /* get display value: */
  plot_vars['plot_container_el_display'] = plot_container_el.style.display;
  /* hide the element: */
  plot_container_el.style.display = 'none';
};

/* function to create time series plot data: */
function get_ts_plot_data(plot_data, ts_data, is_b) {
  /* check if this is secondary data: */
  is_b = is_b == true ? is_b : false;
  /* if this is secondary data: */
  if (is_b == true) {
    /* don't show on legend: */
    var show_legend = false;
    /* use dotted line: */
    var line_dash = 'dot';
  /* else this is primary y axis data: */
  } else {
    /* do show on legend: */
    var show_legend = true;
    /* use solid line: */
    var line_dash = 'solid';
  };
  /* scenarios for which we have data: */
  var scenarios = plot_data['scenarios'];
  scenarios.sort();
  /* units for the data: */
  var units = plot_data['units'];
  /* time series x values: */
  var x = plot_data['x'];
  /* data for plotting: */
  var data = plot_data['data'];
  /* loop through scenarios: */
  for (var i = 0; i < scenarios.length; i++) {
    /* data for this scenarios: */
    var scenario = scenarios[i];
    var scenario_name = plot_vars['scenarios'][scenario]['name'];
    var color = plot_vars['scenarios'][scenario]['color'];
    var fill = plot_vars['scenarios'][scenario]['fill'];
    var scenario_data = data[scenario];
    /* check if percentile data is available: */
    if (data['has_perc'] == true) {
      var y_hi = scenario_data['perc_95'];
      var y_lo = scenario_data['perc_5'];
      var y_med = scenario_data['median'];
    } else {
      var y_hi = null;
      var y_lo = null;
      var y_med = scenario_data['data'];
    }
    /* create the hover text data: */
    var hover_text = [];
    var hover_prefix = plot_data['hover_prefix'];
    for (var j = 0; j < x.length; j++) {
      var my_hover_text = scenario + hover_prefix + ': ' +
                          parseFloat(y_med[j]).toFixed(2) + ' ' + units;
      /* add percentile data if available: */
      if (data['has_perc'] == true) {
          my_hover_text += ' (' +
                           parseFloat(y_lo[j]).toFixed(2) + ' ' + units + ' - ' +
                           parseFloat(y_hi[j]).toFixed(2) + ' ' + units + ')';
      };
      hover_text.push(my_hover_text);
    };
    /* create time series plots. low for fill ... : */
    var ts_lo_fill = {
      'type': 'scatter',
      'name': '5th percentile',
      'x': x,
      'y': y_lo,
      'mode': 'lines',
      'marker': {
        'color': fill
      },
      'line': {
        'width': 0.1
      },
      'legendgroup': scenario_name,
      'showlegend': false,
      'hoverinfo': 'none'
    };
    /* ... high, with fill ... : */
    var ts_hi_fill = {
      'type': 'scatter',
      'name': '95th percentile',
      'x': x,
      'y': y_hi,
      'mode': 'lines',
      'fill': 'tonexty',
      'fillcolor': fill,
      'marker': {
        'color': fill
      },
      'line': {
        'width': 0.1
      },
      'legendgroup': scenario_name,
      'showlegend': false,
      'hoverinfo': 'none'
    };
    /* ... median: */
    var ts_med = {
      'type': 'scatter',
      'name': scenario_name,
      'x': x,
      'y': y_med,
      'mode': 'lines',
      'marker': {
        'color': color
      },
      'line': {
        'dash': line_dash,
        'width': 1.05
      },
      'legendgroup': scenario_name,
      'showlegend': show_legend,
      'hoverinfo': 'x+text',
      'xhoverformat': '04d',
      'hovertext': hover_text
    };
    /* store plots: */
    ts_data.push(ts_lo_fill);
    ts_data.push(ts_hi_fill);
    ts_data.push(ts_med);
  };
  /* return the time series plots: */
  return ts_data;
};

/* time series plotting function: */
function plot_ts(ts_el, plot_data, plot_data_b) {
  /* plotting variables ... units for the data: */
  var units = plot_data['units'];
  /* species of this data, if any: */
  var species = plot_data['species'];
  /* time series variables: */
  var title = plot_data['title'];
  var x_title = plot_data['x_title'];
  var y_title = plot_data['y_title'];
  /* if species is not null, update title: */
  if ((species != null) && (species != '')) {
    title = species + ' ' + title;
  };
  /* if units is not null, update y title: */
  if ((units != null) && (units != '')) {
    y_title = y_title + ' (' + units + ')';
  /* else, make sure units is an empty string: */
  } else {
    units = '';
  };
  /* y min and max: */
  var y_min = plot_data['y_min'];
  var y_max = plot_data['y_max'];
  /* init array for storing all plots: */
  var ts_data = [];
  /* get the plot data: */
  ts_data = get_ts_plot_data(plot_data, ts_data);

  /* if there is secondary data: */
  if (plot_data_b != undefined) {
    ts_data = get_ts_plot_data(plot_data_b, ts_data, true);
  };
  /* time series layout: */
  var ts_layout = {
    'title': {
      'text': title,
      'font': {
        'size': 20
      }
    },
    'xaxis': {
      'tickfont': {
        'size': 16
      },
      'title': {
        'text': x_title,
        'font': {
          'size': 18
        }
      },
      'zeroline': false,
      'spikethickness': 1
    },
    'yaxis': {
      'range': [y_min, y_max],
      'tickfont': {
        'size': 16
      },
      'title': {
        'text': y_title,
        'font': {
          'size': 18
        }
      },
      'zeroline': false
    },
    'legend': {
      'font': {
        'size': 16
      },
      'x': 0.05,
      'y': 1,
      'xanchor': 'left'
    },
    'hovermode': 'x unified',
    'hoverlabel': {
      'font': {
        'size': 14
      }
    },
    'showlegend': true
  };
  /* time series config: */
  var ts_conf = {
    'showLink': false,
    'linkText': '',
    'displaylogo': false,
    'modeBarButtonsToRemove': [
      'autoScale2d',
      'lasso2d',
      'toggleSpikelines',
      'select2d'
    ],
    'responsive': true
  };
  /* create the plot: */
  Plotly.newPlot(
    ts_el, ts_data, ts_layout, ts_conf
  );
};

/* function to prepare data for plotting: */
function get_plot_data(data_type_index) {
  /* data for this data type: */
  var data_type = model_data['data_types'][data_type_index];
  var data_type_data = model_data[data_type];
  var data_type = data_type_data['name'];
  /* min and max values for y axes: */
  var y_min = Math.floor(data_type_data['min']) - 0.25;
  var y_max = Math.ceil(data_type_data['max']) + 0.25;
  /* plot data for this data type: */
  var data_type_plot_data = {
    'data_type': data_type,
    'species': data_type_data['species'],
    'units': data_type_data['units'],
    'scenarios': data_type_data['scenarios'],
    'title': plot_vars['data_types'][data_type]['title'],
    'x_title': plot_vars['data_types'][data_type]['x_title'],
    'y_title': plot_vars['data_types'][data_type]['y_title'],
    'x': data_type_data['date'],
    'y_min': y_min,
    'y_max': y_max,
    'hover_prefix': '',
    'data': data_type_data
  };
  /* return the data: */
  return data_type_plot_data;
};

/* function to download data as csv: */
function get_csv_data(data_indexes) {
  /* check how many data sets we have: */
  var data_count = data_indexes.length;
  /* loop through data sets: */
  for (var i = 0; i < data_count; i++) {
    /* get the data for this data set: */
    var data_index = data_indexes[i];
    var plot_data = get_plot_data(data_index);
    /* name for this data type: */
    var data_name = plot_data['title'].replace(' ', '_');
    if (plot_data['species'] != null) {
      data_name += '_' + plot_data['species'];
    };
    /* init csv data: */
    var csv_data = 'data:text/csv;charset=utf-8,';
    csv_data += 'date';
    /* check for units: */
    if (plot_data['units'] != null) {
      var units = ' (' + plot_data['units'] + ')';
    } else {
      var units = '';
    };
    /* loop through scenarios for header: */
    for (var j = 0; j < plot_data['scenarios'].length; j++) {
      /* this scenario: */
      var scenario = plot_data['scenarios'][j];
      /* if the data has percentiles: */
      if (plot_data['data']['has_perc'] == true) {
         csv_data += ',' + scenario + ' 5th percentile' + units;
         csv_data += ',' + scenario + ' 50th percentile' + units;
         csv_data += ',' + scenario + ' 95th percentile' + units;
      /* else, no percentiles: */
      } else {
         csv_data += ',' + scenario + units;
      };
    };
    csv_data += '\r\n';
    /* loop through data dates: */
    for (var j = 0; j < plot_data['data']['date'].length; j++) {
      /* add date: */
      csv_data += plot_data['data']['date'][j];
      /* loop through scenarios: */
      for (var k = 0; k < plot_data['scenarios'].length; k++) {
        /* this scenario: */
        var scenario = plot_data['scenarios'][k];
        /* if the data has percentiles: */
        if (plot_data['data']['has_perc'] == true) {
           csv_data += ',' + plot_data['data'][scenario]['perc_5'][j];
           csv_data += ',' + plot_data['data'][scenario]['median'][j];
           csv_data += ',' + plot_data['data'][scenario]['perc_95'][j];
        /* else, no percentiles: */
        } else {
           csv_data += ',' + plot_data['data'][scenario]['data'][j];
        };
      };
      csv_data += '\r\n';
    };
    /* encode csv data: */
    var encoded_uri = encodeURI(csv_data);
    /* name for csv file: */
    var csv_name = data_name + '.csv';
    /* create a temporary link element: */
    var csv_link = document.createElement("a");
    csv_link.setAttribute("href", encoded_uri);
    csv_link.setAttribute("download", csv_name);
    csv_link.style.visibility = 'hidden';
    /* add link to document, click to init download, then remove: */
    document.body.appendChild(csv_link);
    csv_link.click();
    document.body.removeChild(csv_link);
  };
};

/* data plotting function: */
function plot_data() {
  /* check for null data: */
  if (model_data == null) {
    return;
  };
  /* enable plot element: */
  var plot_container_el = plot_vars['plot_container_el'];
  plot_container_el.style.display = plot_vars['plot_container_el_display'];

  /* get index of temperature data: */
  var temperature_index = model_data['data_types'].indexOf('temperature');
  /* get index of any forcing sum data: */
  var forcing_sum_index = model_data['data_types'].indexOf('forcing_sum');
  /* get index of any forcing data: */
  var forcing_indexes = [];
  for (var i = 0 ; i < model_data['data_types'].length ; i++) {
    var data_key = model_data['data_types'][i];
    if (model_data[data_key]['name'] == 'forcing') {
      forcing_indexes.push(i);
    };
  };

  /* -- time series plots: -- */

  /* parent element for plots: */
  var parent_el = plot_vars['ts_parent_el'];
  /* remove any existing plot elements: */
  while (parent_el.firstChild) {
    parent_el.removeChild(parent_el.lastChild);
  };
  /*
   * create plot elements ...
   * plot elements will be stored in here:
   */
  var ts_plot_els = [];
  /* data download elements will be stored in here: */
  var ts_dl_els = [];
  /* get a count of the data types we have: */
  var data_types_count = parseInt(model_data['data_types_count']);
  /* count of plot elements is initially same as number of data types: */
  var total_plot_count = data_types_count;
  /*
   * reduce plot count by 1 if both forcing and forcing sum data available, as
   * two forcing data sets will be on same plot:
   */
  if ((forcing_sum_index > -1) && (forcing_indexes.length > 0)) {
    total_plot_count -= 1;
  };
  var elements_count = Math.round(total_plot_count / 2) * 2;
  /* loop through number of required elements and create: */
  for (var i = 0; i < elements_count; i++) {
    /* plot element: */
    var ts_el = document.createElement('div');
    ts_el.classList = 'content_plot';
    /* plot box / container element: */
    var ts_box_el = document.createElement('div');
    if (i >= total_plot_count) {
      /* empty elemnt if odd number of plots: */
      ts_box_el.classList = 'content_plot_box content_plot_box_empty flex_half flex_grow';
    } else {
      /* 'standard' element: */
      ts_box_el.classList = 'content_plot_box flex_half flex_grow';
      /* data download element: */
      var ts_dl_el = document.createElement('div');
      ts_dl_el.classList = 'content_download_csv';
      ts_dl_el.title = 'Download data as CSV';
      ts_el.appendChild(ts_dl_el);
      ts_dl_els.push(ts_dl_el);
    };
    /* add elements to page: */
    ts_box_el.appendChild(ts_el);
    parent_el.appendChild(ts_box_el);
    /* store elements: */
    ts_plot_els.push(ts_el);
  };

  /* init a plot count: */
  var ts_plot_count = 0;

  /* plot temperature first: */
  if (temperature_index > -1) {
    /* plot data for this data type: */
    var data_type_plot_data = get_plot_data(temperature_index);
    /* add plot for this data type: */
    plot_ts(ts_plot_els[ts_plot_count], data_type_plot_data);
    /* add functionality to download element for this plot: */
    var ts_dl_el = ts_dl_els[ts_plot_count];
    ts_dl_el.setAttribute('onclick', 'get_csv_data([' + temperature_index + '])');
    /* increment plot count:*/
    ts_plot_count += 1;
  };

  /* if only forcing sum data available, plot that next: */
  if ((forcing_sum_index > -1) && (forcing_indexes.length < 1)) {
    var data_type_plot_data = get_plot_data(forcing_sum_index);
    plot_ts(ts_plot_els[ts_plot_count], data_type_plot_data);
    /* add functionality to download element for this plot: */
    var ts_dl_el = ts_dl_els[ts_plot_count];
    ts_dl_el.setAttribute('onclick', 'get_csv_data([' + forcing_sum_index + '])');
    /* increment plot count:*/
    ts_plot_count += 1;
  };

  /* loop through all other data types: */
  for (var i = 0; i < data_types_count; i++ ) {

    /* skip temperature and forcing sum data: */
    if ((i == temperature_index) || (i == forcing_sum_index)) {
      continue;
    };

    /* if this is forcing data: */
    if (forcing_indexes.indexOf(i) > -1) {

      /* if only forcing (not sum) data: */
      if ((forcing_sum_index > -1) != true) {
        var data_type_plot_data = get_plot_data(i);
        plot_ts(ts_plot_els[ts_plot_count], data_type_plot_data);
        /* add functionality to download element for this plot: */
        var ts_dl_el = ts_dl_els[ts_plot_count];
        ts_dl_el.setAttribute('onclick', 'get_csv_data([' + i + '])');
        /* increment plot count:*/
        ts_plot_count += 1;
      /* else we have both: */
      } else {
        var forcing_sum_plot_data = get_plot_data(forcing_sum_index);
        var forcing_plot_data = get_plot_data(i);
        forcing_sum_plot_data['hover_prefix'] = ' (total)';
        forcing_sum_plot_data['title'] = forcing_plot_data['species'] +
                                         ' forcing';
        forcing_plot_data['hover_prefix'] = ' (' +
                                            forcing_plot_data['species'] +
                                            ')';
        plot_ts(
          ts_plot_els[ts_plot_count], forcing_sum_plot_data, forcing_plot_data
        );
        /* add functionality to download element for this plot: */
        var ts_dl_el = ts_dl_els[ts_plot_count];
        ts_dl_el.setAttribute(
          'onclick',
          'get_csv_data([' + i + ',' + forcing_sum_index +  '])'
        );
        /* increment plot count:*/
        ts_plot_count += 1;
      };

    /* else, this is not forcing data: */
    } else {
      /* plot data for this data type: */
      var data_type_plot_data = get_plot_data(i);
      /* add plot for this data type: */
      plot_ts(ts_plot_els[ts_plot_count], data_type_plot_data);
      /* add functionality to download element for this plot: */
      var ts_dl_el = ts_dl_els[ts_plot_count];
      ts_dl_el.setAttribute('onclick', 'get_csv_data([' + i + '])');
      /* increment plot count:*/
      ts_plot_count += 1;
    };
  };

};

/* run the model by posting parameters: */
function __run_model(model_params) {
  /* init result variable: */
  var model_result;
  /* run button element: */
  var input_run_button = input_els['run_button'];
  input_els['run_button_display'] = input_run_button.style.display;
  /* model spinner element: */
  var model_spinner = plot_vars['model_spinner'];
  /* disable run button: */
  input_run_button.setAttribute('disabled', true);
  input_run_button.style.display = 'none';
  /* enable spinner: */
  model_spinner.style.display = 'inline';
  /* build request parameters: */
  var req_params = 'scenarios=[' + model_params['scenarios'] + ']&' +
                   'species=[' + model_params['species'] + ']';
  /* request error function: */
  function model_req_error() {
    console.log('* model error');
    /* disable model spinner element: */
    var model_spinner = plot_vars['model_spinner'];
    model_spinner.style.display = 'none';
    /* run button element: */
    var input_run_button = input_els['run_button'];
    /* enable run button: */
    input_run_button.removeAttribute('disabled');
    input_run_button.style.display = input_els['run_button_display'];
    input_run_button.blur();
  };
  /* create new request: */
  var model_req = new XMLHttpRequest();
  model_req.responseType = 'json';
  model_req.open('POST', model_url, true);
  model_req.setRequestHeader(
    'Content-type', 'application/x-www-form-urlencoded'
  );
  /* on request load: */
  model_req.onload = function() {
    /* if not successful: */
    if (model_req.status != 200) {
      model_req_error();
    } else {
      /* model results: */
      model_result = model_req.response;
      console.log('* model run result:');
      console.log('  ' + model_result['status'] + ': ' + model_result['message']);
      /* if model succeeded: */
      if (model_result['status'] == 0) {
        /* store model data: */
        model_data = model_result['data'];
        /* disable status: */
        model_spinner.style.display = 'none';
        /* plot the data: */
        plot_data();
        /* enable run button: */
        input_run_button.removeAttribute('disabled');
        input_run_button.style.display = input_els['run_button_display'];
        input_run_button.blur();
      /* else, handle error: */
      } else {
        model_req_error();
      };
    };
    /* if request fails: */
    model_req.onerror = function() {
      model_req_error();
    };
  };
  /* send the request: */
  console.log('* model pameters:');
  console.log('  ' + req_params);
  model_req.send(req_params);
};

/* model running function: */
function run_model() {
  /* validate input / get model parameters: */
  validate_checkbox_input();
  /* if parameters are o.k.: */
  if (model_params_ok == true) {
    /* run the model by posting parameters: */
    var result = __run_model(model_params);
  };
};

/* --- --- */

/* on page load ... : */
window.addEventListener('load', function() {
  /* add listeners to various elements: */
  add_listeners();
  /* hide some elements ... : */
  hide_elements();
});
