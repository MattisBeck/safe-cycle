"""Tests für den GPS-Sensor-Node (L76X)."""

from unittest.mock import Mock

from sensors.gps_node import (
    GpsState,
    create_gps_payload,
    parse_coordinate,
    parse_nmea_sentence,
    read_sentence,
    verify_checksum,
)


def test_gps_node_can_be_imported() -> None:
    """Prüft, ob das GPS-Modul ohne angeschlossene Hardware importierbar ist."""
    from sensors import gps_node

    assert gps_node.__name__ == "sensors.gps_node"


def test_verify_checksum_valid() -> None:
    """Prüft, dass eine korrekte NMEA-Checksumme als gültig erkannt wird."""
    assert verify_checksum("$GPRMC,220516,A,5133.82,N,00042.24,W,173.8,231.8,130694,004.2,W*70") is True


def test_verify_checksum_invalid() -> None:
    """Prüft, dass fehlerhafte NMEA-Checksummen abgelehnt werden."""
    assert verify_checksum("$GPRMC,220516,A,5133.82,N,00042.24,W,173.8,231.8,130694,004.2,W*71") is False
    assert verify_checksum("GPRMC,123*70") is False
    assert verify_checksum("$GPRMC,123") is False


def test_parse_coordinate_valid() -> None:
    """Prüft die Umrechnung von NMEA-Koordinaten in Dezimalgrad."""
    lat = parse_coordinate("5133.82", "N")
    assert lat is not None
    assert round(lat, 5) == 51.56367

    lon = parse_coordinate("00042.24", "W")
    assert lon is not None
    assert round(lon, 5) == -0.704


def test_parse_coordinate_invalid() -> None:
    """Prüft das Verhalten bei ungültigen oder leeren Koordinaten."""
    assert parse_coordinate("", "N") is None
    assert parse_coordinate("invalid", "N") is None
    assert parse_coordinate("12", "N") is None


def test_parse_nmea_sentence_rmc_valid() -> None:
    """Prüft das Parsen eines gültigen GPRMC-Satzes."""
    sentence = "$GPRMC,220516,A,5133.82,N,00042.24,W,10.0,231.8,130694,004.2,W*4C"
    state = GpsState()
    new_state = parse_nmea_sentence(sentence, state)

    assert new_state.is_valid is True
    assert round(new_state.latitude, 5) == 51.56367
    assert round(new_state.longitude, 5) == -0.704
    assert round(new_state.speed_kmh, 2) == 18.52  # 10 knots * 1.852


def test_parse_nmea_sentence_rmc_invalid_fix() -> None:
    """Prüft, dass bei ungültigem Fix (V) der Status korrekt übernommen wird."""
    sentence = "$GPRMC,220516,V,5133.82,N,00042.24,W,10.0,231.8,130694,004.2,W*5B"
    state = GpsState()
    new_state = parse_nmea_sentence(sentence, state)

    assert new_state.is_valid is False
    assert round(new_state.latitude, 5) == 51.56367


def test_parse_nmea_sentence_gga() -> None:
    """Prüft das Parsen eines GPGGA-Satzes zur Ermittlung der Satelliten."""
    sentence = "$GPGGA,170834,4124.8963,N,08151.6838,W,1,05,1.5,280.2,M,-34.0,M,,,*59"
    state = GpsState(satellites=2)
    new_state = parse_nmea_sentence(sentence, state)

    assert new_state.satellites == 5


def test_create_gps_payload() -> None:
    """Prüft die erfolgreiche Payload-Generierung aus dem GPS-Zustand."""
    state = GpsState(latitude=51.5, longitude=10.0, speed_kmh=15.5, satellites=6, is_valid=True)
    payload = create_gps_payload(state)

    assert payload.timestamp_ms > 0
    assert payload.latitude == 51.5
    assert payload.longitude == 10.0
    assert payload.speed_kmh == 15.5
    assert payload.satellites_connected == 6


def test_read_sentence_valid() -> None:
    """Prüft, dass read_sentence Bytes decodiert und strippt."""
    mock_port = Mock()
    mock_port.readline.return_value = b"$GPRMC,123*FF\r\n"

    result = read_sentence(mock_port)
    assert result == "$GPRMC,123*FF"


def test_read_sentence_empty() -> None:
    """Prüft, dass bei leeren Daten None zurückgegeben wird."""
    mock_port = Mock()
    mock_port.readline.return_value = b""

    result = read_sentence(mock_port)
    assert result is None


def test_read_sentence_exception() -> None:
    """Prüft, dass bei seriellen Fehlern None zurückgegeben wird."""
    mock_port = Mock()
    mock_port.readline.side_effect = Exception("Serial port error")

    result = read_sentence(mock_port)
    assert result is None
