import httpx
from langchain_core.tools import tool

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
FORECAST_DAYS = 3

# WMO weather interpretation codes used by Open-Meteo.
WEATHER_CODES = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "depositing rime fog",
    51: "light drizzle", 53: "moderate drizzle", 55: "dense drizzle",
    56: "light freezing drizzle", 57: "dense freezing drizzle",
    61: "slight rain", 63: "moderate rain", 65: "heavy rain",
    66: "light freezing rain", 67: "heavy freezing rain",
    71: "slight snow", 73: "moderate snow", 75: "heavy snow", 77: "snow grains",
    80: "slight rain showers", 81: "moderate rain showers", 82: "violent rain showers",
    85: "slight snow showers", 86: "heavy snow showers",
    95: "thunderstorm", 96: "thunderstorm with slight hail", 99: "thunderstorm with heavy hail",
}


@tool
async def get_weather(city: str) -> str:
    """Return the current weather and a 3-day forecast for a city.

    Pass only the city name in English, e.g. "Tehran" or "Paris", without country or region.
    """
    async with httpx.AsyncClient(timeout=10) as client:
        geo = await client.get(GEOCODING_URL, params={"name": city, "count": 1})
        geo.raise_for_status()
        places = geo.json().get("results")
        if not places:
            return f"No location found for '{city}'."
        place = places[0]

        forecast = await client.get(FORECAST_URL, params={
            "latitude": place["latitude"],
            "longitude": place["longitude"],
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,weather_code",
            "daily": "weather_code,temperature_2m_min,temperature_2m_max,precipitation_probability_max",
            "timezone": "auto",
            "forecast_days": FORECAST_DAYS,
        })
        forecast.raise_for_status()
        data = forecast.json()

    now, daily = data["current"], data["daily"]
    lines = [
        f"Weather for {place['name']}, {place.get('country', '')} (local time {now['time']}):",
        f"Now: {WEATHER_CODES.get(now['weather_code'], 'unknown')}, {now['temperature_2m']}°C "
        f"(feels like {now['apparent_temperature']}°C), humidity {now['relative_humidity_2m']}%, "
        f"wind {now['wind_speed_10m']} km/h.",
    ]
    for i, day in enumerate(daily["time"]):
        lines.append(
            f"{day}: {WEATHER_CODES.get(daily['weather_code'][i], 'unknown')}, "
            f"{daily['temperature_2m_min'][i]}–{daily['temperature_2m_max'][i]}°C, "
            f"{daily['precipitation_probability_max'][i]}% chance of precipitation."
        )
    return "\n".join(lines)
