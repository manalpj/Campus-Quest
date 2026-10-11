# Campus Quest: Demo Video Script (2 - 3 Minutes)

This script follows **PROJECT_DOC.md (Section 8.7)**. It includes timestamps, visual actions, and word-for-word spoken narration.

> **Important Rule from Spec:** The video must explicitly state out loud when test mode is being used versus real walking.

---

## Timing Overview
- **Total Duration:** ~2 minutes 45 seconds (165 seconds)
- **Scene 1: Introduction** (0:00 - 0:15 | 15s)
- **Scene 2: Admin Dashboard Setup** (0:15 - 0:45 | 30s)
- **Scene 3: Team Registration & Device Lock** (0:45 - 1:05 | 20s)
- **Scene 4: Live Gameplay & Geofencing** (1:05 - 2:05 | 60s)
- **Scene 5: Control, Recovery & Leaderboard** (2:05 - 2:35 | 30s)
- **Scene 6: Architecture Takeaway & Close** (2:35 - 2:50 | 15s)

---

## Scene-by-Scene Breakdown

### Scene 1: Introduction (0:00 - 0:15 | 15s)
* **Visual:**
  * Screen recording starts showing the clean mobile landing screen of Campus Quest running live on HTTPS.
* **Narration (Spoken Aloud):**
  > "Hi! This is **Campus Quest**, a real-time geofenced clue hunt built for students on the IET-DAVV campus for GDGoC. Teams solve cryptic campus clues, navigate to physical locations using real GPS fixes, and unlock checkpoints as they explore."

---

### Scene 2: Admin Dashboard Setup (0:15 - 0:45 | 30s)
* **Visual:**
  * Switch to desktop view at `/gods`.
  * Log in with admin credentials.
  * Click on the interactive Leaflet map near an academic block.
  * Form autofills coordinates; type name "A-Block", clue, hint, and radius (30m). Save checkpoint.
  * Show the checkpoint appearing on the admin live map.
* **Narration (Spoken Aloud):**
  > "Organizers manage the entire quest at `/gods`. Here, an organizer can inspect existing checkpoints or click anywhere on the campus map to create a new one. I'll set a 30-meter radius, enter our clue and hint, and click save. The server validates the boundaries and stores it in SQLite with an immediate transaction."

---

### Scene 3: Team Registration & Device Lock (0:45 - 1:05 | 20s)
* **Visual:**
  * Switch to mobile view (Phone screen or responsive mobile emulator at 360px).
  * Go to `/` and click "Join Quest".
  * Enter Team Name: `Byte Builders` and member names `Aarav, Priya`. Submit.
  * Team dashboard loads showing Checkpoint 1 clue.
  * Show a second incognito tab attempting to join as `Byte Builders`, showing the error: *"Already in play on another device"*.
* **Narration (Spoken Aloud):**
  > "Back on a student's phone, the team registers with their member names. The server issues a secure HttpOnly cookie containing a hashed session token. If another phone tries to log in as the same team, the server rejects it. One team, one device."

---

### Scene 4: Live Gameplay & Geofencing (1:05 - 2:05 | 60s)
* **Visual:**
  * Mobile game screen showing the clue: *"I speak in gears, bolts, and motion..."*.
  * **Test Mode Announcement:** Toggle test mode bar or mock location point outside the zone first (e.g. 150m away). Show radar distance and accuracy indicator `GPS ±12m`. Show lock button disabled or distance remaining.
  * Send weak GPS fix (accuracy > 30m) or point outside: alert shows *"Position too uncertain"* or *"Outside zone"*.
  * Now set mock point inside the 30m zone (or show a real physical walk into A-Block zone).
  * Two consecutive inside fixes register; the phone plays the unlock animation, reveals the story modal, awards 100 base points, and unlocks Checkpoint 2!
  * Tap the Power-Ups button. Show the newly earned **Radius Boost** (+20m) and activate it.
* **Narration (Spoken Aloud):**
  > *"For this next demonstration, I am using test mode coordinates to show how the server enforces geofencing rules."*
  >
  > "First, notice what happens when our simulated GPS point is 150 meters away: the checkpoint stays locked, because the client cannot force an unlock. If a GPS fix is reported with poor accuracy worse than 30 meters, the server filters it out as noise.
  >
  > Now, moving our coordinates inside the 30-meter radius: once two consecutive stable fixes arrive, the server confirms entry! Checkpoint 1 unlocks, displaying the history story and awarding our first power-up. I'll activate our Radius Boost, expanding our next capture zone by 20 meters."

---

### Scene 5: Control, Recovery & Leaderboard (2:05 - 2:35 | 30s)
* **Visual:**
  * Switch to `/board` (Big Screen Leaderboard). Show live ranking with `Byte Builders` on the board.
  * Return to phone: show the "Stuck? Skip Checkpoint" button, with its countdown timer and +10 min penalty label.
  * Quick cut to admin `/gods` Teams tab: show the "Force Clear" button used by organizers if a team has physical issues.
* **Narration (Spoken Aloud):**
  > "On the big screen at `/board`, the live leaderboard ranks teams by completion time and penalties. If a team gets stuck, the system offers built-in resilience: teams can use the Skip button after a 10-minute wait for a time penalty, or organizers can force-clear from the admin panel if there is physical access trouble. Every recovery action is logged to the server audit table."

---

### Scene 6: Architecture Takeaway & Close (2:35 - 2:50 | 15s)
* **Visual:**
  * Final slide or split screen showing mobile UI side-by-side with the GitHub repo architecture diagram (`game.py` -> pure logic, `db.py` -> transactions, `main.py` -> endpoints).
* **Narration (Spoken Aloud):**
  > "The most important engineering decision in Campus Quest is zero client trust: **the server decides everything; the phone only reports location**. Thank you for watching!"

---

## Recording Checklist for the Presenter
- [ ] Test audio levels and microphone clarity before recording.
- [ ] Keep phone layout at 360px width or record directly on a physical phone.
- [ ] Clearly pronounce the test mode disclaimer during Scene 4.
- [ ] Verify total length is strictly between 2:00 and 3:00 minutes.
- [ ] Set video sharing permissions to "Anyone with the link can view".
