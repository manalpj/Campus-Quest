# Deployment Guide: Railway (Production)

This guide walks you through deploying **Campus Quest** to [Railway](https://railway.app) so that the game runs over HTTPS and can be accessed on mobile phones.

---

## Prerequisites

1. A [GitHub](https://github.com) account.
2. A [Railway](https://railway.app) account linked to your GitHub.
3. A mobile phone with GPS and a modern browser (Safari or Chrome).

---

## Step 1: Push Code to GitHub

Make sure your local branch has all current files committed and pushed to your GitHub repository:

```bash
git status
git add .
git commit -m "feat: prepare railway deployment"
git push origin main
```

---

## Step 2: Create a New Project on Railway

1. Open your [Railway Dashboard](https://railway.app/dashboard).
2. Click **+ New Project**.
3. Choose **Deploy from GitHub repo**.
4. Select your `campus-quest` repository.
5. Railway will automatically detect the Python environment and the `Procfile`:
   ```Procfile
   web: uvicorn main:app --host 0.0.0.0 --port $PORT
   ```

---

## Step 3: Configure Environment Variables

Go to your service in Railway, click on the **Variables** tab, and add the variables listed below.

### 🔴 Critical & Required Variables (Must be customized)

These variables **must** be set with real, secure values. If left with default placeholders, `config.py` will refuse to start in production.

| Variable | Recommended Value | Explanation |
|---|---|---|
| `ENV` | `production` | **Required.** Activates production security checks. |
| `ADMIN_USER` | `admin` (or custom name) | Admin dashboard username. Must not contain `change-me`. |
| `ADMIN_PASS` | *(Choose a strong secret password)* | Admin dashboard password. Must not contain `change-me`. |
| `SECRET_KEY` | *(Generate a 32-byte hex token)* | Cookie signing key. Generate locally with: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `FORWARDED_ALLOW_IPS` | `*` | **Required.** Instructs Uvicorn to trust Railway's reverse proxy so client IP rate limits apply per phone instead of sharing the proxy IP. |
| `DB_PATH` | `/data/quest.db` | Points to the persistent volume mounted at `/data` (see Step 4). |

### 🟢 Application & Game Settings (Defaults from `.env.example`)

You can click **Raw Editor** in the Variables tab to paste the standard settings:

```env
PORT=8000
MAX_BODY_BYTES=65536
LOGIN_ATTEMPTS_PER_MIN=5
JOIN_ATTEMPTS_PER_MIN=10

CAMPUS_NAME=IET DAVV Campus
CAMPUS_CENTER_LAT=22.6928
CAMPUS_CENTER_LNG=75.8676
CAMPUS_BOUNDS_SW_LAT=22.6850
CAMPUS_BOUNDS_SW_LNG=75.8580
CAMPUS_BOUNDS_NE_LAT=22.7010
CAMPUS_BOUNDS_NE_LNG=75.8780
CAMPUS_START_ZOOM=17
CAMPUS_MIN_ZOOM=15
CAMPUS_MAX_ZOOM=19

TILE_URL=https://tile.openstreetmap.org/{z}/{x}/{y}.png
TILE_ATTRIBUTION=&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a> contributors

PING_INTERVAL_MS=4000
POLL_INTERVAL_MS=4000

MIN_CHECKPOINTS=5
MIN_MEMBERS=2
COUNTDOWN_S=10
ACCURACY_LIMIT_M=30
STREAK_REQUIRED=2
MAX_SPEED_MPS=12.0

HINT_PENALTY_S=180
RADAR_DURATION_S=60
BOOST_DURATION_S=120
BOOST_EXTRA_RADIUS_M=20
SKIP_WAIT_S=600
SKIP_PENALTY_S=600

ORGANIZER_NAME=GDGoC DAVV Organizing Team
ORGANIZER_CONTACT=gdgoc@davv.ac.in
ALLOW_TEST_MODE=false
```

---

## Step 4: Attach a Persistent Volume for SQLite

Railway containers have ephemeral disk storage; every new deployment replaces the container filesystem. To prevent the database from being wiped on redeploy:

1. In your Railway project canvas, click **+ New** (or right-click the canvas) and select **Volume**.
2. Connect the volume to your `campus-quest` service.
3. Set the **Mount Path** to `/data`.
4. Ensure your environment variable `DB_PATH` is set to `/data/quest.db` (as configured in Step 3).

---

## Step 5: Generate a Public Domain & Redeploy

1. In your service settings, navigate to **Settings** → **Networking**.
2. Click **Generate Domain**. Railway will assign a public domain, such as `https://campus-quest-production.up.railway.app`.
3. Go to the **Deployments** tab and click **Redeploy** to ensure all volume mounts and variables are active.
4. Verify the deployment logs show:
   - Application startup complete.
   - Uvicorn running on `0.0.0.0:<PORT>`.

---

## Step 6: Test on a Mobile Phone

1. Open your generated Railway URL (`https://...up.railway.app`) in your phone browser (Chrome or Safari).
2. When prompted: **Allow location access**.
3. Confirm that:
   - The map loads centered on IET DAVV campus.
   - A blue location marker appears with an accuracy circle showing your live position.
   - The top status bar displays a live GPS accuracy reading (e.g., `GPS ±12m`).
   - The lock button, leaderboard button, and power-up action buttons are responsive.

---

## Troubleshooting

### 1. Build Fails during Deployment
- **Symptom:** Railway deployment fails during the build step.
- **Cause:** Missing Python package or incompatible syntax.
- **Fix:** Check the **Build Logs** in Railway. Ensure all dependencies are listed in `requirements.txt` (`fastapi`, `uvicorn[standard]`, `python-dotenv`).

### 2. 502 Bad Gateway / Application Crashed on Startup
- **Symptom:** Railway displays `502 Bad Gateway` when opening the URL.
- **Cause:** Insecure secrets in `ENV=production`. `config.py` validates `ADMIN_PASS` and `SECRET_KEY` on startup and raises `RuntimeError` if either contains `change-me`.
- **Fix:** Check the **Deploy Logs** in Railway. Ensure `ADMIN_USER`, `ADMIN_PASS`, and `SECRET_KEY` have been replaced with secure values in the **Variables** tab.

### 3. Database is Wiped After Redeploy
- **Symptom:** Team progress or checkpoints disappear after redeploying code.
- **Cause:** Database file was written to the ephemeral container disk rather than the persistent volume.
- **Fix:** Verify that a Railway Volume is mounted at `/data` and that `DB_PATH` is explicitly set to `/data/quest.db`.

### 4. Location Access Blocked on Phone
- **Symptom:** GPS status says "Location permission denied" or location prompt does not appear.
- **Cause:** The browser Geolocation API requires a secure context (HTTPS). Accessing via plain `http://` or an unencrypted IP blocks geolocation.
- **Fix:** Always access the app via the Railway-issued `https://` domain. If previously blocked, tap the lock/settings icon next to the address bar in your mobile browser to re-enable location permission for the site.
