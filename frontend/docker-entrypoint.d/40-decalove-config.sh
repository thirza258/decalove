#!/bin/sh
# Write the deployment settings the bundle reads at boot.
#
# This overwrites the committed development no-op in public/config.js, which is the
# point: a stale default baked into the image must never win over the environment the
# container was actually started with.
set -eu

target="/usr/share/nginx/html/config.js"

cat > "$target" <<EOF
// Generated at container start-up. Edits here are lost on restart.
window.__DECALOVE__ = {
  apiBase: "${DECALOVE_API_BASE:-}",
  apiPrefix: "${DECALOVE_API_PREFIX:-/api/v1}"
};
EOF

echo "decalove: apiBase='${DECALOVE_API_BASE:-}' (empty = same-origin via /api/ proxy)," \
     "apiPrefix='${DECALOVE_API_PREFIX:-/api/v1}', upstream='${DECALOVE_API_UPSTREAM:-unset}'"
