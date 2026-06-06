#!/bin/bash
set -e

# Mirror dashboard-ref-only's startup: create every directory hermes expects
# and seed a default config.yaml if the volume is empty. Without these,
# `hermes dashboard` endpoints that hit logs/, sessions/, cron/, etc. can fail
# with opaque errors even though no auth is actually involved.
mkdir -p /data/.hermes/cron /data/.hermes/sessions /data/.hermes/logs \
         /data/.hermes/memories /data/.hermes/skills /data/.hermes/pairing \
         /data/.hermes/hooks /data/.hermes/image_cache /data/.hermes/audio_cache \
         /data/.hermes/workspace /data/.hermes/skins /data/.hermes/plans \
         /data/.hermes/home

if [ ! -f /data/.hermes/config.yaml ] && [ -f /opt/hermes-agent/cli-config.yaml.example ]; then
  cp /opt/hermes-agent/cli-config.yaml.example /data/.hermes/config.yaml
fi

[ ! -f /data/.hermes/.env ] && touch /data/.hermes/.env

# Bootstrap OAuth tokens from env var (e.g. xAI Grok SuperGrok).
# Set HERMES_AUTH_JSON_BOOTSTRAP to the contents of a locally-generated
# ~/.hermes/auth.json. Written only once — subsequent token refreshes update
# the file in place on the persistent volume.
if [ ! -f /data/.hermes/auth.json ] && [ -n "${HERMES_AUTH_JSON_BOOTSTRAP}" ]; then
  printf '%s' "${HERMES_AUTH_JSON_BOOTSTRAP}" > /data/.hermes/auth.json
  chmod 600 /data/.hermes/auth.json
fi

# Clear any stale gateway PID file left over from the previous container.
# `hermes gateway` writes /data/.hermes/gateway.pid on start but does not
# remove it on SIGTERM. Since /data is a persistent volume, the file
# survives container restarts and causes every subsequent boot to exit with
# "ERROR gateway.run: PID file race lost to another gateway instance".
# No hermes process can be running at this point (we're pre-exec in a fresh
# container), so removing the file unconditionally is safe.
rm -f /data/.hermes/gateway.pid

# One-shot recovery from a corrupted /data/.hermes layout left by ad-hoc
# diagnostics on 2026-05-13: the sessions index was archived without restoring
# sessions.json. Hook quarantine below now validates hook syntax generically, so
# do not disable named hooks here; telegram-noreply-filter is an active
# production hook.
if [ ! -f /data/.hermes/sessions/sessions.json ] && \
   [ -f /data/.hermes/sessions/_archive_20260513/sessions.json.bak ]; then
  cp /data/.hermes/sessions/_archive_20260513/sessions.json.bak \
     /data/.hermes/sessions/sessions.json
fi

# Safety net for user hooks: a syntactically broken handler.py crashes
# gateway:startup and (depending on Hermes loader version) can block boot.
# Quarantine any handler.py that fails py_compile before Hermes loads it.
QUARANTINE="/data/.hermes/hooks/_failed_validation_$(date +%Y%m%d%H%M%S)"
for hook_dir in /data/.hermes/hooks/*/; do
  [ -d "$hook_dir" ] || continue
  case "$(basename "$hook_dir")" in
    _disabled_*|_failed_validation_*) continue ;;
  esac
  handler="$hook_dir/handler.py"
  if [ -f "$handler" ]; then
    if ! python3 -c "import py_compile,sys; py_compile.compile('$handler', doraise=True)" >/dev/null 2>&1; then
      mkdir -p "$QUARANTINE"
      mv "$hook_dir" "$QUARANTINE/" 2>/dev/null || true
      echo "[start.sh] quarantined broken hook: $(basename "$hook_dir") -> $QUARANTINE" >&2
    fi
  fi
done

# Dashboard watchdog: server.py's lifespan() is supposed to spawn `hermes dashboard`
# as a managed subprocess on 127.0.0.1:9119, but this has been observed to silently
# fail on some boot paths (no [dashboard] log lines, port 9119 never binds — leaving
# the reverse-proxy `/` returning 503 even after admin login). This safety net waits
# 30s for server.py to start, then if 9119 still isn't listening, spawns the
# subprocess ourselves. Idempotent: if server.py succeeded, the port check passes
# and we skip the spawn. Logs go to /data/.hermes/logs/dashboard.log for diagnostics.
(
  sleep 30
  if ! python3 -c "import socket; s=socket.socket(); s.settimeout(1); s.connect(('127.0.0.1', 9119))" 2>/dev/null; then
    echo "[start.sh watchdog] dashboard not listening on 9119 after 30s; spawning hermes dashboard" >&2
    mkdir -p /data/.hermes/logs
    nohup hermes dashboard --host 127.0.0.1 --port 9119 --no-open --skip-build </dev/null >>/data/.hermes/logs/dashboard.log 2>&1 &
    disown
  else
    echo "[start.sh watchdog] dashboard already listening on 9119; no-op" >&2
  fi
) &

exec python /app/server.py
