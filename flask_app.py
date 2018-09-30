from flask import Flask, render_template
from flask_wtf import Form
from wtforms import FloatField, SelectField
from wtforms.validators import NumberRange, ValidationError, InputRequired
from fair.forward import fair_scm
#from fair.rcps import rcp26, rcp45, rcp60, rcp85
import numpy as np

app = Flask(__name__)
app.config['SECRET_KEY'] = 'crum47cmcf8zw-00kmxb'

@app.route('/')
def index():
    return render_template('index.jinja2')

@app.route('/fair', methods=['GET', 'POST'])
def fair():
    
    def validate_ecstcr(form, field):
        if form.tcr.data > form.ecs.data:
            raise ValidationError('ECS must be greater than or equal to TCR')
            
    class FairForm(Form):
        rcp = SelectField("Emissions scenario", choices=[
           ('rcp26', 'RCP 2.6'), 
           ('rcp45', 'RCP 4.5'),
           ('rcp60', 'RCP 6.0'),
           ('rcp85', 'RCP 8.5')])
        ecs = FloatField("ECS", validators=[NumberRange(min=0.5,max=15),InputRequired()])
        tcr = FloatField("TCR", validators=[NumberRange(min=0.5,max=10),InputRequired(),validate_ecstcr])
        # check tcr <= ecs
    
    form = FairForm()
    result = None
    
    if form.validate_on_submit():
        tcrecs = np.array([form.tcr.data, form.ecs.data])
        _,_,T = fair_scm(emissions=np.ones(100)*10,
                         useMultigas=False,
                         tcrecs=tcrecs)
        result = T[-1]
    return render_template('fair.jinja2', result=result, form=form)

if __name__ == '__main__':
    app.debug = True
    app.run()