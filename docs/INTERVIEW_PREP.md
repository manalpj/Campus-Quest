# Campus Quest — Interview Preparation Guide

> **Author**: First-Year Student / GDGoC Technical Vertical Applicant  
> **Project**: Campus Quest (Geofenced Clue Hunt for DAVV Campus)  
> **Purpose**: Simple, direct explanations of every major architectural and algorithmic decision in the codebase.

---

## 1. How does the system know a player moved from here to there?

**Answer:**  
The phone does not detect continuous walking by itself. Instead, the mobile browser uses `navigator.geolocation.watchPosition` to read the phone's GPS chip. Every few seconds, the phone sends a single position point (latitude, longitude, and accuracy in metres) to our `/api/ping` endpoint.

When the server receives that point, it calculates the straight-line distance on the Earth's surface between the player's coordinates and the hidden target checkpoint. The system knows the player moved because each new GPS point has different coordinates, and the distance to the target changes.

- **Where it lives:**
  - Client geolocation watcher: `static/app.js` (`setupLocationWatcher`)
  - Server ping evaluation: `main.py` (`ping_location`)
  - Distance formula: `game.py` (`haversine_m`)

---

## 2. Why did you use the Haversine formula instead of the Pythagorean theorem?

**Answer:**  
The Earth is a curved sphere, not a flat sheet of graph paper. The Pythagorean theorem ($a^2 + b^2 = c^2$) works only on flat planes. If you convert latitude and longitude degrees directly with Pythagoras, lines of longitude get closer together as you move away from the equator, causing distorted distances.

Haversine takes two latitude and longitude points, accounts for the curvature of the Earth using spherical trigonometry, and gives the distance in real ground metres ($R = 6,371,000\text{ m}$). We wrote it by hand in pure Python using the standard `math` library so we didn't have to add extra external dependencies like `geopy`.

- **Where it lives:**
  - Formula implementation: `game.py` (`haversine_m`)

---

## 3. How do you handle GPS noise, drift, and accuracy?

**Answer:**  
Mobile GPS chips often jump around by 10 to 30 metres, especially when standing next to tall college buildings or under dense trees. If we weren't careful, a phone could falsely jump inside a 30-metre geofence circle while standing outside.

We handle this with three rules:
1. **Accuracy filtering**: Every GPS reading includes an `accuracy` estimate in metres. If the reading has an error estimate worse than 30 metres (`ACCURACY_LIMIT_M`), the server completely ignores it for geofence checks.
2. **Consecutive streak**: The server requires **2 consecutive valid fixes inside the radius** before unlocking the checkpoint. A single accidental jump will not unlock it.
3. **Appropriate radii**: Checkpoints are set between 25 and 100 metres depending on the size of the landmark so the zone is large enough for normal phone GPS.

- **Where it lives:**
  - Accuracy threshold check: `game.py` (`accuracy_ok`), `config.py` (`ACCURACY_LIMIT_M = 30.0`)
  - Streak state machine: `game.py` (`next_streak`, `should_unlock`)
  - Ping evaluation: `main.py` (`ping_location`)

---

## 4. Can players cheat by spoofing GPS, and how does the server protect against it?

**Answer:**  
The honest answer is: **the server cannot verify with 100% certainty that a GPS coordinate sent over HTTP is physically genuine**. If a student uses a mock location app, Chrome DevTools Sensors, or manually crafts a `curl` request, their phone will send fake numbers.

Because of that reality, we use a defense-in-depth approach:
1. **Hidden coordinates**: The server never sends the target checkpoint's coordinates, radius, or distance to the client. The player only gets the text riddle. A player cannot just read the coordinates from DevTools.
2. **Server-side authority**: The client never tells the server "I unlocked checkpoint 3". The client only sends its position, and the server decides if an unlock happened.
3. **Speed plausibility check**: The server calculates the speed between the player's previous GPS fix and the current one ($v = \text{distance} / \text{time}$). If a player jumps faster than 12 m/s (~43 km/h), the fix is rejected as an impossible jump, the streak resets to 0, and an audit event is logged.
4. **Physical presence**: In a real college event, student organizers are stationed around campus.
5. **Future fix**: The permanent technical fix for spoofing is having physical QR codes or secret answer phrases posted at each landmark that players must enter.

- **Where it lives:**
  - Speed check: `game.py` (`speed_mps`), `config.py` (`MAX_SPEED_MPS = 12.0`)
  - Rejection and streak reset: `main.py` (`ping_location`), `db.py` (`reset_team_streak`)
  - Secret hiding: `main.py` (`get_game_state`)

---

## 5. How is "one device per team" enforced?

**Answer:**  
Web browsers cannot read hardware identifiers like IMEI or MAC addresses due to privacy restrictions. 

Instead, we enforce it using a server-issued cryptographic token:
1. When a team registers, the server generates a high-entropy random token (`secrets.token_urlsafe(32)`).
2. The server stores only the **SHA-256 hash** of that token in the `teams` database table and sends the token back to the phone in an `HttpOnly`, `SameSite=Lax` cookie named `quest_device`.
3. If a second phone tries to join using the team code (`/api/join`), the server checks `teams.device_hash`. Because a device is already bound, the server rejects the second phone with HTTP 409 ("This team is already playing on another device").
4. If a team's phone battery dies, an organizer can click "Release device" in the admin dashboard (`/gods`). This sets `device_hash = NULL`, letting the team re-pair on a teammate's phone using their secret team code.

- **Where it lives:**
  - Token creation and hashing: `auth.py` (`generate_device_token`, `hash_device_token`, `set_device_cookie`)
  - Verification dependency: `auth.py` (`require_team_device`)
  - Binding and release: `db.py` (`bind_team_device`, `release_team_device`), `main.py` (`join_team`, `release_gods_team_device`)

---

## 6. Why is adjusted time the score instead of points?

**Answer:**  
In clue hunts, mixing points and time creates confusing edge cases where a team that wandered around slowly might beat a team that solved riddles cleanly just by hoarding secondary points.

Having **time as the single currency** makes the game intuitive: the fastest team to complete the quest wins.
- Power-ups modify time: taking a Hint adds a +3 minute penalty (+180s) directly to the team's adjusted time.
- Skips modify time: skipping a checkpoint adds a +10 minute penalty (+600s).
- The ranking formula is simple and unambiguous:
  $$\text{Adjusted Time} = \text{Elapsed Seconds at Last Unlock} + \text{Penalties} - \text{Bonuses}$$
Teams are ranked first by most checkpoints cleared, then by lowest adjusted time, and finally by earliest completion timestamp.

- **Where it lives:**
  - Time calculation: `game.py` (`adjusted_time`)
  - Team sorting logic: `game.py` (`rank_teams`)

---

## 7. Why polling instead of WebSockets?

**Answer:**  
WebSockets maintain persistent bidirectional TCP connections between the server and every client. While great for real-time multiplayer games, WebSockets add complexity: connection drops when mobile screens sleep, reconnection handshakes, proxy buffering on platforms like Railway, and heartbeat management.

For our campus event:
- Players poll `/api/state` every 4 seconds.
- Leaderboards poll every 5 seconds.
- Pings are sent periodically as GPS updates arrive.

To make polling lightweight, we added an **in-memory leaderboard cache with a 1-second TTL** on the server. If 50 devices request the leaderboard at the exact same moment, the server calculates the standings once and serves the cached result to everyone else. The cache is invalidated immediately whenever any team unlocks a checkpoint, so updates feel instantaneous without the overhead of WebSockets.

- **Where it lives:**
  - In-memory cache & invalidation: `main.py` (`get_leaderboard`, `invalidate_leaderboard_cache`)
  - Client polling timers: `static/app.js` (`startPolling`, `startLeaderboardPolling`)

---

## 8. Why SQLite, and can it handle the volume of a campus event?

**Answer:**  
Campus Quest is built for a single live college event (e.g. 50–70 teams, around 150–250 students). 

At that volume, write traffic is very small:
- Teams submit GPS pings every 2–4 seconds.
- Unlocks happen only 5 to 10 times per team over an entire hour.
- Leaderboard reads are served mostly from memory.

SQLite has zero configuration, lives in a single file, and has no separate database network daemon that can crash. By enabling **WAL mode (Write-Ahead Logging)** via `PRAGMA journal_mode = WAL`, readers do not block writers and writers do not block readers. Combined with a single-worker Uvicorn process and a 5-second busy timeout (`PRAGMA busy_timeout = 5000`), SQLite handles thousands of operations per second, far exceeding what a campus orientation requires.

On Railway, we mount a **persistent volume** at `/data` and set `DB_PATH=/data/quest.db` so the SQLite file survives server restarts and redeployments.

- **Where it lives:**
  - Connection setup and PRAGMAs: `db.py` (`get_connection`, `init_db`)
  - Deployment instructions: `docs/DEPLOY.md`

---

## 9. Why do you use `BEGIN IMMEDIATE` in your transactions?

**Answer:**  
By default in Python's `sqlite3`, transactions are deferred (`BEGIN DEFERRED`). When a transaction starts with a `SELECT` query, it only acquires a shared read lock. It only tries to upgrade to an exclusive write lock when an `INSERT` or `UPDATE` runs.

If two pings from the same team arrive at the exact same millisecond:
1. Ping A reads the current streak (streak is 1).
2. Ping B reads the current streak (streak is 1).
3. Both try to upgrade to a write lock at the same time to insert into the database, causing a deadlock or duplicate insert error.

`BEGIN IMMEDIATE` takes the exclusive write lock **upfront** before executing any statements. Any other incoming transaction waits cleanly up to the 5-second `busy_timeout`. This guarantees that check-then-insert operations (like checking if a checkpoint was already unlocked) are 100% atomic.

- **Where it lives:**
  - Transaction context manager: `db.py` (`write_tx`)

---

## 10. What happens if the server restarts during the quest?

**Answer:**  
Nothing is lost. 

All authoritative state lives in SQLite on persistent storage:
- Teams and their cryptographic device hashes are stored in `teams`.
- Every unlocked checkpoint is stored in `progress` with its exact unlock timestamp.
- Used hints and power-up expirations are stored in `hint_uses` and `teams`.
- Game settings (like `started_at` and `game_state`) are stored in `settings`.

When the server restarts:
1. Uvicorn boots and connects to the existing `/data/quest.db`.
2. When player phones make their next poll to `/api/state`, their `HttpOnly` cookie authenticates them immediately.
3. The server looks up their progress in SQLite and returns their current clue, cleared count, and active power-ups. The game continues seamlessly.

- **Where it lives:**
  - Persistent tables: `db.py` (`init_db`)
  - Device lookup: `db.py` (`get_team_by_id`, `get_team_cleared_checkpoints`)

---

## 11. Why did you write route endpoints with plain `def` instead of `async def` in FastAPI?

**Answer:**  
FastAPI is built on Python's asynchronous event loop (Starlette / AnyIO). 
- If you declare an endpoint with `async def`, FastAPI runs it directly on the main event loop thread. Any blocking operation (like file I/O or database calls) halts the entire event loop, freezing all other incoming requests.
- Python's standard library `sqlite3` driver is synchronous and blocks while reading or writing to disk.

By declaring route functions as plain `def`, FastAPI automatically offloads each request to an AnyIO **worker threadpool**. The blocking SQLite query runs on a background thread while the main event loop remains free to accept incoming network connections.

- **Where it lives:**
  - Route handlers: `main.py` (`healthz`, `ping_location`, `get_game_state`, etc.)

---

## 12. How do you prevent timing attacks on administrator login?

**Answer:**  
Standard Python string comparison (`a == b`) evaluates characters one by one and stops as soon as it finds the first mismatch. An attacker measuring HTTP response times down to microseconds could theoretically guess the admin password letter by letter based on how long the comparison took.

We use Python's standard `hmac.compare_digest(user_input, actual_pass)` in `auth.py`. It compares the strings in **constant time**, eliminating side-channel timing variations. Additionally, admin logins are throttled by an in-memory sliding-window rate limiter (default 5 attempts per minute per IP).

- **Where it lives:**
  - Constant-time verification: `auth.py` (`verify_admin_credentials`)
  - Rate limiting: `ratelimit.py` (`is_rate_limited`), `main.py` (`gods_login`)

---

## 13. Why are target checkpoint coordinates hidden from the player app?

**Answer:**  
Never trust the client. If the backend returned target coordinates or geofence radii in `GET /api/state`, any tech-savvy student could open Chrome DevTools, inspect the JSON response, and pin the exact location on Google Maps without solving the clue.

In Campus Quest, `GET /api/state` returns only the riddle text (`current_clue`). The physical coordinates (`lat`, `lng`, `radius`) are only revealed in API responses for checkpoints that have **already been unlocked**, allowing the Leaflet map to show green pins for places the team has already visited.

- **Where it lives:**
  - State response construction: `main.py` (`get_game_state`)
  - Secret retention: `db.py` (`get_team_cleared_checkpoints`)

---

## 14. Why are checkpoint coordinates locked once the game starts?

**Answer:**  
If an organizer could change a checkpoint's latitude, longitude, radius, or sequence order while teams are actively running around campus:
1. Teams currently walking to that spot would suddenly be looking in the wrong place.
2. Teams that already unlocked it might have cleared a completely different location than teams behind them.
3. Race conditions could occur if a team submitted a ping while an organizer edited coordinates.

Once `game_state` changes from `"setup"` to `"running"`, the server strictly rejects any `PUT` request that changes coordinates, radius, or route position with HTTP 400. However, organizers are still allowed to fix typos in the clue, hint, or story text without stopping the game.

- **Where it lives:**
  - Checkpoint update locking: `main.py` (`update_checkpoint`)

---

## 15. How does stuck-team recovery work?

**Answer:**  
Orientation games fail if a team gets hopelessly stuck on a riddle and gives up. We provide two safety valves:

1. **Player Skip (`/api/skip`)**:
   - The team must spend at least 10 minutes (`SKIP_WAIT_S = 600s`) on the current checkpoint. The server calculates this using the timestamp of their last unlock (or `started_at` for the first checkpoint).
   - If allowed, skipping adds a **+10 minute penalty** (`SKIP_PENALTY_S = 600s`) to `teams.penalty_s`, advances the team to the next clue, awards **no power-ups**, and records `how = 'skipped'` in the progress table for transparency.
2. **Admin Force-Clear (`/api/gods/teams/{id}/clear`)**:
   - If a student's GPS hardware is malfunctioning or a campus path is physically blocked, an organizer can force-clear the spot from `/gods`.
   - The organizer must provide a written reason (3 to 120 characters), which is recorded in the audit event log. No penalty is charged, no power-up is awarded, and `how = 'admin'` is logged.

- **Where it lives:**
  - Skip endpoint & time check: `main.py` (`skip_current_checkpoint`), `game.py` (`is_skip_allowed`)
  - Skip database transaction: `db.py` (`skip_checkpoint`)
  - Admin force-clear: `main.py` (`force_clear_gods_team_checkpoint`), `db.py` (`admin_force_clear_checkpoint`)

---

## 16. Why does the app need the Screen Wake Lock API, and how does it handle visibility changes?

**Answer:**  
Mobile operating systems automatically sleep the screen after 30 to 60 seconds to save power. When a phone locks or a browser tab is minimized, mobile browsers pause `navigator.geolocation` and throttle JavaScript timers. A team walking between checkpoints with their screen off would stop transmitting pings, meaning the geofence wouldn't unlock when they arrive.

We use the browser's `navigator.wakeLock.request('screen')` during active gameplay to keep the screen awake. Because mobile browsers release the wake lock whenever a user switches apps or minimizes the tab, we listen to the `document.addEventListener('visibilitychange')` event to automatically re-acquire the wake lock as soon as the tab becomes visible again. If the browser or battery saver rejects the wake lock, we display a calm banner reminding players to keep the screen on.

- **Where it lives:**
  - Client wake lock management: `static/app.js` (`requestWakeLock`, `handleVisibilityChange`)

---

## 17. What would you improve if you had more time?

**Answer:**  
If taking this project into production for a campus-wide event of 500+ students, I would make five key improvements:

1. **Balanced route groups**: Instead of having every team follow checkpoints in the same order (1..N), create 2 or 3 route sequences of equal walking distance (e.g. forward, reverse, alternating) assigned round-robin so teams do not crowd at the first few checkpoints.
2. **On-site QR codes or answer phrases**: Put physical QR codes or landmark answer riddles at each spot. Combining GPS geofencing with a physical code scan completely eliminates remote GPS spoofing.
3. **WebSockets for large-scale leaderboards**: Replace 5-second polling with a single WebSocket broadcast feed for the projector big screen and player standings when team counts grow into hundreds.
4. **PostgreSQL**: Switch from SQLite to PostgreSQL if the event scales to multiple simultaneous campuses or concurrent games.
5. **Real footpath routing**: Compute walking distances using OpenStreetMap pedestrian routing graphs instead of great-circle straight lines.

- **Where it lives:**
  - Documented in: `docs/PROJECT_DOC.md` (Section 8.9: Possible future improvements)
