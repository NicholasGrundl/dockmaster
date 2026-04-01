# Monitoring & Logs Guide

How to monitor dockmaster in production and work with its logs.

## Log Configuration

Dockmaster uses [structlog](https://www.structlog.org/) for structured logging.

| Setting | Env Var | Default | Description |
|---|---|---|---|
| `log_level` | `LOG_LEVEL` | `INFO` | Python log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `log_file` | `LOG_FILE` | *none* | Path to log file. When set, JSON logs are written here in addition to stdout |
| `log_file_max_bytes` | `LOG_FILE_MAX_BYTES` | `10485760` (10 MB) | Max file size before rotation |
| `log_file_backup_count` | `LOG_FILE_BACKUP_COUNT` | `5` | Number of rotated files to keep |

### Output Format

- **`DEBUG` level** (dev mode): Human-readable colored console output
- **`INFO`+ level** (prod mode): JSON lines, one object per log event
- **File output**: Always JSON, regardless of log level

### Docker Compose Setup

The default `.env.dockmaster.example` writes logs to `/data/logs/dockmaster.log`,
which maps to the `dockmaster-data` Docker volume.

```
LOG_FILE=/data/logs/dockmaster.log
LOG_FILE_MAX_BYTES=10485760
LOG_FILE_BACKUP_COUNT=5
```

This produces:
```
/data/logs/dockmaster.log       # current log (up to 10 MB)
/data/logs/dockmaster.log.1     # previous rotation
/data/logs/dockmaster.log.2     # ...
/data/logs/dockmaster.log.3
/data/logs/dockmaster.log.4
/data/logs/dockmaster.log.5     # oldest kept
```

Total max disk usage: ~60 MB (6 files x 10 MB).

---

## Viewing Live Logs

### Docker stdout (real-time)

```bash
# Follow live logs from the container
docker compose logs -f dockmaster

# Last 100 lines
docker compose logs --tail=100 dockmaster
```

Docker stdout shows the same structlog output (JSON in prod, colored in dev).

### Log files (inside the container)

```bash
# Read the current log file
docker compose exec dockmaster cat /data/logs/dockmaster.log

# Follow the log file in real-time
docker compose exec dockmaster tail -f /data/logs/dockmaster.log

# Last 50 lines
docker compose exec dockmaster tail -50 /data/logs/dockmaster.log
```

### Log files (from the host via Docker volume)

```bash
# Find where Docker stores the volume
docker volume inspect dockmaster_dockmaster-data | jq '.[0].Mountpoint'

# Then read directly (requires root on most setups)
sudo tail -f /var/lib/docker/volumes/dockmaster_dockmaster-data/_data/logs/dockmaster.log
```

---

## Parsing JSON Logs

Each log line is a JSON object. Use `jq` to filter and format:

```bash
# Pretty-print all logs
docker compose exec dockmaster cat /data/logs/dockmaster.log | jq .

# Filter by log level
docker compose exec dockmaster cat /data/logs/dockmaster.log | jq 'select(.level == "error")'

# Filter by event name
docker compose exec dockmaster cat /data/logs/dockmaster.log | jq 'select(.event == "starting up")'

# Show only timestamps and events
docker compose exec dockmaster cat /data/logs/dockmaster.log | jq '{timestamp, event, level}'

# Find auth failures
docker compose exec dockmaster cat /data/logs/dockmaster.log | jq 'select(.event | test("denied|unauthorized|forbidden"; "i"))'
```

### Common Log Events

| Event | Level | When |
|---|---|---|
| `starting up` | INFO | App startup — shows log_level and log_file path |
| `shutting down` | INFO | App shutdown |
| `sa_key_loaded` | INFO | SA key file loaded (shows email, key_id) |
| `sa_signer_initialized` | INFO | JWT signer ready |
| `token_issuer_initialized` | INFO | Ephemeral keypair generated (shows kid) |
| `oauth_client_initialized` | INFO | OAuth client configured |
| `secrets_storage_initialized` | INFO | Connected to Secret Manager |
| `rbac_authority_initialized` | INFO | RBAC engine ready (shows cache_ttl) |
| `session_store_initialized` | INFO | Session store backend |

---

## Health Check

```bash
# From the host
curl http://localhost:8001/auth/health

# From inside Docker network
docker compose exec dockmaster python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8001/auth/health').read().decode())"
```

Response: `{"service": "dockmaster", "status": "ok"}`

The Docker Compose healthcheck runs this automatically every 30 seconds.

---

## Monitoring Tips

### What to Watch

1. **Container restarts** — `docker compose ps` shows restart count. Frequent
   restarts indicate a crash loop (check logs for the error before shutdown).

2. **502 responses** — If you see 502s in Caddy logs, dockmaster's
   `RequireProxyHeadersMiddleware` is rejecting requests because
   `X-Forwarded-Proto` is missing. Check Caddy config.

3. **503 responses** — Dockmaster returns 503 when a required component isn't
   configured (e.g., `SA_KEY_FILE` missing, `SECRETS_PROJECT` missing,
   `ADMIN_SA_KEY_FILE` missing for write operations). Check startup logs to see
   which components initialized vs which emitted warnings.

4. **Disk usage** — Log rotation caps file logs at ~60 MB. Docker's own log
   driver also accumulates stdout logs. Configure Docker's json-file driver
   with max-size if needed:

   ```yaml
   # docker-compose.yml
   services:
     dockmaster:
       logging:
         driver: json-file
         options:
           max-size: "10m"
           max-file: "3"
   ```

### Caddy Access Logs

Caddy logs all proxied requests. Check these for HTTP-level issues:

```bash
sudo journalctl -u caddy -f
```

### Startup Verification Checklist

After deploying, check the startup log for these lines:

```bash
docker compose logs dockmaster | head -20
```

You should see:
- `starting up` with correct `log_level`
- `sa_key_loaded` (if SA_KEY_FILE is set)
- `token_issuer_initialized` (always — ephemeral keypair)
- `oauth_client_initialized` (if CLIENT_ID is set)
- `secrets_storage_initialized` (if SECRETS_PROJECT is set)
- `session_store_initialized` with `backend=in-memory`

Missing components log a WARNING with the impact (e.g., "OAuth login will return 503").
