#!/usr/bin/env bash

set -Eeuo pipefail

readonly REPO_DIR="/var/www/conceptuallyfootball"
readonly BACKEND_DIR="$REPO_DIR/backend"
readonly WEB_DIR="$REPO_DIR/web"
readonly BACKUP_DIR="/var/backups/statballer"
readonly DATABASE_NAME="statballer"
readonly BACKUP_PATH="$BACKUP_DIR/pre-deploy-$(date -u +%Y%m%dT%H%M%SZ).dump"
readonly SERVICES=(
  statballer-web
  statballer-celery-ingestion
  statballer-celery-planner
  statballer-celery-beat
)

services_stopped=0
deployment_succeeded=0
backup_created=0

log() {
  printf '\n==> %s\n' "$1"
}

start_services() {
  if systemctl start "${SERVICES[@]}"; then
    services_stopped=0
    return 0
  fi

  return 1
}

handle_exit() {
  exit_code=$?

  if (( exit_code != 0 )) && (( services_stopped == 1 )); then
    printf '\nDeployment failed; attempting to restore application services.\n' >&2
    start_services || printf 'WARNING: one or more services could not be restarted.\n' >&2
  fi

  if (( deployment_succeeded == 0 )) && (( backup_created == 1 )); then
    printf 'The new backup has been retained at %s\n' "$BACKUP_PATH" >&2
  fi

  exit "$exit_code"
}

trap handle_exit EXIT

if (( EUID != 0 )); then
  printf 'Run this script as root.\n' >&2
  exit 1
fi

if [[ ! -d "$REPO_DIR/.git" ]]; then
  printf 'Repository not found at %s\n' "$REPO_DIR" >&2
  exit 1
fi

cd "$REPO_DIR"
if [[ -n "$(git status --porcelain --untracked-files=normal)" ]]; then
  printf 'Refusing to deploy with local repository changes:\n' >&2
  git status --short >&2
  exit 1
fi

log "Creating and validating PostgreSQL backup"
install -d -m 700 -o postgres -g postgres "$BACKUP_DIR"
sudo -u postgres pg_dump --format=custom --file="$BACKUP_PATH" "$DATABASE_NAME"
backup_created=1
sudo -u postgres pg_restore --list "$BACKUP_PATH" >/dev/null
ls -lh "$BACKUP_PATH"

log "Stopping application services"
systemctl stop statballer-celery-beat
systemctl stop statballer-celery-planner
systemctl stop statballer-celery-ingestion
systemctl stop statballer-web
services_stopped=1

log "Updating main"
git fetch origin
git checkout main
git pull --ff-only origin main

log "Updating and checking the backend"
cd "$BACKEND_DIR"
venv/bin/python -m pip install -r requirements.txt
venv/bin/python manage.py check
venv/bin/python manage.py migrate
venv/bin/python manage.py collectstatic --noinput

log "Installing and building the frontend"
cd "$WEB_DIR"
npm ci
npm run build

log "Seeding and checking competition slices"
cd "$BACKEND_DIR"
venv/bin/python manage.py seed_competition_slices
venv/bin/python manage.py check
venv/bin/python manage.py shell -c "from ingestion.models import CompetitionSeason; [print(cs.id, cs.competition.short_code, cs.season.label, cs.is_published, cs.refresh_enabled) for cs in CompetitionSeason.objects.select_related('competition','season').filter(refresh_enabled=True).order_by('competition__short_code')]"

log "Planning the daily refresh"
venv/bin/python manage.py orchestrate_daily_refresh --no-jitter

log "Starting application services"
start_services

log "Validating and reloading Nginx"
nginx -t
systemctl reload nginx

log "Checking service status"
systemctl status statballer-web --no-pager
systemctl status statballer-celery-ingestion --no-pager
systemctl status statballer-celery-planner --no-pager
systemctl status statballer-celery-beat --no-pager

log "Removing superseded deployment backups"
find "$BACKUP_DIR" -maxdepth 1 -type f -name 'pre-deploy-*.dump' ! -path "$BACKUP_PATH" -delete

deployment_succeeded=1
log "Deployment completed successfully"
printf 'Current backup: %s\n' "$BACKUP_PATH"
