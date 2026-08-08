import os
import json
import logging
from flask import Flask, render_template, request, jsonify, redirect, make_response
from tuya_api import TuyaAPI

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

@app.before_request
def check_authentication():
    pwd_login = os.environ.get("PWD_LOGIN", "6913").strip()
    
    # Allow accessing static files, login page, login API, and the Alexa endpoint
    # (The Alexa endpoint has its own token-based auth via ?token= and is called by Amazon, not the browser)
    if request.path in ["/login", "/api/login", "/api/alexa"] or request.path.startswith("/static/"):
        return
        
    # Check authentication cookie
    auth_token = request.cookies.get("login_token")
    if auth_token != pwd_login:
        if request.path.startswith("/api/"):
            return jsonify({"success": False, "error": "No autorizado"}), 401
        return redirect("/login")

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

def get_alarm_host(sensors, others=None):
    """
    Finds the central alarm host device ("Alarma 4G", "Central de Alarma", etc.)
    from lists of sensors and other devices.
    """
    all_devices = list(sensors or []) + list(others or [])
    for dev in all_devices:
        if not isinstance(dev, dict):
            continue
        cat = dev.get("category", "")
        icon = dev.get("sensor_icon", "")
        dev_name = (dev.get("name") or "").lower()
        if cat == "mal" or icon == "shield" or "alarma" in dev_name or "alarm" in dev_name:
            return dev
    return None

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
    
    name_lower = name.lower() + " " + product_name.lower()
    
    # Priority check for Alarm Host (e.g., "Alarma 4G", "Alarma", "Alarm Panel")
    if any(kw in name_lower for kw in ["alarma 4g", "alarma", "alarm host", "central de alarma", "panel de alarma"]):
        is_sensor = True
        sensor_type = "Central de Alarma"
        sensor_icon = "shield"
    elif category in category_mapping:
        is_sensor = True
        sensor_type = category_mapping[category]["type"]
        sensor_icon = category_mapping[category]["icon"]
    else:
        # Fallback keyword matching in device or product name
        if any(kw in name_lower for kw in ["sensor", "detect", "contacto", "alarm", "panel"]):
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
                sensor_type = "Central de Alarma"
                sensor_icon = "shield"

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
            
    elif category == "mal" or sensor_icon == "shield" or "alarma" in name_lower or "alarm" in name_lower:
        # Alarm Host ("Alarma 4G", "Central de Alarma", etc.)
        state_val = status_dict.get("master_mode") or status_dict.get("mode") or status_dict.get("alarm_state") or status_dict.get("arm_state")
        if state_val == "disarmed" or state_val is False or state_val == "disarm":
            state_desc = "Desarmado"
        elif state_val in ["arm", "armed", "arm_mode", "away"]:
            state_desc = "Armado (Ausente)"
        elif state_val in ["home", "stay", "home_arm"]:
            state_desc = "Armado (En Casa)"
        else:
            state_desc = str(state_val).capitalize() if state_val is not None else "Desarmado"
            
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

@app.route("/login")
def login_page():
    return render_template("login.html")

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.json or {}
    password = data.get("password", "").strip()
    pwd_login = os.environ.get("PWD_LOGIN", "6913").strip()
    
    if password == pwd_login:
        response = make_response(jsonify({"success": True}))
        # Set persistent login cookie for 30 days
        response.set_cookie("login_token", pwd_login, max_age=30*24*60*60, httponly=True, samesite='Lax')
        return response
    else:
        return jsonify({"success": False, "error": "Código PIN incorrecto"}), 401

@app.route("/api/devices/<device_id>/commands", methods=["POST"])
def send_device_commands(device_id):
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
        data = request.json or {}
        commands = data.get("commands", [])
        
        if not commands:
            return jsonify({"success": False, "error": "No se proporcionaron comandos"}), 400
            
        api = TuyaAPI(client_id, client_secret, base_url)
        access_token, uid = api.get_access_token()
        
        result = api.send_device_commands(access_token, device_id, commands)
        return jsonify({"success": True, "result": result})
        
    except Exception as e:
        logger.error(f"Error sending commands to device {device_id}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

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

# --- ALEXA SKILL INTEGRATION ---
# Endpoint to securely handle Alexa Skill requests using a simple secret token for personal security
@app.route("/api/alexa", methods=["POST"])
def alexa_skill():
    # Simple token validation (optional but highly recommended for private endpoints in Render)
    expected_token = os.environ.get("PWD_LOGIN", "6913").strip()
    provided_token = request.args.get("token", "").strip()
    
    # If the user has custom PWD_LOGIN but doesn't pass token=XXXX in Alexa URL, deny access.
    # This prevents anyone from calling your public Render URL's Alexa endpoint.
    if expected_token and provided_token != expected_token:
        # Return a standard unauthorized response
        return jsonify({
            "version": "1.0",
            "response": {
                "outputSpeech": {
                    "type": "PlainText",
                    "text": "Acceso no autorizado. Por favor configura el token correcto en la consola de Alexa."
                },
                "shouldEndSession": True
            }
        }), 401

    request_data = request.json or {}
    alexa_request = request_data.get("request", {})
    request_type = alexa_request.get("type", "LaunchRequest")
    
    # Base Alexa response structure
    alexa_response = {
        "version": "1.0",
        "response": {
            "shouldEndSession": True
        }
    }

    try:
        # Load Tuya configuration (from env vars or config.json)
        config = load_config()
        client_id = config.get("client_id")
        client_secret = config.get("client_secret")
        base_url = config.get("base_url", "https://openapi.tuyaus.com")
        
        if not client_id or not client_secret:
            alexa_response["response"]["outputSpeech"] = {
                "type": "PlainText",
                "text": "El panel de control todavía no está configurado con tus credenciales de Tuya."
            }
            return jsonify(alexa_response)

        api = TuyaAPI(client_id, client_secret, base_url)
        access_token, uid = api.get_access_token()
        raw_devices = api.get_devices(access_token, uid)
        
        sensors = []
        others = []
        for dev in raw_devices:
            parsed = parse_sensor_device(dev)
            if parsed["is_sensor"]:
                sensors.append(parsed)
            else:
                others.append(parsed)
                
    except Exception as e:
        logger.error(f"Alexa Tuya integration error: {e}")
        alexa_response["response"]["outputSpeech"] = {
            "type": "PlainText",
            "text": f"Hubo un error al conectar con la nube de Tuya: {str(e)}"
        }
        return jsonify(alexa_response)

    # 1. LAUNCH REQUEST ("Alexa, abre mi panel de alarma" or "Alexa, abre panel de sensores")
    if request_type == "LaunchRequest":
        # Check alarm readiness
        # Door/window (mcs) and vibration (zd) sensors are associated
        unsafe_sensors = []
        associated_count = 0
        
        for s in sensors:
            # For Alexa (without client-side localStorage), we auto-associate mcs and zd
            if s["category"] in ["mcs", "zd"]:
                associated_count += 1
                if not s["online"]:
                    unsafe_sensors.append(f"{s['name']} (fuera de línea)")
                else:
                    desc = str(s.get("state_description", "")).lower()
                    if "abierto" in desc or "vibración" in desc:
                        unsafe_sensors.append(s["name"])

        # Check if there is an active alarm device in the system ("Alarma 4G", "Central de Alarma", etc.)
        alarm_host = get_alarm_host(sensors, others)
        alarm_state = "desarmado"
        if alarm_host and alarm_host.get("status_raw") and alarm_host["status_raw"].get("master_mode"):
            mode = alarm_host["status_raw"]["master_mode"]
            alarm_state = "armado en casa" if mode == "home" else ("armado ausente" if mode in ["arm", "armed"] else "desarmado")

        if len(unsafe_sensors) == 0:
            speech_text = f"Hola. Tu sistema de alarma está actualmente {alarm_state}. Todos los {associated_count} sensores asociados están en orden y cerrados. La alarma está lista para ser activada."
        else:
            speech_text = f"Hola. El sistema está {alarm_state}, pero no está listo para ser armado de forma segura. Hay {len(unsafe_sensors)} sensores abiertos: {', '.join(unsafe_sensors)}. Por favor ciérralos antes de activar la alarma."

        # Add APL visual directive if supported by the Echo Hub
        # Check if device supports APL
        supports_apl = "Alexa.Presentation.APL" in request_data.get("context", {}).get("System", {}).get("device", {}).get("supportedInterfaces", {})
        
        if supports_apl:
            # We'll return an APL directive with a clean, visual state
            apl_doc = {
                "type": "APL",
                "version": "1.8",
                "import": [
                    {
                        "name": "alexa-layouts",
                        "version": "1.5.0"
                    }
                ],
                "mainTemplate": {
                    "parameters": ["payload"],
                    "items": [
                        {
                            "type": "Container",
                            "width": "100%",
                            "height": "100%",
                            "backgroundColor": "${payload.bg_color}",
                            "justifyContent": "center",
                            "alignItems": "center",
                            "padding": "20dp",
                            "items": [
                                {
                                    "type": "Text",
                                    "text": "${payload.title}",
                                    "fontSize": "32dp",
                                    "fontWeight": "bold",
                                    "color": "#ffffff",
                                    "textAlign": "center"
                                },
                                {
                                    "type": "Text",
                                    "text": "${payload.description}",
                                    "fontSize": "20dp",
                                    "color": "#e2e8f0",
                                    "textAlign": "center",
                                    "marginTop": "15dp"
                                }
                            ]
                        }
                    ]
                }
            }
            
            bg_color = "#10b981" if len(unsafe_sensors) == 0 else "#ef4444"
            title = "SISTEMA LISTO" if len(unsafe_sensors) == 0 else "SISTEMA ABIERTO"
            desc = f"Alarma {alarm_state.upper()}.\n{associated_count} sensores bajo control." if len(unsafe_sensors) == 0 else f"No se puede armar.\nZonas abiertas: {', '.join(unsafe_sensors)}"
            
            alexa_response["response"]["directives"] = [{
                "type": "Alexa.Presentation.APL.RenderDocument",
                "document": apl_doc,
                "datasources": {
                    "payload": {
                        "bg_color": bg_color,
                        "title": title,
                        "description": desc
                    }
                }
            }]

        alexa_response["response"]["outputSpeech"] = {
            "type": "PlainText",
            "text": speech_text
        }

    # 2. INTENT REQUEST (Handles custom intents we'll define)
    elif request_type == "IntentRequest":
        intent_name = alexa_request.get("intent", {}).get("name")
        
        # Intent: GetStatusIntent ("¿Cómo están los sensores?" or "¿Cuál es el estado de la alarma?")
        if intent_name == "GetStatusIntent":
            unsafe_sensors = []
            for s in sensors:
                if s["category"] in ["mcs", "zd"]:
                    desc = str(s["state_description"]).lower()
                    if "abierto" in desc or "vibración" in desc or not s["online"]:
                        unsafe_sensors.append(s["name"])
            
            if len(unsafe_sensors) == 0:
                speech_text = f"El sistema de seguridad está en perfectas condiciones. Todos los sensores están cerrados."
            else:
                speech_text = f"Atención, tienes {len(unsafe_sensors)} zonas abiertas: {', '.join(unsafe_sensors)}."

            alexa_response["response"]["outputSpeech"] = {
                "type": "PlainText",
                "text": speech_text
            }
            
        # Intent: ArmAlarmIntent ("Arma la alarma en modo ausente" or "Activa la alarma en casa")
        elif intent_name == "ArmAlarmIntent":
            # Check for slots
            slots = alexa_request.get("intent", {}).get("slots", {})
            mode_slot = slots.get("mode", {}).get("value", "ausente").lower()
            
            target_mode = "arm" if "ausente" in mode_slot or "total" in mode_slot else "home"
            mode_label = "Armado Ausente" if target_mode == "arm" else "Armado en Casa"
            
            # Check if any associated sensors are open first
            unsafe_sensors = []
            for s in sensors:
                if s["category"] in ["mcs", "zd"]:
                    desc = str(s["state_description"]).lower()
                    if "abierto" in desc or "vibración" in desc or not s["online"]:
                        unsafe_sensors.append(s["name"])

            if len(unsafe_sensors) > 0 and target_mode == "arm":
                speech_text = f"No puedo armar la alarma en modo Ausente porque hay sensores abiertos: {', '.join(unsafe_sensors)}. Por favor ciérralos e inténtalo de nuevo."
            else:
                # Find alarm device ("Alarma 4G", "Central de Alarma", etc.)
                alarm_host = get_alarm_host(sensors, others)
                if alarm_host:
                    try:
                        commands = [{"code": "master_mode", "value": target_mode}]
                        api.send_device_commands(access_token, alarm_host["id"], commands)
                        speech_text = f"Entendido, he enviado el comando para activar la alarma en modo {mode_label}."
                    except Exception as e:
                        speech_text = f"No se pudo completar la operación en Tuya Cloud: {str(e)}"
                else:
                    speech_text = f"Comando simulado. El panel ha sido armado en modo {mode_label}."

            alexa_response["response"]["outputSpeech"] = {
                "type": "PlainText",
                "text": speech_text
            }

        # Intent: DisarmAlarmIntent ("Desarma la alarma" or "Desactiva el panel")
        elif intent_name == "DisarmAlarmIntent":
            # Find alarm device ("Alarma 4G", "Central de Alarma", etc.)
            alarm_host = get_alarm_host(sensors, others)
            if alarm_host:
                try:
                    commands = [{"code": "master_mode", "value": "disarmed"}]
                    api.send_device_commands(access_token, alarm_host["id"], commands)
                    speech_text = "Sistema de seguridad desarmado exitosamente."
                except Exception as e:
                    speech_text = f"Error al desarmar en la nube: {str(e)}"
            else:
                speech_text = "Comando simulado. El panel ha sido desarmado."

            alexa_response["response"]["outputSpeech"] = {
                "type": "PlainText",
                "text": speech_text
            }

        else:
            alexa_response["response"]["outputSpeech"] = {
                "type": "PlainText",
                "text": "Disculpa, no entiendo ese comando para el panel de alarma."
            }

    # 3. ALEXA PRESENTATION LANGUAGE (APL) USER EVENT REQUEST
    # Triggers when a button on the visual APL Skill screen OR the Widget is touched/tapped
    elif request_type == "Alexa.Presentation.APL.UserEvent":
        arguments = alexa_request.get("arguments", [])
        action = arguments[0] if len(arguments) > 0 else ""
        
        # User tapped "arm_away", "arm_home", or "disarm" buttons on the screen or widget
        if action in ["arm", "home", "disarmed"]:
            mode_label = "Armado Ausente" if action == "arm" else ("Armado en Casa" if action == "home" else "Desarmado")
            
            # Find alarm device ("Alarma 4G", "Central de Alarma", etc.)
            alarm_host = get_alarm_host(sensors, others)
            
            success = True
            error_details = ""
            
            if alarm_host:
                try:
                    commands = [{"code": "master_mode", "value": action}]
                    api.send_device_commands(access_token, alarm_host["id"], commands)
                except Exception as e:
                    success = False
                    error_details = str(e)
            
            if success:
                speech_text = f"Comando ejecutado exitosamente. El panel ha sido cambiado a {mode_label}."
            else:
                speech_text = f"No se pudo completar el comando en la nube de Tuya: {error_details}"
                
            alexa_response["response"]["outputSpeech"] = {
                "type": "PlainText",
                "text": speech_text
            }
            
            # Update the widget/screen locally in real-time by pushing dynamic values or APL update
            # (Alexa handles returning a visual feedback speech)
            
        else:
            alexa_response["response"]["outputSpeech"] = {
                "type": "PlainText",
                "text": "Comando táctil no reconocido."
            }

    return jsonify(alexa_response)

@app.route("/api/automations", methods=["GET", "POST"])
def manage_automations():
    # Credentials resolution
    client_id = request.headers.get("X-Tuya-Client-Id")
    client_secret = request.headers.get("X-Tuya-Client-Secret")
    base_url = request.headers.get("X-Tuya-Base-Url", "https://openapi.tuyaus.com")
    
    if not client_id or not client_secret:
        config = load_config()
        client_id = config.get("client_id")
        client_secret = config.get("client_secret")
        base_url = config.get("base_url", "https://openapi.tuyaus.com")
        
    if not client_id or not client_secret:
        return jsonify({"success": False, "error": "Tuya no está configurado todavía"}), 401
        
    try:
        api = TuyaAPI(client_id, client_secret, base_url)
        access_token, uid = api.get_access_token()
        
        # Get homes first
        homes = api.get_user_homes(access_token, uid)
        home_id = homes[0].get("home_id") if homes else None
        
        if request.method == "GET":
            if not home_id:
                return jsonify({"success": True, "automations": [], "msg": "No se encontraron casas/hogares asociados"})
            automations = api.get_automations(access_token, home_id)
            return jsonify({"success": True, "home_id": home_id, "result": automations})
            
        elif request.method == "POST":
            data = request.json or {}
            target_home_id = data.get("home_id") or home_id
            if not target_home_id:
                return jsonify({"success": False, "error": "home_id no encontrado. Se requiere especificar el ID del hogar"}), 400
            
            result = api.create_automation(access_token, target_home_id, data)
            return jsonify({"success": True, "result": result})
            
    except Exception as e:
        logger.error(f"Error en /api/automations: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    # Bind to 0.0.0.0 to make it accessible inside local networks if needed
    app.run(host="0.0.0.0", port=port, debug=True)
