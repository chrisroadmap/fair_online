from base64 import b64encode
from fair.forward import fair_scm
from fair.RCPs import rcp26, rcp45, rcp60, rcp85
from fair.ancil import natural, cmip6_volcanic, cmip6_solar
from flask import Flask, render_template, make_response
from flask_wtf import Form
from io import BytesIO
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from matplotlib.figure import Figure
from wtforms import FloatField, SelectField, BooleanField
from wtforms.validators import NumberRange, ValidationError, InputRequired
import numpy as np


app = Flask(__name__)
app.config.from_envvar('APPLICATION_SETTINGS')

@app.route('/')
def index():
    return render_template('index.jinja2')

@app.route('/fair', methods=['GET', 'POST'])
def fair():

    def validate_ecstcr(form, field):
        if type(form.tcr.data)==float and type(form.ecs.data)==float:
            if form.tcr.data > form.ecs.data:
                raise ValidationError(
                    'ECS must be greater than or equal to TCR')

    def validate_nonco2(form, field):
        if form.useMultigas.data and field.data==None:
            raise ValidationError('Field is required')

    class FairForm(Form):
        useMultigas = BooleanField("Multi-forcing run", default=True)
        rcp = SelectField("Emissions scenario", choices=[
           ('rcp26', 'RCP 2.6'),
           ('rcp45', 'RCP 4.5'),
           ('rcp60', 'RCP 6.0'),
           ('rcp85', 'RCP 8.5')])
        ecs = FloatField(
            "ECS",
            validators=[
                NumberRange(min=0.5,max=15),
                InputRequired(),
                validate_ecstcr],
            default=3.0)
        tcr = FloatField(
            "TCR",
            validators=[
                NumberRange(min=0.5,max=10),
                InputRequired(),
                validate_ecstcr],
            default=1.75)
        r0 = FloatField(
            "r0",
            validators=[
                NumberRange(min=0,max=100),
                InputRequired()],
            default=35)
        rc = FloatField(
            "rC",
            validators=[
                NumberRange(min=0.000,max=0.100),
                InputRequired()],
            default=0.019)
        rt = FloatField(
            "rT",
            validators=[
                NumberRange(min=0.000,max=20.000),
                InputRequired()],
            default=4.165)
        sf_co2 = FloatField(
            "CO2",
            validators=[
                NumberRange(min=0,max=3),
                InputRequired()],
            default=1)
        sf_ch4 = FloatField(
            "CH4",
            validators=[
                NumberRange(min=0,max=3),
                validate_nonco2],
            default=1)
        sf_n2o = FloatField(
            "N2O",
            validators=[
                NumberRange(min=0,max=3),
                validate_nonco2],
            default=1)
        sf_other = FloatField(
            "Other GHG",
            validators=[
                NumberRange(min=0,max=3),
                validate_nonco2],
            default=1)
        sf_tro3 = FloatField(
            "Tropospheric O3",
            validators=[
                NumberRange(min=-1,max=4),
                validate_nonco2],
            default=1)
        sf_sto3 = FloatField(
            "Stratospheric O3",
            validators=[
                NumberRange(min=-2,max=5),
                validate_nonco2],
            default=1)
        sf_sth2o = FloatField(
            "Stratospheric H2O from methane oxidation",
            validators=[
                NumberRange(min=-2,max=5),
                validate_nonco2],
            default=1)
        sf_con = FloatField(
            "Contrails",
            validators=[
                NumberRange(min=-2,max=5),
                validate_nonco2],
            default=1)
        sf_aer = FloatField(
            "Aerosols",
            validators=[
                NumberRange(min=-2,max=5),
                validate_nonco2],
            default=1)
        sf_bcsnow = FloatField(
            "Black carbon on snow",
            validators=[
                NumberRange(min=0,max=5),
                validate_nonco2],
            default=1)
        sf_landuse = FloatField(
            "Land use",
            validators=[
                NumberRange(min=-2,max=5),
                validate_nonco2],
            default=1)
        sf_vol = FloatField(
            "Volcanic",
            validators=[
                NumberRange(min=0,max=5),
                validate_nonco2],
            default=1)
        sf_sol = FloatField(
            "Solar",
            validators=[
                NumberRange(min=0,max=10),
                validate_nonco2],
            default=1)

    form = FairForm()
    result = None
    #T = np.array([0])

    if form.validate_on_submit():
        # must be more pythonic way
        all_emissions_switch = {
            'rcp26': rcp26.Emissions.emissions,
            'rcp45': rcp45.Emissions.emissions,
            'rcp60': rcp60.Emissions.emissions,
            'rcp85': rcp85.Emissions.emissions}
        co2_emissions_switch = {
            'rcp26': rcp26.Emissions.co2,
            'rcp45': rcp45.Emissions.co2,
            'rcp60': rcp60.Emissions.co2,
            'rcp85': rcp85.Emissions.co2}
        if form.useMultigas.data:
            emissions = all_emissions_switch[form.rcp.data][:336,:]
            nat   = natural.Emissions.emissions[:336,:]
            scale = np.ones(13)
            scale[0] = form.sf_co2.data
            scale[1] = form.sf_ch4.data
            scale[2] = form.sf_n2o.data
            scale[3] = form.sf_other.data
            scale[4] = form.sf_tro3.data
            scale[5] = form.sf_sto3.data
            scale[6] = form.sf_sth2o.data
            scale[7] = form.sf_con.data
            scale[8] = form.sf_aer.data
            scale[9] = form.sf_bcsnow.data
            scale[10] = form.sf_landuse.data
            scale[11] = form.sf_vol.data
            scale[12] = form.sf_sol.data
        else:
            emissions = co2_emissions_switch[form.rcp.data][:336]
            nat   = None
            scale = np.ones(336) * form.sf_co2.data
                # a temporary fix until 1.3.5 is released
        tcrecs = np.array([form.tcr.data, form.ecs.data])
        _,_,T = fair_scm(
            emissions=emissions,
            useMultigas=form.useMultigas.data,
            tcrecs=tcrecs,
            natural=nat,
            F_volcanic=cmip6_volcanic.Forcing.volcanic[:336],
            F_solar=cmip6_solar.Forcing.solar[:336],
            scale=scale,
            r0=form.r0.data,
            rc=form.rc.data,
            rt=form.rt.data)
        result = T[-1]
    if result:
        return render_template(
            'fair.jinja2',
            result=result,
            form=form,
            output=b64encode(plot_temp(T)).decode())
    else:
        return render_template(
            'fair.jinja2',
            result=result,
            form=form)


@app.route('/plot_temp')
def plot_temp(T, years=np.arange(1765,2101)):
#def plot_temp():
    fig  = Figure()
    ax   = fig.add_subplot(1, 1, 1)
    ax.plot(years, T)
    ax.set_xlim(1765,2100)
    ax.set_ylabel('Temperature anomaly since pre-industrial, $^{\circ}$C')
    ax.set_xlabel('Year')
    ax.grid()
#    ax.plot(np.arange(10), np.arange(10)**2)
    canvas = FigureCanvas(fig)
    output = BytesIO()
    canvas.print_png(output)
    response = output.getvalue()
    return response


if __name__ == '__main__':
    app.debug = True
    app.run()