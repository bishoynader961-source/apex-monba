import os
import json
from http.server import BaseHTTPRequestHandler
from urllib.request import Request, urlopen

REDIS_URL = os.environ.get("UPSTASH_REDIS_REST_URL")
REDIS_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN")

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        
        try:
            data = json.loads(body)
        except Exception:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Invalid JSON"}).encode())
            return

        license_key = data.get("license_key")
        device_id = data.get("device_id")

        if not license_key or not device_id:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Missing parameters"}).encode())
            return

        # Query Upstash Redis
        url = f"{REDIS_URL}/get/license:{license_key}"
        req = Request(url, headers={"Authorization": f"Bearer {REDIS_TOKEN}"})
        
        try:
            with urlopen(req) as response:
                res_data = json.loads(response.read().decode())
                if not res_data.get("result"):
                    self.send_response(404)
                    self.end_headers()
                    self.wfile.write(json.dumps({"activated": False, "error": "License not found"}).encode())
                    return
                
                license_data = json.loads(res_data["result"])
                
                if license_data.get("status") != "active":
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(json.dumps({"activated": False, "error": "License inactive"}).encode())
                    return
                
                current_device = license_data.get("device_id")
                if current_device and current_device != device_id:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(json.dumps({"activated": False, "error": "License bound to another hardware unit"}).encode())
                    return
                
                # Bind device ID locally if empty
                license_data["device_id"] = device_id
                
                # Save updated mapping back to Upstash Redis
                set_url = f"{REDIS_URL}/set/license:{license_key}"
                set_payload = json.dumps(license_data)
                set_req = Request(set_url, data=set_payload.encode(), headers={"Authorization": f"Bearer {REDIS_TOKEN}"}, method="POST")
                urlopen(set_req)

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"activated": True}).encode())
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())
