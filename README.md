# Campus Quest

A geofenced clue hunt for the DAVV Takshashila Campus (GDGoC Technical Task 3).

## Stack

- **Backend**: Python 3.10+, FastAPI, Uvicorn (single worker)
- **Database**: SQLite3 (standard library, WAL mode)
- **Frontend**: Vanilla HTML5, CSS3, JavaScript (no frontend build step)
- **Map**: Leaflet with OpenStreetMap tiles

---

## Getting Started

### 1. Prerequisites

- Python 3.10+ installed
- Git

### 2. Installation

Clone the repository and set up a Python virtual environment:

```bash
# Clone repository
git clone https://github.com/manalpj/Campus-Quest.git
cd Campus-Quest

# Create and activate virtual environment
python -m venv .venv

# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt -r requirements-dev.txt
```

### 3. Environment Configuration

Copy the example environment file:

```bash
cp .env.example .env
```

Review `.env` to configure campus settings, ports, or secrets for your environment.

### 4. Running the Development Server

Start the FastAPI server:

```bash
uvicorn main:app --reload --port 8000
```

Open your browser at:
- **Player App / Home**: [http://localhost:8000/](http://localhost:8000/)
- **Health Check**: [http://localhost:8000/healthz](http://localhost:8000/healthz)
- **Public Config**: [http://localhost:8000/api/config](http://localhost:8000/api/config)
- **Interactive API Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)

### 5. Running Tests

Run the test suite with `pytest`:

```bash
pytest
```

### 6. Location Test Mode & Spoofing Limitations

For local development, automated verification, and demonstration walks, Campus Quest includes an optional location test mode:

1. **Enabling Test Mode**: Set `ALLOW_TEST_MODE=1` in your `.env` file. Organizers can then toggle test mode on or off from the **Game** tab in the admin panel (`/gods`).
2. **Simulating Locations**: When test mode is active on the server, a visible **TEST MODE** banner appears on all screens, and players can tap anywhere on the campus map to simulate their GPS location.
3. **Protection & Limitations**:
   - The server enforces test mode authorization: any ping sent with `test: true` while test mode is off is immediately rejected with `403 Forbidden` and audited in the event log.
   - **Important note on external spoofing**: This protection safeguards only the built-in app test feature. The server cannot verify physical device hardware or detect GPS spoofing performed outside the app (e.g., using third-party mock location apps or browser DevTools Sensors). Instead, server-side rules limit damage through speed plausibility limits, accuracy filters, hidden coordinates, and on-site organizers.

---

## Architecture Overview

- `main.py`: FastAPI application routes and middleware.
- `config.py`: Environment variable loading, typed configuration, and secret validation.
- `static/`: Static client assets (HTML, CSS, JS).
- `docs/`: Architectural specifications and technical briefs.