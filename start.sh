#!/bin/bash
set -e

# Mirror dashboard-ref-only's startup: create every directory hermes expects
# and seed a default config.yaml if the volume is empty. Without these,
# `hermes dashboard` endpoints that hit logs/, sessions/, cron/, etc. can fail
# with opaque errors even though no auth is actually involved.
mkdir -p /data/.hermes/cron /data/.hermes/sessions /data/.hermes/logs \
         /data/.hermes/memories /data/.hermes/skills /data/.hermes/pairing \
         /data/.hermes/hooks /data/.hermes/image_cache /data/.hermes/audio_cache \
         /data/.hermes/workspace

if [ ! -f /data/.hermes/config.yaml ] && [ -f /opt/hermes-agent/cli-config.yaml.example ]; then
  cp /opt/hermes-agent/cli-config.yaml.example /data/.hermes/config.yaml
fi

[ ! -f /data/.hermes/.env ] && touch /data/.hermes/.env

# Clear any stale gateway PID file left over from the previous container.
# `hermes gateway` writes /data/.hermes/gateway.pid on start but does not
# remove it on SIGTERM. Since /data is a persistent volume, the file
# survives container restarts and causes every subsequent boot to exit with
# "ERROR gateway.run: PID file race lost to another gateway instance".
# No hermes process can be running at this point (we're pre-exec in a fresh
# container), so removing the file unconditionally is safe.
rm -f /data/.hermes/gateway.pid

# One-shot recovery from a corrupted /data/.hermes layout left by ad-hoc
# diagnostics on 2026-05-13: an experimental hooks/telegram-noreply-filter
# directory caused gateway:startup to crash, and sessions index was archived
# without restoring sessions.json — both block boot. Idempotent: no-op once
# volume is healthy. Safe to leave in start.sh permanently.
if [ -d /data/.hermes/hooks/telegram-noreply-filter ]; then
  mkdir -p /data/.hermes/hooks/_disabled_20260513
  mv /data/.hermes/hooks/telegram-noreply-filter \
     /data/.hermes/hooks/_disabled_20260513/ 2>/dev/null || true
fi
if [ ! -f /data/.hermes/sessions/sessions.json ] && \
   [ -f /data/.hermes/sessions/_archive_20260513/sessions.json.bak ]; then
  cp /data/.hermes/sessions/_archive_20260513/sessions.json.bak \
     /data/.hermes/sessions/sessions.json
fi

exec python /app/server.py
