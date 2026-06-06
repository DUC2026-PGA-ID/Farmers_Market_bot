# ─────────────────────────────────────────────────────────────
#  src/services/weather_service.py
#  Lead Developer: ROEUNG BUNHENG
#  Purpose: Live third-party API integration (Open-Meteo).
#           Fetches real-time weather data for Phnom Penh.
#           All network calls are wrapped in try/except for
#           graceful exception handling (Requirement 3).
# ─────────────────────────────────────────────────────────────
import json
import logging
import ssl
import urllib.request

logger = logging.getLogger(__name__)

# ── SSL Context — fixes certificate issues on Windows/Render ─
_SSL_CTX = ssl.create_default_context()

# ── Open-Meteo API — 100% free, no API key required ─────────
# Coordinates: Phnom Penh, Cambodia
_WEATHER_URL = (
    "https://api.open-meteo.com/v1/forecast"
    "?latitude=11.5625"
    "&longitude=104.916"
    "&current_weather=true"
    "&wind_speed_unit=kmh"
)

# WMO Weather Condition Code → human-readable label
_WMO_CODES = {
    0:  ("☀️", "Clear sky"),
    1:  ("🌤️", "Mainly clear"),
    2:  ("⛅", "Partly cloudy"),
    3:  ("☁️", "Overcast"),
    45: ("🌫️", "Foggy"),
    48: ("🌫️", "Icy fog"),
    51: ("🌦️", "Light drizzle"),
    53: ("🌦️", "Moderate drizzle"),
    55: ("🌧️", "Dense drizzle"),
    61: ("🌧️", "Slight rain"),
    63: ("🌧️", "Moderate rain"),
    65: ("🌧️", "Heavy rain"),
    71: ("❄️", "Slight snow"),
    73: ("❄️", "Moderate snow"),
    75: ("❄️", "Heavy snow"),
    80: ("🌦️", "Rain showers"),
    81: ("🌧️", "Moderate showers"),
    82: ("⛈️", "Violent showers"),
    95: ("⛈️", "Thunderstorm"),
    96: ("⛈️", "Thunderstorm + hail"),
    99: ("⛈️", "Heavy thunderstorm + hail"),
}


def fetch_weather() -> dict:
    """
    Calls Open-Meteo API and returns a clean weather dict.

    Returns:
        {
          "temperature": 32.1,
          "windspeed": 12.5,
          "icon": "⛅",
          "condition": "Partly cloudy",
          "is_day": 1
        }

    Exception Handling (Requirement 3):
      - Timeout (5s) → raises ConnectionError with user-friendly message
      - Invalid JSON / missing key → raises ValueError with user-friendly message
      - Caller (message handler) catches these and sends error message to user
    """
    try:
        req = urllib.request.Request(
            _WEATHER_URL,
            headers={"User-Agent": "AgriTradeBot/1.0"},
        )
        with urllib.request.urlopen(req, timeout=10, context=_SSL_CTX) as response:
            raw = json.loads(response.read().decode("utf-8"))

        cw = raw["current_weather"]
        wmo = int(cw.get("weathercode", 0))
        icon, condition = _WMO_CODES.get(wmo, ("🌡️", "Unknown"))

        return {
            "temperature": cw.get("temperature", "—"),
            "windspeed":   cw.get("windspeed", "—"),
            "icon":        icon,
            "condition":   condition,
            "is_day":      cw.get("is_day", 1),
        }

    except urllib.error.URLError as exc:
        logger.exception("weather_service: Network error calling Open-Meteo")
        raise ConnectionError(
            "⚠️ <b>មិនអាចទាក់ទង API ទេ / Could not reach weather service.</b>\n"
            "សូមព្យាយាមម្ដងទៀតក្រោយ / Please try again later."
        ) from exc

    except (KeyError, ValueError, json.JSONDecodeError) as exc:
        logger.exception("weather_service: Unexpected API response format")
        raise ValueError(
            "⚠️ <b>ទិន្នន័យ API មិនត្រឹមត្រូវ / Unexpected API response.</b>\n"
            "សូមព្យាយាមម្ដងទៀតក្រោយ / Please try again later."
        ) from exc
