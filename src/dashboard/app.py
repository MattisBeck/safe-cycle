"""Einstiegspunkt für das lokale Post-Ride-Dashboard.

Stellt eine lokale API und die statischen Dateien bereit.
"""

import json
import socketserver
from http.server import SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "rides"
STATIC_DIR = Path(__file__).parent / "static"


class DashboardHandler(SimpleHTTPRequestHandler):
    """Handler für das lokale Dashboard und die API-Routen."""

    def __init__(self, *args, **kwargs):  # type: ignore
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def do_GET(self) -> None:
        """Behandelt GET-Anfragen für statische Dateien und die API."""
        parsed_path = urlparse(self.path)
        
        # API-Endpunkt, um alle JSON-Dateien aus data/rides zu laden
        if parsed_path.path == "/api/rides":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            
            rides = []
            if DATA_DIR.exists():
                for json_file in DATA_DIR.glob("*.json"):
                    try:
                        with open(json_file, "r", encoding="utf-8") as f:
                            rides.append(json.loads(f.read()))
                    except Exception as e:
                        print(f"Fehler beim Lesen von {json_file}: {e}")
                        
            self.wfile.write(json.dumps(rides).encode("utf-8"))
            return
            
        return super().do_GET()


def run_server(port: int = 8000) -> None:
    """Startet den lokalen Dashboard-Server."""
    with socketserver.TCPServer(("", port), DashboardHandler) as httpd:
        print(f"Dashboard läuft auf http://localhost:{port}/map.html")
        httpd.serve_forever()


if __name__ == "__main__":
    run_server()
