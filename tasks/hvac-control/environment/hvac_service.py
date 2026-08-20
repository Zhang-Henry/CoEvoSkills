#!/usr/bin/env python3
"""Private HTTP service implementing the stateful HVAC thermal plant."""

import json
import random
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


PROCESS_GAIN = 0.12
TIME_CONSTANT = 40.0

with Path("/srv/room_config.json").open() as config_file:
    _config = json.load(config_file)

AMBIENT = float(_config["ambient_temp"])
NOISE_STD = float(_config["noise_std"])
DT = float(_config["dt"])
MAX_SAFE_TEMP = float(_config["max_safe_temp"])

_states = {}
_lock = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def _write_json(self, status, body):
        payload = json.dumps(body, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path == "/health":
            self._write_json(200, {"status": "ok"})
        else:
            self._write_json(404, {"error": "not found"})

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            request = json.loads(self.rfile.read(length))
            session = str(request["session"])

            with _lock:
                if self.path == "/reset":
                    _states[session] = {
                        "temperature": AMBIENT,
                        "safety_triggered": False,
                    }
                    measurement = AMBIENT + random.gauss(0.0, NOISE_STD)
                    response = {"temperature": measurement}
                elif self.path == "/step":
                    state = _states.get(session)
                    if state is None:
                        raise ValueError("unknown session; call reset first")

                    power = min(100.0, max(0.0, float(request["heater_power"])))
                    if state["temperature"] >= MAX_SAFE_TEMP:
                        power = 0.0
                        state["safety_triggered"] = True

                    state["temperature"] += (
                        PROCESS_GAIN * power + AMBIENT - state["temperature"]
                    ) / TIME_CONSTANT * DT
                    measurement = state["temperature"] + random.gauss(0.0, NOISE_STD)
                    response = {
                        "temperature": measurement,
                        "heater_power": power,
                        "safety_triggered": state["safety_triggered"],
                    }
                else:
                    self._write_json(404, {"error": "not found"})
                    return

            self._write_json(200, response)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self._write_json(400, {"error": str(exc)})

    def log_message(self, _format, *_args):
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
