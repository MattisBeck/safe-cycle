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


    // Daten dynamisch über die API laden 
    fetch('/api/rides')
        .then(response => {
            if (!response.ok) {
                throw new Error(`Fehler beim Laden der Daten: ${response.statusText}`);
            }
            return response.json();
        })
        .then(rides => {
            let allCoordinates = [];

            // Iteriere über alle Rides (JSON-Dateien)
            rides.forEach(rideData => {
                // Koordinaten sammeln und gefahrene Route auf die Karte zeichnen
                if (rideData.route_logs && rideData.route_logs.length > 0) {
                    const routeCoordinates = rideData.route_logs.map(log => [log.lat, log.lon]);
                    allCoordinates = allCoordinates.concat(routeCoordinates);
                    
                    // Erstelle eine blaue Linie entlang der Route
                    L.polyline(routeCoordinates, {
                        color: '#3b82f6', // Farbe der Linie
                        weight: 5,        // Dicke der Linie
                        opacity: 0.8,
                        smoothFactor: 1
                    }).addTo(map);
                }

                // Violations als Marker auf der Karte anzeigen
                if (rideData.violations && rideData.violations.length > 0) {
                    rideData.violations.forEach(violation => {
                        allCoordinates.push([violation.coordinates.lat, violation.coordinates.lon]);

                        // Erstelle roten Marker für jeden Verstoß
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
                                     onerror="this.style.display='none';">
                            </div>
                        `;
                        
                        // Verbinde das Popup mit dem Marker
                        marker.bindPopup(popupContent);
                    });
                }
            });

            // Kartenausschnitt für alle geladenen Punkte auf einmal anpassen
            if (allCoordinates.length > 0) {
                map.fitBounds(allCoordinates, { padding: [50, 50], maxZoom: 16 });
            }
        })
        .catch(error => {
            console.error('Fehler beim Abrufen der JSON-Daten:', error);
        });

});
