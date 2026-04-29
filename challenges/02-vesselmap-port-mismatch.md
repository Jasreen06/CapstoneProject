# Challenge: VesselMap API Port Mismatch

## Symptom
The Live Vessels tab's port congestion circles did not reflect actual congestion data from the main backend, even when the backend was running and serving correct scores on port 8004.

## Root Cause
`VesselMap.jsx` had a hardcoded `API_BASE` pointing to port 8000:

```javascript
const API_BASE = "http://localhost:8000";   // WRONG
```

The main backend actually runs on port **8004**. The port congestion hook (`usePortCongestion`) was fetching from the wrong port, the request failed silently, and the fallback logic defaulted all scores to 50.

### Why Port 8000?
During earlier development the backend was on port 8000 (see README Known Issues section, port 8000 was permanently occupied by an unkillable process, so development moved to port 8004). When `VesselMap.jsx` was created, it was initially pointed at port 8000 before the port migration was fully propagated.

The existing `useApi.js` hooks correctly use port 8004:
```javascript
const BASE = process.env.REACT_APP_API_URL || "http://localhost:8004";
```

But `VesselMap.jsx` uses its own `API_BASE` constant rather than the shared hook, so it didn't pick up the correct port.

## Resolution
Changed `API_BASE` in `VesselMap.jsx` from port 8000 to port 8004:

```javascript
const API_BASE = "http://localhost:8004";   // FIXED
```

## Files Changed
- `venv2/frontend/src/VesselMap.jsx`: line 18, port number corrected
