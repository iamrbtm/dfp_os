#!/usr/bin/env bash
set -euo pipefail

# ──────────────────────────────────────────────
# deploy.sh — deploy DFPos to breath.local
# Usage: ./deploy.sh [--skip-build] [--dry-run]
# ──────────────────────────────────────────────

SCRIPT_NAME=$(basename "$0")
REMOTE_HOST="breath.local"
REMOTE_USER="rbtm2006"
REMOTE_DIR="/mnt/storage/docker/dfpos"
LOCAL_ENV_FILE=".env"
RSYNC_EXCLUDES=(
  --exclude '.venv'
  --exclude 'node_modules'
  --exclude '.git'
  --exclude 'uploads'
  --exclude '__pycache__'
  --exclude '*.pyc'
  --exclude '.DS_Store'
  --exclude '.env'
)

SKIP_BUILD=false
DRY_RUN=false

for arg in "$@"; do
  case "$arg" in
    --skip-build) SKIP_BUILD=true ;;
    --dry-run)    DRY_RUN=true ;;
    --help)
      echo "Usage: $SCRIPT_NAME [--skip-build] [--dry-run]"
      exit 0
      ;;
  esac
done

info()  { printf "\033[36m▶\033[0m %s\n" "$*"; }
ok()    { printf "\033[32m✔\033[0m %s\n" "$*"; }
err()   { printf "\033[31m✘\033[0m %s\n" "$*" >&2; }

SSH_CMD="ssh ${REMOTE_USER}@${REMOTE_HOST}"

# ── Phase 0: Preflight ───────────────────────

info "Preflight checks..."

if [ ! -f "$LOCAL_ENV_FILE" ]; then
  err "$LOCAL_ENV_FILE not found. Create it from .env.example first."
  exit 1
fi

if ! ssh -q -o ConnectTimeout=5 -o BatchMode=yes "${REMOTE_USER}@${REMOTE_HOST}" exit 2>/dev/null; then
  err "Cannot connect to ${REMOTE_HOST}. Check:"
  err "  • Is the host reachable?  ping ${REMOTE_HOST}"
  err "  • SSH key added?         ssh ${REMOTE_USER}@${REMOTE_HOST}"
  exit 1
fi

if ! ${SSH_CMD} "docker info" >/dev/null 2>&1; then
  err "Docker is not accessible (without sudo) on ${REMOTE_HOST}."
  err "Fix: ${SSH_CMD} sudo usermod -aG docker ${REMOTE_USER}   then log out and back in."
  exit 1
fi

ok "All preflight checks passed."

# ── Phase 1: Copy files ──────────────────────

info "Checking remote deploy directory..."
if ${SSH_CMD} "test -d ${REMOTE_DIR} && test -w ${REMOTE_DIR}"; then
  ok "Remote deploy directory is ready."
else
  info "Remote deploy directory needs setup. Sudo may prompt once."
  # -t flag needed here because sudo on breath requires a TTY
  ssh -t "${REMOTE_USER}@${REMOTE_HOST}" "sudo mkdir -p ${REMOTE_DIR} && sudo chown ${REMOTE_USER}:${REMOTE_USER} ${REMOTE_DIR} && test -w ${REMOTE_DIR}"
  ok "Remote deploy directory created and assigned to ${REMOTE_USER}."
fi

if [ "$DRY_RUN" = true ]; then
  info "[DRY-RUN] Would rsync project to ${REMOTE_HOST}:${REMOTE_DIR}"
  rsync --dry-run -avz --delete --checksum "${RSYNC_EXCLUDES[@]}" ./ "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/"
  info "[DRY-RUN] Done. No files were transferred."
  exit 0
fi

info "Rsyncing project files to ${REMOTE_HOST}:${REMOTE_DIR}..."
rsync -avz --delete --checksum "${RSYNC_EXCLUDES[@]}" ./ "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/"
ok "Project files synced."

info "Copying .env files..."
scp "$LOCAL_ENV_FILE" "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/.env"

# Copy all service-specific .env files (audit-log, api-docs, etc.)
# Ensure each service has a .env file (create from .env.example if missing)
for svc_dir in services/*/; do
  [ -d "$svc_dir" ] || continue
  svc_name=$(basename "$svc_dir")
  local_env="${svc_dir}.env"
  example_env="${svc_dir}.env.example"

  if [ ! -f "$local_env" ] && [ -f "$example_env" ]; then
    info "Creating ${local_env} from ${example_env}"
    cp "$example_env" "$local_env"
  fi

  if [ -f "$local_env" ]; then
    target_dir="${REMOTE_DIR}/${svc_dir}"
    ${SSH_CMD} "mkdir -p ${target_dir}"
    scp "$local_env" "${REMOTE_USER}@${REMOTE_HOST}:${target_dir}/.env"
    ok "Copied ${svc_name} .env"
  else
    info "Skipping ${svc_name}: no .env or .env.example found"
  fi
done

ok ".env files copied."

# ── Phase 2: Build and restart ───────────────

if [ "$SKIP_BUILD" = true ]; then
  info "Skipping Docker build (--skip-build)."
  info "Run 'docker compose up -d' manually on breath if needed."
  exit 0
fi

info "Building and restarting on ${REMOTE_HOST}..."

${SSH_CMD} bash -s -- "${REMOTE_DIR}" <<-'REMOTECMD'
  set -euo pipefail
  DIR="$1"
  cd "${DIR}"

  echo "  → Building images..."
  docker compose build --pull 2>&1 | sed 's/^/    /'
  echo "  → Restarting services..."
  docker compose up -d 2>&1 | sed 's/^/    /'
  echo "  → Cleaning up dangling images..."
  docker image prune -f 2>&1 | sed 's/^/    /'
REMOTECMD

ok "Deploy complete."

# ── Phase 3: Status ──────────────────────────

info "Service status on ${REMOTE_HOST}:"

${SSH_CMD} bash -s -- "${REMOTE_DIR}" <<-'REMOTECMD'
  cd "$1"
  docker compose ps --format 'table {{.Name}}\t{{.Status}}\t{{.Ports}}'
REMOTECMD
