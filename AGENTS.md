# Campus Quest: agent rules

Project: a geofenced clue hunt for the DAVV campus (GDGoC Technical task 3).
Spec: @docs/PROJECT_DOC.md  Design: @docs/DESIGN_BRIEF.md  References: @docs/REFERENCES.md

## Who you are working with
The owner is a first-year student who must explain every line in an interview.
Clear and simple beats clever. If you are about to add something the task does not ask for, stop and ask.

## Workflow for every task (do not skip steps)
1. Read the attached files and the relevant existing code.
2. Reply with a short plan: files to create or change, endpoints, edge cases, anything unclear. Ask questions. Do NOT write code yet.
3. Wait for me to say "approved".
4. Implement only what the task asks. Do not build features from later tasks.
5. Write or update tests for the logic you touched and run them.
6. Tell me how to run it and what I should check by hand.
7. Explain the change as I would in an interview: 5 plain lines, then 2 questions an interviewer might ask, with short answers. Append this to docs/NOTES.md under the task name.
8. Suggest one commit message (conventional commits). Do not commit unless I ask.

## Stack (fixed)
Python 3, FastAPI, uvicorn (one worker), sqlite3 from the standard library, vanilla JavaScript, Leaflet, no frontend build step. No new dependency without asking me first.

## Architecture rules
- The server decides everything. The client sends only its position and button presses. Never trust client state.
- game.py holds pure logic (no HTTP, no SQL). db.py holds every SQL statement (parameterised). main.py holds routes.
- Endpoints are plain def, not async def, because sqlite3 blocks.
- All time comes from the server clock.
- Check-then-insert writes use BEGIN IMMEDIATE (db.write_tx).
- Configuration comes from environment variables through config.py. Never hard-code secrets, tile URLs or campus coordinates.
- Never return uncleared checkpoint coordinates, radii or distances (except Radar while it is active).

## Code style
- Small functions, clear names, a comment explaining WHY for every non-obvious rule.
- No dead code. No TODO left behind without telling me.
- Validate every input (pydantic models, ranges, length limits).

## Safety
- Never read, print or commit .env. Only edit .env.example.
- Never run destructive commands (delete, force push, reset --hard, clean) without asking me.
- No analytics, trackers or third-party scripts other than Leaflet and the map tiles.
- Keep every response header compatible with OpenStreetMap tiles: never use Referrer-Policy no-referrer.