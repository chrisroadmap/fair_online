"""Flask application for the FaIR interactive climate model dashboard."""
import io
import csv as csv_module

from flask import Flask, jsonify, render_template, request, Response

import fair_engine as fe

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/config")
def api_config():
    scenarios = fe.list_scenarios()
    editable_species = {
        specie: {
            "unit": fe.EMISSIONS_UNITS[specie],
            "defaults": {
                scen: fe.default_emissions_control_points(scen, specie) for scen in scenarios
            },
        }
        for specie in fe.EDITABLE_SPECIES
    }
    return jsonify(
        {
            "scenarios": scenarios,
            "editable_species": editable_species,
            "edit_anchor_year": fe.EDIT_ANCHOR_YEAR,
            "climate_meta": fe.CLIMATE_META,
            "year_start": fe.YEAR_START,
            "year_end": fe.YEAR_END,
            "base_climate_params": {
                "kappa": fe._BASE_K,
                "capacity": fe._BASE_C,
                "epsilon": fe._BASE_EPS,
                "forcing_4co2": fe._BASE_F4,
            },
            "observed": fe.observed_data(),
        }
    )


def _parse_run_request(body):
    scenario = body.get("scenario", "M")
    ecs = body.get("ecs")
    ecs = float(ecs) if ecs is not None else None
    ohu_scale = float(body.get("ocean_heat_uptake_scale", 1.0))
    co2_scale = float(body.get("co2_forcing_scale", 1.0))
    aerosol_scale = float(body.get("aerosol_forcing_scale", 1.0))
    advanced = body.get("advanced")
    emissions_overrides = body.get("emissions_overrides") or {}
    return dict(
        scenario=scenario,
        ecs=ecs,
        ocean_heat_uptake_scale=ohu_scale,
        co2_forcing_scale=co2_scale,
        aerosol_forcing_scale=aerosol_scale,
        advanced=advanced,
        emissions_overrides=emissions_overrides,
    )


@app.route("/api/run", methods=["POST"])
def api_run():
    body = request.get_json(force=True) or {}
    try:
        params = _parse_run_request(body)
        result = fe.run_scenario(**params)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 400
    return jsonify(result)


@app.route("/api/download", methods=["POST"])
def api_download():
    body = request.get_json(force=True) or {}
    try:
        params = _parse_run_request(body)
        result = fe.run_scenario(**params)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 400

    buf = io.StringIO()
    writer = csv_module.writer(buf)
    header = [
        "year",
        "temperature_anomaly_C_rel_1850-1900",
        "forcing_total_Wm2",
        "forcing_co2_Wm2",
        "forcing_ch4_Wm2",
        "forcing_n2o_Wm2",
        "forcing_aerosol_Wm2",
        "forcing_other_Wm2",
        "co2_concentration_ppm",
        "ch4_concentration_ppb",
        "n2o_concentration_ppb",
    ]
    writer.writerow(header)
    for i, year in enumerate(result["years"]):
        writer.writerow(
            [
                year,
                result["temperature_anomaly"][i],
                result["forcing_total"][i],
                result["forcing_co2"][i],
                result["forcing_ch4"][i],
                result["forcing_n2o"][i],
                result["forcing_aerosol"][i],
                result["forcing_other"][i],
                result["concentration_co2"][i],
                result["concentration_ch4"][i],
                result["concentration_n2o"][i],
            ]
        )
    scenario = params["scenario"]
    filename = f"fair_{scenario}_ecs{params['ecs'] or 'default'}.csv"
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


if __name__ == "__main__":
    app.run(debug=True, port=5050)
