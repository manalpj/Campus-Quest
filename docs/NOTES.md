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

---

## Task 14: Admin team management and stuck-team recovery (/gods)

### 5-Line Interview Summary
- Added the "Teams" management dashboard to `/gods` behind `require_admin`, enabling organizers to inspect registered teams, members, device bindings, and progress in real time.
- Implemented `POST /api/gods/teams/{id}/release-device` to clear `device_hash` under `write_tx(BEGIN IMMEDIATE)`, letting teams re-pair when a phone dies or gets lost.
- Built `POST /api/gods/teams/{id}/force-clear` with required audit reasons to advance stuck teams without awarding power-ups, immediately invalidating the cached leaderboard.
- Created `POST /api/gods/teams/{id}/adjust-time` and `DELETE /api/gods/teams/{id}` for organizer penalties, credits, or test team removals, logging all operational actions to `events`.
- Delivered responsive mobile-first UI with status chips, relative last-seen timers, confirmation dialogs, accessible action modals, and automated tests for all endpoints.

### Interview Questions & Answers
**Q1: Why does admin force-clearing a checkpoint record `how = 'admin'` and award no power-ups, unlike a normal GPS unlock?**  
**A1:** Campus Quest tracks integrity in the `progress` table: recording `how = 'admin'` maintains transparency for the final results. When an organizer force-clears a checkpoint (for example due to GPS hardware failure or an inaccessible zone), it unstucks the team, but granting power-ups (Radar or Radius Boost) would give an unearned competitive advantage over teams that reached the physical coordinates.

**Q2: What happens when an organizer clicks "Release device", and how does that prevent device hijacking?**  
**A2:** Releasing a device executes `UPDATE teams SET device_hash = NULL` inside an atomic `BEGIN IMMEDIATE` transaction and logs the organizer's action. The existing phone's cookie token immediately fails verification on its next request because its hash no longer matches SQLite. The team can then enter their secret team code (`/api/join`) on a replacement phone, which binds a newly generated token, ensuring exactly one active device per team at all times.

---

## Task 14: Event logging (the events table and log_event helper)

### 5-Line Interview Summary
- Implemented `db.log_event(conn, team_id, type, detail)` storing high-resolution server timestamps and allowing `NULL` for `team_id`.
- Defined nine canonical event constants in `game.py` covering registrations, device bindings, unlocks, power-ups, game lifecycle, and admin logins.
- Architected `log_event` to execute safely both inside existing `write_tx` transactions (atomic with progress unlocks) and as standalone writes.
- Secured sensitive credentials by logging only client IP and result on failed admin logins, never recording passwords, usernames, tokens, or cookies.
- Added `GET /api/gods/events` protected by `require_admin` to serve the latest audit events in reverse chronological order with bounded pagination.

### Interview Questions & Answers
**Q1: Why does `log_event` check `conn.in_transaction` before executing, rather than always wrapping its query in `with write_tx(conn):`?**  
**A1:** In SQLite with autocommit (`isolation_level=None`), attempting `BEGIN IMMEDIATE` while already in an open transaction raises `sqlite3.OperationalError: cannot start a transaction within a transaction`. Checking `conn.in_transaction` allows `log_event` to participate in the caller's existing write transaction (such as checkpoint unlock or team creation) atomically, while still safely acquiring its own write transaction when called independently.

**Q2: Why do failed admin logins log only the client IP and result, rather than including the attempted username?**  
**A2:** Users frequently mistype and accidentally enter their password into the username input field. Logging attempted usernames on failed logins is a known vulnerability that exposes actual passwords in audit logs. Recording only the client IP and failure status provides the necessary security telemetry for intrusion detection without risking credential leakage.

---

## Task 15: Radius boost power-up

### 5-Line Interview Summary
- Replaced the fixed metre addition with a proportional 30% expansion (`BOOST_PERCENT = 0.30`) in `compute_effective_radius`, dynamically scaling to each checkpoint's configured radius.
- Scaled geofence unlocks proportionally across varying route locations (e.g. a 25m spot expands by +7.5m to 32.5m, while a 60m plaza expands by +18m to 78m).
- Enforced server-side power-up validation in `POST /api/powerup/boost` under `write_tx(BEGIN IMMEDIATE)`, rejecting activations with HTTP 400 when inventory is zero.
- Upgraded the player Tray UI in `static/app.js` and HUD tag to display `+30%` along with live second-by-second countdown ticking (e.g. `x0 (118s)`).
- Added automated unit and integration tests verifying percentage boost scaling, immediate return to base radius upon timer expiration, and refusal when none are left.

### Interview Questions & Answers
**Q1: Why is a percentage expansion (+30%) superior to a fixed metre addition (like +20m) for radius boost?**  
**A1:** Fixed metre boosts distort game balance: adding 20m to a tight 25m landmark almost doubles its size (+80%), making a difficult physical clue trivial, whereas on a wide 100m open field it only adds a negligible 20% margin. A 30% multiplier scales consistently with the intended physical scale of every checkpoint location.

**Q2: How does the server prevent floating-point rounding errors when calculating the 30% boosted radius during location checks?**  
**A2:** In `game.py`, `compute_effective_radius` returns `base_radius * 1.30` as a standard Python 64-bit float, evaluated against Haversine distance using `is_inside(distance_m, effective_radius)`. Since geofence coordinates and distance metrics have natural tolerances of several centimetres, standard IEEE 754 arithmetic avoids domain edge cases without requiring arbitrary rounding hacks.

---

## Task 16: Speed plausibility check

### 5-Line Interview Summary
- Implemented pure function `speed_mps()` in `game.py` computing great-circle Haversine distance divided by server receive time delta with a minimum 1.0 s gap to prevent zero-division or division blow-ups.
- Enforced speed plausibility in `/api/ping`: rejected any fix exceeding `MAX_SPEED_MPS` (12 m/s, ~43 km/h) by resetting `inside_streak` to 0 and returning `{"status": "implausible"}`.
- Recorded a `speed_rejected` audit event in SQLite (`events` table) capturing the offending speed reading and limit threshold for organizer inspection.
- Preserved `last_fix` coordinates and timestamp on rejected fixes so an implausible jump or spoof attempt never poisons subsequent legitimate location checks.
- Handled network signal blackouts gracefully because legitimate jumps over long time gaps (e.g. 600m in 5 minutes) yield low speeds and are accepted.

### Interview Questions & Answers
**Q1: Why does a rejected speed fix NOT update `last_fix` in SQLite?**  
**A1:** If an implausible fix (e.g. a 1,000 m teleport) updated `last_fix`, the very next fix—even when sent from the player's true physical location—would be compared against the fake teleport coordinates. The player would then be flagged as teleporting back across campus (another 1,000 m jump), poisoning the chain and locking them out of legitimate pings. Leaving `last_fix` untouched ensures one bad fix is safely dropped without corrupting future comparisons.

**Q2: Can this speed plausibility check stop GPS spoofing entirely?**  
**A2:** No, and we must be honest about that limitation. Speed plausibility stops rapid teleportation (e.g. jumping between opposite ends of campus in seconds), but it cannot detect a player walking at normal speeds while simulating GPS coordinates via developer tools or mocking apps. True physical presence verification relies on on-site organizers and physical proofs like QR codes or checkpoint answer phrases.

---

## Task 17: Admin Teams tab (Release device, Adjust minutes, Delete team)

### 5-Line Interview Summary
- Added `GET /api/gods/teams` protected by `require_admin` returning team names, members, codes, device binding status (`bound` vs `free`), `last_seen`, cleared counts, and adjusted times.
- Implemented `POST /api/gods/teams/{id}/release` atomically clearing `device_hash` to NULL, locking out the old device immediately and allowing replacement phones to bind via team code.
- Created `POST /api/gods/teams/{id}/adjust` to apply time penalties (+min) or bonuses (-min) with mandatory audit reasons (3 to 120 chars) and invalidating the leaderboard cache.
- Built `DELETE /api/gods/teams/{id}` with cascade deletion across progress and hints, audited via `team_deleted` in the events table.
- Developed the `/gods` Teams tab in vanilla JavaScript with 5-second polling, warning highlights for teams inactive for >60s, and accessible modals for adjustments and deletions.

### Interview Questions & Answers
**Q1: How does "Release device" lock out a dead or lost phone without the phone having to call the server to log out?**  
**A1:** The device cookie contains only a random secret token; the server stores its SHA-256 hash in `teams.device_hash`. When an admin releases the device, `device_hash` is set to `NULL` in SQLite. On every subsequent request (`/api/state` or `/api/ping`), the dependency `auth.require_team_device` verifies that `team["device_hash"]` is present and matches the token hash. Because `device_hash` is now `NULL`, the old device immediately fails verification with HTTP 401.

**Q2: Why do time adjustments invalidate the in-memory leaderboard cache immediately?**  
**A2:** The public leaderboard endpoint caches computed team rankings for up to 1 second to minimize database load. When an organizer adds or removes minutes (or deletes a team), players watching the big screen or lobby expect instantaneous updates. Invalidating `_leaderboard_cache` on every adjust and delete ensures standings reflect penalty corrections on the very next 5-second poll cycle without stale delay.

---

## Fix: Checkpoint Readiness Counter Sync in Admin Panel

### 5-Line Interview Summary
- Identified desynchronization where the Game tab's checkpoint readiness counter (`game-cp-counter`) remained stale while the Checkpoints tab reflected the true count.
- Updated `renderCheckpoints()` in `gods.js` to synchronously update both `#cp-counter-pill` and `#game-cp-counter` / `#game-cp-status-text`.
- Replaced isolated checkpoint loading with `Promise.all([loadCheckpoints(), loadGameStatus()])` inside `saveCheckpointForm`, `handleReorderCheckpoint`, and `handleDeleteCheckpoint`.
- Added automatic re-fetching in `switchTab()` so navigating between Game, Checkpoints, and Teams immediately updates the active view.
- Introduced 5-second polling on the Game tab so quest status, registration state, and checkpoint readiness stay fresh automatically.

### Interview Questions & Answers
**Q1: Why did the Checkpoints tab show 6 checkpoints while the Game tab showed "0 of 5 needed"?**  
**A1:** The Checkpoints tab updated its local DOM pill `#cp-counter-pill` directly from the `/api/gods/checkpoints` response, but checkpoint creation and deletion functions never re-fetched `/api/gods/game/status` nor updated the Game tab's DOM element `#game-cp-counter`. Furthermore, switching tabs did not trigger a fresh status load, leaving the Game tab displaying its initial static HTML.

**Q2: How does the fix prevent this state discrepancy between the two tabs?**  
**A2:** First, `renderCheckpoints()` now simultaneously updates both tab counter elements whenever checkpoints are loaded. Second, checkpoint mutations (add, reorder, delete) now await both `loadCheckpoints()` and `loadGameStatus()` together. Finally, `switchTab()` immediately re-fetches the active tab's endpoint and runs 5-second polling on the Game tab.

---

## Task: Reset Game to Setup (/gods)

### 5-Line Interview Summary
- Implemented `POST /api/gods/game/reset` protected by the `require_admin` dependency to restore the game lifecycle back to `"setup"`.
- Cleared the `started_at` timestamp setting to empty string so new quest sessions start with a pristine countdown clock.
- Recorded a canonical `game_reset` audit event in SQLite (`events` table) without altering registered checkpoints.
- Added a "Reset to Setup" button (`#btn-game-reset`) to the Quest State control card in `/gods`, enabled when the game is ended or running.
- Protected the admin reset button with a native confirmation dialog to prevent accidental resets during live gameplay.

### Interview Questions & Answers
**Q1: Why is the reset endpoint restricted to admins and audited in the events table?**  
**A1:** Resetting the game state changes the authoritative server status for every connected player and device. If an unauthorized client could call `/api/reset`, they could disrupt an in-progress campus hunt. Guarding it with `require_admin` (via the signed `quest_admin` session cookie) ensures only authenticated organizers can trigger it, while writing an audit event to SQLite (`game_reset`) provides accountability of who reset the game and when.

**Q2: What happens to the countdown timer and checkpoint locks when the game is reset back to "setup"?**  
**A2:** In `setup` state, `started_at` is cleared to empty (`None` in API responses), which stops any active countdown banner. Crucially, returning to `setup` releases the strict live-game checkpoint locking rules, allowing organizers to once again edit checkpoint coordinates, adjust radii, add new checkpoints, or reorder the route before starting the next quest.

---

## Task 18: Stuck-team recovery (Player Skip and Admin Force-clear)

### 5-Line Interview Summary
- Added `POST /api/skip` allowing players to skip their active checkpoint only after spending at least `SKIP_WAIT_S` (default 600s) on it.
- Applied `SKIP_PENALTY_S` (default 600s) to `teams.penalty_s`, recorded progress with `how = 'skipped'`, awarded no power-ups, returned no story, and advanced to the next clue.
- Built `POST /api/gods/teams/{id}/clear` requiring admin authentication and a logged reason (3 to 120 chars) to clear a checkpoint with `how = 'admin'` and zero penalty.
- Enforced concurrency safety with `write_tx()` (`BEGIN IMMEDIATE`) and SQLite's `PRIMARY KEY (team_id, checkpoint_id)` constraint so double clicks can never clear twice.
- Integrated UI controls: a Skip button on the player clue card unlocked after wait time with a penalty confirmation modal, and a "Clear Checkpoint" button in the admin Teams table.

### Interview Questions & Answers
**Q1: How does the server calculate how long a team has spent on their current checkpoint to decide if Skip is allowed?**  
**A1:** The server queries `MAX(unlocked_at)` from `progress` for the team. If the team has cleared earlier checkpoints, that timestamp marks the start of the current one; if they are on the very first checkpoint, the server uses `started_at` from `settings`. Subtracting that start time from the authoritative server clock (`time.time()`) gives elapsed seconds on that spot, preventing players from manipulating client timestamps to bypass the wait rule.

**Q2: Why does skipping award no power-ups and return no story, while GPS unlock awards both?**  
**A2:** Skip is a recovery mechanism for stuck teams, not a normal accomplishment. Checkpoint stories are narrative rewards for physically reaching a campus landmark, and power-ups (alternating Radar and Radius boost) are earned milestone rewards for genuine geofenced unlocks. Withholding them maintains competitive integrity and incentivizes physical exploration, while adding the 10-minute penalty keeps the leaderboard fair.

---

## Task 19: Reliability (Wake Lock, error states, and session persistence)

### 5-Line Interview Summary
- Integrated the Screen Wake Lock API (`navigator.wakeLock.request('screen')`) during active gameplay, automatically re-requesting locks on `visibilitychange` when returning to the tab.
- Provided a persistent yet dismissible "Keep this screen on" attention banner whenever Wake Lock is unsupported, rejected by battery saver mode, or released.
- Implemented heuristic in-app browser detection alerting players with a calm advisory banner to open the hunt in Chrome or Safari for reliable Geolocation.
- Engineered calm, actionable error guidance covering Location permission denial (with clear re-enable steps), GPS hardware unavailability, weak GPS chips, and auto-reconnecting offline alerts.
- Preserved zero client-side game state (zero `localStorage` or `sessionStorage`), ensuring page reloads resume authoritative state strictly via HttpOnly device cookies and the server clock.

### Interview Questions & Answers
**Q1: Why does the app need the Screen Wake Lock API, and why do you re-request it on the `visibilitychange` event?**  
**A1:** Mobile operating systems pause Geolocation watchers and throttle network timers when a phone locks or a screen turns off to save battery. If a player's phone locks while walking between checkpoints, location pings halt and geofences cannot be confirmed. The Screen Wake Lock API prevents the screen from sleeping. Browsers automatically release this lock whenever a user switches apps or minimizes the tab; listening to `visibilitychange` ensures the lock is seamlessly re-acquired as soon as the page becomes visible again.

**Q2: Why do you show an advisory banner for in-app browsers instead of strictly blocking or enforcing browser detection?**  
**A2:** User agent strings across mobile webviews (like Instagram, WhatsApp, or WeChat) are fragmented, frequently updated, and prone to false positives. Treating in-app detection as a hard block risks locking out legitimate players whose browsers might handle Geolocation and cookies without issue. Providing a calm advisory banner ("Open this link in Chrome or Safari for location to work properly") alerts players to common in-app location sandbox limitations without preventing teams from playing.

---

## Task 20: Test mode, Rules tab, and FAQ

### 5-Line Interview Summary
- Implemented `POST /api/gods/game/test-mode` allowing admins to toggle simulated test fixes only when `ALLOW_TEST_MODE` is enabled in the environment.
- Enforced server-side validation in `/api/ping`: pings with `test: true` are refused with HTTP 403 and logged if test mode is inactive on the server.
- Allowed map tapping during active test mode to simulate location fixes, with speed plausibility checks bypassed for test pings to permit testing across campus.
- Displayed prominent, calm "TEST MODE ACTIVE" banners across player and organizer screens whenever test mode is turned on.
- Built public `GET /api/rules` dynamically formatting rules and all 5 field FAQ entries directly from `config.py` variables so numbers never go out of date.

### Interview Questions & Answers
**Q1: Why does the server refuse `test: true` with a 403 and log it when test mode is disabled, and why can't the server detect spoofing done outside the app?**  
**A1:** The `test: true` flag protects the built-in development and demo feature so players in a live event cannot tap the map to jump between checkpoints. However, the server only receives coordinates and an accuracy estimate from the HTTP body; it cannot verify whether the phone's OS produced those coordinates through satellite signals or an external mock location app (or Chrome DevTools Sensors). To mitigate external spoofing, the server enforces independent defenses: speed plausibility checks (rejecting speeds over 12 m/s), accuracy thresholds, hidden uncleared coordinates, and on-site organizers.

**Q2: Why does `GET /api/rules` build its text dynamically from configuration settings instead of serving a static text or HTML document?**  
**A2:** In game-driven applications, rules often change during tuning—such as adjusting hint penalties from 3 minutes to 5 minutes, or changing skip wait times from 10 to 15 minutes. If rules and FAQ entries were hardcoded in static HTML, code changes in `config.py` would cause the documentation to display conflicting or obsolete numbers to players. Computing the text dynamically from `config.HINT_PENALTY_S`, `config.SKIP_WAIT_S`, `config.ACCURACY_LIMIT_M`, etc., guarantees that player-facing documentation stays 100% synchronized with the server's authoritative game engine.

---

## Fix: SQLite Cross-Thread Connection Close & Dotenv Hot-Reload

### 5-Line Interview Summary
- Diagnosed `sqlite3.ProgrammingError` where worker threads in FastAPI's AnyIO threadpool attempted to close connection handles created on another worker thread.
- Added `check_same_thread=False` to `sqlite3.connect()` in `db.get_connection()`, allowing cross-thread cleanup during `get_db` generator exit.
- Added `override=True` to `load_dotenv()` in `config.py` so modifying `.env` flags (such as `ALLOW_TEST_MODE`) takes immediate effect on server reload.
- Created `test_get_db_cross_thread_close` in `tests/test_db.py` to ensure multi-threaded context cleanup never raises `ProgrammingError`.
- Verified that all 139 tests across the entire test suite pass cleanly without warnings or thread lockups.

### Interview Questions & Answers
**Q1: Why does FastAPI trigger a `sqlite3.ProgrammingError` on `conn.close()` if `check_same_thread=False` is omitted?**  
**A1:** Synchronous routes and dependencies in FastAPI run inside an AnyIO worker threadpool (`anyio.to_thread.run_sync`). When a dependency like `get_db` yields a connection, the generator enters on one threadpool worker. When the response finishes, FastAPI runs the context manager exit (`conn.close()`) on whatever worker thread is available next. By default, Python's `sqlite3` enforces `check_same_thread=True` and raises `ProgrammingError` whenever a connection is touched or closed from a different thread ID. Setting `check_same_thread=False` permits cross-thread closure while SQLite's file-level WAL locking maintains database safety.

**Q2: Why did setting `ALLOW_TEST_MODE=1` in `.env` not take effect until `override=True` was added?**  
**A2:** By default, `python-dotenv`'s `load_dotenv()` ignores any keys that already exist in `os.environ`. When Uvicorn boots, environment variables are cached; when `.env` is modified and a module is reloaded, `load_dotenv()` without `override=True` leaves the old value intact. Specifying `load_dotenv(override=True)` forces `python-dotenv` to overwrite in-memory environment variables with newly saved values on reload.

---

## Fix: Test Mode Interactive Cursor & Simulated Location Fix Helper

### 5-Line Interview Summary
- Overrode Leaflet's default `.leaflet-grab { cursor: grab; }` style with `cursor: crosshair !important` on `#map` whenever test mode is active.
- Added dynamic toggling of `test-mode-map` and `test-mode-active` CSS classes inside `setTestMode()` in `app.js`.
- Implemented the missing `updatePlayerLocation(lat, lng, accuracy)` helper function in `app.js` to eliminate a runtime `ReferenceError`.
- Reused `updatePlayerLocation` inside both real GPS watcher callbacks and simulated test click pings for consistent marker rendering.
- Enhanced user feedback with instant toast confirmation showing coordinates and descriptive errors if the game is not running.

### Interview Questions & Answers
**Q1: Why did clicking the Leaflet map fail silently when test mode was enabled?**  
**A1:** The click handler in `app.js` invoked `updatePlayerLocation()`, but that function had not yet been defined in the client script. In JavaScript, invoking an undeclared function raises an unhandled `ReferenceError`. This crashed the click event handler before `fetch('/api/ping')` could be called, leaving no visual feedback and preventing the HTTP request from ever dispatching. Defining `updatePlayerLocation()` and sharing it across both simulated clicks and genuine `watchPosition` callbacks resolved the crash.

**Q2: Why did hovering over the map show an open hand cursor instead of a pointer or crosshair?**  
**A2:** Leaflet's stylesheet explicitly sets `cursor: -webkit-grab; cursor: grab;` on `.leaflet-grab` and `.leaflet-container` for map dragging. Standard CSS rules on `#map` alone do not override Leaflet's class-specific grabbing selectors without an `!important` rule or targeting `.leaflet-grab`. Applying `.test-mode-active #map, .test-mode-map .leaflet-grab { cursor: crosshair !important; }` ensures the browser displays a target crosshair cursor immediately whenever test mode is toggled on.

---

## Fix: Tile URL Template Fallback & Map Viewport Invalidation

### 5-Line Interview Summary
- Added automatic validation in `config.py` checking if `TILE_URL` contains the required `{z}` coordinate placeholder.
- Implemented a safe fallback to `"https://tile.openstreetmap.org/{z}/{x}/{y}.png"` if a user accidentally pastes an OpenStreetMap browser link into `.env`.
- Corrected `.env.example` line 67 from a static web link to the working Leaflet tile template URL.
- Added `mapInstance.invalidateSize()` in `app.js` upon switching to the Map tab to guarantee proper tile container recalculation.
- Confirmed `GET /api/config` delivers the valid tile template, restoring full map rendering without blank gray tiles.

### Interview Questions & Answers
**Q1: Why did pasting an OpenStreetMap web URL cause the Leaflet map to turn solid gray?**  
**A1:** Leaflet `L.tileLayer` requests map tiles using coordinate template variables `{z}/{x}/{y}.png`. If an administrator or developer pastes an OpenStreetMap web URL (like `https://www.openstreetmap.org/#map=17/...`), the URL lacks these placeholders. Leaflet attempts to load the OpenStreetMap HTML website as an image for every tile grid coordinate, failing HTTP image decoding and leaving the Leaflet container completely gray.

**Q2: How does the configuration fallback in `config.py` prevent this failure?**  
**A2:** By checking `if "{z}" not in _raw_tile_url:`, the backend identifies when an invalid or standard browser URL was provided in environment variables. Instead of propagating the broken URL to clients via `GET /api/config`, it automatically falls back to `"https://tile.openstreetmap.org/{z}/{x}/{y}.png"`. This makes the application resilient against common configuration mistakes during deployment or local setup.

---

## Task 21: Big-screen leaderboard page (/board)

### 5-Line Interview Summary
- Added `GET /board` to deliver a projector-friendly HTML page (`static/board.html`) with high contrast and enlarged typography.
- Built `GET /api/board` as a public, read-only endpoint that reuses the cached in-memory leaderboard function.
- Sanitized the API response to strip team codes, member names, device tokens, and coordinates, exposing only rank, name, cleared/total, and adjusted time.
- Integrated a live game state indicator (Waiting, Running, Ended) with an auto-updating 5-second polling loop and an automatic offline error banner.
- Added comprehensive unit tests in `tests/test_board.py` verifying HTML serving, field whitelisting, and strict absence of sensitive data.

### Interview Questions & Answers
**Q1: Why does `/api/board` reuse the cached leaderboard function instead of querying the database directly?**  
**A1:** The main leaderboard is polled frequently by many player devices and the projector screen simultaneously. Reusing `get_leaderboard()`, which caches sorted rankings with a 1-second TTL and invalidates immediately on checkpoint unlocks, eliminates redundant database queries. `/api/board` simply projects and sanitizes this in-memory ranking, keeping database load minimal.

**Q2: Why is it critical that `/api/board` completely strips team codes, member lists, and coordinates?**  
**A2:** `/api/board` is a completely unauthenticated, public endpoint designed for public projector displays and spectators. Exposing team codes would allow spectators to hijack player devices via `/api/join`, exposing member names leaks student identities without consent, and exposing coordinates or distances would give away checkpoint locations before teams solve the clues.

---

## Task: Team Progress Reset & Game 2 Isolation

### 5-Line Interview Summary
- Updated `POST /api/gods/game/reset` to automatically wipe all team progress, hint history, power-ups, streaks, and completion timestamps when resetting the game back to setup.
- Added admin endpoints `POST /api/gods/teams/reset` (for all teams) and `POST /api/gods/teams/{id}/reset` (for an individual team) protected by `require_admin`.
- Preserved team registrations, secret join codes, member rosters, and device pairings in `teams` table so players never have to re-register their phones for Game 2.
- Updated player device UI logic (`static/app.js`) to automatically dismiss the "Quest Completed!" modal when returning to setup state, countdown, or active route.
- Added "Reset Teams Progress" buttons to both the Game and Teams admin tabs with native confirmation dialogs and immediate leaderboard cache invalidation.

### Interview Questions & Answers
**Q1: Why did resetting the game state to "setup" previously still show "Quest Completed!" on player phones?**  
**A1:** Previously, `/api/gods/game/reset` only updated `game_state = 'setup'` in the `settings` table, leaving `teams.finished_at` and `progress` rows intact. When the game restarted, `/api/state` still returned `finished: true`, and the client never hid the `#finish-overlay`. Wiping `progress`, `hint_uses`, and team gameplay columns on reset—and hiding `#finish-overlay` when `!state.finished`—ensures Game 2 starts with a clean slate.

**Q2: Why does resetting team progress preserve `code` and `device_hash` instead of deleting the teams?**  
**A2:** In a live campus event, having 50 teams re-type team names, member rosters, and re-bind device cookies before Game 2 would cause huge friction and delays. By clearing only dynamic run attributes (`penalty_s`, `bonus_s`, `radar_left`, `boost_left`, `radar_until`, `boost_until`, `inside_streak`, `last_fix_*`, `finished_at`) along with `progress` and `hint_uses` rows, the paired phones remain authenticated and ready to play the next quest immediately.

---

## Task 22: Trust and hygiene pages

### 5-Line Interview Summary
- Added plain-language `/privacy` and `/terms` pages disclosing data collection, cookie usage, OpenStreetMap tile IP visibility, and campus safety rules with organizer contacts.
- Added a required consent checkbox to player registration linking directly to `/privacy` and `/terms`, with touch targets meeting mobile accessibility standards.
- Built custom 404 routing serving a user-friendly HTML error page for browser navigation and structured JSON for `/api` routes.
- Defined unique `<title>` tags across all application views and delivered a clean SVG favicon linked across all pages.
- Implemented an authenticated admin action `POST /api/gods/wipe` requiring typing `WIPE` to delete all teams, progress, hints, and event history while preserving checkpoints and settings.

### Interview Questions & Answers
**Q1: Why is it important to disclose OpenStreetMap tiles in the privacy notice, and why must Referrer-Policy be strict-origin-when-cross-origin instead of no-referrer?**  
**A1:** Map tiles are fetched directly by the player's browser from `tile.openstreetmap.org`, which means OpenStreetMap's servers receive the client's IP address. OpenStreetMap's Tile Usage Policy requires a valid HTTP `Referer` header identifying the application to monitor traffic and prevent abuse. Setting `Referrer-Policy: no-referrer` would strip the header and violate OSM's policy, causing map tiles to fail loading, whereas `strict-origin-when-cross-origin` safely shares the origin while protecting sub-paths.

**Q2: Why does the admin "Wipe event data" action delete teams, progress, hints, and events, but leave checkpoints and settings untouched?**  
**A2:** Checkpoints represent the carefully curated physical geofences and riddles surveyed by organizers across the campus, and settings store operational parameters. Between orientation sessions or after an event concludes, organizers need to purge all player personal data (names, timestamps, device hashes) for privacy and hygiene without having to re-enter all physical checkpoint coordinates and clues from scratch.

---

## Task 23: Design pass and accessibility

### 5-Line Interview Summary
- Centralized all palette colors, borders, radius, fonts, and spacing scale into `:root` CSS custom properties in `style.css`.
- Removed all drop shadows in favor of crisp 1px borders, leaving at most one subtle shadow on modal overlays per the design brief.
- Enforced a minimum 44px touch target on every button, link, and interactive control, including small secondary and dismiss buttons.
- Added universal `:focus-visible` keyboard rings, explicit input `<label>` and `aria-label` attributes, and `aria-live` error announcements.
- Upgraded text contrast above 4.5:1 across all states, applied tabular numerals to timers and ranks, and verified layout resilience at 200% text zoom.

### Interview Questions & Answers
**Q1: Why did you eliminate drop shadows and switch to 1px borders across cards, chips, and HUD controls?**  
**A1:** Out in direct sunlight on campus pathways, subtle drop shadows wash out completely and reduce interface contrast. Following the signage-inspired design brief, crisp 1px borders (#D9D4C8) on card surfaces (#FFFFFF) against a warm off-white background (#F6F4EF) provide clear visual boundaries and high readability without relying on trendy "vibecoded" styling.

**Q2: Why is the universal `:focus-visible` ring important, and why set `min-height: 44px` on all buttons?**  
**A2:** Keyboard and screen-reader users rely on `:focus-visible` to know exactly which control is active without adding distracting outlines during mouse clicks. For mobile players running outdoors, touch targets smaller than 44px lead to frequent mis-taps. Setting `min-height: 44px` ensures compliance with WCAG 2.5.5 and guarantees that buttons are effortless to tap on phones of any size.

---

## Task 24: Security review and hardening

### 5-Line Interview Summary
- Conducted a comprehensive audit of the entire codebase covering authentication, route authorization, input limits, rate limiting, and SQL injection safety.
- Isolated sliding-window rate limiter buckets per action (`login:`, `join:`, `register:`) to prevent cross-endpoint bucket collisions and throttled team registrations.
- Hardened client IP extraction from reverse-proxy `X-Forwarded-For` headers by selecting the immediate client hop to defend against forged client headers.
- Capped maximum team members at 10 to prevent bloated payloads and rejected chunked transfer encoding and negative body lengths.
- Added re-activation protection for Radar and Boost power-ups to avoid burning charges, and handled concurrent unlock ping races gracefully.

### Interview Questions & Answers
**Q1: Why did using a shared client IP as the rate limiter key create an issue, and how did namespacing fix it?**  
**A1:** Previously, `/api/gods/login` and `/api/join` passed `client_ip` directly to the rate limiter without an action prefix. Because both endpoints stored timestamps in the same in-memory list `_buckets[client_ip]`, attempts on one endpoint counted against the other. For example, failed login attempts on campus Wi-Fi would prematurely lock out teams trying to join with a code. Namespacing keys with an action prefix (e.g. `login:{ip}`, `join:{ip}`, `register:{ip}`) keeps rate limits completely isolated per endpoint.

**Q2: How does the application ensure that concurrent requests cannot double-unlock a checkpoint or double-apply a power-up penalty?**  
**A2:** SQLite is run in WAL mode with autocommit disabled (`isolation_level=None`), and state-mutating transactions use `BEGIN IMMEDIATE` via `db.write_tx`. This acquires SQLite's write lock immediately at transaction start, preventing interleaved check-then-insert operations. Furthermore, the database schema enforces composite primary keys (`PRIMARY KEY (team_id, checkpoint_id)`) on `progress` and `hint_uses`, guaranteeing at the database level that duplicate unlocks or hints cannot be recorded even under simultaneous requests.

---

## Task 25: README and interview preparation

### 5-Line Interview Summary
- Overhauled `README.md` for project reviewers, including a text-only walkthrough, live and video link placeholders, and complete setup instructions.
- Documented the ping-to-unlock flow in exactly six clear lines alongside an end-to-end Mermaid architecture diagram.
- Summarized core architectural decisions with one-sentence rationale, followed by a complete categorized API endpoint index.
- Plainly documented the six honest operational limitations (background tracking, GPS noise, token-based device identity, outdoor-only, GPS spoofing, fixed route order).
- Created `docs/INTERVIEW_PREP.md` consolidating the entire project's rationale into conversational questions, short answers, and exact source code locations.

### Interview Questions & Answers
**Q1: Why is it important to state the project's limitations (such as GPS spoofing and background tracking) honestly in the README?**  
**A1:** In real-world engineering and technical evaluations, demonstrating a clear understanding of system constraints and hardware boundaries is far more impressive than making false claims. Stating clearly that web browsers cannot track in the background or verify GPS authenticity proves we understand browser security sandboxes, explain how we mitigated those risks (Wake Lock, speed plausibility, accuracy gating), and know the proper production fixes (physical QR codes).

**Q2: Why did you compile `docs/INTERVIEW_PREP.md` with explicit file and function references?**  
**A2:** During a technical interview, an applicant needs to connect conceptual explanations directly to concrete code implementations. Having the exact file and function names (such as `game.py:haversine_m`, `main.py:ping_location`, `db.py:write_tx`) readily memorized allows me to answer with precision, walk an interviewer through the exact lines of code, and demonstrate complete ownership of the entire codebase.

---

## Update: Campus Naming to IET DAVV Campus & Browser Page Indexing

### 5-Line Interview Summary
- Standardized the campus name across all documentation, configuration, and tests to "IET DAVV Campus".
- Replaced outdated "Takshashila" references in `README.md`, `docs/DEPLOY.md`, `config.py`, and test fixtures.
- Updated `config.py` default fallback for `CAMPUS_NAME` to ensure consistency with `.env.example`.
- Expanded the "Open your browser" quickstart section in `README.md` to link all 7 user-facing and admin pages (Player, Admin, Board, Privacy, Terms, Health check, Docs).
- Verified that all 168 automated tests continue to pass cleanly without failures.

### Interview Questions & Answers
**Q1: Why is it important to synchronize `CAMPUS_NAME` across `.env.example`, `config.py`, and documentation?**  
**A1:** Default values in configuration modules act as the fallback whenever an environment variable is omitted or during new developer onboardings. Having inconsistent naming across `.env.example`, `config.py`, and deployment documentation causes confusing header displays or broken assumptions during orientation events. Standardizing on "IET DAVV Campus" guarantees that regardless of deployment environment, the correct campus identity is reflected.

**Q2: Why list trust pages like `/privacy` and `/terms` alongside the main app in the README quickstart?**  
**A2:** Evaluators reviewing a repository need to verify not just the core gameplay, but also the hygiene, compliance, and user safety aspects of the application. Placing direct links to `/privacy`, `/terms`, and `/healthz` right next to `/` and `/gods` in the README enables reviewers to immediately test and inspect all application surfaces without guessing URL routes.

---

## Task 26: Final checks and demo support

### 5-Line Interview Summary
- Added CLI support for `seed.py --demo` to populate the real verified checkpoints from `docs/CHECKPOINTS_DRAFT.md`.
- Enforced strict production safeguards requiring `--force` to run `seed.py` whenever `config.ENV == "production"`.
- Created `docs/FINAL_CHECKLIST.md` merging Section 8.8 submission requirements with production Railway deployment and field testing checks.
- Formulated `docs/DEMO_SCRIPT.md` detailing a 2.5-minute video presentation with exact timings and explicit announcements of test mode vs real walks.
- Added comprehensive unit tests in `tests/test_seed.py` covering CLI options, demo data seeding, and production safety guards.

### Interview Questions & Answers
**Q1: Why does `seed.py` strictly require the `--force` flag in production environments?**  
**A1:** Accidentally running a database seed script against a live production deployment would truncate or overwrite existing checkpoints, wiping out team progress in the middle of a live campus event. Requiring `--force` when `ENV=production` ensures an operator must consciously acknowledge the risk, preventing accidental data loss from automated deployment scripts or developer mistakes.

**Q2: Why does the demo video script specifically require stating out loud when test mode is active?**  
**A2:** In GPS-based applications, it is impossible for an evaluator watching a screen recording to differentiate between authentic satellite hardware fixes and simulated developer coordinates without explicit audio or visual disclosure. Calling out test mode coordinates aloud demonstrates transparency, honesty about simulated testing scenarios, and proves how the server handles geofence bounds in edge cases.

---

## Task: Mobile HUD Overhaul and Navigation Menu Drawer

### 5-Line Interview Summary
- Removed the 4-button bottom navigation bar to maximize map visibility and eliminate duplicate leaderboard buttons.
- Stacked the circular Menu and Leaderboard buttons in the top-left corner with 44px accessible touch targets.
- Positioned the HUD status chips (checkpoints cleared, timer, GPS status) cleanly in the top-right header area.
- Anchored active gameplay elements into a responsive bottom HUD container, keeping power-up controls visible on the bottom-left and zoom controls unobstructed on the bottom-right.
- Transformed the hamburger menu into a full navigation drawer providing structured access to Team Details, Cleared Checkpoints history, Rules & FAQ, Privacy Policy, and Terms.

### Interview Questions & Answers
**Q1: Why did you eliminate the bottom tab bar in favor of a navigation drawer for a mobile geolocation game?**  
**A1:** Geofenced outdoor games require as much visible map real estate as possible so players can orient themselves and navigate physical paths. Having a fixed bottom tab bar on mobile screens shrank the interactive map and collided with the clue card and power-up controls, while also duplicating the floating leaderboard button. Consolidating non-urgent panels (Team details, Rules, Route history, Privacy, Terms) into a drawer menu frees up the viewport for immediate gameplay.

**Q2: How did you prevent dynamic clue card sizing from covering power-up controls or Leaflet map zoom buttons?**  
**A2:** We placed the power-up tray and the active clue card inside a dedicated flexbox column container (`.game-bottom-hud`) pinned to the bottom with safe-area insets. By setting the power-up tray to `align-self: flex-start`, power-up buttons naturally sit directly above the clue card on the bottom-left regardless of card content height. Similarly, we offset the bottom-right Leaflet zoom controls so they hover above the bottom HUD without overlapping.

---

## Task: Alternate Checkpoint Power-ups with 2m 30s Speed Bonus

### 5-Line Interview Summary
- Added `POWERUP_FIND_TIME_LIMIT_S` (150 seconds / 2m 30s) configuration to `config.py` and `.env.example`.
- Refactored pure logic in `game.award_for` to only grant power-ups on alternate checkpoint clears (1st, 3rd, 5th, ...).
- Enforced a speed qualification check requiring teams to find the checkpoint within 150 seconds to receive the power-up.
- Added `db.get_team_last_progress_time` to compute checkpoint search durations authoritatively on the server clock.
- Updated automated test suites in `tests/test_game.py` and `tests/test_powerups.py` confirming alternate stop qualification and time limit enforcement.

### Interview Questions & Answers
**Q1: Why is the 2m 30s time limit measured on the server rather than using timestamps sent by the player's phone?**  
**A1:** Client devices can manipulate their internal system clock, buffer and delay GPS packets, or fake elapsed intervals. Relying on client-reported search duration would make power-up qualification trivial to cheat. Measuring elapsed time on the server between the prior checkpoint unlock timestamp (or game start) and the current unlock timestamp guarantees authoritative fair play across all teams.

**Q2: How does the server determine when search began for the 1st checkpoint versus subsequent checkpoints?**  
**A2:** For the very first checkpoint, the clue becomes active when the global start countdown finishes, so the search interval is `now - started_at`. For all subsequent checkpoints, search time starts the exact second the previous checkpoint was cleared or skipped, queried via `SELECT MAX(unlocked_at) FROM progress WHERE team_id = ?`.

---

## Task: Hint Penalty Tuning (+5m) and Live HUD Timer Synchronization

### 5-Line Interview Summary
- Updated the default hint penalty from 3 minutes (+180s) to 5 minutes (+300s) across server configuration and environment templates.
- Fixed the player HUD timer to display authoritative adjusted time (`elapsed + penalty - bonus`) instead of raw elapsed time.
- Ensured hint activations immediately advance the displayed HUD clock without waiting for the next polling cycle.
- Synchronized all player UI badges, clue cards, confirmation modals, and toast alerts to consistently state the 5-minute penalty.
- Updated automated test suites verifying 300-second penalty application, idempotency, and leaderboard adjusted time accuracy.

### Interview Questions & Answers
**Q1: Why did the player HUD timer previously show the wrong time after taking a hint, even though the database recorded it correctly?**  
**A1:** The server recorded the penalty in `teams.penalty_s` and computed adjusted time for the leaderboard, but the client JavaScript timer only calculated raw elapsed seconds (`now - started_at`). By updating the timer tick calculation to incorporate `penalty_s` and `bonus_s`, the HUD display now reflects the team's true adjusted time during active gameplay.

**Q2: Why is the hint penalty configured centrally in `config.py` rather than hardcoding 300 seconds across routes and frontend scripts?**  
**A2:** Event rules often undergo tuning during playtesting. Storing `HINT_PENALTY_S` in `config.py` allows organizers to change penalties via environment variables without touching database schemas or route handlers, while dynamic endpoints like `/api/rules` automatically format and broadcast the synchronized values to players.




---

## Task: Admin Session Hardening and Per-Device Authentication

### 5-Line Interview Summary
- Added strict Cache-Control: no-store, no-cache, must-revalidate, private and Pragma: no-cache headers to /gods and all /api/gods/* routes in middleware.
- Changed the quest_admin session cookie from a persistent 8-hour max-age cookie to a true browser session cookie.
- Prevented edge proxies, CDNs, and browsers from caching authenticated admin status across different devices on the same network.
- Ensured newly opened browsers and sessions require explicit credential verification (ADMIN_USER and ADMIN_PASS) before granting admin panel access.
- Expanded test coverage in tests/test_auth.py verifying no-cache header delivery, unauthenticated rejection, and session cookie lifetime flags.

### Interview Questions & Answers
**Q1: Why is setting Cache-Control: no-store, private essential on authenticated endpoints when deploying behind platforms like Railway or Cloudflare?**  
**A1:** Without explicit no-cache response headers, intermediate edge proxies, CDNs, or corporate network gateways may cache HTTP 200 responses for sensitive endpoints like /api/gods/me. If a response is cached at the edge, a subsequent request from a different device on the same network could receive the cached 200 JSON payload instead of querying the backend, erroneously exposing admin state without credentials.

**Q2: What is the difference between setting max_age versus omitting it on an authentication cookie?**  
**A2:** Setting max_age (e.g. 28800 seconds) writes a persistent cookie to the client's persistent disk storage that survives closing and reopening the browser until the timer expires. Omitting max_age creates a transient in-memory browser session cookie that the browser automatically purges when the session ends or browser is closed, ensuring that reopening the application or opening on a new device necessitates freshly entering login credentials.
