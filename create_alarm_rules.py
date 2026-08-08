#!/usr/bin/env python3
"""
Script to create Tuya Cloud Automations for Alarm Host ("Alarma 4G")
and all vibration / contact sensors.
"""

import sys
import os
import json
import logging

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tuya_api import TuyaAPI

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def load_config_file():
    """Attempts to load credentials from config.json if available."""
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def find_alarm_host(raw_devices):
    """Finds the central alarm host device ("Alarma 4G", "Central de Alarma", etc.)"""
    for dev in raw_devices:
        name_lower = (dev.get("name") or "").lower()
        cat = dev.get("category", "")
        if cat == "mal" or any(kw in name_lower for kw in ["alarma 4g", "alarma", "alarm host", "central de alarma", "panel de alarma"]):
            return dev
    return None

def generate_and_create_rules(client_id, client_secret, base_url="https://openapi.tuyaus.com"):
    logger.info("Connecting to Tuya Cloud API...")
    api = TuyaAPI(client_id, client_secret, base_url)
    access_token, uid = api.get_access_token()
    logger.info(f"Authenticated successfully! UID: {uid}")

    # Get user homes
    homes = api.get_user_homes(access_token, uid)
    if not homes:
        logger.error("No homes/families found for this Tuya user account.")
        return {"success": False, "error": "No homes found for user"}
        
    home_id = homes[0].get("home_id")
    logger.info(f"Using Home ID: {home_id}")

    # Fetch all devices
    raw_devices = api.get_devices(access_token, uid)
    logger.info(f"Fetched {len(raw_devices)} devices from Tuya account.")

    # Find Alarma 4G
    alarm_host = find_alarm_host(raw_devices)

    if not alarm_host:
        logger.error("Dispositivo 'Alarma 4G' o Central de Alarma no encontrado.")
        return {"success": False, "error": "No se encontró el dispositivo de Alarma 4G"}

    alarm_id = alarm_host.get("id")
    alarm_name = alarm_host.get("name", "Alarma 4G")
    logger.info(f"Found Alarm Host: {alarm_name} (ID: {alarm_id})")

    # Detect alarm mode DP code and panic trigger code
    raw_alarm = next((d for d in raw_devices if d.get("id") == alarm_id), {})
    alarm_status_list = raw_alarm.get("status", [])
    alarm_status_dict = {item.get("code"): item.get("value") for item in alarm_status_list if "code" in item}

    # Alarm mode code
    alarm_mode_code = "master_mode"
    if "master_mode" not in alarm_status_dict:
        for possible in ["mode", "alarm_state", "arm_state"]:
            if possible in alarm_status_dict:
                alarm_mode_code = possible
                break

    # Panic trigger code/value
    panic_value = "sos"
    if alarm_mode_code in alarm_status_dict:
        # master_mode usually accepts 'sos' or 'alarm' or 'panic'
        panic_value = "sos"

    logger.info(f"Alarm Mode Code: '{alarm_mode_code}', Panic Value: '{panic_value}'")

    created_rules = []
    failed_rules = []

    # Process each raw device
    for dev in raw_devices:
        dev_id = dev.get("id")
        dev_name = dev.get("name", "Dispositivo")
        cat = dev.get("category", "")
        status_list = dev.get("status", [])
        status_dict = {item.get("code"): item.get("value") for item in status_list if "code" in item}
        name_lower = dev_name.lower()

        is_vibration = cat == "zd" or any(kw in name_lower for kw in ["vibrat", "vibr", "zd"])
        is_contact = cat == "mcs" or any(kw in name_lower for kw in ["puerta", "ventana", "contact", "door", "window", "mcs"])

        if dev_id == alarm_id:
            continue

        if not (is_vibration or is_contact):
            continue

        logger.info(f"Processing sensor: '{dev_name}' (ID: {dev_id}, Category: {cat})")

        # Determine DP code and target value for trigger
        dp_code = None
        trigger_value = None

        if is_vibration:
            for candidate in ["shock_state", "vibration_status", "vibration_state", "vibration"]:
                if candidate in status_dict:
                    dp_code = candidate
                    trigger_value = "vibration"
                    break
            if not dp_code:
                dp_code = "shock_state"
                trigger_value = "vibration"

        elif is_contact:
            for candidate in ["doorcontact_state", "switch", "window_state"]:
                if candidate in status_dict:
                    dp_code = candidate
                    trigger_value = True
                    break
            if not dp_code:
                dp_code = "doorcontact_state"
                trigger_value = True

        # Rules to create: Ausente and Casa
        modes = [
            {"mode_val": "arm", "suffix": "Ausente", "label": "Ausente"},
            {"mode_val": "home", "suffix": "Casa", "label": "Casa"}
        ]

        for m in modes:
            rule_name = f"{dev_name} {m['suffix']}"
            
            automation_payload = {
                "name": rule_name,
                "background": "https://images.tuyaus.com/smart/rule/cover/1.png",
                "match_type": 2,  # Match ALL conditions
                "conditions": [
                    {
                        "entity_type": 1,  # Device status
                        "order_num": 1,
                        "entity_id": dev_id,
                        "display": {
                            "code": dp_code,
                            "operator": "==",
                            "value": trigger_value
                        }
                    },
                    {
                        "entity_type": 1,  # Device status
                        "order_num": 2,
                        "entity_id": alarm_id,
                        "display": {
                            "code": alarm_mode_code,
                            "operator": "==",
                            "value": m["mode_val"]
                        }
                    }
                ],
                "actions": [
                    {
                        "entity_id": alarm_id,
                        "action_executor": "dpIssue",
                        "executor_property": {
                            alarm_mode_code: panic_value
                        }
                    }
                ]
            }

            logger.info(f"Creating rule: '{rule_name}'...")
            try:
                res = api.create_automation(access_token, home_id, automation_payload)
                if isinstance(res, dict) and res.get("success"):
                    result_obj = res.get("result")
                    rule_id = result_obj.get("id") if isinstance(result_obj, dict) else result_obj
                    logger.info(f"✓ Rule created successfully: '{rule_name}' (ID: {rule_id})")
                    created_rules.append({"name": rule_name, "id": rule_id, "sensor": dev_name})
                else:
                    msg = res.get("msg", "Unknown error") if isinstance(res, dict) else str(res)
                    code = res.get("code", "N/A") if isinstance(res, dict) else "N/A"
                    logger.warning(f"✗ Failed to create rule '{rule_name}': Code {code} - {msg}")
                    failed_rules.append({"name": rule_name, "error": f"Code {code}: {msg}"})
            except Exception as e:
                logger.error(f"✗ Exception creating rule '{rule_name}': {e}")
                failed_rules.append({"name": rule_name, "error": str(e)})

    return {
        "success": True,
        "home_id": home_id,
        "alarm": alarm_name,
        "created_count": len(created_rules),
        "created_rules": created_rules,
        "failed_rules": failed_rules
    }

if __name__ == "__main__":
    client_id = os.environ.get("TUYA_CLIENT_ID") or os.environ.get("CLIENT_ID")
    client_secret = os.environ.get("TUYA_CLIENT_SECRET") or os.environ.get("CLIENT_SECRET")
    base_url = os.environ.get("TUYA_BASE_URL", "https://openapi.tuyaus.com")

    if not client_id or not client_secret:
        cfg = load_config_file()
        client_id = cfg.get("client_id")
        client_secret = cfg.get("client_secret")
        base_url = cfg.get("base_url", "https://openapi.tuyaus.com")

    if len(sys.argv) >= 3:
        client_id = sys.argv[1]
        client_secret = sys.argv[2]
        if len(sys.argv) >= 4:
            base_url = sys.argv[3]

    if not client_id or not client_secret:
        print("Uso: python3 create_alarm_rules.py <client_id> <client_secret> [base_url]")
        print("O configura las variables de entorno TUYA_CLIENT_ID y TUYA_CLIENT_SECRET.")
        sys.exit(1)

    result = generate_and_create_rules(client_id, client_secret, base_url)
    print(json.dumps(result, indent=2, ensure_ascii=False))
