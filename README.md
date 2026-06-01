# Conceptually Football

Conceptually Football is a football data site aiming to make it easier to access and visualise football data from around the world in interesting ways as well as making it easy for people to create simple data graphics 

The project focuses on turning player, team, and league data into practical interactive tools: searchable stat tables, player profiles, team views, comparison tools, visual charts, regression experiments, and galaxy-style similarity maps. It is also designed to make it easy for people to create simple football data graphics without needing to manually collect or reshape the data.

Live site: [conceptuallyfootball.com](https://conceptuallyfootball.com/)

## Features

- Player and team stat matrices by competition and season
- Player profile pages with percentile views and stat sections
- Team profile pages and squad views
- Player comparison tools
- Data visualiser for quick charts and shareable graphics
- Regression lab for exploring relationships between football metrics
- Galaxy view for visualising player similarity and archetypes
- Backend ingestion pipeline for collecting, merging, and materialising football data

## Tech Stack

- Frontend: React, TypeScript, Vite, Tailwind CSS
- Backend: Django, Django REST Framework
- Data processing: Python, scikit-learn, UMAP
- Workers: Celery with Redis
- Database: PostgreSQL in normal development/production, with SQLite support for local-only workflows

## Repository Structure

```text
backend/   Django API, ingestion pipeline, derived stats, and tests
web/       React/Vite frontend
scripts/   Utility scripts for maintenance tasks
src/       Local/private source data workspace, ignored by Git
docs/      Project documentation
```

## Local Development

Create the backend environment:

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py runserver
```

Run the frontend:

```bash
cd web
npm install
npm run dev
```

The frontend dev server proxies API requests to the Django backend at `http://localhost:8000`.

## Environment

Runtime configuration lives in environment variables. Use `backend/.env.example` as the starting point for local development.

The frontend accepts `VITE_GA_MEASUREMENT_ID` for Google Analytics. Set this only in the production frontend environment so local development does not send analytics events.

Do not commit real secrets, local databases, private CSVs, generated reports, or deployment runbooks. The repository ignore rules are configured to keep those local-only files out of Git.

## Data

This repository contains the application code and public frontend assets. Some local data inputs and generated outputs are intentionally excluded from Git because they may be large, private, provider-specific, or environment-specific.

## Status

This is an active project. APIs, ingestion commands, and data coverage may change as more competitions, seasons, and visualisation tools are added.
