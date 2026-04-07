# DockWise AI — Getting Started Guide

Step-by-step instructions to clone, set up, and run the full DockWise AI application on a new machine.

---

## Prerequisites

| Requirement | Minimum Version | Check Command |
|-------------|-----------------|---------------|
| **Python** | 3.10+ | `python3 --version` |
| **Node.js** | 18+ | `node -v` |
| **npm** | 9+ | `npm -v` |
| **Git** | any | `git --version` |

---

## 1. Clone the Repository

```bash
git clone https://github.com/Jasreen06/CapstoneProject.git
cd CapstoneProject
```

To work on the Pramod branch (AIS + Live Vessels features):
```bash
git checkout Pramod
```

---

## 2. Set Up the Python Virtual Environment

Create a virtual environment and install all backend dependencies:

```bash
python3 -m venv venv2/venv
source venv2/venv/bin/activate          # macOS / Linux
# OR
venv2\Scripts\activate                  # Windows
```

Install requirements:
```bash
pip install -r venv2/backend/requirements.txt
pip install websockets                  # needed for AIS live stream
```

---

## 3. Configure Environment Variables

Create the file `venv2/backend/.env` with your API keys:

```
WEATHER_API_KEY=your_openweathermap_api_key
GROQ_API_KEY=your_groq_api_key
AISSTREAM_API_KEY=your_aisstream_api_key
```

**Where to get keys:**

| Key | Service | Sign-up URL |
|-----|---------|-------------|
| `WEATHER_API_KEY` | OpenWeatherMap | https://openweathermap.org/api |
| `GROQ_API_KEY` | Groq (LLaMA-3.3-70B) | https://console.groq.com |
| `AISSTREAM_API_KEY` | aisstream.io (live vessel tracking) | https://aisstream.io |

> The application will still start without these keys, but the corresponding features (weather, AI advisor, live vessel tracking) will not function.

---

## 4. Install Frontend Dependencies

```bash
cd venv2/frontend
npm install
cd ../..
```

---

## 5. Run the Application

You need **three terminal windows** (or tabs) — one for each service.

### Terminal 1 — Main Backend (port 8004)

```bash
cd venv2/backend
source ../venv/bin/activate             # macOS / Linux (skip if already activated)
# OR: ..\venv\Scripts\activate          # Windows

python -m uvicorn api:app --port 8004 --reload
```

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8004
INFO:     Started reloader process
```

> **First run on a new machine:** The backend will automatically detect that the data files (`portwatch_us_data.csv`, `chokepoint_data.csv`) are missing and download them from the IMF PortWatch API. This one-time download takes **2-5 minutes** (~42MB). Subsequent startups skip this step and load instantly.

### Terminal 2 — AIS Backend (port 8001)

```bash
cd venv2/backend
source ../venv/bin/activate             # macOS / Linux
# OR: ..\venv\Scripts\activate          # Windows

python -m uvicorn AIS.ais_api:app --port 8001
```

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8001
INFO:     AIS consumer started — connecting to aisstream.io
```

> This service connects to aisstream.io via WebSocket and streams live vessel positions in US waters. It takes ~30 seconds to start receiving vessel data.

### Terminal 3 — Frontend (port 3000)

```bash
cd venv2/frontend
npm start
```

The browser should open automatically to `http://localhost:3000`.

> **Note:** If port 3000 is taken, React will prompt you to use another port (e.g., 3001). Accept with `y`.

---

## 6. Verify Everything is Running

| Service | URL | What to Check |
|---------|-----|---------------|
| Frontend | http://localhost:3000 | Dashboard loads with tabs |
| Main API | http://localhost:8004/docs | Swagger UI loads |
| Main API health | http://localhost:8004/health | Returns `{"status":"ok"}` |
| AIS API | http://localhost:8001/docs | Swagger UI loads |
| AIS API health | http://localhost:8001/health | Returns `{"status":"ok","service":"ais"}` |

### Quick health check from terminal:
```bash
curl http://localhost:8004/health
curl http://localhost:8001/health
```

---

## 7. Using the Dashboard

### Tab 1: Port Intelligence
- Select a port from the left sidebar (ranked by congestion score)
- View congestion KPIs, 7-day forecast, weather, vessel mix, and upstream chokepoint risks
- Toggle between ARIMA / Prophet / XGBoost forecast models

### Tab 2: Live Vessels
- Real-time map of AIS vessel positions in US waters (~4,000+ vessels)
- Port congestion circles (red = HIGH, amber = MEDIUM, green = LOW)
- Use the port dropdown to zoom into a specific port
- Filter vessels by type (Cargo, Tanker, Passenger, etc.) or navigational status
- Click a vessel to see its details (MMSI, speed, destination, etc.)

### Tab 3: Chokepoints
- View global chokepoint disruption scores
- Click a chokepoint for detailed transit history and vessel mix

### Tab 4: AI Advisor
- Chat with the AI advisor about port conditions, congestion causes, and recommendations
- Context from the currently selected port is automatically included

---

## Windows Quick Start (Alternative)

On Windows, you can double-click `start.bat` from the project root. It will:
1. Kill any stale process on port 8004
2. Clear Python bytecode cache
3. Start the main backend
4. Start the frontend

> **Note:** `start.bat` does not start the AIS backend. You still need to run Terminal 2 separately for live vessel tracking.

---

## Updating Port Data

The main backend serves cached CSV data. To pull the latest data from IMF PortWatch:

```bash
cd venv2/backend
source ../venv/bin/activate
python data_pull.py
```

This incrementally downloads new records since the last pull. Restart the main backend after pulling new data.

---

## Troubleshooting

### Port already in use

```bash
# macOS / Linux — find and kill process on a port
lsof -ti :8004 | xargs kill
lsof -ti :8001 | xargs kill

# Windows
netstat -aon | findstr ":8004"
taskkill /PID <pid> /F
```

### Backend starts but endpoints return errors
- Make sure `.env` exists at `venv2/backend/.env` with valid API keys
- The backend auto-downloads CSV data files on first startup — if this fails (e.g., no internet), you can manually run: `python data_pull.py`
- Check the backend terminal for "Port data pull complete" / "Chokepoint data pull complete" messages on first run

### All port congestion scores show 50 (MEDIUM)
- This means the data files haven't been downloaded yet — the backend auto-pulls them on first startup, which takes 2-5 minutes
- Wait for the backend to finish downloading, then refresh the dashboard
- If the auto-pull failed, run `python data_pull.py` manually from `venv2/backend/`

### Live Vessels tab shows 0 vessels
- Confirm the AIS backend is running on port 8001 (`curl http://localhost:8001/health`)
- Check that `AISSTREAM_API_KEY` is set in `.env`
- It takes ~30 seconds after startup for vessels to start appearing
- Check the AIS backend terminal for WebSocket connection errors

### Frontend won't start
- Make sure you ran `npm install` in `venv2/frontend/`
- If you see module errors, delete `node_modules` and reinstall:
  ```bash
  cd venv2/frontend
  rm -rf node_modules
  npm install
  ```

### Prophet installation fails
- Prophet requires a C++ compiler. On macOS: `xcode-select --install`
- On Windows: Install Visual Studio Build Tools
- Alternative: `conda install -c conda-forge prophet` if using Anaconda

---

## Project Structure (Key Files)

```
CapstoneProject/
├── README.md                           ← Full project documentation
├── GETTING_STARTED.md                  ← This file
├── start.bat                           ← Windows quick launcher
│
└── venv2/
    ├── backend/
    │   ├── .env                        ← API keys (not in git)
    │   ├── requirements.txt            ← Python dependencies
    │   ├── api.py                      ← Main FastAPI server (port 8004)
    │   ├── data_pull.py                ← Fetch data from IMF PortWatch
    │   ├── data_cleaning.py            ← Data pipeline + scoring
    │   ├── forecasting.py              ← ARIMA / Prophet / XGBoost
    │   ├── weather.py                  ← OpenWeatherMap integration
    │   ├── llm.py                      ← AI Advisor (Groq + LangChain)
    │   ├── vessel_agent.py             ← Vessel arrival risk agent
    │   ├── portwatch_us_data.csv       ← US port data
    │   ├── chokepoint_data.csv         ← Global chokepoint data
    │   └── AIS/
    │       ├── ais_api.py              ← AIS FastAPI server (port 8001)
    │       ├── ais_consumer.py         ← WebSocket consumer (aisstream.io)
    │       └── ais_store.py            ← In-memory vessel store
    │
    └── frontend/
        ├── package.json
        └── src/
            ├── App.jsx                 ← Main app + tab router
            ├── VesselMap.jsx           ← Live Vessels map (Leaflet)
            ├── hooks/useApi.js         ← API hooks
            └── components/             ← Dashboard components
```

---

## Summary of Services

| Service | Port | Command | Purpose |
|---------|------|---------|---------|
| Main Backend | 8004 | `uvicorn api:app --port 8004` | Port data, forecasting, weather, AI advisor |
| AIS Backend | 8001 | `uvicorn AIS.ais_api:app --port 8001` | Live vessel positions via aisstream.io |
| Frontend | 3000 | `npm start` | React dashboard |
