from flask import Flask, render_template, redirect, url_for, request, jsonify
from mqtt import send_message

app = Flask(__name__)

@app.route("/")
def auth():
    return redirect(url_for('control'))

@app.route("/control")
def control():
    return render_template('control.html')

@app.route("/settings")
def settings():
    return render_template('settings.html')

@app.route("/api/power", methods = ['POST'])
def power():
    response = request.get_json()
    send_message("power", response.get('state'))
    return {'status': 'finished'}

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)