// FaIR dashboard front-end logic.

const COLORS = {
  series1: '#2a78d6', // blue
  series2: '#eb6834', // orange
  series3: '#1baf7a', // aqua
  series4: '#eda100', // yellow
  series5: '#e87ba4', // magenta
  muted: '#898781',
  textSecondary: '#52514e',
  gridline: '#e1e0d9',
};

const SPECIES_ORDER = ['CO2 FFI', 'CO2 AFOLU', 'CH4', 'N2O', 'Sulfur'];
const SPECIES_COLOR = {
  'CO2 FFI': COLORS.series1,
  'CO2 AFOLU': COLORS.series2,
  'CH4': COLORS.series3,
  'N2O': COLORS.series4,
  'Sulfur': COLORS.series5,
};
const CONTROL_YEARS = [2030, 2040, 2050, 2060, 2075, 2100];

let CONFIG = null;
let lastResult = null;
let lastParams = null;
let comparisonResult = null;
let advancedMode = false;

const PLOTLY_FONT = { family: 'system-ui, -apple-system, "Segoe UI", sans-serif', color: COLORS.textSecondary, size: 12 };

function baseLayout(extra) {
  return Object.assign({
    margin: { t: 10, r: 20, l: 55, b: 40 },
    font: PLOTLY_FONT,
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: 'rgba(0,0,0,0)',
    hovermode: 'x unified',
    xaxis: { gridcolor: COLORS.gridline, zeroline: false, showline: true, linecolor: COLORS.gridline },
    yaxis: { gridcolor: COLORS.gridline, zeroline: false, showline: false },
    legend: { orientation: 'h', y: -0.18 },
  }, extra || {});
}

const PLOTLY_CONFIG = { displaylogo: false, responsive: true, modeBarButtonsToRemove: ['lasso2d', 'select2d'] };

async function loadConfig() {
  const resp = await fetch('/api/config');
  CONFIG = await resp.json();
  populateScenarioSelect();
  populateEmissionsEditor();
  populateAdvancedPanel();
  updateEcsRangeBand();
}

function populateScenarioSelect() {
  const sel = document.getElementById('scenario-select');
  sel.innerHTML = '';
  for (const [key, meta] of Object.entries(CONFIG.scenarios)) {
    const opt = document.createElement('option');
    opt.value = key;
    opt.textContent = meta.label;
    if (key === 'medium-overshoot') opt.selected = true;
    sel.appendChild(opt);
  }
  updateScenarioSubtitle();
  sel.addEventListener('change', () => {
    updateScenarioSubtitle();
    populateEmissionsEditor();
  });
}

function updateScenarioSubtitle() {
  const key = document.getElementById('scenario-select').value;
  const meta = CONFIG.scenarios[key];
  document.getElementById('scenario-subtitle').textContent = `${meta.subtitle} — roughly ${meta.approx_2100_warming} by 2100 at central climate sensitivity.`;
}

function updateEcsRangeBand() {
  const p = CONFIG.climate_meta.ecs_percentiles;
  const min = 1.5, max = 6.5;
  const left = ((p['5'] - min) / (max - min)) * 100;
  const width = ((p['95'] - p['5']) / (max - min)) * 100;
  const band = document.getElementById('ecs-range-band');
  band.style.left = left + '%';
  band.style.width = width + '%';
}

function populateEmissionsEditor() {
  const scenario = document.getElementById('scenario-select').value;
  const container = document.getElementById('emissions-editor');
  container.innerHTML = '';
  for (const specie of SPECIES_ORDER) {
    const info = CONFIG.editable_species[specie];
    const defaults = info.defaults[scenario];
    const block = document.createElement('div');
    block.className = 'species-block';
    block.dataset.specie = specie;

    const header = document.createElement('div');
    header.className = 'species-header';
    header.innerHTML = `<span class="species-swatch" style="background:${SPECIES_COLOR[specie]}"></span>${specie} <span class="species-unit">(${info.unit})</span>`;
    block.appendChild(header);

    const grid = document.createElement('div');
    grid.className = 'control-points-grid';
    CONTROL_YEARS.forEach((year, i) => {
      const field = document.createElement('div');
      field.className = 'cp-field';
      const val = defaults[i][1];
      field.innerHTML = `<span>${year}</span><input type="number" step="any" data-year="${year}" value="${val.toFixed(2)}">`;
      grid.appendChild(field);
    });
    block.appendChild(grid);

    const resetBtn = document.createElement('button');
    resetBtn.className = 'reset-species-btn';
    resetBtn.textContent = 'Reset to preset';
    resetBtn.addEventListener('click', () => {
      const inputs = grid.querySelectorAll('input');
      defaults.forEach((pt, i) => { inputs[i].value = pt[1].toFixed(2); });
    });
    block.appendChild(resetBtn);

    container.appendChild(block);
  }
}

function populateAdvancedPanel() {
  const p = CONFIG.base_climate_params;
  const grid = document.getElementById('advanced-grid');
  const fields = [
    ['kappa0', 'Heat transfer &kappa;&#8321; (W/m&sup2;/K)', p.kappa[0]],
    ['kappa1', 'Heat transfer &kappa;&#8322;', p.kappa[1]],
    ['kappa2', 'Heat transfer &kappa;&#8323;', p.kappa[2]],
    ['c0', 'Heat capacity C&#8321; (W yr/m&sup2;/K)', p.capacity[0]],
    ['c1', 'Heat capacity C&#8322;', p.capacity[1]],
    ['c2', 'Heat capacity C&#8323;', p.capacity[2]],
    ['epsilon', 'Deep ocean efficacy &epsilon;', p.epsilon],
    ['forcing4co2', 'Forcing at 4&times;CO&#8322; (W/m&sup2;)', p.forcing_4co2],
  ];
  grid.innerHTML = '';
  fields.forEach(([id, labelHtml, val]) => {
    const wrap = document.createElement('label');
    wrap.innerHTML = `${labelHtml}<input type="number" step="any" id="adv-${id}" value="${val}">`;
    grid.appendChild(wrap);
  });
}

function resetAdvancedPanel() { populateAdvancedPanel(); }

function readAdvancedPanel() {
  const g = (id) => parseFloat(document.getElementById(`adv-${id}`).value);
  return {
    kappa: [g('kappa0'), g('kappa1'), g('kappa2')],
    capacity: [g('c0'), g('c1'), g('c2')],
    epsilon: g('epsilon'),
    forcing_4co2: g('forcing4co2'),
  };
}

function gatherEmissionsOverrides() {
  const overrides = {};
  document.querySelectorAll('#emissions-editor .species-block').forEach((block) => {
    const specie = block.dataset.specie;
    const points = [];
    block.querySelectorAll('input').forEach((inp) => {
      points.push([parseFloat(inp.dataset.year), parseFloat(inp.value)]);
    });
    overrides[specie] = points;
  });
  return overrides;
}

function gatherRequestBody() {
  const body = {
    scenario: document.getElementById('scenario-select').value,
    ocean_heat_uptake_scale: parseFloat(document.getElementById('ohu-slider').value),
    aerosol_forcing_scale: parseFloat(document.getElementById('aerosol-slider').value),
    co2_forcing_scale: parseFloat(document.getElementById('co2-forcing-slider').value),
    emissions_overrides: gatherEmissionsOverrides(),
  };
  if (advancedMode) {
    body.advanced = readAdvancedPanel();
  } else {
    body.ecs = parseFloat(document.getElementById('ecs-slider').value);
  }
  return body;
}

function fmt(n, digits = 2) {
  if (n === null || n === undefined || Number.isNaN(n)) return '—';
  return n.toFixed(digits);
}

async function runScenario() {
  const btn = document.getElementById('run-btn');
  btn.disabled = true;
  btn.textContent = 'Running…';
  try {
    const body = gatherRequestBody();
    const resp = await fetch('/api/run', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    if (!resp.ok) {
      const err = await resp.json();
      alert('Could not run the model: ' + (err.error || resp.statusText));
      return;
    }
    const result = await resp.json();

    if (document.getElementById('keep-comparison-chk').checked && lastResult) {
      comparisonResult = lastResult;
    }

    lastResult = result;
    lastParams = body;
    renderAll(result);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Run scenario';
  }
}

function renderAll(result) {
  document.getElementById('kpi-2024').textContent = fmt(result.warming_2024);
  document.getElementById('kpi-2050').textContent = fmt(result.warming_2050);
  document.getElementById('kpi-2100').textContent = fmt(result.warming_2100);
  document.getElementById('diag-ecs').textContent = fmt(result.ecs, 2) + '°C';
  document.getElementById('diag-tcr').textContent = fmt(result.tcr, 2) + '°C';

  renderTemperatureChart(result);
  renderForcingChart(result);
  renderConcentrationCharts(result);
  renderEmissionsChart(result);
  renderDataTable(result);
}

function renderTemperatureChart(result) {
  const traces = [{
    x: result.years, y: result.temperature_anomaly.map((v) => Number(v.toFixed(3))),
    type: 'scatter', mode: 'lines', name: 'This run',
    line: { color: COLORS.series1, width: 2 },
  }];
  if (comparisonResult) {
    traces.push({
      x: comparisonResult.years, y: comparisonResult.temperature_anomaly.map((v) => Number(v.toFixed(3))),
      type: 'scatter', mode: 'lines', name: 'Previous run',
      line: { color: COLORS.muted, width: 2, dash: 'dash' },
    });
  }
  Plotly.react('chart-temperature', traces, baseLayout({ yaxis: { title: '°C vs 1850–1900', gridcolor: COLORS.gridline } }), PLOTLY_CONFIG);
}

function renderForcingChart(result) {
  const series = [
    ['forcing_co2', 'CO₂', COLORS.series1],
    ['forcing_ch4', 'CH₄', COLORS.series2],
    ['forcing_n2o', 'N₂O', COLORS.series3],
    ['forcing_aerosol', 'Aerosols', COLORS.series4],
    ['forcing_other', 'Other', COLORS.series5],
  ];
  const traces = series.map(([key, name, color]) => ({
    x: result.years, y: result[key].map((v) => Number(v.toFixed(3))),
    type: 'scatter', mode: 'lines', name,
    stackgroup: 'forcing', line: { color, width: 1 }, fillcolor: color + '33',
  }));
  Plotly.react('chart-forcing', traces, baseLayout({ yaxis: { title: 'W/m²', gridcolor: COLORS.gridline } }), PLOTLY_CONFIG);
}

function renderConcentrationCharts(result) {
  const container = document.getElementById('chart-concentrations');
  container.innerHTML = '';
  const panels = [
    ['co2', 'CO₂ (ppm)', result.concentration_co2, COLORS.series1],
    ['ch4', 'CH₄ (ppb)', result.concentration_ch4, COLORS.series2],
    ['n2o', 'N₂O (ppb)', result.concentration_n2o, COLORS.series3],
  ];
  panels.forEach(([id, title, data, color]) => {
    const div = document.createElement('div');
    div.className = 'mini-chart';
    div.id = 'conc-' + id;
    container.appendChild(div);
    Plotly.react(div.id, [{
      x: result.years, y: data.map((v) => Number(v.toFixed(2))),
      type: 'scatter', mode: 'lines', name: title, line: { color, width: 2 }, showlegend: false,
    }], baseLayout({ margin: { t: 26, r: 10, l: 45, b: 30 }, title: { text: title, font: { size: 12, color: COLORS.textSecondary } }, legend: { visible: false } }), PLOTLY_CONFIG);
  });
}

function renderEmissionsChart(result) {
  const card = document.getElementById('emissions-preview-card');
  const hasEmissions = result.emissions && Object.keys(result.emissions).length > 0;
  card.style.display = hasEmissions ? '' : 'none';
  if (!hasEmissions) return;
  const traces = SPECIES_ORDER.filter((s) => result.emissions[s]).map((specie) => ({
    x: result.emissions_years, y: result.emissions[specie].map((v) => Number(v.toFixed(3))),
    type: 'scatter', mode: 'lines', name: specie, line: { color: SPECIES_COLOR[specie], width: 2 },
  }));
  Plotly.react('chart-emissions', traces, baseLayout({ yaxis: { title: 'Emissions (native units)', gridcolor: COLORS.gridline } }), PLOTLY_CONFIG);
}

function renderDataTable(result) {
  const wrap = document.getElementById('data-table-wrap');
  const years = result.years;
  const showYears = years.filter((y) => y % 5 === 0 || y === years[years.length - 1]);
  let html = '<table class="data-table"><thead><tr><th>Year</th><th>Temp anomaly (°C)</th><th>Total ERF (W/m²)</th><th>CO₂ (ppm)</th><th>CH₄ (ppb)</th><th>N₂O (ppb)</th></tr></thead><tbody>';
  showYears.forEach((y) => {
    const i = years.indexOf(y);
    html += `<tr><td>${y}</td><td>${fmt(result.temperature_anomaly[i])}</td><td>${fmt(result.forcing_total[i])}</td><td>${fmt(result.concentration_co2[i], 1)}</td><td>${fmt(result.concentration_ch4[i], 0)}</td><td>${fmt(result.concentration_n2o[i], 1)}</td></tr>`;
  });
  html += '</tbody></table>';
  wrap.innerHTML = html;
}

async function downloadCSV() {
  const body = lastParams || gatherRequestBody();
  const resp = await fetch('/api/download', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  if (!resp.ok) { alert('Could not generate download.'); return; }
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `fair_${body.scenario}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function resetAllControls() {
  document.getElementById('ecs-slider').value = CONFIG.climate_meta.central_ecs.toFixed(1);
  document.getElementById('ohu-slider').value = 1.0;
  document.getElementById('aerosol-slider').value = 1.0;
  document.getElementById('co2-forcing-slider').value = 1.0;
  updateSliderBadges();
  resetAdvancedPanel();
  advancedMode = false;
  document.getElementById('advanced-panel').classList.add('hidden');
  document.getElementById('toggle-advanced').textContent = 'Show advanced physical parameters ▾';
  document.getElementById('ecs-slider').disabled = false;
  document.getElementById('ohu-slider').disabled = false;
  populateEmissionsEditor();
}

function updateSliderBadges() {
  document.getElementById('ecs-value').textContent = parseFloat(document.getElementById('ecs-slider').value).toFixed(1) + '°C';
  document.getElementById('ohu-value').textContent = parseFloat(document.getElementById('ohu-slider').value).toFixed(2) + '×';
  document.getElementById('aerosol-value').textContent = parseFloat(document.getElementById('aerosol-slider').value).toFixed(2) + '×';
  document.getElementById('co2-forcing-value').textContent = parseFloat(document.getElementById('co2-forcing-slider').value).toFixed(2) + '×';
}

function initEventListeners() {
  ['ecs-slider', 'ohu-slider', 'aerosol-slider', 'co2-forcing-slider'].forEach((id) => {
    document.getElementById(id).addEventListener('input', updateSliderBadges);
  });

  document.getElementById('run-btn').addEventListener('click', runScenario);
  document.getElementById('reset-btn').addEventListener('click', resetAllControls);
  document.getElementById('download-btn').addEventListener('click', downloadCSV);

  document.getElementById('toggle-advanced').addEventListener('click', () => {
    advancedMode = !advancedMode;
    const panel = document.getElementById('advanced-panel');
    panel.classList.toggle('hidden', !advancedMode);
    document.getElementById('toggle-advanced').textContent = advancedMode ? 'Hide advanced physical parameters ▴' : 'Show advanced physical parameters ▾';
    document.getElementById('ecs-slider').disabled = advancedMode;
    document.getElementById('ohu-slider').disabled = advancedMode;
  });
  document.getElementById('reset-advanced').addEventListener('click', resetAdvancedPanel);

  document.getElementById('clear-comparison-btn').addEventListener('click', () => {
    comparisonResult = null;
    if (lastResult) renderTemperatureChart(lastResult);
  });

  document.getElementById('toggle-table-btn').addEventListener('click', () => {
    const wrap = document.getElementById('data-table-wrap');
    const hidden = wrap.classList.toggle('hidden');
    document.getElementById('toggle-table-btn').textContent = hidden ? 'Show data table' : 'Hide data table';
  });
}

(async function init() {
  await loadConfig();
  updateSliderBadges();
  initEventListeners();
  await runScenario();
})();
