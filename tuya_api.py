import hmac
import hashlib
import time
import json
import logging

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    import urllib.request
    import urllib.error

logger = logging.getLogger(__name__)

class TuyaAPI:
    def __init__(self, client_id, client_secret, base_url="https://openapi.tuyaus.com"):
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = base_url.rstrip('/')

    def _http_request(self, method, url, headers, body=None, timeout=15):
        """Sends HTTP request using requests if available, or urllib as standard library fallback."""
        if HAS_REQUESTS:
            if method.upper() == "GET":
                resp = requests.get(url, headers=headers, timeout=timeout)
            else:
                resp = requests.post(url, headers=headers, data=body, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        else:
            data_bytes = body.encode('utf-8') if body else None
            req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method.upper())
            try:
                with urllib.request.urlopen(req, timeout=timeout) as response:
                    res_body = response.read().decode('utf-8')
                    return json.loads(res_body)
            except urllib.error.HTTPError as e:
                err_body = e.read().decode('utf-8')
                try:
                    return json.loads(err_body)
                except Exception:
                    raise Exception(f"HTTP Error {e.code}: {e.reason}")
            except Exception as e:
                raise Exception(f"Network error: {e}")

    def _get_timestamp(self):
        """Returns 13-digit timestamp as string."""
        return str(int(time.time() * 1000))

    def _calculate_sha256(self, body):
        """Calculates SHA256 of request body. For empty body, returns standard SHA256."""
        if not body:
            return "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        if isinstance(body, str):
            body = body.encode('utf-8')
        return hashlib.sha256(body).hexdigest()

    def _build_sorted_url(self, path, params):
        """Sorts query parameters alphabetically and builds the URL path."""
        if not params:
            return path
        sorted_keys = sorted(params.keys())
        query_string = "&".join(f"{k}={params[k]}" for k in sorted_keys)
        return f"{path}?{query_string}"

    def _calculate_sign(self, t, method, url_path, body=None, access_token=""):
        """
        Calculates the Tuya API signature.
        Formula: sign = HMAC-SHA256(client_id + access_token + t + stringToSign, secret).toUpperCase()
        where stringToSign = HTTPMethod + "\n" + Content-SHA256 + "\n" + Headers + "\n" + URL
        """
        body_sha = self._calculate_sha256(body)
        
        # Headers is empty for normal requests (denoted by empty string, which adds a newline)
        headers_str = ""
        
        # Format stringToSign
        string_to_sign = f"{method.upper()}\n{body_sha}\n{headers_str}\n{url_path}"
        
        # Concatenate payload
        payload = f"{self.client_id}{access_token}{t}{string_to_sign}"
        
        # Compute HMAC-SHA256 signature
        sign = hmac.new(
            self.client_secret.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest().upper()
        
        return sign

    def get_access_token(self):
        """
        Fetches an access token from Tuya.
        Endpoint: GET /v1.0/token?grant_type=1
        Returns: Tuple (access_token, uid)
        """
        t = self._get_timestamp()
        url_path = "/v1.0/token?grant_type=1"
        sign = self._calculate_sign(t, "GET", url_path)
        
        headers = {
            "client_id": self.client_id,
            "sign": sign,
            "t": t,
            "sign_method": "HMAC-SHA256",
            "Content-Type": "application/json"
        }
        
        url = f"{self.base_url}{url_path}"
        try:
            logger.info(f"Requesting access token from Tuya US West (url: {url})")
            data = self._http_request("GET", url, headers=headers, timeout=15)
            
            if not data.get("success"):
                error_msg = data.get("msg", "Unknown error")
                error_code = data.get("code", "No code")
                raise Exception(f"Tuya API Error (Code {error_code}): {error_msg}")
                
            result = data.get("result", {})
            access_token = result.get("access_token")
            uid = result.get("uid")
            
            if not access_token or not uid:
                raise Exception("Tuya API returned success but access_token or uid is missing in the response.")
                
            return access_token, uid
        except Exception as e:
            raise Exception(f"Network error connecting to Tuya API: {e}")

    def get_devices(self, access_token, uid=None):
        """
        Fetches all devices for the Tuya account.
        First tries the robust associated-users/devices endpoint which does not require specific user UIDs
        and fetches all linked account devices successfully.
        Fallback to user-scoped devices list if that fails.
        """
        t = self._get_timestamp()
        
        # Method 1: Get all associated devices (highly robust, works with linked Smart Life / Tuya accounts)
        params = {"size": "100"}
        url_path = self._build_sorted_url("/v1.0/iot-01/associated-users/devices", params)
        sign = self._calculate_sign(t, "GET", url_path, access_token=access_token)
        
        headers = {
            "client_id": self.client_id,
            "sign": sign,
            "t": t,
            "sign_method": "HMAC-SHA256",
            "access_token": access_token,
            "Content-Type": "application/json"
        }
        
        url = f"{self.base_url}{url_path}"
        try:
            logger.info(f"Requesting associated devices list (url: {url})")
            data = self._http_request("GET", url, headers=headers, timeout=15)
            
            if data.get("success"):
                result = data.get("result", {})
                if isinstance(result, dict) and "devices" in result:
                    return result.get("devices", [])
                elif isinstance(result, list):
                    return result
                    
            logger.warning(f"Associated devices query was not successful: {data.get('msg')}. Trying user-scoped fallback...")
        except Exception as e:
            logger.warning(f"Error querying associated devices: {e}. Trying user-scoped fallback...")

        # Method 2: Fallback to user-scoped list
        if not uid:
            raise Exception("Cannot list devices: Both associated-devices list failed and no user UID is available.")
            
        t = self._get_timestamp()
        url_path = f"/v1.0/users/{uid}/devices"
        sign = self._calculate_sign(t, "GET", url_path, access_token=access_token)
        
        headers = {
            "client_id": self.client_id,
            "sign": sign,
            "t": t,
            "sign_method": "HMAC-SHA256",
            "access_token": access_token,
            "Content-Type": "application/json"
        }
        
        url = f"{self.base_url}{url_path}"
        try:
            logger.info(f"Requesting user devices list for uid {uid} (url: {url})")
            data = self._http_request("GET", url, headers=headers, timeout=15)
            
            if not data.get("success"):
                error_msg = data.get("msg", "Unknown error")
                error_code = data.get("code", "No code")
                raise Exception(f"Tuya API Error (Code {error_code}): {error_msg}")
                
            return data.get("result", [])
        except Exception as e:
            raise Exception(f"Network error fetching user devices: {e}")

    def send_device_commands(self, access_token, device_id, commands):
        """
        Sends commands to a Tuya device.
        Endpoint: POST /v1.0/devices/{device_id}/commands (Standard) or POST /v1.0/iot-03/devices/{device_id}/commands
        """
        t = self._get_timestamp()
        
        # Standard device command control endpoint is /v1.0/devices/{device_id}/commands
        url_path = f"/v1.0/devices/{device_id}/commands"
        
        # Serialize the body as compact JSON for signature calculation
        body = json.dumps({"commands": commands}, separators=(',', ':'))
        
        sign = self._calculate_sign(t, "POST", url_path, body=body, access_token=access_token)
        
        headers = {
            "client_id": self.client_id,
            "sign": sign,
            "t": t,
            "sign_method": "HMAC-SHA256",
            "access_token": access_token,
            "Content-Type": "application/json"
        }
        
        url = f"{self.base_url}{url_path}"
        try:
            logger.info(f"Sending commands to device {device_id} (url: {url})")
            data = self._http_request("POST", url, headers=headers, body=body, timeout=15)
            
            # If standard /v1.0/devices/ fails with path error, we can try /v1.0/iot-03/devices/ fallback
            if not data.get("success") and "uri" in str(data.get("msg", "")).lower():
                logger.warning("Standard control endpoint failed with URI error. Trying iot-03 fallback...")
                t = self._get_timestamp()
                url_path_fallback = f"/v1.0/iot-03/devices/{device_id}/commands"
                sign_fallback = self._calculate_sign(t, "POST", url_path_fallback, body=body, access_token=access_token)
                headers["sign"] = sign_fallback
                headers["t"] = t
                url_fallback = f"{self.base_url}{url_path_fallback}"
                data = self._http_request("POST", url_fallback, headers=headers, body=body, timeout=15)
                
            return data
        except Exception as e:
            raise Exception(f"Network error sending commands: {e}")

    def get_user_homes(self, access_token, uid):
        """
        Fetches home/family IDs associated with user account.
        First tries /v2.0/cloud/space/child (cloud spaces/homes), then /v1.0/users/{uid}/homes fallback.
        """
        t = self._get_timestamp()
        
        # Method 1: Get cloud spaces / homes
        url_path = "/v2.0/cloud/space/child"
        sign = self._calculate_sign(t, "GET", url_path, access_token=access_token)
        headers = {
            "client_id": self.client_id,
            "sign": sign,
            "t": t,
            "sign_method": "HMAC-SHA256",
            "access_token": access_token,
            "Content-Type": "application/json"
        }
        url = f"{self.base_url}{url_path}"
        try:
            data = self._http_request("GET", url, headers=headers, timeout=15)
            if data.get("success"):
                result = data.get("result", {})
                space_list = []
                if isinstance(result, dict) and "data" in result:
                    space_list = result.get("data", [])
                elif isinstance(result, list):
                    space_list = result
                
                if space_list:
                    return [{"home_id": sid, "name": f"Home {sid}"} for sid in space_list]
        except Exception as e:
            logger.warning(f"Cloud space/home endpoint error: {e}. Trying user homes fallback...")

        # Method 2: Fallback to /v1.0/users/{uid}/homes
        t = self._get_timestamp()
        url_path = f"/v1.0/users/{uid}/homes"
        sign = self._calculate_sign(t, "GET", url_path, access_token=access_token)
        headers["t"] = t
        headers["sign"] = sign
        url = f"{self.base_url}{url_path}"
        try:
            data = self._http_request("GET", url, headers=headers, timeout=15)
            if data.get("success"):
                return data.get("result", [])
            return []
        except Exception as e:
            logger.warning(f"Error fetching user homes: {e}")
            return []

    def get_automations(self, access_token, home_id):
        """
        Fetches scenes/automations for a home.
        Primary Endpoint: GET /v1.0/homes/{home_id}/automations
        Fallback Endpoint: GET /v1.0/homes/{home_id}/scenes
        """
        t = self._get_timestamp()
        url_path = f"/v1.0/homes/{home_id}/automations"
        sign = self._calculate_sign(t, "GET", url_path, access_token=access_token)
        headers = {
            "client_id": self.client_id,
            "sign": sign,
            "t": t,
            "sign_method": "HMAC-SHA256",
            "access_token": access_token,
            "Content-Type": "application/json"
        }
        url = f"{self.base_url}{url_path}"
        try:
            data = self._http_request("GET", url, headers=headers, timeout=15)
            if data.get("success"):
                return data
            # Fallback if automations query fails
            t = self._get_timestamp()
            url_path_fb = f"/v1.0/homes/{home_id}/scenes"
            sign_fb = self._calculate_sign(t, "GET", url_path_fb, access_token=access_token)
            headers["t"] = t
            headers["sign"] = sign_fb
            data_fb = self._http_request("GET", f"{self.base_url}{url_path_fb}", headers=headers, timeout=15)
            return data_fb
        except Exception as e:
            logger.warning(f"Error fetching home automations: {e}")
            return {"success": False, "error": str(e)}

    def create_automation(self, access_token, home_id, automation_payload):
        """
        Creates a scene/automation rule for a home in Tuya Cloud.
        Primary Endpoint: POST /v1.0/homes/{home_id}/automations
        Fallback Endpoint: POST /v1.0/homes/{home_id}/scenes
        """
        t = self._get_timestamp()
        url_path = f"/v1.0/homes/{home_id}/automations"
        body = json.dumps(automation_payload, separators=(',', ':'))
        sign = self._calculate_sign(t, "POST", url_path, body=body, access_token=access_token)
        headers = {
            "client_id": self.client_id,
            "sign": sign,
            "t": t,
            "sign_method": "HMAC-SHA256",
            "access_token": access_token,
            "Content-Type": "application/json"
        }
        url = f"{self.base_url}{url_path}"
        try:
            logger.info(f"Creating automation in home {home_id} via {url_path}")
            data = self._http_request("POST", url, headers=headers, body=body, timeout=15)
            
            # Fallback if URI or endpoint issue
            if not data.get("success") and any(err in str(data.get("msg", "")).lower() for err in ["uri", "path", "not exist", "permission"]):
                logger.warning("Primary automation endpoint failed. Trying scenes endpoint fallback...")
                t = self._get_timestamp()
                url_path_fallback = f"/v1.0/homes/{home_id}/scenes"
                sign_fallback = self._calculate_sign(t, "POST", url_path_fallback, body=body, access_token=access_token)
                headers["sign"] = sign_fallback
                headers["t"] = t
                url_fallback = f"{self.base_url}{url_path_fallback}"
                data = self._http_request("POST", url_fallback, headers=headers, body=body, timeout=15)
                
            return data
        except Exception as e:
            logger.error(f"Error creating automation in Tuya Cloud: {e}")
            raise Exception(f"Network error creating automation: {e}")

    def delete_automation(self, access_token, home_id, automation_id):
        """
        Deletes an automation rule from a home in Tuya Cloud.
        Endpoint: DELETE /v1.0/homes/{home_id}/automations/{automation_id}
        """
        t = self._get_timestamp()
        url_path = f"/v1.0/homes/{home_id}/automations/{automation_id}"
        sign = self._calculate_sign(t, "DELETE", url_path, access_token=access_token)
        headers = {
            "client_id": self.client_id,
            "sign": sign,
            "t": t,
            "sign_method": "HMAC-SHA256",
            "access_token": access_token,
            "Content-Type": "application/json"
        }
        url = f"{self.base_url}{url_path}"
        try:
            logger.info(f"Deleting automation {automation_id} in home {home_id}")
            data = self._http_request("DELETE", url, headers=headers, timeout=15)
            return data
        except Exception as e:
            logger.warning(f"Error deleting automation {automation_id}: {e}")
            return {"success": False, "error": str(e)}
