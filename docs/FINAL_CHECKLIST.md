# Campus Quest: Final Submission & Pre-Event Checklist

This checklist combines the core task requirements from **PROJECT_DOC.md (Section 8.8)** with crucial operational, deployment, and testing checkpoints required before final submission and before running the live campus event.

---

## 1. Project & Repository Hygiene

- [ ] **GitHub Repository Public & Accessible**: Repository is public or viewable by anyone with the link.
- [ ] **Comprehensive README**: Covers project overview, how it works, architecture (`game.py` / `db.py` / `main.py`), setup instructions, design decisions, and limitations.
- [ ] **Zero Exposed Secrets**:
  - [ ] No passwords, cookies, session hashes, or secret keys committed to Git.
  - [ ] `.env` is ignored by `.gitignore`; only `.env.example` is committed.
  - [ ] Production credentials (`ADMIN_PASS`, `SECRET_KEY`) do not use default or `change-me` placeholders.
- [ ] **Test Suite Green**: Full test suite passes cleanly (`pytest`) with no regressions.

---

## 2. Railway Production Deployment & Infrastructure

- [ ] **Railway Service Live**: FastAPI web service is running and accessible over HTTPS.
- [ ] **Environment Variables Configured in Railway**:
  - [ ] `ENV=production` set.
  - [ ] `ADMIN_USER` and strong `ADMIN_PASS` set (no `change-me`).
  - [ ] `SECRET_KEY` set to a securely generated 32-byte hex token.
  - [ ] `FORWARDED_ALLOW_IPS=*` configured so Uvicorn trusts Railway's reverse proxy headers and client IP rate limiting works per mobile device.
  - [ ] `ALLOW_TEST_MODE=false` configured for the real event (strict GPS geofencing only).
- [ ] **Persistent Volume Attached**:
  - [ ] Railway volume mounted at `/data`.
  - [ ] `DB_PATH=/data/quest.db` verified so database state survives restarts.
- [ ] **Persistence Verification Test**:
  - [ ] Create a test team or checkpoint in production.
  - [ ] Trigger a manual redeploy from the Railway dashboard.
  - [ ] Reload the app and verify that team progress, checkpoints, and event logs remain intact.
- [ ] **Map Tiles Tested on Mobile**:
  - [ ] `TILE_URL` loads quickly and reliably on mobile Safari and mobile Chrome without broken tiles or CORS/Referrer policy blocks.

---

## 3. Real-World & Field Testing

- [ ] **Two-Phone Simultaneous Dry Run**:
  - [ ] Phone A and Phone B register different teams (`Team Alpha`, `Team Beta`).
  - [ ] Verify that Phone A cannot control or read Phone B's session.
  - [ ] Verify that opening the same team on a second device is rejected with device binding alert ("Already in play on another device").
  - [ ] Verify live leaderboard (`/board`) updates correctly as each phone makes progress.
- [ ] **On-Campus Walk Verification**:
  - [ ] Walk all 6 checkpoints on the IET-DAVV campus using a phone on mobile data.
  - [ ] Confirm GPS lock and accuracy circle on Leaflet map.
  - [ ] Confirm entry detection: unlock triggers smoothly when within 30m radius after 2 consecutive fixes.
  - [ ] Confirm no checkpoints placed on inaccessible private areas, busy roads, or upper floors.
- [ ] **Power-Ups and Recovery Checks**:
  - [ ] Radar power-up reveals distance and direction on compass.
  - [ ] Radius Boost expands capture circle by 20m.
  - [ ] Clue Hint adds 3-minute time penalty.
  - [ ] Skip button functions after the 10-minute wait window (or admin force-clear from `/gods`).

---

## 4. Final Submission Deliverables

- [ ] **Demo Video Uploaded**:
  - [ ] 2 to 3 minute demo recorded following `docs/DEMO_SCRIPT.md`.
  - [ ] Video uploaded (YouTube / Google Drive) and sharing permissions set to **"Anyone with the link can view"**.
  - [ ] Spoken audio clearly announces test mode versus live walk segments.
- [ ] **Incognito Link Verification**:
  - [ ] GitHub repository URL opens in an incognito/private browser tab.
  - [ ] Live Railway web application URL opens in an incognito tab.
  - [ ] Demo video URL opens and plays without login in an incognito tab.
- [ ] **Submission Document Formatted & Named**:
  - [ ] Document named exactly: `YourName_TechnicalTask2026.pdf` (or `.docx`).
  - [ ] Contains all three verified links:
    1. GitHub Repository Link
    2. Live Prototype Link (Railway)
    3. Demo Video Link
- [ ] **Google Form Submission**:
  - [ ] Document submitted through the official GDGoC DAVV recruitment Google Form before the deadline.
  - [ ] Railway service confirmed running and volume kept active through interview evaluations (post Oct 20).

---

## 5. Interview Readiness

- [ ] **Core Architectural Principle**: Ready to articulate clearly:
  > *"The server decides everything; the phone only reports location."*
- [ ] **Line-by-Line Ownership**: Can explain every line in `game.py` (pure logic), `db.py` (atomic transactions), and `main.py` (HTTP endpoints).
- [ ] **Key Questions Prepared**: Re-read `docs/NOTES.md` and Section 8.10 of `PROJECT_DOC.md` for Haversine, GPS noise handling, cookie token hashing, and concurrency safety.
