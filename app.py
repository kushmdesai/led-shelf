from flask import Flask, render_template, redirect, url_for, request, jsonify
from mqtt import send_message
from threading import Lock

state_lock = Lock()
app = Flask(__name__)

device_state = {
    "power": "off",
    "brightness": 80,
    "color": "#ffffff",
    "whitebalance": 4000
}

def validate_int(value, min_v=None, max_v=None):
    try:
        v = int(value)
    except (TypeError, ValueError):
        return None

    if min_v is not None and v < min_v:
        return None
    if max_v is not None and v > max_v:
        return None

    return v

def validate_hex(color):
    if not isinstance(color, str):
        return None

    if len(color) != 7:
        return None

    if not color.startswith("#"):
        return None

    # ensure it's valid hex characters
    hex_part = color[1:]
    try:
        int(hex_part, 16)
    except ValueError:
        return None

    return color

def error(msg):
    return {"status": "error", "message": msg}, 400

@app.route("/")
def auth():
    return redirect(url_for('control'))

@app.route("/control")
def control():
    return render_template('control.html')

@app.route("/settings")
def settings():
    return render_template('settings.html')

@app.route("/api/power", methods=['POST'])
def power():
    data = request.get_json() or {}
    state = data.get('state')

    if state not in ["on", "off"]:
        return error("invalid state")

    with state_lock:
        device_state["power"] = state
    send_message("power", state)

    return {"status": "ok", "state": state}

@app.route("/api/brightness", methods=['POST'])
def brightness():
    data = request.get_json() or {}
    value = validate_int(data.get('value'), 0, 100)

    if value is None:
        return error("invalid brightness")

    with state_lock:
        device_state["brightness"] = value
    send_message("brightness", str(value))

    return {"status": "ok", "value": value}

@app.route("/api/color", methods=['POST'])
def color():
    data = request.get_json() or {}
    hex_color = validate_hex(data.get('hex'))

    if hex_color is None:
        return error("invalid color")

    with state_lock:
        device_state["color"] = hex_color
    send_message("color", hex_color)

    return {"status": "ok", "hex": hex_color}

@app.route("/api/whitebalance", methods=['POST'])
def whitebalance():
    data = request.get_json() or {}
    kelvin = validate_int(data.get('kelvin'), 1000, 10000)

    if kelvin is None:
        return error("invalid kelvin")

    with state_lock:
        device_state["whitebalance"] = kelvin
    send_message("whitebalance", str(kelvin))

    return {"status": "ok", "kelvin": kelvin}

@app.route("/api/state", methods=['GET'])
def get_state():
    return jsonify(device_state)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)