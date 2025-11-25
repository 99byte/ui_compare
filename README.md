# Design Comparison Tool

A visual comparison tool for analyzing differences between design mockups and generated code using AI-powered image recognition.

## Architecture

- Backend: Python Flask API
- Frontend: Next.js + TypeScript + shadcn/ui

## Structure

```
ui_compare/
├─ backend/ (Flask API & dependencies)
├─ frontend/ (Next.js app & dependencies)
├─ output/ (runtime artifacts, ignored)
├─ start.sh (one-click start)
└─ .gitignore
```

## Features

- Upload JSON files containing UI component trees
- Visual comparison with colored bounding boxes (red for design, blue for code)
- Real-time metrics calculation (match rate, component count, completeness)
- AI-powered improvement suggestions

## Backend Setup
```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py                # http://localhost:5050
```

Health check: `GET http://localhost:5050/health`

## Frontend Setup
```bash
cd frontend
npm install
npm run dev                  # http://localhost:3000
```

The frontend calls `http://localhost:5050/api/compare`.

## One-Click Start
```bash
bash start.sh
```

## Outputs
- Backend writes intermediate artifacts to root `output/`.