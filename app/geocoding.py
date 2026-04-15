import os
import requests
from dotenv import load_dotenv

load_dotenv()
MAPS_KEY = os.getenv("GOOGLE_MAPS_API_KEY")


def geocode(address: str) -> dict | None:
    """Resolve a text address to {lat, lng, display_name} using Google Maps."""
    if not MAPS_KEY:
        return None
    try:
        resp = requests.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params={"address": address, "region": "co", "language": "es", "key": MAPS_KEY},
            timeout=5,
        )
        data = resp.json()
        if data.get("status") == "OK":
            loc = data["results"][0]["geometry"]["location"]
            name = data["results"][0]["formatted_address"]
            return {"lat": loc["lat"], "lng": loc["lng"], "display_name": name}
    except Exception:
        pass
    return None
