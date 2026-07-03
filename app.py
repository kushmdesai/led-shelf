import os
from functools import wraps

from flask import Flask, render_template, redirect, url_for, request, jsonify, session
from mqtt import MQTT_HOST, MQTT_PORT, client as mqtt_client, send_message
from threading import Lock
from werkzeug.security import check_password_hash
import db
from schedule import start_scheduler


state_lock = Lock()
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or os.urandom(32)
db.init_db()
start_scheduler(state_lock=state_lock)

PASSWORD_HASH_ENV = "LED_SHELF_PASSWORD_HASH"

INT_STATE_KEYS = {"brightness", "whitebalance", "speed"}
INT_SETTING_KEYS = {"mqtt_port", "led_count", "max_brightness"}
BOOL_SETTING_KEYS = {"startup_effect"}
VALID_EFFECTS = [
    'rainbow', 'rainbow_wave', 'breathe', 'color_wipe',
    'theater_chase', 'twinkle', 'fire', 'meteor',
    'color_cycle', 'strobe', 'bouncing_ball', 'running_lights', 'none'
]

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

def is_logged_in():
    return session.get("logged_in") is True

def require_auth(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if is_logged_in():
            return view(*args, **kwargs)

        if request.path.startswith("/api/"):
            return {"status": "error", "message": "authentication required"}, 401

        return redirect(url_for("login", next=request.path))

    return wrapped

def password_is_valid(password):
    password_hash = os.environ.get(PASSWORD_HASH_ENV)

    if not password_hash:
        return False

    return check_password_hash(password_hash, password)

def safe_next_url(next_url):
    if next_url and next_url.startswith("/") and not next_url.startswith("//"):
        return next_url

    return url_for("control")

def normalize_device_state(raw_state):
    state = dict(raw_state)

    for key in INT_STATE_KEYS:
        if key in state:
            value = validate_int(state[key])
            if value is not None:
                state[key] = value

    return state

def normalize_settings(raw_settings):
    settings = dict(raw_settings)
    settings["mqtt_host"] = MQTT_HOST
    settings["mqtt_port"] = MQTT_PORT

    for key in INT_SETTING_KEYS:
        if key in settings:
            value = validate_int(settings[key])
            if value is not None:
                settings[key] = value

    for key in BOOL_SETTING_KEYS:
        if key in settings:
            settings[key] = str(settings[key]).lower() == "true"

    return settings

def get_max_brightness():
    settings = db.get_settings()
    return validate_int(settings.get("max_brightness"), 1, 100) or 100

def validate_schedule_time(time):
    if not isinstance(time, str) or len(time) != 5 or time[2] != ":":
        return False

    hour = validate_int(time[:2], 0, 23)
    minute = validate_int(time[3:], 0, 59)

    return hour is not None and minute is not None

@app.route("/")
@require_auth
def auth():
    return redirect(url_for('control'))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        if is_logged_in():
            return redirect(url_for("control"))
        return render_template("login.html")

    password = request.form.get("password", "")

    if password_is_valid(password):
        session.clear()
        session["logged_in"] = True
        return redirect(safe_next_url(request.form.get("next")))

    return render_template("login.html", error="Invalid password"), 401

@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/control")
@require_auth
def control():
    return render_template('control.html')

@app.route("/settings")
@require_auth
def settings():
    return render_template('settings.html')

@app.route("/schedule")
@require_auth
def schedule():
    return render_template('schedule.html')

@app.route("/api/power", methods=['POST'])
@require_auth
def power():
    data = request.get_json() or {}
    state = data.get('state')

    if state not in ["on", "off"]:
        return error("invalid state")

    with state_lock:
        db.set_device_state("power", state)
        settings = normalize_settings(db.get_settings())
        device_state = db.get_device_state()

    send_message("power", state)

    startup_effect = device_state.get("effect")
    if state == "on" and settings.get("startup_effect") and startup_effect != "none":
        send_message("effect", startup_effect)

    return {"status": "ok", "state": state}

@app.route("/api/brightness", methods=['POST'])
@require_auth
def brightness():
    data = request.get_json() or {}
    value = validate_int(data.get('value'), 0, get_max_brightness())

    if value is None:
        return error("invalid brightness")

    with state_lock:
        db.set_device_state("brightness", value)
    send_message("brightness", str(value))

    return {"status": "ok", "value": value}

@app.route("/api/color", methods=['POST'])
@require_auth
def color():
    data = request.get_json() or {}
    r = validate_int(data.get('r'), 0, 255)
    g = validate_int(data.get('g'), 0, 255)
    b = validate_int(data.get('b'), 0, 255)

    if None in (r, g, b):
        return error("invalid color")

    color_value = f"{r},{g},{b}"

    with state_lock:
        db.set_device_state("color", color_value)
    send_message("color", color_value)

    return {"status": "ok", "r": r, "g": g, "b": b}

@app.route("/api/whitebalance", methods=['POST'])
@require_auth
def whitebalance():
    data = request.get_json() or {}
    kelvin = validate_int(data.get('kelvin'), 1000, 10000)

    if kelvin is None:
        return error("invalid kelvin")

    with state_lock:
        db.set_device_state("whitebalance", kelvin)
    send_message("whitebalance", str(kelvin))

    return {"status": "ok", "kelvin": kelvin}

@app.route("/api/state", methods=['GET'])
@require_auth
def get_state():
    with state_lock:
        return jsonify(normalize_device_state(db.get_device_state()))

@app.route("/effects")
@require_auth
def effects():
    return render_template('effects.html')

@app.route("/api/effect", methods=['POST'])
@require_auth
def effect():
    data = request.get_json() or {}
    effect_name = data.get('effect')

    if effect_name not in VALID_EFFECTS:
        return error("invalid effect")

    with state_lock:
        db.set_device_state("effect", effect_name)
    send_message("effect", effect_name)

    return {"status": "ok", "effect": effect_name}


@app.route("/api/speed", methods=['POST'])
@require_auth
def speed():
    data = request.get_json() or {}
    value = validate_int(data.get('value'), 1, 100)

    if value is None:
        return error("invalid speed")

    with state_lock:
        db.set_device_state("speed", value)
    send_message("speed", str(value))

    return {"status": "ok", "value": value}

@app.route("/api/settings", methods=["GET"])
@require_auth
def get_settings():
    with state_lock:
        return jsonify(normalize_settings(db.get_settings()))


@app.route("/api/settings", methods=["POST"])
@require_auth
def update_settings():
    data = request.get_json() or {}
    changes = {}

    if "led_count" in data:
        led_count = validate_int(data.get("led_count"), 1, 5000)
        if led_count is None:
            return error("invalid led count")
        changes["led_count"] = led_count

    if "max_brightness" in data:
        max_brightness = validate_int(data.get("max_brightness"), 1, 100)
        if max_brightness is None:
            return error("invalid max brightness")
        changes["max_brightness"] = max_brightness

    if "startup_effect" in data:
        if not isinstance(data["startup_effect"], bool):
            return error("invalid startup effect")
        changes["startup_effect"] = "true" if data["startup_effect"] else "false"

    with state_lock:
        settings = normalize_settings(db.set_settings(changes)) if changes else normalize_settings(db.get_settings())

    if "led_count" in changes:
        send_message("led_count", str(settings["led_count"]))

    return {"status": "ok", "message": "Settings saved", "settings": settings}


@app.route("/api/status", methods=["GET"])
@require_auth
def get_status():
    with state_lock:
        settings = normalize_settings(db.get_settings())
        device_state = normalize_device_state(db.get_device_state())

    mqtt_online = mqtt_client.is_connected()
    power = device_state.get("power", "off")

    return jsonify({
        "led_online": mqtt_online,
        "led_power": power,
        "switch_online": False,
        "mqtt_online": mqtt_online,
        "mqtt_host": settings["mqtt_host"],
        "mqtt_port": settings["mqtt_port"],
        "pi_online": True,
    })

@app.route("/api/schedule", methods=["GET"])
@require_auth
def get_schedules():
    with state_lock:
        return jsonify(db.get_schedules())


@app.route("/api/schedule", methods=["POST"])
@require_auth
def add_schedule():
    data = request.get_json() or {}

    time = data.get("time")
    action = data.get("action")
    enabled = data.get("enabled", True)
    repeat_days = data.get("repeat_days", "daily")

    if not validate_schedule_time(time):
        return error("invalid time")

    if action not in ["on", "off"]:
        return error("invalid action")

    if not isinstance(enabled, bool):
        return error("invalid enabled")

    if not isinstance(repeat_days, str) or not repeat_days:
        return error("invalid repeat_days")

    with state_lock:
        schedule = db.add_schedule(time, action, enabled, repeat_days)

    return {"status": "ok", "schedule": schedule}


@app.route("/api/schedule/<int:schedule_id>", methods=["PATCH"])
@require_auth
def update_schedule(schedule_id):
    data = request.get_json() or {}
    changes = {}

    if "enabled" in data:
        if not isinstance(data["enabled"], bool):
            return error("invalid enabled")
        changes["enabled"] = data["enabled"]

    if "time" in data:
        if not validate_schedule_time(data["time"]):
            return error("invalid time")
        changes["time"] = data["time"]

    if "action" in data:
        if data["action"] not in ["on", "off"]:
            return error("invalid action")
        changes["action"] = data["action"]

    if "repeat_days" in data:
        if not isinstance(data["repeat_days"], str) or not data["repeat_days"]:
            return error("invalid repeat_days")
        changes["repeat_days"] = data["repeat_days"]

    with state_lock:
        schedule = db.update_schedule(schedule_id, **changes)

    if schedule is not None:
        return {"status": "ok", "schedule": schedule}

    return {"status": "error", "message": "schedule not found"}, 404


@app.route("/api/schedule/<int:schedule_id>", methods=["DELETE"])
@require_auth
def delete_schedule(schedule_id):
    with state_lock:
        deleted = db.delete_schedule(schedule_id)

    if deleted:
        return {"status": "ok"}

    return {"status": "error", "message": "schedule not found"}, 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)
