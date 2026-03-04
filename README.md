# Orchestrator

## Run With Docker

1. Build and start services:

```bash
docker compose up --build
```

2. Open apps:
- Frontend: http://localhost:13000
- Backend API: http://localhost:18000
- Backend health: http://localhost:18000/healthz

3. Stop services:

```bash
docker compose down
```

## Notes

- Backend uses `repos.docker.yaml` inside containers (`REPOS_CONFIG_PATH=/workspace/repos.docker.yaml`).
- Dev auth token defaults to `orchestrator-dev-token`.
- Override host ports if needed:

```bash
ORCHESTRATOR_FRONTEND_PORT=3000 ORCHESTRATOR_BACKEND_PORT=8000 docker compose up --build
```
- For PR creation from the backend container, run `gh auth login` inside the container:

```bash
docker compose exec backend gh auth login
```
