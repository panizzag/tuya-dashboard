import hmac
import hashlib
import time
import json
import requests
import logging

logger = logging.getLogger(__name__)

class TuyaAPI:
    def __init__(self, client_id, client_secret, base_url="https://openapi.tuyaus.com"):
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = base_url.rstrip('/')

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
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            data = response.json()
            
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
        except requests.exceptions.RequestException as e:
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
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            data = response.json()
            
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
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            data = response.json()
            
            if not data.get("success"):
                error_msg = data.get("msg", "Unknown error")
                error_code = data.get("code", "No code")
                raise Exception(f"Tuya API Error (Code {error_code}): {error_msg}")
                
            return data.get("result", [])
        except requests.exceptions.RequestException as e:
            raise Exception(f"Network error fetching user devices: {e}")

    def send_device_commands(self, access_token, device_id, commands):
        """
        Sends commands to a Tuya device.
        Endpoint: POST /v1.0/iot-01/devices/{device_id}/commands
        """
        t = self._get_timestamp()
        url_path = f"/v1.0/iot-01/devices/{device_id}/commands"
        
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
            response = requests.post(url, headers=headers, data=body, timeout=15)
            response.raise_for_status()
            data = response.json()
            return data
        except requests.exceptions.RequestException as e:
            raise Exception(f"Network error sending commands: {e}")
