"""Einstiegspunkt für Post-Ride-Dashboard"""

import json
import socketserver
from http.server import SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

import folium
from folium.plugins import HeatMap

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "rides"
STATIC_DIR = Path(__file__).parent / "static"


def generate_map() -> str:
    """Generiert die Folium-Karte basierend auf den JSON-Dateien."""
    m = folium.Map(location=[52.5200, 13.4050], zoom_start=13)
    
    all_coords = []
    heatmap_data = []
    rides_data = []
    
    #Alle JSON-Dateien einlesen
    if DATA_DIR.exists():
        for json_file in DATA_DIR.glob("*.json"):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    ride_data = json.load(f)
                    rides_data.append(ride_data)
            except Exception as e:
                print(f"Fehler beim Verarbeiten von {json_file}: {e}")
                
    if rides_data:
        #neueste Fahrt finden (basierend auf start_time)
        newest_ride = max(rides_data, key=lambda r: r.get("start_time", 0))
        
        #Route der neusten Fahrt zeichnen
        route_logs = newest_ride.get("route_logs", [])
        if route_logs:
            route_coords = [[log["lat"], log["lon"]] for log in route_logs]
            all_coords.extend(route_coords)
            folium.PolyLine(
                route_coords,
                color="#3b82f6",
                weight=5,
                opacity=0.8
            ).add_to(m)
            
        #Verstöße aus allen Fahrten für Heatmap sammeln
        for ride in rides_data:
            violations = ride.get("violations", [])
            for v in violations:
                lat = v["coordinates"]["lat"]
                lon = v["coordinates"]["lon"]
                
                # Gewichtung berechnen (Gefahren-Score)
                distance = v.get("distance_cm", 150.0)
                speed = v.get("speed_kmh", 30.0)
                
                # Basis-Gewicht pro Verstoß
                weight = 1.0
                
                # Je enger (< 150cm), desto gefährlicher
                distance_penalty = max(0, 150.0 - distance) / 50.0
                
                # Hohe Geschwindigkeit verstärkt die Gefahr
                speed_multiplier = max(1.0, speed / 30.0)
                
                # Endgültiges Gewicht
                weight += (distance_penalty * speed_multiplier)
                
                #Heatmap[Lat, Lon, Weight]
                heatmap_data.append([lat, lon, weight])
                all_coords.append([lat, lon])
                
    # HeatMap hinzufügen, wenn es Verstöße gibt
    if heatmap_data:
        HeatMap(heatmap_data).add_to(m)
                
    # Kartenausschnitt automatisch anpassen, wenn Daten vorhanden sind
    if all_coords:
        m.fit_bounds(m.get_bounds())
        
    # Legende als benutzerdefiniertes HTML-Element hinzufügen
    legend_html = """
    <div style="
        position: fixed; 
        bottom: 25px; 
        right: 10px; 
        width: 220px; 
        background-color: rgba(255, 255, 255, 0.95); 
        z-index: 9999; 
        font-size: 11px; 
        padding: 8px 10px; 
        border: 1px solid #d1d5db; 
        border-radius: 5px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        font-family: 'Inter', Arial, sans-serif;
    ">
        <h4 style="margin: 0 0 5px 0; color: #111827; font-size: 12px;">Gefahren-Heatmap</h4>
        <div style="background: linear-gradient(to right, blue, cyan, lime, yellow, red); width: 100%; height: 8px; border-radius: 2px; margin-bottom: 3px;"></div>
        <div style="display: flex; justify-content: space-between; font-size: 9px; color: #4b5563; font-weight: 600;">
            <span>Geringer</span>
            <span>Hoch</span>
        </div>
        <ul style="margin: 5px 0 0 0; padding-left: 15px; font-size: 10px; color: #374151;">
            <li style="margin-bottom: 2px;"><strong>Blau/Grün:</strong> &gt; 1.5m Abstand</li>
            <li><strong>Rot/Gelb:</strong> &lt; 1.5m oder schnell</li>
        </ul>
        <hr style="border: 0; border-top: 1px solid #e5e7eb; margin: 6px 0;">
        <p style="font-size: 9px; margin: 0; color: #6b7280; line-height: 1.2;">
            <i><b>Tipp:</b> Mehrere Vorfälle am selben Ort verstärken das Rot ebenfalls.</i>
        </p>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))
        
    # Gib den generierten HTML-Code der Karte zurück
    return m.get_root().render()


class DashboardHandler(SimpleHTTPRequestHandler):
    """Handler für das lokale Dashboard und die statischen Dateien."""

    def __init__(self, *args, **kwargs):  # type: ignore
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def do_GET(self) -> None:
        """Behandelt GET-Anfragen und liefert die Folium-Karte aus."""
        parsed_path = urlparse(self.path)
        
        # Generiere die Karte dynamisch, wenn das Hauptverzeichnis abgefragt wird
        if parsed_path.path == "/" or parsed_path.path == "/map.html":
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            
            html_content = generate_map()
            self.wfile.write(html_content.encode("utf-8"))
            return
            
        # Für alle anderen Dateien den Standard-Handler nutzen
        return super().do_GET()


def run_server(port: int = 8000) -> None:
    """Startet den lokalen Dashboard-Server."""
    with socketserver.TCPServer(("", port), DashboardHandler) as httpd:
        print(f"Folium-Dashboard läuft auf http://localhost:{port}/")
        httpd.serve_forever()


if __name__ == "__main__":
    run_server()
