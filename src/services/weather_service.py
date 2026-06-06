# ─────────────────────────────────────────────────────────────
#  src/services/weather_service.py
#  Lead Developer: ROEUNG BUNHENG
#  Purpose: Live third-party API integration (wttr.in).
#           Fetches real-time weather data for Phnom Penh.
#           All network calls are wrapped in try/except for
#           graceful exception handling (Requirement 3).
# ─────────────────────────────────────────────────────────────
import logging

import requests

logger = logging.getLogger(__name__)

# ── wttr.in API — 100% free, no API key, works on all servers
# JSON format for Phnom Penh, Cambodia
_WEATHER_URL = "https://wttr.in/Phnom+Penh"
_WEATHER_PARAMS = {
    "format": "j1",
    "lang":   "en",
}

# Weather condition code → emoji mapping
_CONDITION_ICONS = {
    "sunny":             "☀️",
    "clear":             "☀️",
    "partly cloudy":     "⛅",
    "cloudy":            "☁️",
    "overcast":          "☁️",
    "mist":              "🌫️",
    "fog":               "🌫️",
    "drizzle":           "🌦️",
    "rain":              "🌧️",
    "heavy rain":        "🌧️",
    "thunder":           "⛈️",
    "thunderstorm":      "⛈️",
    "snow":              "❄️",
    "blizzard":          "❄️",
    "blowing snow":      "❄️",
}


def _get_icon(description: str) -> str:
    desc_lower = description.lower()
    for key, icon in _CONDITION_ICONS.items():
        if key in desc_lower:
            return icon
    return "🌡️"


def fetch_weather() -> dict:
    """
    Calls wttr.in API and returns a clean weather dict.

    Returns:
        {
          "temperature": 32,
          "feels_like": 38,
          "humidity": 75,
          "windspeed": 12,
          "icon": "⛅",
          "condition": "Partly cloudy",
        }

    Exception Handling (Requirement 3):
      - Timeout / connection error → raises ConnectionError
      - Bad response / JSON parse error → raises ValueError
      - Caller (message handler) sends user-friendly message
    """
    try:
        resp = requests.get(
            _WEATHER_URL,
            params=_WEATHER_PARAMS,
            timeout=10,
            headers={"User-Agent": "AgriTradeBot/1.0"},
            verify=False,
        )
        resp.raise_for_status()
        raw = resp.json()

        current = raw["current_condition"][0]
        condition = current["weatherDesc"][0]["value"]
        icon = _get_icon(condition)

        return {
            "temperature": current.get("temp_C", "—"),
            "feels_like":  current.get("FeelsLikeC", "—"),
            "humidity":    current.get("humidity", "—"),
            "windspeed":   current.get("windspeedKmph", "—"),
            "icon":        icon,
            "condition":   condition,
        }

    except requests.exceptions.ConnectionError as exc:
        logger.exception("weather_service: Connection error")
        raise ConnectionError(
            "⚠️ <b>មិនអាចទាក់ទង API ទេ / Could not reach weather service.</b>\n"
            "សូមព្យាយាមម្ដងទៀតក្រោយ / Please try again later."
        ) from exc

    except requests.exceptions.Timeout as exc:
        logger.exception("weather_service: Timeout")
        raise ConnectionError(
            "⚠️ <b>API យឺតពេក / Weather service timed out.</b>\n"
            "សូមព្យាយាមម្ដងទៀតក្រោយ / Please try again later."
        ) from exc

    except requests.exceptions.HTTPError as exc:
        logger.exception("weather_service: HTTP error %s",
                         exc.response.status_code if exc.response else "?")
        raise ConnectionError(
            "⚠️ <b>API បញ្ជូនកំហុស / Weather API returned an error.</b>\n"
            "សូមព្យាយាមម្ដងទៀតក្រោយ / Please try again later."
        ) from exc

    except (KeyError, ValueError, requests.exceptions.JSONDecodeError) as exc:
        logger.exception("weather_service: Unexpected API response format")
        raise ValueError(
            "⚠️ <b>ទិន្នន័យ API មិនត្រឹមត្រូវ / Unexpected API response.</b>\n"
            "សូមព្យាយាមម្ដងទៀតក្រោយ / Please try again later."
        ) from exc

    except requests.exceptions.RequestException as exc:
        logger.exception("weather_service: Unexpected error: %s", type(exc).__name__)
        raise ConnectionError(
            "⚠️ <b>មានបញ្ហាក្នុងការភ្ជាប់ / Network error.</b>\n"
            "សូមព្យាយាមម្ដងទៀតក្រោយ / Please try again later."
        ) from exc
