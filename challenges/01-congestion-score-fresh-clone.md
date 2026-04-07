# Challenge: All Congestion Scores Show 50 (MEDIUM) on Fresh Clone

## Symptom
After cloning the repository on a new machine and starting the application, every port in the Live Vessels tab displayed a fixed congestion score of 50 with MEDIUM status. The pulsating red animation for highly congested ports was absent.

## Root Cause
The `.gitignore` file excludes all CSV files (`*.csv`). The two data files required by the backend — `portwatch_us_data.csv` (34MB, 309k rows) and `chokepoint_data.csv` (8MB, 74k rows) — are not tracked in git. On a fresh clone these files do not exist.

### Failure Chain

```
.gitignore: *.csv
    → CSV files not in git
    → Fresh clone has no data files

api.py: get_df()
    → Path("portwatch_us_data.csv").exists() returns False
    → Raises HTTPException(503)

GET /api/top-ports
    → Returns HTTP 503

VesselMap.jsx: usePortCongestion()
    → fetch() catches the error silently (empty catch block)
    → congestionPorts stays [] (empty array)

VesselMap.jsx: portMarkers (line 557)
    → const score = cong?.current_score ?? 50    // cong is undefined
    → const status = cong?.status || "MEDIUM"     // falls back to MEDIUM
    → Every port renders as MEDIUM (amber)

Pulse animation
    → Only triggers when status === "HIGH" (score >= 67)
    → No port reaches HIGH → no pulsating rings visible
```

### Why Score = 50 Specifically
The z-score formula maps a z-value of 0 to a congestion score of exactly 50:
```
score = (z + 3) / 6 * 100
     = (0 + 3) / 6 * 100
     = 50.0
```
The frontend fallback (`?? 50`) produces the same "no data" value — both code paths converge on 50.

## Resolution
Added a `@app.on_event("startup")` handler in `api.py` that checks if CSV files exist on startup. If missing, it calls `data_pull.run_ports()` and `data_pull.run_chokepoints()` to download them from the public IMF PortWatch API automatically.

```python
@app.on_event("startup")
async def ensure_data():
    if not Path(DATA_FILE).exists():
        data_pull.run_ports()
    if not Path(CHOKEPOINT_FILE).exists():
        data_pull.run_chokepoints()
```

**Trade-offs considered:**
- Committing CSVs to git was rejected — 42MB is too large and the data updates daily
- Making data pull a manual step was rejected — too easy to forget, breaks first-run experience
- Auto-pull adds 2-5 minutes to first startup, but only runs once per machine

## Files Changed
- `venv2/backend/api.py` — startup event
- `GETTING_STARTED.md` — first-run documentation
- `README.md` — first-run note in How to Run section
