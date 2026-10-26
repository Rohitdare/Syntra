# Research Desk API

FastAPI backend service for Research Desk.

## Requirements

- Python 3.12 (see `.python-version`)

## Setup

```bash
# Create a virtual environment
python -m venv .venv

# Activate the virtual environment
# Windows (PowerShell):
.\.venv\Scripts\Activate.ps1
# Linux / macOS:
source .venv/bin/activate

# Upgrade pip and install dependencies
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

## Running Checks

Using `python -m <module>` ensures compatibility across environments and execution control policies:

```bash
# Linting
python -m ruff check .

# Format check
python -m ruff format --check .

# Type checking
python -m mypy src

# Tests
python -m pytest

# Dev server
python -m uvicorn research_desk.main:app --reload --port 8000
```
