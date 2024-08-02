from flask import Flask

app = Flask(__name__)

@app.route('/')
def hello_world():
    return 'the new fair model interactive is on its way!'

