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

## Task 4: SQLite schema, connection handling and seed script

### 5-Line Interview Summary
- Implemented `db.py` to isolate all SQLite schema DDL and connection management away from API routes and game rules.
- Created the core relational tables (`settings`, `checkpoints`, `teams`, `progress`, `hint_uses`, `events`) and seeded initial game settings with `INSERT OR IGNORE`.
- Configured production PRAGMAs (`WAL` journal mode, 5-second `busy_timeout`, and `foreign_keys=ON`) with a per-request FastAPI dependency.
- Engineered a `write_tx()` context manager using `BEGIN IMMEDIATE` and autocommit mode (`isolation_level=None`) to prevent check-then-insert race conditions.
- Built a guarded `seed.py` CLI script creating 6 realistic DAVV campus checkpoints for local development while strictly refusing to execute when `ENV=production`.

### Interview Questions & Answers
**Q1: Why do we use `BEGIN IMMEDIATE` inside `write_tx()` instead of SQLite's default transaction behavior?**  
**A1:** Python's default SQLite transactions are deferred, starting with a shared read lock and only attempting to upgrade to a write lock on the first write statement. When multiple clients concurrently read then write (e.g. check-then-insert), both hold read locks and deadlock trying to upgrade simultaneously. `BEGIN IMMEDIATE` acquires SQLite's write lock upfront, queuing concurrent writers gracefully up to `busy_timeout` (5000 ms) and guaranteeing atomic check-then-write transactions.

**Q2: Why must `PRAGMA foreign_keys = ON` be executed explicitly on every newly opened connection?**  
**A2:** In SQLite, foreign key constraint enforcement is disabled by default for backwards compatibility and is a per-connection runtime setting rather than a persistent schema property. Executing `PRAGMA foreign_keys = ON` on every connection ensures relational constraints (such as preventing progress entries for non-existent teams) are strictly validated on every insert and delete.

## Task 5: Admin login at /gods

### 5-Line Interview Summary
- Built constant-time credential verification in `auth.py` with `hmac.compare_digest` to prevent timing attacks against organizer logins.
- Implemented tamper-resistant session management via HMAC-SHA256 signed `quest_admin` cookies containing an 8-hour expiry timestamp and username.
- Created an in-memory sliding-window rate limiter in `ratelimit.py` to throttle brute-force login attempts per client IP after `LOGIN_ATTEMPTS_PER_MIN`.
- Protected administrative endpoints (`/api/gods/me`, `/api/gods/logout`) with a reusable `require_admin` dependency and verified all future `/api/gods/` routes require it.
- Developed the unlinked `/gods` admin interface with vanilla JS and design tokens, serving a login form that transitions into an empty authenticated admin shell.

### Interview Questions & Answers
**Q1: Why do we compare credentials using `hmac.compare_digest` instead of standard `==` string equality?**  
**A1:** Standard string comparison (`==`) evaluates characters sequentially and short-circuits at the first mismatch, leaking timing variations that allow attackers to deduce characters one by one. `hmac.compare_digest` executes in constant time regardless of where differences occur, eliminating side-channel timing attacks.

**Q2: Why use a signed, HttpOnly cookie with an explicit expiry timestamp rather than storing session tokens in localStorage?**  
**A2:** `HttpOnly` cookies cannot be accessed or stolen by client-side JavaScript, protecting against XSS attacks, while `SameSite=Strict` blocks CSRF. Embedding an HMAC-SHA256 signature and timestamp directly in the cookie provides stateless verification against the server clock without trusting client state or requiring a database lookup on every admin request.

## Task 6: Admin checkpoint management on a map

### 5-Line Interview Summary
- Added interactive Leaflet map checkpoint management to `/gods` behind `require_admin`, enabling organizers to visually add, edit, move, reorder, and delete route checkpoints.
- Created `game.py` for pure domain logic (coordinate bounds verification and route sequence positioning) isolated from HTTP routes and SQL queries.
- Implemented parameterised CRUD operations in `db.py` under `BEGIN IMMEDIATE` transactions to prevent race conditions and safely compact or shift route positions without duplicate gaps.
- Enforced strict server-side Pydantic validation across coordinates, campus bounds, radius ranges (25–100 m), and string lengths (clue/hint/story max 300, name max 60).
- Delivered a responsive, mobile-first admin interface with real-time radius circles, draggable pins, a "x of N needed" counter, and comprehensive unit tests covering validation and reordering.

### Interview Questions & Answers
**Q1: Why did you implement position shifting and gap compaction inside `BEGIN IMMEDIATE` in `db.py` instead of letting the client send updated positions for every checkpoint?**  
**A1:** Relying on the client to calculate and update every checkpoint's position introduces race conditions and risks duplicate or fragmented positions if two admins edit simultaneously or if a network request fails halfway through. By executing the shift or compaction inside a single atomic `BEGIN IMMEDIATE` transaction on the server, we guarantee that the route sequence remains dense, contiguous (1..N), and free of collisions regardless of concurrent actions or client state.

**Q2: Why do we validate coordinates against campus bounding boxes on the server using Pydantic when the Leaflet map already restricts clicks to campus bounds?**  
**A2:** Client-side UI constraints are purely advisory for user experience and can be easily bypassed by direct API calls, DevTools, or forged HTTP requests. Enforcing campus bounding box validation on the server via Pydantic model validators guarantees that invalid, out-of-bounds coordinates can never be persisted in SQLite, ensuring the game boundary rule is non-negotiable.

## Task 7: Team registration with one device per team, and the lobby

### 5-Line Interview Summary
- Built `POST /api/register` to create teams with unique 8-character codes (e.g. `PHX-4821`) using Python's `secrets` module with collision retries under `write_tx`.
- Bound one device per team by issuing a high-entropy device token stored strictly as a SHA-256 hash in SQLite and set as an HttpOnly `quest_device` cookie.
- Implemented `POST /api/join` protected by per-IP rate limiting, rejecting duplicate joins with HTTP 409 ("This team is already playing on another device").
- Created `GET /api/state` protected by constant-time token verification to seamlessly restore team lobby state upon page reload without relying on localStorage.
- Built a mobile-first player interface featuring clean tabbed registration, dynamic member inputs, and an outdoors-readable waiting lobby with quick quest rules.

### Interview Questions & Answers
**Q1: Why do we store only the SHA-256 hash of the device token in the database rather than the plaintext token itself?**  
**A1:** Storing only cryptographic hashes follows defense-in-depth principles. If the SQLite database file or a backup is ever compromised, attackers cannot forge device tokens or hijack playing teams because SHA-256 is an irreversible one-way function. The server only validates incoming tokens by hashing them and using `hmac.compare_digest` against the database record.

**Q2: Why does the client restore its session using the HttpOnly `quest_device` cookie and `GET /api/state` instead of keeping team state in browser `localStorage`?**  
**A2:** Browser `localStorage` can be viewed and modified by client scripts or lost if browser storage is cleared, creating synchronization and trust issues. Keeping all authoritative state on the server and authenticating strictly via an HttpOnly cookie prevents client-side tampering, keeps sensitive tokens invisible to JavaScript, and ensures a seamless resume on page reload.

## Task 8: Pure geofence logic with tests

### 5-Line Interview Summary
- Implemented hand-crafted `haversine_m` in `game.py` using Python's standard `math` module and $R = 6,371,000\text{ m}$ to compute spherical ground distances without external libraries.
- Added numeric safety clamping ($a \in [0.0, 1.0]$) to protect against floating-point roundoff errors during `asin` and `sqrt` calculations for identical or antipodal points.
- Built clean domain rule functions (`is_inside`, `accuracy_ok`, `next_streak`, `should_unlock`) containing zero SQL and zero HTTP dependencies.
- Enforced geofence boundary rules where exact radius matches count as inside, while GPS accuracy limits reject noisy readings that exceed the threshold.
- Authored a comprehensive unit test suite in `tests/test_game.py` verifying known geographic coordinates, longitude meridian convergence, boundary edges, and streak reset mechanics.

### Interview Questions & Answers
**Q1: Why did you write your own Haversine calculation with the `math` module instead of using an existing library like `geopy`?**  
**A1:** Writing Haversine by hand avoids introducing third-party dependencies for a single formula, keeps our deployment footprint lean, and allows us to explain every line in an interview. Haversine with a mean spherical radius of 6,371,000 metres provides sub-metre accuracy across campus-scale distances, which is ideal for verifying 25–40 metre geofence radii.

**Q2: Why do we require a consecutive streak of 2 inside fixes rather than unlocking immediately on the first fix inside the radius?**  
**A2:** Mobile phone GPS chips frequently experience transient multipath signal reflections and momentary drift, particularly when near large campus buildings or trees. Requiring two consecutive valid fixes inside the geofence radius filters out single-frame jumps, ensuring the player has genuinely walked into and remained at the physical location before triggering an unlock.

## Task 9: Game control (registration, Start, End) and the locking rule

### 5-Line Interview Summary
- Built administrative lifecycle control endpoints (`POST /api/gods/registration/{open,close}` and `POST /api/gods/game/{start,end}`) guarded by `require_admin` with operational audit logging in SQLite.
- Refused game start unless at least `MIN_CHECKPOINTS` checkpoints exist, setting `started_at = server_time + COUNTDOWN_S` (default 10 s) so all connected devices share a synchronized launch countdown.
- Enforced checkpoint locking rules after game start: PUT rejects modifications to coordinates, radius, and route position (HTTP 400) while permitting clue, hint, and story edits; DELETE and POST are strictly rejected.
- Extended `GET /api/state` to return `server_now_ms`, `started_at_ms`, and `game_state`, enabling client phones to compute a one-time server clock offset and run accurate countdowns without trusting local phone clocks.
- Added a responsive "Game" tab in `/gods` with state badges, registration toggle, checkpoint readiness counters, and confirmation-guarded End button, alongside player UI lobby-to-game transitions.

### Interview Questions & Answers
**Q1: Why does `GET /api/state` return `server_now_ms` and how does the client calculate the countdown without trusting the phone's clock?**  
**A1:** Mobile phone clocks are frequently desynchronized due to manual adjustments, battery-saver drift, or network discrepancies. When the client receives `/api/state`, it calculates a clock offset once (`server_offset = server_now_ms - Date.now()`). For all subsequent countdown ticks, it computes estimated server time as `Date.now() + server_offset`. This guarantees that every phone counts down to `started_at_ms` in lockstep regardless of local device clock skew.

**Q2: Why do we enforce the checkpoint locking rule once the game is running, while still allowing clue, hint, and story text edits?**  
**A2:** Changing coordinates, radii, positions, or deleting checkpoints during a live game would corrupt players' route order, create race conditions with active geofence evaluations, and create unfair advantages. However, organizers may notice a typo or want to clarify confusing clue or hint wording while teams are hunting. Allowing text updates while locking physical coordinates and sequence order protects game integrity without locking out organizers from clarifying clues.

## Task 10: Location ping, accuracy gating, streak progression and unlock

### 5-Line Interview Summary
- Implemented `POST /api/ping` validating coordinates and accuracy via Pydantic, guarded by `require_team_device` cookie authentication.
- Rejected pings with HTTP 409 if the game is not running or the launch countdown has not elapsed, ensuring nobody unlocks checkpoints prematurely.
- Gated position fixes against `ACCURACY_LIMIT_M` (30 m), returning `status: weak_gps` without modifying streaks to prevent inaccurate drift from falsifying player location.
- Tracked consecutive `inside_streak` using Haversine distance and required 2 consecutive inside fixes before atomically writing to `progress` under `write_tx(BEGIN IMMEDIATE)`.
- Strictly withheld physical coordinates, radii, and distance numbers in all responses, returning only progress counts, unlocked story text, and the subsequent clue.

### Interview Questions & Answers
**Q1: Why do we ignore fixes with accuracy worse than 30 metres instead of using them or penalizing the team?**  
**A1:** Checkpoint geofence radii are typically 25 to 40 metres wide. A GPS reading with an estimated accuracy circle of 50+ metres has an error margin wider than the target zone itself, making it impossible to reliably know if the player is actually within the perimeter. Ignoring noisy fixes protects the team from having an active streak reset by momentary satellite multipath error while simultaneously preventing accidental false unlocks from outside the zone.

**Q2: How does the server prevent two simultaneous pings from creating duplicate unlock records or skipping a checkpoint?**  
**A2:** The unlock operation runs inside `write_tx()` using SQLite's `BEGIN IMMEDIATE`, which acquires the exclusive database write lock upfront. Inside the transaction, it checks whether a row already exists in `progress` for `(team_id, checkpoint_id)` before inserting, backed by SQLite's compound primary key constraint. Any concurrent ping is queued by `busy_timeout` and either encounters the existing row or sees an updated streak, guaranteeing that exactly one progress entry is recorded and sequence integrity is preserved.

---

## Task 11: Player game screen: send pings, show clues, show unlocks

### 5-Line Interview Summary
- Delivered the active mobile game HUD including the status bar (cleared count, server-offset elapsed timer, GPS accuracy chip), docked clue card, and tab bar for Map and Team views.
- Wired `navigator.geolocation.watchPosition` to periodically transmit fixes newer than the last sent ping every `PING_INTERVAL_MS` to `/api/ping` while polling `/api/state` every `POLL_INTERVAL_MS`.
- Built the interactive unlock modal popup that celebrates when a checkpoint is cleared, displaying its name, history story, and a continue button to reveal the next clue.
- Rendered cleared checkpoints on the Leaflet map as green tick markers with popups, while populating a full route history drawer accessible from the top-left navigation menu.
- Enforced strict geofence secrecy in `GET /api/state`, ensuring uncleared checkpoint coordinates and radii are never transmitted to player clients, verified by automated tests.

### Interview Questions & Answers
**Q1: Why do we only send a GPS ping if its timestamp is newer than the last sent fix instead of firing on every timer tick?**  
**A1:** Mobile browsers sometimes report cached or unchanged coordinates if satellite visibility drops or the device is stationary. Sending stale fixes wastes client battery and server bandwidth without providing new spatial information. Verifying `fix.ts > lastSentFixTs` guarantees that the server only evaluates fresh movement readings, preventing duplicate evaluations of identical stationary fixes.

**Q2: Why must `GET /api/state` strictly omit the coordinates and radius of the next target checkpoint?**  
**A2:** Client-side web state cannot be trusted. If the backend returned target coordinates or geofence radii in API payloads, any player opening the browser DevTools network tab could instantly plot the exact physical coordinates on a map, defeating the clue-solving purpose of the hunt. The server validates geofencing internally and only reveals a checkpoint's coordinates and story after it has already been legitimately unlocked.

---

## Task 12: Ranking and live leaderboard

### 5-Line Interview Summary
- Added pure functions `adjusted_time()` and `rank_teams()` in `game.py`, sorting strictly by cleared checkpoints (desc), adjusted time (asc), and earlier last unlock timestamp (asc).
- Handled zero-clear teams gracefully so they remain at the bottom of the table without breaking timestamp comparisons or numeric sorts.
- Delivered `GET /api/leaderboard` cached in memory with a 1-second TTL to shield SQLite from concurrent poll storms across dozens of competing devices.
- Invalidated the leaderboard cache immediately on every successful checkpoint unlock so standings update live with zero perceived lag.
- Built the player Leaderboard tab with own-team highlighting and an automatic Finish screen displaying final rank and verified adjusted time when completing the last checkpoint.

### Interview Questions & Answers
**Q1: Why do we cache `/api/leaderboard` in memory for 1 second and clear it on unlock instead of querying SQLite on every request?**  
**A1:** With 70+ teams polling every few seconds, high concurrency would hammer SQLite with dozens of redundant table aggregations per second on a single-worker server. An in-memory cache with a 1-second TTL collapses these spikes down to at most one calculation per second. Clearing the cache inside `unlock_checkpoint` ensures that whenever actual game state changes, the very next request reflects the new standing instantly without waiting for TTL expiration.

**Q2: Why is adjusted time the only currency for rankings rather than combining points and speed?**  
**A2:** Mixed point and time formulas often produce unintuitive edge cases where a team that had a slow, messy run beats a team that solved clues quickly and cleanly just by hoarding side points. By translating all actions into time adjustments (`elapsed at last unlock + penalties − bonuses`), the best physical run wins, and trade-offs (like a +3 min hint penalty) have a concrete, unambiguous impact on the leaderboard.

---

## Task 13: Power-ups (Hint, Radar, Radius boost) and ranking rules

### 5-Line Interview Summary
- Built `POST /api/powerup/{hint,radar,boost}` guarded by `require_team_device` cookie authentication and running state validation under `write_tx(BEGIN IMMEDIATE)`.
- Implemented Hint power-up with a +3 minute penalty recorded in `hint_uses` (`UNIQUE(team_id, checkpoint_id)`), ensuring hints can only be charged once per checkpoint.
- Added inventory consumption and time windows for Radar (60s live distance feedback in `/api/ping`) and Radius Boost (+20m geofence expansion in `/api/ping`).
- Implemented the alternating earning rule: GPS unlocks award exactly one power-up, alternating Radar on odd-numbered clears and Radius Boost on even-numbered clears.
- Created mobile-first player UI with a docked power-up tray, confirmation modal for hint time penalties, HUD tags for active Radar/Boost timers, and real-time toast feedback.

### Interview Questions & Answers
**Q1: How do we prevent players from finding checkpoint coordinates when Radar is active?**  
**A1:** Even with Radar active, the server never returns checkpoint coordinates or geofence radii in API responses. It calculates the Haversine distance on the server and returns only the scalar distance in metres (e.g. 142 m) or "You're very close!" when within 30 metres. Once the 60-second window expires on the server clock, `/api/ping` immediately stops including any distance metric, preserving the security rule that target coordinates are never leaked.

**Q2: Why does using a hint add time to `penalty_s` rather than deducting a point score, and why is `hint_uses` protected by a unique constraint?**  
**A2:** Campus Quest uses time as its single currency (`adjusted_time = elapsed_at_last_unlock + penalties - bonuses`), so taking a hint directly costs +3 minutes (180 s) on the team's leaderboard time. The `UNIQUE(team_id, checkpoint_id)` constraint in `hint_uses` and atomic check in `write_tx` guarantee idempotency: if a team re-requests or reloads the page, they receive the hint text without ever being charged a second penalty for the same checkpoint.
