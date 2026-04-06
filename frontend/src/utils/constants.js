export const CONGESTION_COLORS = {
  LOW: '#22c55e',
  MEDIUM: '#eab308',
  HIGH: '#ef4444',
  UNKNOWN: '#64748b',
};

export const CONGESTION_BG = {
  LOW: 'bg-green-500/20 text-green-400 border border-green-500/30',
  MEDIUM: 'bg-yellow-500/20 text-yellow-400 border border-yellow-500/30',
  HIGH: 'bg-red-500/20 text-red-400 border border-red-500/30',
  UNKNOWN: 'bg-slate-600/20 text-slate-400 border border-slate-600/30',
};

export const VESSEL_TYPE_LABELS = {
  30: 'Fishing', 31: 'Fishing', 32: 'Fishing', 33: 'Fishing', 34: 'Fishing',
  35: 'Military', 36: 'Sailing', 37: 'Pleasure Craft',
  40: 'High Speed', 41: 'High Speed', 42: 'High Speed', 43: 'High Speed',
  50: 'Pilot', 51: 'SAR', 52: 'Tug', 53: 'Port Tender', 55: 'Law Enforcement',
  60: 'Passenger', 61: 'Passenger', 62: 'Passenger', 63: 'Passenger', 69: 'Passenger',
  70: 'Cargo', 71: 'Cargo (Haz A)', 72: 'Cargo (Haz B)', 73: 'Cargo (Haz C)',
  74: 'Cargo (Haz D)', 75: 'Cargo', 76: 'Cargo', 77: 'Cargo', 78: 'Cargo', 79: 'Cargo',
  80: 'Tanker', 81: 'Tanker (Haz A)', 82: 'Tanker (Haz B)', 83: 'Tanker (Haz C)',
  84: 'Tanker (Haz D)', 85: 'Tanker', 86: 'Tanker', 87: 'Tanker', 88: 'Tanker', 89: 'Tanker',
  90: 'Other', 91: 'Other', 99: 'Other',
};

export const NAV_STATUS_LABELS = {
  0: 'Under Way',
  1: 'At Anchor',
  2: 'Not Under Command',
  3: 'Restricted Maneuverability',
  4: 'Constrained by Draught',
  5: 'Moored',
  6: 'Aground',
  7: 'Fishing',
  8: 'Sailing',
  15: 'Not Defined',
};

export const PORT_COORDS = {
  'Los Angeles-Long Beach': [33.75, -118.22],
  'Oakland': [37.80, -122.27],
  'Seattle': [47.60, -122.34],
  'Tacoma': [47.27, -122.41],
  'San Diego': [32.71, -117.17],
  'Houston': [29.75, -95.08],
  'New Orleans': [29.95, -90.06],
  'Corpus Christi': [27.80, -97.40],
  'New York-New Jersey': [40.68, -74.04],
  'Savannah': [32.08, -81.09],
  'Charleston': [32.78, -79.94],
  'Baltimore': [39.27, -76.58],
  'Norfolk': [36.85, -76.30],
  'Philadelphia': [39.87, -75.14],
  'Miami': [25.77, -80.19],
  'Boston': [42.36, -71.05],
  'Chicago': [41.85, -87.65],
  'Detroit': [42.33, -83.05],
  'Cleveland': [41.51, -81.69],
  'Duluth': [46.78, -92.10],
  'Honolulu': [21.31, -157.87],
  'Jacksonville': [30.33, -81.66],
  'Tampa': [27.94, -82.45],
  'Mobile': [30.69, -88.04],
  'Portland, OR': [45.52, -122.68],
};

export const SUGGESTED_QUESTIONS = [
  'Which inbound vessels to Houston should consider rerouting?',
  "What's the congestion outlook for Los Angeles this week?",
  'How will Suez disruption affect East Coast ports in the next 14 days?',
  'What are the top 5 most congested US ports right now?',
  'Should tankers heading to New York consider alternative ports?',
];

export const VESSEL_COLORS = {
  LOW: '#22c55e',
  MEDIUM: '#eab308',
  HIGH: '#ef4444',
  NONE: '#64748b',
};

// ── Vessel type colors for map rendering ─────────────────────────────────
export const VESSEL_TYPE_COLORS = {
  Cargo: '#3b82f6',
  Tanker: '#f59e0b',
  Passenger: '#8b5cf6',
  Fishing: '#22c55e',
  'High Speed': '#06b6d4',
  Military: '#dc2626',
  Tug: '#a855f7',
  Other: '#94a3b8',
  Unknown: '#64748b',
};

// ── Nav status colors (for anchored/moored differentiation) ──────────────
export const NAV_STATUS_COLORS = {
  0: null,       // Under Way — use vessel type color
  1: '#f97316',  // At Anchor — orange
  5: '#06b6d4',  // Moored — cyan
  7: '#22c55e',  // Fishing — green
};

// ── Filter option arrays ─────────────────────────────────────────────────
export const VESSEL_TYPE_FILTER_OPTIONS = [
  { value: '', label: 'All Types' },
  { value: 'Cargo', label: 'Cargo' },
  { value: 'Tanker', label: 'Tanker' },
  { value: 'Passenger', label: 'Passenger' },
  { value: 'Fishing', label: 'Fishing' },
  { value: 'High Speed Craft', label: 'High Speed' },
  { value: 'Tug', label: 'Tug' },
];

export const NAV_STATUS_FILTER_OPTIONS = [
  { value: '', label: 'All Statuses' },
  { value: '0', label: 'Under Way' },
  { value: '1', label: 'At Anchor' },
  { value: '5', label: 'Moored' },
  { value: '7', label: 'Fishing' },
];

// ── Descriptions for filter tooltips & vessel detail ─────────────────────
export const VESSEL_TYPE_DESCRIPTIONS = {
  Cargo: 'Freight vessels carrying containerized or bulk goods across trade routes.',
  Tanker: 'Vessels carrying liquid bulk cargo such as crude oil, chemicals, or LNG.',
  Passenger: 'Cruise ships and ferries transporting passengers between ports.',
  Fishing: 'Vessels actively engaged in commercial fishing operations.',
  'High Speed': 'Fast craft including hydrofoils and high-speed ferries.',
  Military: 'Naval and coast guard vessels on patrol or transit.',
  Tug: 'Tugboats assisting larger vessels with docking and maneuvering.',
  Other: 'Miscellaneous vessels including research ships and cable layers.',
};

export const NAV_STATUS_DESCRIPTIONS = {
  0: 'Under Way — Vessel is moving under engine power toward its destination.',
  1: 'At Anchor — Vessel is stationary, held in place by its anchor in open water (not tied to a dock).',
  2: 'Not Under Command — Vessel cannot maneuver due to exceptional circumstances.',
  3: 'Restricted Maneuverability — Vessel is limited in its ability to maneuver (e.g., dredging, diving).',
  4: 'Constrained by Draught — Vessel draft limits its ability to deviate from course.',
  5: 'Moored — Vessel is tied to a dock, berth, or fixed structure at a port facility.',
  6: 'Aground — Vessel has run aground and is not floating freely.',
  7: 'Fishing — Vessel is actively engaged in fishing with gear deployed.',
  8: 'Sailing — Vessel is under sail (not using engine).',
  15: 'Not Defined — Navigation status has not been reported.',
};

// ── Port alternative mappings (mirrors backend config) ───────────────────
export const PORT_ALTERNATIVES = {
  'Los Angeles-Long Beach': ['Oakland', 'Seattle', 'Tacoma', 'San Diego'],
  'Oakland': ['Los Angeles-Long Beach', 'Seattle', 'Tacoma'],
  'Seattle': ['Tacoma', 'Oakland', 'Los Angeles-Long Beach'],
  'Tacoma': ['Seattle', 'Oakland', 'Los Angeles-Long Beach'],
  'San Diego': ['Los Angeles-Long Beach', 'Oakland'],
  'New York-New Jersey': ['Philadelphia', 'Baltimore', 'Norfolk', 'Savannah'],
  'Savannah': ['Charleston', 'Jacksonville', 'Norfolk'],
  'Charleston': ['Savannah', 'Norfolk', 'Jacksonville'],
  'Baltimore': ['Norfolk', 'Philadelphia', 'New York-New Jersey'],
  'Norfolk': ['Baltimore', 'Philadelphia', 'Savannah'],
  'Philadelphia': ['Baltimore', 'New York-New Jersey', 'Norfolk'],
  'Jacksonville': ['Savannah', 'Charleston', 'Miami'],
  'Boston': ['New York-New Jersey', 'Providence'],
  'Houston': ['Corpus Christi', 'New Orleans', 'Freeport', 'Galveston'],
  'New Orleans': ['Houston', 'Baton Rouge', 'Mobile'],
  'Corpus Christi': ['Houston', 'Port Lavaca', 'Freeport'],
  'Galveston': ['Houston', 'Freeport', 'Corpus Christi'],
  'Mobile': ['New Orleans', 'Gulfport', 'Tampa'],
  'Tampa': ['Mobile', 'Jacksonville', 'Miami'],
};

// ── Map legend entries ───────────────────────────────────────────────────
export const MAP_LEGEND = [
  { label: 'Cargo', color: '#3b82f6', shape: 'circle' },
  { label: 'Tanker', color: '#f59e0b', shape: 'circle' },
  { label: 'Passenger', color: '#8b5cf6', shape: 'circle' },
  { label: 'Fishing', color: '#22c55e', shape: 'circle' },
  { label: 'Anchored', color: '#f97316', shape: 'diamond' },
  { label: 'Moored', color: '#06b6d4', shape: 'square' },
];
