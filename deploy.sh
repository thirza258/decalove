#!/usr/bin/env bash
#
# Decalove — bring the whole game up in Docker: story engine, workers, and the web
# client. One command for what would otherwise be a compose invocation you have to
# remember the flags for.
#
#   ./deploy.sh                 build and start everything
#   ./deploy.sh --gpu           ...with local SDXL image generation on the GPU
#   ./deploy.sh --no-web        API and workers only (shipping the Ren'Py build instead)
#   ./deploy.sh --no-build      restart without rebuilding images
#   ./deploy.sh down            stop everything
#   ./deploy.sh logs [service]  follow logs
#   ./deploy.sh ps              what is running
#
# DECALOVE_WAIT_TIMEOUT=600 ./deploy.sh raises the 300s health wait, for a slow disk.
#
# Configuration lives in api/.env, which app/config.py already treats as the single
# source of truth; this script only starts things. See api/.env.example.

set -euo pipefail

# Resolve the repo from this script's own location, so the script works from any cwd.
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_DIR="$ROOT/api"
ENV_FILE="$COMPOSE_DIR/.env"
ENV_EXAMPLE="$COMPOSE_DIR/.env.example"

# Compose's own healthchecks decide when the stack is ready. Generous, because a cold
# MongoDB and a cold MinIO both have start periods before they report healthy.
WAIT_TIMEOUT="${DECALOVE_WAIT_TIMEOUT:-300}"

COMMAND="up"
USE_GPU=false
WITH_WEB=true
DO_BUILD=true

# -- output ---------------------------------------------------------------------------

if [ -t 1 ]; then BOLD=$'\033[1m'; DIM=$'\033[2m'; RED=$'\033[31m'; GREEN=$'\033[32m'; OFF=$'\033[0m'
else BOLD=""; DIM=""; RED=""; GREEN=""; OFF=""; fi

say()  { printf '%s\n' "${BOLD}==>${OFF} $*"; }
note() { printf '%s\n' "    ${DIM}$*${OFF}"; }
die()  { printf '%s\n' "${RED}error:${OFF} $*" >&2; exit 1; }

usage() {
    # The comment block below the shebang, up to the first line that is not a
    # comment. A hard-coded line range silently starts printing code the next time
    # the header grows.
    awk 'NR > 1 { if (/^#/) { sub(/^# ?/, ""); print } else { exit } }' "${BASH_SOURCE[0]}"
}

# -- arguments ------------------------------------------------------------------------

while [ $# -gt 0 ]; do
    case "$1" in
        up|down|logs|ps)   COMMAND="$1"; shift ;;
        --gpu)             USE_GPU=true; shift ;;
        --no-web)          WITH_WEB=false; shift ;;
        --no-build)        DO_BUILD=false; shift ;;
        -h|--help|help)    usage; exit 0 ;;
        --)                shift; break ;;
        -*)                die "unknown option: $1 (try --help)" ;;
        *)                 break ;;   # a service name, for `logs`
    esac
done

# -- preflight ------------------------------------------------------------------------

command -v docker >/dev/null 2>&1 || die "docker is not installed or not on PATH."

if ! docker info >/dev/null 2>&1; then
    die "the Docker daemon is not reachable. Start Docker Desktop (or dockerd) and retry."
fi

docker compose version >/dev/null 2>&1 ||
    die "this needs Compose v2 (the 'docker compose' subcommand), not the old docker-compose binary."

[ -f "$COMPOSE_DIR/docker-compose.yml" ] || die "no compose file at $COMPOSE_DIR/docker-compose.yml"

# -- configuration --------------------------------------------------------------------

# The compose file declares `env_file: .env` as optional, so a missing one is not fatal
# -- the config.py defaults simply apply. Creating it anyway is the difference between
# "the story is authored prose" being a mystery and being a line the user can see and
# edit.
if [ ! -f "$ENV_FILE" ] && [ -f "$ENV_EXAMPLE" ]; then
    cp "$ENV_EXAMPLE" "$ENV_FILE"
    say "created api/.env from api/.env.example"
    note "no OPENROUTER_API_KEY yet, so the story runs on the scripted narrator."
    note "add your key to api/.env and re-run to have the model write it."
fi

# Whether the user is already managing the compose file list themselves. api/.env can
# set COMPOSE_FILE -- that is the documented way to switch the GPU overlay on -- and
# passing -f here would silently override it and drop the overlay.
user_manages_files() {
    [ -n "${COMPOSE_FILE:-}" ] && return 0
    [ -f "$ENV_FILE" ] && grep -qE '^[[:space:]]*COMPOSE_FILE[[:space:]]*=' "$ENV_FILE"
}

compose_files=()
if $USE_GPU; then
    [ -f "$COMPOSE_DIR/docker-compose.gpu.yml" ] || die "--gpu needs api/docker-compose.gpu.yml"
    compose_files=(-f docker-compose.yml -f docker-compose.gpu.yml)
elif user_manages_files; then
    note "COMPOSE_FILE is set, so the file list is left to it"
fi

# Run from api/, which is the compose project directory: every relative path in the
# compose file (../frontend as a build context, .env as an env_file) is written against
# it, and this is the invocation the README documents.
cd "$COMPOSE_DIR"

compose() { docker compose "${compose_files[@]+"${compose_files[@]}"}" "$@"; }

# -- commands -------------------------------------------------------------------------

case "$COMMAND" in
    down)
        say "stopping the Decalove stack"
        compose down --remove-orphans
        note "volumes are kept; 'docker compose -f api/docker-compose.yml down -v' also drops saves and art."
        exit 0
        ;;
    logs)
        # Not `exec`: compose is a shell function here, and exec only replaces the
        # shell with an external command -- it cannot run a function.
        compose logs -f --tail=100 "$@"
        exit $?
        ;;
    ps)
        compose ps
        exit $?
        ;;
esac

# -- up -------------------------------------------------------------------------------

up_args=(-d --remove-orphans --wait --wait-timeout "$WAIT_TIMEOUT")
$DO_BUILD && up_args+=(--build)
# Scaled to zero rather than omitted, so `up` still reconciles the rest of the stack
# and a web container from an earlier run is actually stopped.
$WITH_WEB || up_args+=(--scale web=0)

$USE_GPU && note "GPU overlay on: worker-images reserves an NVIDIA device"
$WITH_WEB || note "web client disabled"

if $DO_BUILD; then
    say "starting the Decalove stack, building images first"
    note "a first build pulls a CUDA base image and installs Node and Python deps; expect a few minutes."
else
    say "starting the Decalove stack from the images already built"
fi

if ! compose up "${up_args[@]}"; then
    printf '%s\n' "${RED}the stack did not come up healthy.${OFF}" >&2
    printf '%s\n' "  what is running:  ./deploy.sh ps" >&2
    printf '%s\n' "  why it stopped:   ./deploy.sh logs" >&2
    exit 1
fi

# Ask compose where it actually published things, rather than repeating the defaults
# here where they could drift from the compose file.
published() {
    local service="$1" port="$2" mapped
    mapped="$(compose port "$service" "$port" 2>/dev/null || true)"
    # Explicitly successful when there is nothing to report: `--scale web=0` leaves the
    # web port unmapped, and under `set -e` a failing $(...) assignment kills the script
    # -- which would swallow "Decalove is up." after a perfectly good `up`.
    [ -n "$mapped" ] || return 0
    printf '%s' "http://localhost:${mapped##*:}"
}

api_url="$(published api 8000)"
web_url="$(published web 80)"

printf '\n%s\n' "${GREEN}Decalove is up.${OFF}"
[ -n "$web_url" ] && printf '  %-18s %s\n' "game" "$web_url"
[ -n "$api_url" ] && printf '  %-18s %s\n' "API" "$api_url"
[ -n "$api_url" ] && printf '  %-18s %s\n' "health" "$api_url/health"
printf '  %-18s %s\n' "MinIO console" "http://localhost:9001"

# Only MongoDB, MinIO and Redis declare healthchecks, so `up --wait` counts the API and
# the two Celery workers ready as soon as they are *running* -- a worker that dies on a
# bad broker URL and is restarted by `restart: unless-stopped` still reaches this line.
printf '\n%s\n' "  ${DIM}the API and workers report ready once running; ./deploy.sh ps confirms they stayed up.${OFF}"
printf '%s\n' "  logs: ./deploy.sh logs        stop: ./deploy.sh down"
