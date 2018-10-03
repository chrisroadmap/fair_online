from flask import Flask, render_template
from flask_wtf import Form
from wtforms import FloatField, SelectField, BooleanField
from wtforms.validators import NumberRange, ValidationError, InputRequired
from fair.forward import fair_scm
from fair.RCPs import rcp26, rcp45, rcp60, rcp85
from fair.ancil import natural, cmip6_volcanic, cmip6_solar
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
                NumberRange(min=0.0,max=100),
                InputRequired()],
            default=35)
        sf_co2 = FloatField(
            "CO2",
            validators=[
                NumberRange(min=0.0,max=3.0),
                InputRequired()],
            default=1.0)
        sf_ch4 = FloatField(
            "CH4",
            validators=[
                NumberRange(min=0.0,max=3.0),
                validate_nonco2],
            default=1.0)
        sf_n2o = FloatField(
            "N2O",
            validators=[
                NumberRange(min=0.0,max=3.0),
                validate_nonco2],
            default=1.0)

    form = FairForm()
    result = None

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
            r0=form.r0.data)
        result = T[-1]
    return render_template('fair.jinja2', result=result, form=form)

if __name__ == '__main__':
    app.debug = True
    app.run()