#!/usr/bin/env bash
# scripts/docker_entrypoint.sh — runs as root at the start of every
# DFPos container to fix up volume permissions before the appuser
# process starts.
#
# Why: named volumes (like dfpos_audit_queue) are created by Docker
# with root ownership. When they are mounted onto a path that the
# appuser needs to write to, the first runtime write fails with
# EACCES. We can't chown at build time because the volume mount
# happens after the build, so we do it here.
set -euo pipefail

# Ensure the audit-queue directory exists and is writable by appuser.
# Idempotent: mkdir -p is a no-op if it already exists.
mkdir -p /app/uploads/audit-queue
chown -R appuser:appuser /app/uploads/audit-queue

# Make sure the rest of /app/uploads is also writable for the
# appuser, in case any other named volume was mounted here.
chown -R appuser:appuser /app/uploads

# Run the original CMD as the appuser so the process doesn't run as
# root. ``runuser`` is part of util-linux and is present in the
# Python-slim base image.
exec runuser -u appuser -- "$@"
