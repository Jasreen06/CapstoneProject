# Auto-Pull Data on First Startup

## Overview
Added a startup event to the main backend (`api.py`) that automatically downloads port and chokepoint data from the IMF PortWatch API if the CSV files are missing. This fixes the issue where a fresh clone shows all congestion scores as 50 (MEDIUM).

## Problem
On a fresh clone, `portwatch_us_data.csv` and `chokepoint_data.csv` do not exist because `*.csv` is in `.gitignore` (the files are ~42MB total). Without data, the API returns HTTP 503 and the frontend defaults every port to score=50 / MEDIUM. The pulsating animation for HIGH congestion ports never triggers since no port reaches the >=67 threshold.

## File Modified

### `venv2/backend/api.py`
Added `import data_pull` and a `@app.on_event("startup")` handler:

```python
@app.on_event("startup")
async def ensure_data():
    """Auto-pull data from IMF PortWatch if CSV files are missing."""
    if not Path(DATA_FILE).exists():
        logger.info(f"Data file '{DATA_FILE}' not found — pulling from PortWatch API...")
        try:
            data_pull.run_ports()
            logger.info("Port data pull complete.")
        except Exception as e:
            logger.error(f"Port data pull failed: {e}")

    if not Path(CHOKEPOINT_FILE).exists():
        logger.info(f"Chokepoint file '{CHOKEPOINT_FILE}' not found — pulling from PortWatch API...")
        try:
            data_pull.run_chokepoints()
            logger.info("Chokepoint data pull complete.")
        except Exception as e:
            logger.error(f"Chokepoint data pull failed: {e}")
```

**Behaviour:**
- If CSV files already exist (e.g., on an existing setup), the guard skips the pull and startup is instant
- On a fresh clone, the first startup takes ~2-5 minutes to download ~42MB from the PortWatch API
- The PortWatch API is public (no API key required)
- Each pull uses the existing `data_pull.run_ports()` and `data_pull.run_chokepoints()` functions (paginated fetch, 2000 records per batch)

## Files Also Updated

### `GETTING_STARTED.md`
- Added first-run note explaining the auto-download delay
- Added troubleshooting entry for "All port congestion scores show 50 (MEDIUM)"

### `README.md`
- Added first-run note in Section 14 (How to Run)

## Additional Fix

### `venv2/frontend/src/VesselMap.jsx`
Fixed `API_BASE` port mismatch — was `http://localhost:8000`, corrected to `http://localhost:8004` to match the actual backend port. This was committed in the previous commit alongside the GETTING_STARTED.md doc.
