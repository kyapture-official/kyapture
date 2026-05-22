# KYAPTURE

Main folder.

## Current Status

This repository currently contains the folder/file structure only. The app logic has not been written yet.

## What To Install

- Python 3.12+
- Node.js 20+
- PostgreSQL
- Docker Desktop if you want to use `docker-compose.yml`

## Backend Setup

From `KYAPTURE/backend`:

In Terminal:
pip install -r requirements.txt


The current backend dependencies are:

- Django
- djangorestframework
- psycopg2-binary
- django-cors-headers
- djangorestframework-simplejwt

## Frontend Setup

From `KYAPTURE/frontend`:

In Terminal:
npm install


The frontend package file is currently only a scaffold, so add app dependencies as the UI is built.(David work)

## Team Workflow

Use one branch per task or feature. Nobody should work directly on `main`.

Suggested branch pattern:

- `feature/<short-name>` for new work
- `fix/<short-name>` for bug fixes
- `chore/<short-name>` for setup or cleanup

For a 3-person team:

- Senior dev Mausam dai reviews pull requests and guards `main`.
- Kroman and David work on separate branches.
- Merge only after review and a clean pull from `main`.

Recommended flow:

1. Start with `git pull origin main`.
2. Create a feature branch.
3. Work only in that branch.
4. Commit small changes often.
5. Push your branch.
6. Open a pull request.
7. Pull latest `main` again before starting the next task.

To avoid conflicts:

- Keep each task small.
- Do not edit the same file at the same time.
- Pull before we start and before we push.
- If two people need the same file, we should decide the order first.

Pull request checklist:

- Branch is up to date with `main`.
- Changes match the assigned task.
- No unrelated files are included.
- README is updated if setup or workflow changed.
- At least one person reviews before merge.(It's imp)

## Connection Between Parts

- `backend/` is for Django API, database models, and server logic.
- `frontend/` is for the React interface.
- `docker-compose.yml` is for running backend, frontend, and PostgreSQL together later.
- `.env` files hold secret values and must not be committed.

## Next Step

When development starts, kroman will add the real backend apps, David will add frontend dependencies, and environment values, then update this README with exact run commands.
