# AI Debugging Assistant for Legacy Codebases

🚀 AI-powered backend system that analyzes errors, detects recurring issues, and provides system-level debugging insights.

## Features

- Debug API for code + error analysis
- Error fingerprinting to detect recurring issues
- Context-aware debugging using history
- Analytics endpoint for debugging trends
- AI-generated insights

## Tech Stack

- Python
- FastAPI
- OpenAI API

## Endpoints

- POST /debug
- GET /history
- GET /analytics
- GET /insights

## Run locally

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload