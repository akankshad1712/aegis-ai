# AEGIS AI deployment starter pack

This pack adds Docker packaging and GitHub Actions CI around your existing AEGIS AI source. It does not include or replace your application code.

## Copy these files into your project root

- `Dockerfile`
- `.dockerignore`
- `docker-compose.yml`
- `requirements.txt` (merge with your current dependencies if you have additional packages)
- `.github/workflows/ci.yml`

Apply the one-line `DB_PATH` environment override described in `DB_PATH_PATCH.txt` to `app/db.py`. This allows SQLite data to persist in the Docker named volume at `/data/aegis.db` while keeping the existing local default path.

## Run locally first (PowerShell)

```powershell
python -m pip install -r requirements.txt
python -m py_compile app\main.py app\db.py
python -m pytest -q
```

## Build and run with Docker Desktop

```powershell
docker compose up --build -d
docker compose ps
docker compose logs -f aegis-api
```

Open `http://localhost:8000/` and `http://localhost:8000/api/health`.

Stop the service:

```powershell
docker compose down
```

The named volume preserves the SQLite database when the container is recreated. `docker compose down -v` deletes the volume and its stored database, so do not run that unless you intend to reset the data.

## CI

Copy `.github/workflows/ci.yml` to your GitHub repository. Every push and pull request will install dependencies, compile Python files, and run pytest. GitHub Actions will only work after the project is pushed to GitHub.

## Security and scope

- This container setup does not itself add user authentication.
- Keep `.env` and credentials out of Git.
- The recovery actions remain simulations only.
- For public production deployment, add real authentication, HTTPS, trusted proxy configuration, backups, and a persistent database strategy before exposing write endpoints.
