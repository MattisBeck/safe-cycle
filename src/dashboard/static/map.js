// Initialisiert die Karte, sobald das HTML-Dokument vollständig geladen ist.
document.addEventListener('DOMContentLoaded', () => {
    
    // Konfiguration der Karte.
    const mapOptions = {
        center: [52.5200, 13.4050], // Initiale Startkoordinaten (werden später durch die Route überschrieben)
        zoom: 13,                   
        dragging: true,             
        scrollWheelZoom: true       
    };

    // Erstellt das Kartenobjekt und verbindet es mit dem 'map_container' div im HTML.
    const map = L.map('map_container', mapOptions);

    // Fügt die Kartenebene (Tiles) von OpenStreetMap hinzu.


    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: 'Map data from <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
    }).addTo(map);


    // Beispieldaten, später dynamisch
    // =========================================================================
    const rideData = {
        "ride_id": "tour_2026_06_05_1430",
        "start_time": 1717618000,
        "end_time": 1717625000,
        "route_logs": [
            {"timestamp": 1717618010, "lat": 51.3127, "lon": 9.4924},
            {"timestamp": 1717618020, "lat": 51.3128, "lon": 9.4925}
        ],
        "violations": [
            {
                "timestamp": 1717618015,
                "coordinates": {"lat": 51.31275, "lon": 9.49245},
                "distance_cm": 85.5,
                "speed_kmh": 22.1,
                "image_path": "images/violations/auto_id_5_1717618015.jpg"
            }
        ]
    };

    //gefahrene Route auf die Karte zeichnen
    if (rideData.route_logs && rideData.route_logs.length > 0) {
        // Wandle die Koordinaten aus dem JSON in das Format von Leaflet [lat, lon] um
        const routeCoordinates = rideData.route_logs.map(log => [log.lat, log.lon]);
        
        // Erstelle eine blaue Linie entlang der Route
        const routeLine = L.polyline(routeCoordinates, {
            color: '#3b82f6', // Farbe der Linie
            weight: 5,        // Dicke der Linie
            opacity: 0.8,
            smoothFactor: 1
        }).addTo(map);

        //Kartenausschnitt automatisch anpassen

        map.fitBounds(routeLine.getBounds(), { padding: [50, 50], maxZoom: 16 });
    }

    // Violations als Marker auf der Karte anzeigen
    if (rideData.violations && rideData.violations.length > 0) {
        rideData.violations.forEach(violation => {
            // Erstelle einen auffälligen roten Kreis für jeden Verstoß
            const marker = L.circleMarker([violation.coordinates.lat, violation.coordinates.lon], {
                radius: 8,
                fillColor: '#ef4444', // Rot
                color: '#ffffff',     // Weißer Rand
                weight: 2,
                opacity: 1,
                fillOpacity: 0.9
            }).addTo(map);

            // HTML-Inhalt für Popup-Fenster, beim Klicken auf Marker
            const popupContent = `
                <div style="font-family: 'Inter', sans-serif; min-width: 200px; color: #1f2937;">
                    <h3 style="margin: 0 0 8px 0; font-size: 16px; color: #111827;">Kritischer Überholvorgang</h3>
                    <p style="margin: 4px 0; font-size: 14px;"><strong>Abstand:</strong> ${violation.distance_cm} cm</p>
                    <p style="margin: 4px 0; font-size: 14px;"><strong>Geschwindigkeit:</strong> ${violation.speed_kmh} km/h</p>
                    <!-- Das Bild wird relativ zum Ausführungsort geladen -->
                    <img src="${violation.image_path}" 
                         alt="Beweisbild" 
                         style="width: 100%; border-radius: 4px; margin-top: 8px; border: 1px solid #e5e7eb;" 
                         onerror="this.style.display='none';"> <!-- Versteckt das Bild, falls es nicht gefunden wird -->
                </div>
            `;
            
            // Verbinde das Popup mit dem Marker
            marker.bindPopup(popupContent);
        });
    }

});
