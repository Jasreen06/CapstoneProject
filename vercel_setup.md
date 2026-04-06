# Vercel Deployment Guide — DockWise AI v2

## Overview

The DockWise AI v2 project uses a **split deployment**:
- **Frontend (React)** → Vercel (free tier)
- **Backend (FastAPI)** → Railway or Render (free tier)

Vercel is ideal for the React frontend because it offers instant deploys from GitHub, automatic preview deployments on PRs, and a generous free tier. However, Vercel's serverless functions have a 10-second timeout (free tier) and don't support persistent WebSocket connections, so the FastAPI backend must be hosted elsewhere.

---

## Step 1: Prepare the Frontend for Vercel

### 1.1 Project Structure

Vercel needs to know which directory contains the frontend. Since our repo has both `backend/` and `frontend/`, we'll tell Vercel to use the `frontend/` directory.

### 1.2 Create `frontend/vercel.json`

This file tells Vercel how to handle client-side routing (React Router):

```json
{
  "rewrites": [
    { "source": "/(.*)", "destination": "/" }
  ]
}
```

### 1.3 Create `frontend/.env.production`

This sets the backend API URL for production builds:

```env
VITE_API_BASE_URL=https://your-backend-url.railway.app
```

**Note:** Replace with your actual Railway/Render backend URL once deployed. During development, `frontend/.env.development` should have:

```env
VITE_API_BASE_URL=http://localhost:8004
```

### 1.4 API Client Configuration

In `frontend/src/api/client.js`, use the environment variable:

```javascript
const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8004';

export async function fetchJSON(endpoint) {
  const res = await fetch(`${API_BASE}${endpoint}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export function createSSE(endpoint) {
  return new EventSource(`${API_BASE}${endpoint}`);
}
```

### 1.5 Vite Config

`frontend/vite.config.js`:

```javascript
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // Dev proxy to avoid CORS during local development
      '/api': {
        target: 'http://localhost:8004',
        changeOrigin: true,
      },
    },
  },
});
```

---

## Step 2: Connect GitHub to Vercel

You've already connected your GitHub account. Now:

### 2.1 Import the Repository

1. Go to [vercel.com/new](https://vercel.com/new)
2. You should see `CapstoneProject_Pramod` (or `CapstoneProject`) in your GitHub repos
3. Click **Import**

### 2.2 Configure the Project

On the configuration screen:

| Setting | Value |
|---------|-------|
| **Framework Preset** | Vite |
| **Root Directory** | `frontend` ← IMPORTANT: click "Edit" and type `frontend` |
| **Build Command** | `npm run build` (default) |
| **Output Directory** | `dist` (default for Vite) |
| **Install Command** | `npm install` (default) |

### 2.3 Environment Variables

Click "Environment Variables" and add:

| Key | Value | Environment |
|-----|-------|-------------|
| `VITE_API_BASE_URL` | `https://your-backend.railway.app` | Production |
| `VITE_MAPBOX_TOKEN` | `your_mapbox_token` | Production |

**Note:** `VITE_` prefix is required — Vite only exposes env vars starting with `VITE_` to the client bundle.

### 2.4 Deploy

Click **Deploy**. Vercel will:
1. Clone the repo
2. `cd frontend`
3. Run `npm install`
4. Run `npm run build`
5. Deploy the `dist/` folder to their CDN

You'll get a URL like `https://capstone-project-pramod.vercel.app`

---

## Step 3: Automatic Deployments

Once connected, Vercel automatically deploys:

- **Push to `main`** → Production deployment
- **Push to any branch** → Preview deployment (unique URL per branch)
- **Pull Request** → Preview deployment with a comment on the PR

Since we're working on the `v2-live-ais` branch:
- Every push to `v2-live-ais` creates a preview at a URL like `capstone-project-git-v2-live-ais-pramod.vercel.app`
- When we merge to `main`, it auto-deploys to production

---

## Step 4: Deploy the Backend (Railway)

The backend can't run on Vercel because it needs:
- Persistent WebSocket connection to aisstream.io
- Long-running background tasks (AIS consumer)
- In-memory state (vessel store)

### Option A: Railway (Recommended)

1. Go to [railway.app](https://railway.app) and sign in with GitHub
2. Click "New Project" → "Deploy from GitHub Repo"
3. Select `CapstoneProject` repo
4. Configure:
   - **Root Directory:** `backend`
   - **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Add environment variables in Railway dashboard:
   - `AISSTREAM_API_KEY`
   - `WEATHER_API_KEY`
   - `GROQ_API_KEY`
   - `FRONTEND_URL` = your Vercel URL (for CORS)
6. Railway gives you a URL like `https://dockwise-backend.up.railway.app`

### Option B: Render

1. Go to [render.com](https://render.com) and sign in with GitHub
2. New → Web Service → Connect repo
3. Configure:
   - **Root Directory:** `backend`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Add environment variables
5. Free tier has cold starts (spins down after 15 min of inactivity)

### Option C: Google Cloud Run (if you want to stay on GCP)

```bash
# From backend/ directory
gcloud run deploy dockwise-backend \
  --source . \
  --region us-east1 \
  --allow-unauthenticated \
  --set-env-vars "AISSTREAM_API_KEY=...,WEATHER_API_KEY=...,GROQ_API_KEY=..."
```

---

## Step 5: Connect Frontend to Backend

After deploying the backend:

1. Copy the backend URL (e.g., `https://dockwise-backend.up.railway.app`)
2. In Vercel dashboard → Project Settings → Environment Variables
3. Update `VITE_API_BASE_URL` to the backend URL
4. Redeploy (Vercel dashboard → Deployments → redeploy latest)

### Backend CORS Configuration

In `backend/main.py`, allow the Vercel frontend origin:

```python
from fastapi.middleware.cors import CORSMiddleware

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        FRONTEND_URL,
        "http://localhost:5173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## Step 6: Custom Domain (Optional)

If you want a cleaner URL:

1. Vercel dashboard → Project → Settings → Domains
2. Add a custom domain or use Vercel's subdomain
3. Vercel handles SSL automatically

---

## Deployment Checklist

- [ ] Frontend `vercel.json` exists with SPA rewrites
- [ ] `VITE_API_BASE_URL` environment variable set in Vercel
- [ ] Backend deployed to Railway/Render with all API keys
- [ ] Backend CORS allows the Vercel frontend URL
- [ ] `frontend/` set as Root Directory in Vercel project settings
- [ ] Framework preset set to "Vite" in Vercel
- [ ] `.env` files are in `.gitignore` (never committed)
- [ ] Health check endpoint (`/health`) returns 200 on backend
- [ ] SSE endpoint works through Railway/Render (test with `curl`)

---

## Troubleshooting

### "404 on page refresh"
→ Missing `vercel.json` with rewrites. React Router routes need the catch-all rewrite.

### "CORS error in browser console"
→ Backend CORS `allow_origins` doesn't include the Vercel URL. Update `FRONTEND_URL` env var on backend.

### "API calls fail in production but work locally"
→ `VITE_API_BASE_URL` not set or wrong. Check Vercel env vars. Remember: env vars need `VITE_` prefix.

### "Build fails on Vercel"
→ Check Root Directory is set to `frontend`. Check build logs for missing dependencies.

### "Backend WebSocket disconnects"
→ Railway/Render may have idle timeouts. Add a keepalive ping in the aisstream consumer. Railway's free tier has no idle timeout; Render's free tier spins down after 15 min.

### "Vessel data not updating"
→ Check backend logs for aisstream connection errors. Verify API key is valid. Check that the background task started (look for startup log message).

---

## Cost Summary (Free Tier)

| Service | Free Tier Limits | Our Usage |
|---------|-----------------|-----------|
| **Vercel** | 100 GB bandwidth, 100k serverless invocations | Frontend only, well within limits |
| **Railway** | $5/month credit, 500 execution hours | Backend should fit if not running 24/7 |
| **Render** | 750 hours/month, spins down after 15 min idle | Works but cold starts are annoying |
| **aisstream.io** | Free, no stated limits | ~300 msg/sec at global scale |
| **OpenWeatherMap** | 1,000 calls/day (free) | Sufficient with caching |
| **Groq** | Free tier: 30 req/min, 6000 tokens/min | Sufficient for demo |
| **Mapbox** | 50,000 map loads/month | Sufficient for capstone |