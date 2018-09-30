from flask import Flask, render_template
from flask_wtf import Form
from wtforms import FloatField
from wtforms.validators import NoneOf, NumberRange
from fair.forward import fair_scm
import numpy as np

app = Flask(__name__)
app.config['SECRET_KEY'] = 'crum47cmcf8zw-00kmxb'

@app.route('/')
def index():
    return render_template('index.jinja2')

@app.route('/divide', methods=['GET', 'POST'])
def divide():

    class DivideForm(Form):
        number = FloatField("Number")
        divide_by = FloatField("Divide by", validators=[NoneOf([0])])

    form = DivideForm()
    result = None

    if form.validate_on_submit():
        result = form.number.data / form.divide_by.data

    return render_template('divide.jinja2', result=result, form=form)

@app.route('/fair', methods=['GET', 'POST'])
def fair():
    class EcsForm(Form):
        ecs = FloatField("ECS", validators=[NumberRange(min=0.5,max=15)])
    
    form = EcsForm()
    result = None
    
    if form.validate_on_submit():
        tcrecs = np.array([1.6, form.ecs.data])
        _,_,T = fair_scm(emissions=np.ones(100)*10,
                         useMultigas=False,
                         tcrecs=tcrecs)
        result = T[-1]
    return render_template('fair.jinja2', result=result, form=form)

if __name__ == '__main__':
    app.debug = True
    app.run()