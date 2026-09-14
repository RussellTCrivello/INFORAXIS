# Deployment Guide

## Environments

The application supports three deployment environments, each with its own
configuration overlay in the `config/` directory.

| Environment | `FLASK_ENV` | Debug | Rate Limit | Use case |
|-------------|:-----------:|:-----:|:----------:|----------|
| Development | `development` | ✅ | 300/min | Local iteration |
| Staging | `staging` | ❌ | 120/min | Pre-production testing |
| Production | `production` | ❌ | 30/min | Live deployment |

Set the environment in `.env`:
```
FLASK_ENV=production
```

## Configuration Layers

Configuration is resolved with the following precedence (highest wins):

1. **OS environment variables** — always win
2. **`.env` file** — project-local, loaded at startup
3. **`config.json`** — structured JSON configuration
4. **`config/{env}.json`** — environment-specific overlay
5. **`config.example.json`** — project defaults
6. **Dataclass defaults** — built into source code

## Production Checklist

### Before deploying

- [ ] Set `FLASK_ENV=production` in `.env`
- [ ] Set `FLASK_DEBUG=false` in `.env`
- [ ] Generate a strong `FLASK_SECRET_KEY` (>= 64 hex characters)
- [ ] Set a strong `DB_PASSWORD`
- [ ] Set `APP_ADMIN_PASSWORD` or retrieve the generated one
- [ ] Review `INGESTION_ROOTS` — only allow directories that should be accessible
- [ ] Review rate limits in `config/production.json`
- [ ] Verify PostgreSQL is configured with appropriate authentication
- [ ] Ensure `.env` file has restricted permissions (600)
- [ ] Run `python verify_readiness.py` and confirm all checks pass

### Security settings (production defaults)

| Setting | Value | Rationale |
|---------|-------|-----------|
| `SECURITY_MAX_FAILED_LOGINS` | 3 | Stricter than dev/staging |
| `SECURITY_LOCKOUT_MINUTES` | 30 | Longer lockout period |
| `SECURITY_SESSION_HOURS` | 8 | Shorter session lifetime |
| `SECURITY_SESSION_IDLE_HOURS` | 2 | Shorter idle timeout |
| `RATE_LIMIT_PER_MINUTE` | 30 | Lower request rate |
| `RATE_LIMIT_PER_HOUR` | 300 | Lower hourly budget |
| `LOG_LEVEL` | WARNING | Reduce log verbosity |

### Network security

- Bind to `127.0.0.1` (not `0.0.0.0`) if the app should only be accessible locally
- Use a reverse proxy (nginx, Apache) for TLS termination
- Never expose port 5000 directly to the internet

### WSGI server

The built-in Flask server is for development only. For production:

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 "apps.web.app:app"
```

Or with uWSGI:
```bash
uwsgi --http 0.0.0.0:5000 --module apps.web.app --callable app --processes 4
```

## Docker deployment (outline)

```dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . .

# Configuration via environment variables
ENV FLASK_ENV=production
ENV FLASK_DEBUG=false

EXPOSE 5000
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "apps.web.app:app"]
```

```bash
docker build -t file-analysis .
docker run -d \
  -p 5000:5000 \
  -e DB_HOST=db \
  -e DB_PASSWORD=secret \
  --name file-analysis \
  file-analysis
```

## Backup and restore

### Database backup
```bash
pg_dump -U postgres -h localhost analysis > backup_$(date +%Y%m%d).sql
```

### Database restore
```bash
psql -U postgres -h localhost analysis < backup_20260101.sql
```

### Settings backup
Settings are stored in:
- `.env` — environment configuration
- `config.json` — JSON configuration
- `data/settings.json` — runtime settings (managed by app)
- `%LOCALAPPDATA%\file-analysis\config\` — persistent settings store

## Health check

The application exposes a health endpoint at `/health` that returns:
- `200` when the application is healthy
- `503` when the database is unreachable

Use this for load balancer health checks and monitoring.
