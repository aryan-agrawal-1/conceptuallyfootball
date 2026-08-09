# Conceptually Football

Conceptually Football is a football data site aiming to make it easier to access and visualise football data from around the world in interesting ways as well as making it easy for people to create simple data graphics 

The project focuses on turning player, team, and league data into practical interactive tools: searchable stat tables, player profiles, team views, comparison tools, visual charts, regression experiments, and galaxy-style similarity maps. It is also designed to make it easy for people to create simple football data graphics without needing to manually collect or reshape the data.

Live site: [conceptuallyfootball.com](https://conceptuallyfootball.com/)

Copyright (C) 2026 Aryan Agrawal.

The project code is licensed under the GNU Affero General Public License, version 3 only. See [LICENSE](LICENSE) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for the project and third party asset notices.

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

## Season and Competition Operations

Competition seasons remain private until their current player materialisation rows come from a successful derived run. Publish or hide a ready slice intentionally with:

```bash
cd backend
python manage.py set_competition_season_publication <competition-season-id> --publish
python manage.py set_competition_season_publication <competition-season-id> --hide
```

Domestic aggregate scopes are derived from competitions marked as domestic and included in aggregates. Continental competitions are excluded from those aggregates. The default domestic eligibility threshold is 450 minutes; the initial UEFA threshold is 270 minutes (three full matches). Changing a competition threshold requires rerunning the versioned outfield, goalkeeper, and galaxy materialisations before publishing the slice.

Before a season rollover, run the read-only identity preflight and reconcile any reported provider IDs before ingestion:

```bash
cd backend
python manage.py diagnose_season_rollover <competition-season-id> --candidate-file path/to/candidate-teams.json --fail-on-anomaly
```

## Inviting editorial staff

Staff access is invite-only. After applying migrations, a superuser can open Django admin and add a record under **Staff access**. Enter the invitee's email, role, and a temporary password, then share those credentials with them securely.

Writers sign in at `/staff/login` and must replace the temporary password before `/analysis` becomes available. Use the same Staff access record to assign a new temporary password, revoke access, reactivate access, or change roles. Editorial writers and approvers do not receive Django `is_staff` access; operations users receive `is_staff` plus a separate operations permission.

## Status

This is an active project. APIs, ingestion commands, and data coverage may change as more competitions, seasons, and visualisation tools are added.

## Contributing

Any contributions are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) before opening an issue or pull request. All changes should be made on a branch and submitted through a pull request into `main`.
