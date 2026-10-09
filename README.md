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

---

## Architecture Overview

- `main.py`: FastAPI application routes and middleware.
- `config.py`: Environment variable loading, typed configuration, and secret validation.
- `static/`: Static client assets (HTML, CSS, JS).
- `docs/`: Architectural specifications and technical briefs.