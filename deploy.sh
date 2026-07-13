#!/usr/bin/env bash
set -euo pipefail

# ──────────────────────────────────────────────
# deploy.sh — deploy DFPos to breath.local
# Usage: ./deploy.sh [--skip-build] [--dry-run] [--sync-db]
# ──────────────────────────────────────────────

SCRIPT_NAME=$(basename "$0")
REMOTE_HOST="breath.local"
REMOTE_USER="rbtm2006"
REMOTE_DIR="/mnt/storage/docker/dfpos"
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
SYNC_DB=false
LOCAL_POSTGRES_CONTAINER="dfp_os-intelligence-postgres-1"
REMOTE_POSTGRES_SERVICE="intelligence-postgres"
LOCAL_DB_NAME="dfp_intelligence"
LOCAL_DB_USER="dfp_intelligence"

for arg in "$@"; do
  case "$arg" in
    --skip-build) SKIP_BUILD=true ;;
    --dry-run)    DRY_RUN=true ;;
    --sync-db)    SYNC_DB=true ;;
    --help)
      echo "Usage: $SCRIPT_NAME [--skip-build] [--dry-run] [--sync-db]"
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

if [ ! -f ".env" ]; then
  err ".env not found. Create it from .env.example first."
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
  rsync --dry-run -avz --delete --size-only "${RSYNC_EXCLUDES[@]}" ./ "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/"
  info "[DRY-RUN] Done. No files were transferred."
  exit 0
fi

info "Rsyncing project files to ${REMOTE_HOST}:${REMOTE_DIR}..."
rsync -avz --delete --checksum "${RSYNC_EXCLUDES[@]}" ./ "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/"
ok "Project files synced."

info "Copying .env files..."
rsync -avz --size-only \
  --include='.env' \
  --include='*/' \
  --exclude='*' \
  --exclude='.venv' \
  --exclude='node_modules' \
  --exclude='.git' \
  --exclude='__pycache__' \
  --prune-empty-dirs \
  ./ "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/"
ok ".env files copied."

# ── Phase 2: Database sync (optional) ────────

if [ "$SYNC_DB" = true ]; then
  info "Syncing intelligence database to ${REMOTE_HOST}..."

  DUMP_FILE="/tmp/dfp_intelligence_dump.sql.gz"

  # ── Dump local intelligence DB ──
  info "Dumping local intelligence PostgreSQL..."
  if ! docker ps --format '{{.Names}}' | grep -q "^${LOCAL_POSTGRES_CONTAINER}$"; then
    err "Local container '${LOCAL_POSTGRES_CONTAINER}' is not running. Start it first."
    exit 1
  fi
  docker exec "${LOCAL_POSTGRES_CONTAINER}" pg_dump -U "${LOCAL_DB_USER}" -d "${LOCAL_DB_NAME}" --clean --if-exists | gzip > "${DUMP_FILE}"
  ok "Local DB dumped (${DUMP_FILE})."

  # ── Transfer to remote ──
  info "Transferring dump to ${REMOTE_HOST}..."
  scp "${DUMP_FILE}" "${REMOTE_USER}@${REMOTE_HOST}:${DUMP_FILE}"
  ok "Dump transferred."

  # ── Restore on remote ──
  info "Restoring on ${REMOTE_HOST}..."
  ${SSH_CMD} bash -s -- "${REMOTE_DIR}" "${DUMP_FILE}" "${LOCAL_DB_NAME}" "${LOCAL_DB_USER}" <<-'REMOTEDB'
    set -euo pipefail
    DIR="$1"
    DUMP="$2"
    DB="$3"
    DB_USER="$4"

    cd "${DIR}"

    # Derive remote postgres container name from compose project
    COMPOSE_PROJECT=$(basename "$(pwd)")
    REMOTE_PG_CONTAINER="${COMPOSE_PROJECT}-intelligence-postgres-1"

    echo "  → Stopping intelligence service..."
    docker compose stop intelligence 2>&1 | sed 's/^/    /'

    echo "  → Waiting for postgres to be ready..."
    until docker exec "${REMOTE_PG_CONTAINER}" pg_isready -U "${DB_USER}" >/dev/null 2>&1; do
      sleep 1
    done

    echo "  → Dropping and recreating database..."
    docker exec "${REMOTE_PG_CONTAINER}" psql -U "${DB_USER}" -d postgres -c "DROP DATABASE IF EXISTS ${DB};" 2>&1 | sed 's/^/    /'
    docker exec "${REMOTE_PG_CONTAINER}" psql -U "${DB_USER}" -d postgres -c "CREATE DATABASE ${DB};" 2>&1 | sed 's/^/    /'

    echo "  → Restoring database..."
    gunzip -c "${DUMP}" | docker exec -i "${REMOTE_PG_CONTAINER}" psql -U "${DB_USER}" -d "${DB}" 2>&1 | sed 's/^/    /'

    echo "  → Starting intelligence service..."
    docker compose start intelligence 2>&1 | sed 's/^/    /'

    rm -f "${DUMP}"
    echo "  → Remote cleanup done."
	REMOTEDB

  ok "Intelligence database synced."

  # ── Cleanup local dump ──
  rm -f "${DUMP_FILE}"
  ok "Local dump cleaned up."
fi

# ── Phase 3: Build and restart ───────────────

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

  echo "  → Running database migrations..."
  docker compose --profile release run --rm migrate 2>&1 | sed 's/^/    /'
  echo "  → Building images..."
  docker compose build --pull 2>&1 | sed 's/^/    /'
  echo "  → Clearing stale Python bytecode cache..."
  docker compose run --rm --no-deps web find /app -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
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
