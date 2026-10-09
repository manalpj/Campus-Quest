# Notes

## Task 1: Project scaffold, configuration and health check

### 5-Line Interview Summary
- Set up a lightweight FastAPI application that reads and validates all operational configuration from environment variables via python-dotenv.
- Created `/healthz` for deployment liveness probes and `/api/config` to safely publish map coordinates and polling intervals without leaking server secrets.
- Mounted safe static file serving from `static/` with mobile-first CSS following a strict design token system and zero build steps.
- Implemented production validation in `config.py` that fails fast if critical secrets still contain default placeholders.
- Added automated pytest tests covering endpoint contracts, static routing, secret sanitization, and path traversal prevention.

### Interview Questions & Answers
**Q1: Why did you separate public configuration into `/api/config` rather than embedding it directly into the HTML or JavaScript files?**  
**A1:** Hardcoding coordinates, tile URLs, or zoom bounds into client files couples the frontend to a single deployment. Fetching from `/api/config` allows the client to adapt dynamically to environment variables (like changing campus bounds or map tiles) while ensuring server secrets (like `ADMIN_PASS` and `SECRET_KEY`) are filtered out and never exposed to players.

**Q2: Why use plain `def` for FastAPI endpoints instead of `async def`?**  
**A2:** Plain `def` handlers in FastAPI run inside a worker thread pool rather than directly on the main asynchronous event loop. Because SQLite calls in Python's standard library are synchronous and block during disk I/O, using `async def` would freeze the entire event loop for every client. Plain `def` offloads blocking operations to threads, keeping the server responsive.

## Task 2: Campus map with a live location dot

### 5-Line Interview Summary
- Integrated Leaflet 1.9.4 via CDN to render an interactive map centered dynamically on DAVV campus using `/api/config`.
- Locked map panning and tile requests strictly within campus bounds using Leaflet's `maxBounds` and `maxBoundsViscosity` along with `minZoom` and `maxZoom`.
- Connected the browser's `navigator.geolocation.watchPosition` to track the user's location with high accuracy without sending coordinates to the server.
- Represented user presence on the map using a distinct blue dot marker (`L.circleMarker`) and an accuracy circle (`L.circle`) that update seamlessly on every GPS fix.
- Built a mobile-first full-screen interface featuring a live one-line GPS status chip and circular accessible action buttons (navigation menu, leaderboard, power-up inventory).

### Interview Questions & Answers
**Q1: Why do you configure `maxBounds` and zoom constraints on Leaflet instead of letting the user pan freely anywhere?**  
**A1:** Restricting bounds and zoom keeps tile requests strictly within the campus perimeter, respecting OpenStreetMap's usage policy against bulk downloading unnecessary tiles and keeping players focused on the playable game area.

**Q2: Why is the phone's live location dot handled strictly client-side without sending location pings to the server in this task?**  
**A2:** Pure client-side tracking gives players instant, smooth visual feedback with zero latency or network traffic. Separating client display from server game checks prevents unnecessary battery drain and server load until formal verification rules (like checkpoint detection) are needed.

## Task 3: Railway deployment configuration and deploy guide

### 5-Line Interview Summary
- Added a root `Procfile` instructing Railway to launch Uvicorn bound to all interfaces (`0.0.0.0`) on the dynamically assigned `$PORT`.
- Hardened environment variable parsing in `config.py` to trim whitespace and cleanly resolve production `PORT`, `ENV`, and `DB_PATH`.
- Verified why `FORWARDED_ALLOW_IPS=*` is mandatory on Railway so reverse proxy headers propagate real player client IPs for per-device rate limiting.
- Documented a step-by-step production deployment manual in `docs/DEPLOY.md` covering persistent volume mounting at `/data` and HTTPS mobile access.
- Added comprehensive unit tests in `tests/test_deploy.py` validating the deployment contract and production environment parsing.

### Interview Questions & Answers
**Q1: Why do we need a Railway Volume mounted at `/data` instead of using the default local `data/quest.db` path?**  
**A1:** Cloud container platforms like Railway use ephemeral container filesystems that are wiped and recreated on every deployment or restart. Mounting a persistent volume at `/data` and pointing `DB_PATH` to `/data/quest.db` ensures that SQLite database transactions, team registrations, and game progress persist safely across container restarts.

**Q2: What happens if `FORWARDED_ALLOW_IPS=*` is omitted on Railway when rate limits are active?**  
**A2:** Railway routes traffic through internal reverse proxy load balancers. Without trusting forwarded proxy headers, Uvicorn reports Railway's proxy IP as the client address for every request. Any per-IP rate limiter (such as brute-force protection on `/api/join` or `/gods`) would group all players into a single IP bucket, prematurely throttling the entire campus event.