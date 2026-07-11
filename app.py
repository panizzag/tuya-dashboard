import os
import json
import logging
from flask import Flask, render_template, request, jsonify
from tuya_api import TuyaAPI

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

def load_config():
    """Loads configuration from environment variables or config.json."""
    config = {}
    
    # 1. Try config.json
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
        except Exception as e:
            logger.error(f"Error reading config file: {e}")
            
    # 2. Try Environment Variables (takes precedence, useful for Render)
    env_client_id = os.environ.get("TUYA_CLIENT_ID") or os.environ.get("CLIENT_ID")
    env_client_secret = os.environ.get("TUYA_CLIENT_SECRET") or os.environ.get("CLIENT_SECRET")
    env_base_url = os.environ.get("TUYA_BASE_URL") or os.environ.get("BASE_URL")
    
    if env_client_id:
        config["client_id"] = env_client_id
    if env_client_secret:
        config["client_secret"] = env_client_secret
    if env_base_url:
        config["base_url"] = env_base_url
        
    return config

def save_config(config_data):
    """Saves configuration to config.json."""
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config_data, f, indent=4)
        return True
    except Exception as e:
        logger.error(f"Error saving config file: {e}")
        return False

def parse_sensor_device(device):
    """
    Parses a raw Tuya device and returns a normalized dictionary
    specialized for sensors (contact, motion, temp/humidity, etc.)
    """
    name = device.get("name", "Dispositivo")
    category = device.get("category", "")
    online = device.get("online", False)
    device_id = device.get("id", "")
    product_name = device.get("product_name", "Tuya Device")
    
    is_sensor = False
    sensor_type = "Otro"
    sensor_icon = "cpu"  # default icon
    
    # Map of Tuya categories to Spanish labels and Icon types
    category_mapping = {
        "mcs": {"type": "Contacto (Puerta/Ventana)", "icon": "door-closed", "is_sensor": True},
        "pir": {"type": "Movimiento (PIR)", "icon": "motion", "is_sensor": True},
        "wsdcg": {"type": "Temperatura y Humedad", "icon": "temp", "is_sensor": True},
        "sj": {"type": "Fuga de Agua / Inundación", "icon": "water", "is_sensor": True},
        "ywbj": {"type": "Humo / Incendio", "icon": "smoke", "is_sensor": True},
        "rqbj": {"type": "Fuga de Gas", "icon": "gas", "is_sensor": True},
        "zd": {"type": "Vibración", "icon": "vibrate", "is_sensor": True},
        "sos": {"type": "Botón de Emergencia (SOS)", "icon": "sos", "is_sensor": True},
        "hps": {"type": "Presencia Humana", "icon": "presence", "is_sensor": True},
        "mal": {"type": "Central de Alarma", "icon": "shield", "is_sensor": True},
        "sfkzq": {"type": "Controlador de Riego", "icon": "valve", "is_sensor": True},
    }
    
    if category in category_mapping:
        is_sensor = True
        sensor_type = category_mapping[category]["type"]
        sensor_icon = category_mapping[category]["icon"]
    else:
        # Fallback keyword matching in device or product name
        name_lower = name.lower() + " " + product_name.lower()
        if any(kw in name_lower for kw in ["sensor", "detect", "contacto", "alarm"]):
            is_sensor = True
            if any(kw in name_lower for kw in ["puerta", "ventana", "contact", "door", "window", "mcs"]):
                sensor_type = "Contacto (Puerta/Ventana)"
                sensor_icon = "door-closed"
            elif any(kw in name_lower for kw in ["movimiento", "motion", "pir", "presencia"]):
                sensor_type = "Movimiento (PIR)"
                sensor_icon = "motion"
            elif any(kw in name_lower for kw in ["temp", "hum", "wsdcg"]):
                sensor_type = "Temperatura y Humedad"
                sensor_icon = "temp"
            elif any(kw in name_lower for kw in ["agua", "water", "leak", "fuga", "sj"]):
                sensor_type = "Fuga de Agua / Inundación"
                sensor_icon = "water"
            elif any(kw in name_lower for kw in ["humo", "smoke", "ywbj"]):
                sensor_type = "Humo / Incendio"
                sensor_icon = "smoke"
            elif any(kw in name_lower for kw in ["gas", "rqbj"]):
                sensor_type = "Fuga de Gas"
                sensor_icon = "gas"
            elif any(kw in name_lower for kw in ["vibr", "vibrat", "zd"]):
                sensor_type = "Vibración"
                sensor_icon = "vibrate"
            elif any(kw in name_lower for kw in ["sos", "emergencia"]):
                sensor_type = "Botón de Emergencia (SOS)"
                sensor_icon = "sos"
            else:
                sensor_type = "Sensor General"
                sensor_icon = "cpu"

    # Datapoints status extraction
    status_list = device.get("status", [])
    status_dict = {item.get("code"): item.get("value") for item in status_list if "code" in item}
    
    # 1. Parse Battery Status
    battery_percentage = None
    battery_text = "N/A"
    
    if "battery_percentage" in status_dict:
        val = status_dict["battery_percentage"]
        if isinstance(val, (int, float)):
            battery_percentage = int(val)
    elif "battery" in status_dict:
        val = status_dict["battery"]
        if isinstance(val, (int, float)) and 0 <= val <= 100:
            battery_percentage = int(val)
            
    # Check battery_state if no percentage
    if battery_percentage is None:
        if "battery_state" in status_dict:
            state = str(status_dict["battery_state"]).lower()
            if "high" in state:
                battery_percentage = 90
                battery_text = "90% (Alto)"
            elif "middle" in state or "mid" in state:
                battery_percentage = 50
                battery_text = "50% (Medio)"
            elif "low" in state:
                battery_percentage = 15
                battery_text = "15% (Bajo)"
        elif "battery_value" in status_dict:
            val = status_dict["battery_value"]
            if isinstance(val, (int, float)):
                if 0 <= val <= 100:
                    battery_percentage = int(val)
                elif val > 100:
                    # Likely millivolts (e.g., 3000mV). We'll show voltage representation
                    battery_text = f"{val/1000:.2f}V"
                    
    if battery_percentage is not None:
        battery_text = f"{battery_percentage}%"

    # 2. Parse Sensor State Description
    state_desc = "Desconocido"
    
    if category == "mcs" or sensor_icon == "door-closed":
        # Contact door/window sensor
        state_val = status_dict.get("doorcontact_state")
        if state_val is None:
            state_val = status_dict.get("switch")
            
        if state_val is True or str(state_val).lower() in ["open", "true", "abierto"]:
            state_desc = "Abierto"
        elif state_val is False or str(state_val).lower() in ["close", "closed", "false", "cerrado"]:
            state_desc = "Cerrado"
        else:
            state_desc = "Cerrado" if online else "Desconectado" # Default sensible state for a closed door
            
    elif category == "pir" or sensor_icon == "motion":
        # Human motion sensor
        state_val = status_dict.get("pir")
        if state_val == "pir" or state_val is True or str(state_val).lower() in ["true", "alarm", "motion"]:
            state_desc = "Movimiento Detectado"
        elif state_val == "none" or state_val is False or str(state_val).lower() in ["false", "normal", "none"]:
            state_desc = "Sin Movimiento"
        else:
            state_desc = "Sin Movimiento"
            
    elif category == "wsdcg" or sensor_icon == "temp":
        # Temp/Humidity
        temp = status_dict.get("temp_current")
        humidity = status_dict.get("humidity_value")
        
        parts = []
        if temp is not None:
            if isinstance(temp, (int, float)):
                # Divide by 10 if integer scaled
                if temp > 100 or temp < -100:
                    temp = temp / 10.0
                parts.append(f"{temp}°C")
        if humidity is not None:
            parts.append(f"{humidity}% HR")
            
        state_desc = ", ".join(parts) if parts else "Sin datos"
        
    elif category == "sj" or sensor_icon == "water":
        # Water leak
        state_val = status_dict.get("watersensor_state")
        if state_val in ["alarm", "water"] or state_val is True:
            state_desc = "¡Fuga de Agua!"
        elif state_val in ["normal", "no_water"] or state_val is False:
            state_desc = "Seco / Sin Fuga"
        else:
            state_desc = "Normal"
            
    elif category == "ywbj" or sensor_icon == "smoke":
        # Smoke
        state_val = status_dict.get("smoke_sensor_status") or status_dict.get("smoke_sensor_state")
        if state_val in ["alarm", "smoke"] or state_val is True:
            state_desc = "¡Humo Detectado!"
        else:
            state_desc = "Normal"
            
    elif category == "rqbj" or sensor_icon == "gas":
        # Gas
        state_val = status_dict.get("gas_sensor_status") or status_dict.get("gas_sensor_state")
        if state_val in ["alarm", "gas"] or state_val is True:
            state_desc = "¡Gas Detectado!"
        else:
            state_desc = "Normal"
            
    elif category == "zd" or sensor_icon == "vibrate":
        # Vibration
        state_val = status_dict.get("vibration_status") or status_dict.get("vibration_state") or status_dict.get("shock_state")
        if state_val in ["vibrate", "alarm", "vibration", "vibrat"] or state_val is True:
            state_desc = "Vibración Detectada"
        elif state_val in ["normal", "no_vibration"] or state_val is False:
            state_desc = "Sin Vibración"
        else:
            state_desc = "Sin Vibración"
            
    elif category == "mal" or sensor_icon == "shield":
        # Alarm Host
        state_val = status_dict.get("master_mode")
        if state_val == "disarmed":
            state_desc = "Desarmado"
        elif state_val in ["arm", "armed", "arm_mode"]:
            state_desc = "Armado"
        elif state_val == "home":
            state_desc = "Armado Parcial"
        else:
            state_desc = str(state_val).capitalize() if state_val else "Normal"
            
    elif category == "sfkzq" or sensor_icon == "valve":
        # Irrigation Valve
        state_val = status_dict.get("switch")
        if state_val is True or str(state_val).lower() in ["true", "on"]:
            state_desc = "Abierto (Regando)"
        else:
            state_desc = "Cerrado"
            
    elif category == "sos" or sensor_icon == "sos":
        state_val = status_dict.get("sos_state") or status_dict.get("sos")
        if state_val in ["alarm", "sos"] or state_val is True:
            state_desc = "¡SOS Activado!"
        else:
            state_desc = "En espera"
            
    elif category == "hps" or sensor_icon == "presence":
        state_val = status_dict.get("presence_state") or status_dict.get("presence")
        if state_val in ["presence", "alarm"] or state_val is True:
            state_desc = "Presencia Detectada"
        else:
            state_desc = "Sin Presencia"
            
    else:
        # Generic state extraction fallback
        relevant_keys = [k for k in status_dict.keys() if k not in ["battery_percentage", "battery_value", "battery_state", "battery", "va_battery", "temper_alarm"]]
        if relevant_keys:
            key = relevant_keys[0]
            val = status_dict[key]
            if isinstance(val, bool):
                state_desc = "Activo" if val else "Inactivo"
            else:
                state_desc = str(val)
        else:
            state_desc = "Conectado" if online else "Desconectado"
            
    return {
        "id": device_id,
        "name": name,
        "category": category,
        "product_name": product_name,
        "online": online,
        "is_sensor": is_sensor,
        "sensor_type": sensor_type,
        "sensor_icon": sensor_icon,
        "state_description": state_desc,
        "battery_percentage": battery_percentage,
        "battery_text": battery_text,
        "status_raw": status_dict
    }

@app.route("/")
def index():
    config = load_config()
    is_configured = "client_id" in config and "client_secret" in config
    return render_template("index.html", is_configured=is_configured, config=config)

@app.route("/api/config", methods=["POST"])
def configure():
    data = request.json or {}
    client_id = data.get("client_id", "").strip()
    client_secret = data.get("client_secret", "").strip()
    base_url = data.get("base_url", "https://openapi.tuyaus.com").strip()
    
    if not client_id or not client_secret:
        return jsonify({"success": False, "error": "Client ID y Client Secret son requeridos"}), 400
        
    try:
        # Validate by requesting an access token
        api = TuyaAPI(client_id, client_secret, base_url)
        access_token, uid = api.get_access_token()
        
        # Save config
        config_data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "base_url": base_url,
            "uid": uid
        }
        if save_config(config_data):
            return jsonify({"success": True, "uid": uid})
        else:
            return jsonify({"success": False, "error": "No se pudo guardar la configuración localmente"}), 500
            
    except Exception as e:
        logger.error(f"Configuration validation failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 400

@app.route("/api/devices", methods=["GET"])
def get_devices():
    # 1. Try credentials from Request Headers (localStorage client-side persistence)
    client_id = request.headers.get("X-Tuya-Client-Id")
    client_secret = request.headers.get("X-Tuya-Client-Secret")
    base_url = request.headers.get("X-Tuya-Base-Url", "https://openapi.tuyaus.com")
    
    # 2. Fallback to loaded config (config.json + Environment variables)
    if not client_id or not client_secret:
        config = load_config()
        client_id = config.get("client_id")
        client_secret = config.get("client_secret")
        base_url = config.get("base_url", "https://openapi.tuyaus.com")
        
    if not client_id or not client_secret:
        return jsonify({"success": False, "error": "Tuya no está configurado todavía"}), 401
        
    try:
        api = TuyaAPI(client_id, client_secret, base_url)
        
        # Fetch token and UID
        access_token, uid = api.get_access_token()
        
        # In case the config has an outdated/missing UID, update it (only if we are using config.json)
        if os.path.exists(CONFIG_FILE):
            config = load_config()
            if config.get("uid") != uid and config.get("client_id") == client_id:
                config["uid"] = uid
                save_config(config)
            
        # Get raw device list
        raw_devices = api.get_devices(access_token, uid)
        
        # Parse and divide into sensors and other devices
        sensors = []
        others = []
        
        for dev in raw_devices:
            parsed = parse_sensor_device(dev)
            if parsed["is_sensor"]:
                sensors.append(parsed)
            else:
                others.append(parsed)
                
        return jsonify({
            "success": True,
            "sensors": sensors,
            "others": others
        })
        
    except Exception as e:
        logger.error(f"Error fetching devices: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/logout", methods=["POST"])
def logout():
    if os.path.exists(CONFIG_FILE):
        try:
            os.remove(CONFIG_FILE)
            return jsonify({"success": True})
        except Exception as e:
            logger.error(f"Error deleting config file during logout: {e}")
            return jsonify({"success": False, "error": str(e)}), 500
    return jsonify({"success": True})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    # Bind to 0.0.0.0 to make it accessible inside local networks if needed
    app.run(host="0.0.0.0", port=port, debug=True)
