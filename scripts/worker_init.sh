#!/usr/bin/env bash
# scripts/worker_init.sh — DEPRECATED.
#
# The audit deadman replay is now wired into celery_app.py via a
# ``worker_ready`` signal handler, so the worker self-replays any
# deadman'd events when it boots. This script is kept for manual
# debugging: ``docker exec dfpos-worker-1 /app/scripts/worker_init.sh``
# will trigger the replay on demand.
set -euo pipefail

exec /opt/venv/bin/celery \
    -A app.celery_app.celery \
    call app.tasks.audit_outbox.replay_deadman
