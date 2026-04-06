"""
config.py
=========
Central configuration for DockWise AI v2.
Loads environment variables and defines all shared constants.
"""

from __future__ import annotations
import os
from dotenv import load_dotenv

load_dotenv()

# ── API Keys ──────────────────────────────────────────────────────────────────
AISSTREAM_API_KEY: str = os.getenv("AISSTREAM_API_KEY", "")
WEATHER_API_KEY: str = os.getenv("WEATHER_API_KEY", "")
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:5173")

# ── AIS Stream Configuration ──────────────────────────────────────────────────
WSS_URL = "wss://stream.aisstream.io/v0/stream"

BOUNDING_BOXES = [
    # US West Coast (San Diego to Seattle)
    [[32.5, -125.0], [49.0, -117.0]],
    # US Gulf Coast (Brownsville to Key West)
    [[24.5, -97.5], [30.5, -80.0]],
    # US East Coast (Miami to Maine)
    [[25.0, -82.0], [45.0, -66.0]],
    # Hawaii
    [[18.0, -161.0], [23.0, -154.0]],
    # Alaska (major ports)
    [[55.0, -170.0], [65.0, -140.0]],
]

MESSAGE_TYPES = ["PositionReport", "ShipStaticData", "StandardClassBPositionReport"]

# ── Navigational Status Labels ────────────────────────────────────────────────
NAV_STATUS_LABELS: dict[int, str] = {
    0: "Under Way Using Engine",
    1: "At Anchor",
    2: "Not Under Command",
    3: "Restricted Manoeuvrability",
    4: "Constrained by Draught",
    5: "Moored",
    6: "Aground",
    7: "Engaged in Fishing",
    8: "Under Way Sailing",
    9: "Reserved",
    10: "Reserved",
    11: "Reserved",
    12: "Reserved",
    13: "Reserved",
    14: "AIS-SART active",
    15: "Not Defined",
}

# ── Vessel Type Labels ─────────────────────────────────────────────────────────
def get_vessel_type_label(type_code: int) -> str:
    if 30 <= type_code <= 39:
        return "Fishing"
    elif 40 <= type_code <= 49:
        return "High Speed Craft"
    elif 50 <= type_code <= 59:
        return "Special Craft"
    elif 60 <= type_code <= 69:
        return "Passenger"
    elif 70 <= type_code <= 79:
        return "Cargo"
    elif 80 <= type_code <= 89:
        return "Tanker"
    elif 90 <= type_code <= 99:
        return "Other"
    return "Unknown"

# ── Port Coordinates (lat, lon) ───────────────────────────────────────────────
PORT_COORDS: dict[str, tuple[float, float]] = {
    # West Coast
    "Los Angeles-Long Beach": (33.75, -118.22),
    "Oakland": (37.80, -122.27),
    "Seattle": (47.60, -122.34),
    "Tacoma": (47.27, -122.41),
    "San Diego": (32.71, -117.17),
    "San Francisco": (37.79, -122.39),
    "Port Hueneme": (34.15, -119.20),
    "Portland, OR": (45.52, -122.68),
    "Longview": (46.14, -122.93),
    "Everett": (47.97, -122.20),
    "Bellingham": (48.74, -122.49),
    # Alaska / Hawaii
    "Anchorage (Alaska)": (61.22, -149.90),
    "Dutch Harbor": (53.89, -166.54),
    "Kodiak": (57.80, -152.41),
    "Honolulu": (21.31, -157.87),
    "Hilo": (19.73, -155.09),
    # Gulf Coast
    "Houston": (29.75, -95.08),
    "South Louisiana": (29.95, -90.36),
    "New Orleans": (29.95, -90.06),
    "Baton Rouge": (30.44, -91.19),
    "Beaumont": (30.08, -94.10),
    "Port Arthur": (29.88, -93.93),
    "Corpus Christi": (27.80, -97.40),
    "Freeport": (28.95, -95.36),
    "Galveston": (29.30, -94.80),
    "Texas City": (29.39, -94.90),
    "Lake Charles": (30.22, -93.21),
    "Mobile": (30.69, -88.04),
    "Tampa": (27.94, -82.45),
    "Port Lavaca": (28.62, -96.63),
    "Brownsville": (25.93, -97.49),
    "Gulfport": (30.37, -89.09),
    "Pascagoula": (30.35, -88.56),
    "Pensacola": (30.42, -87.22),
    "Panama City": (30.16, -85.66),
    "Fourchon": (29.11, -90.20),
    # East Coast
    "New York-New Jersey": (40.68, -74.04),
    "Philadelphia": (39.87, -75.14),
    "Baltimore": (39.27, -76.58),
    "Norfolk": (36.85, -76.30),
    "Port of Virginia": (36.93, -76.33),
    "Newport News": (37.00, -76.43),
    "Savannah": (32.08, -81.09),
    "Charleston": (32.78, -79.94),
    "Jacksonville": (30.33, -81.66),
    "Miami": (25.77, -80.19),
    "Port Everglades": (26.09, -80.12),
    "Canaveral Harbor": (28.41, -80.59),
    "Wilmington, NC": (34.24, -77.95),
    "Brunswick": (31.15, -81.49),
    "Boston": (42.36, -71.05),
    "Providence": (41.82, -71.40),
    "Portland, ME": (43.66, -70.25),
    "Marcus Hook": (39.82, -75.41),
    "Wilmington, DE": (39.74, -75.55),
    "Dominion Cove Point": (38.39, -76.38),
    # Great Lakes
    "Chicago": (41.85, -87.65),
    "Detroit": (42.33, -83.05),
    "Cleveland": (41.51, -81.69),
    "Toledo": (41.66, -83.55),
    "Duluth": (46.78, -92.10),
    "Milwaukee": (43.04, -87.91),
    "Gary": (41.60, -87.35),
    "Green Bay": (44.52, -88.02),
    "Erie": (42.13, -80.08),
    "Ashtabula": (41.90, -80.79),
}

# ── Port Channel Depths (meters) ──────────────────────────────────────────────
PORT_DEPTHS_METERS: dict[str, float] = {
    "Los Angeles-Long Beach": 16.8,
    "Oakland": 15.2,
    "Seattle": 15.8,
    "Tacoma": 15.2,
    "San Diego": 12.0,
    "New York-New Jersey": 15.2,
    "Savannah": 14.0,
    "Charleston": 14.0,
    "Baltimore": 13.7,
    "Norfolk": 14.0,
    "Port of Virginia": 14.0,
    "Philadelphia": 12.2,
    "Jacksonville": 12.5,
    "Houston": 14.0,
    "New Orleans": 13.7,
    "Corpus Christi": 13.7,
    "Galveston": 12.5,
    "Freeport": 12.2,
    "Mobile": 12.8,
    "Tampa": 11.0,
    "Miami": 13.7,
    "Boston": 12.0,
    "Providence": 10.0,
    "Chicago": 9.1,
    "Detroit": 9.1,
    "Cleveland": 9.1,
    "Duluth": 8.2,
}

# ── Rerouting Alternatives ─────────────────────────────────────────────────────
ALTERNATIVES: dict[str, dict[str, list[str]]] = {
    "West Coast": {
        "Los Angeles-Long Beach": ["Oakland", "Seattle", "Tacoma", "San Diego"],
        "Oakland": ["Los Angeles-Long Beach", "Seattle", "Tacoma"],
        "Seattle": ["Tacoma", "Oakland", "Los Angeles-Long Beach"],
        "Tacoma": ["Seattle", "Oakland", "Los Angeles-Long Beach"],
        "San Diego": ["Los Angeles-Long Beach", "Oakland"],
    },
    "East Coast": {
        "New York-New Jersey": ["Philadelphia", "Baltimore", "Norfolk", "Savannah"],
        "Savannah": ["Charleston", "Jacksonville", "Norfolk"],
        "Charleston": ["Savannah", "Norfolk", "Jacksonville"],
        "Baltimore": ["Norfolk", "Philadelphia", "New York-New Jersey"],
        "Norfolk": ["Baltimore", "Philadelphia", "Savannah"],
        "Philadelphia": ["Baltimore", "New York-New Jersey", "Norfolk"],
        "Jacksonville": ["Savannah", "Charleston", "Miami"],
        "Boston": ["New York-New Jersey", "Providence"],
    },
    "Gulf Coast": {
        "Houston": ["Corpus Christi", "New Orleans", "Freeport", "Galveston"],
        "New Orleans": ["Houston", "Baton Rouge", "Mobile"],
        "Corpus Christi": ["Houston", "Port Lavaca", "Freeport"],
        "Galveston": ["Houston", "Freeport", "Corpus Christi"],
        "Mobile": ["New Orleans", "Gulfport", "Tampa"],
        "Tampa": ["Mobile", "Jacksonville", "Miami"],
    },
}

# ── Port to Chokepoint Mapping ─────────────────────────────────────────────────
PORT_TO_CHOKEPOINTS: dict[str, list[str]] = {
    "west_coast": ["Malacca Strait", "Taiwan Strait", "Panama Canal", "Luzon Strait"],
    "gulf_coast": ["Panama Canal", "Strait of Hormuz", "Bab el-Mandeb Strait", "Suez Canal"],
    "great_lakes": ["Suez Canal", "Panama Canal", "Dover Strait", "Gibraltar Strait"],
    "east_coast": ["Suez Canal", "Bab el-Mandeb Strait", "Panama Canal", "Dover Strait"],
}

WEST_COAST_PORTS = {"los angeles", "long beach", "oakland", "seattle", "tacoma", "san diego", "honolulu"}
GULF_COAST_PORTS = {"houston", "new orleans", "corpus christi", "galveston", "mobile", "tampa", "baton rouge", "freeport"}
GREAT_LAKES_PORTS = {"chicago", "detroit", "cleveland", "duluth", "milwaukee", "gary"}


def get_port_chokepoints(port_name: str) -> list[str]:
    """Return the upstream chokepoints relevant to a given port."""
    lower = port_name.lower()
    if any(p in lower for p in WEST_COAST_PORTS):
        return PORT_TO_CHOKEPOINTS["west_coast"]
    elif any(p in lower for p in GULF_COAST_PORTS):
        return PORT_TO_CHOKEPOINTS["gulf_coast"]
    elif any(p in lower for p in GREAT_LAKES_PORTS):
        return PORT_TO_CHOKEPOINTS["great_lakes"]
    return PORT_TO_CHOKEPOINTS["east_coast"]


def resolve_port_name(raw_destination: str) -> str | None:
    """
    Resolve a raw AIS destination string to a known PortWatch port name.
    AIS destinations are often abbreviated/messy, e.g.:
      "SAN DIEGO-US SAN" → "San Diego"
      "PORT TENDER"      → None (not a real port)
      "HOUSTON TX"       → "Houston"
      "NY/NJ"            → "New York-New Jersey"
    """
    if not raw_destination:
        return None
    dest = raw_destination.upper().strip()

    # Direct match first
    for port_name in PORT_COORDS:
        if port_name.lower() == dest.lower():
            return port_name

    # Keyword-based matching — check if any key port name fragment is in the destination
    _PORT_KEYWORDS: dict[str, str] = {
        "LOS ANGELES": "Los Angeles-Long Beach",
        "LONG BEACH": "Los Angeles-Long Beach",
        "LA/LB": "Los Angeles-Long Beach",
        "LALB": "Los Angeles-Long Beach",
        "OAKLAND": "Oakland",
        "SEATTLE": "Seattle",
        "TACOMA": "Tacoma",
        "SAN DIEGO": "San Diego",
        "SAN FRANC": "San Francisco",
        "HOUSTON": "Houston",
        "NEW ORLEANS": "New Orleans",
        "NOLA": "New Orleans",
        "CORPUS CHR": "Corpus Christi",
        "NEW YORK": "New York-New Jersey",
        "NY/NJ": "New York-New Jersey",
        "NEWARK": "New York-New Jersey",
        "SAVANNAH": "Savannah",
        "CHARLESTON": "Charleston",
        "BALTIMORE": "Baltimore",
        "NORFOLK": "Norfolk",
        "PHILADELPHIA": "Philadelphia",
        "PHILLY": "Philadelphia",
        "MIAMI": "Miami",
        "BOSTON": "Boston",
        "JACKSONVILLE": "Jacksonville",
        "JAX": "Jacksonville",
        "TAMPA": "Tampa",
        "MOBILE": "Mobile",
        "PORTLAND OR": "Portland, OR",
        "PORTLAND,OR": "Portland, OR",
        "GALVESTON": "Galveston",
        "FREEPORT": "Freeport",
        "BEAUMONT": "Beaumont",
        "PORT ARTHUR": "Port Arthur",
        "BATON ROUGE": "Baton Rouge",
        "CHICAGO": "Chicago",
        "DETROIT": "Detroit",
        "CLEVELAND": "Cleveland",
        "DULUTH": "Duluth",
        "HONOLULU": "Honolulu",
        "ANCHORAGE": "Anchorage (Alaska)",
        "BRUNSWICK": "Brunswick",
        "WILMINGTON NC": "Wilmington, NC",
        "WILMINGTON DE": "Wilmington, DE",
        "PORT EVERGLADES": "Port Everglades",
        "FT LAUDERDALE": "Port Everglades",
        "CANAVERAL": "Canaveral Harbor",
        "GULFPORT": "Gulfport",
        "PASCAGOULA": "Pascagoula",
        "PENSACOLA": "Pensacola",
        "LAKE CHARLES": "Lake Charles",
        "TEXAS CITY": "Texas City",
        "SOUTH LOUIS": "South Louisiana",
    }

    for keyword, port_name in _PORT_KEYWORDS.items():
        if keyword in dest:
            return port_name

    return None


def get_alternative_ports(destination: str) -> list[str]:
    """Return alternative ports for a given destination (resolves fuzzy names)."""
    resolved = resolve_port_name(destination) or destination
    for region, ports in ALTERNATIVES.items():
        for port, alts in ports.items():
            if port.lower() == resolved.lower():
                return alts
    return []
