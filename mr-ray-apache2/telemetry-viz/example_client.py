"""
Demo client — pushes synthetic sine/cosine telemetry to the server.
Usage: python example_client.py [SERVER_URL]
Default SERVER_URL: http://localhost:5701
"""

import math
import sys
import time

import requests

SERVER = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5701"
INTERVAL = 0.5


def main():
    t = 0.0
    print(f"Pushing telemetry to {SERVER}/telemetry every {INTERVAL}s (Ctrl+C to stop)")
    while True:
        payload = [
            {"timestamp": t, "sensor_name": "sine", "value": math.sin(t)},
            {"timestamp": t, "sensor_name": "cosine", "value": math.cos(t)},
            {"timestamp": t, "sensor_name": "altitude_m", "value": 1000 + 50 * math.sin(t * 0.3)},
        ]
        try:
            r = requests.post(f"{SERVER}/telemetry", json=payload, timeout=2)
            r.raise_for_status()
            print(f"t={t:.1f} accepted={r.json().get('accepted')}")
        except requests.RequestException as e:
            print(f"error: {e}")
        t += INTERVAL
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
