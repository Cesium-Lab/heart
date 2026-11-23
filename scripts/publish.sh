#!/usr/bin/env bash
# publish.sh: rebuild the site and put it live on cesiumlab.net. No sudo, ~10 s.
#
#   Publish your frontend changes:     ./scripts/publish.sh
#   Also reinstall npm packages:       ./scripts/publish.sh --fresh
#
# Builds into frontend/dist.next, then swaps it in for frontend/dist (what Apache serves), so
# visitors never see a half-built site. If the build fails, the live site is left untouched.
# Only the static site: backend code changes still need `sudo systemctl restart <name>`,
# and a full deploy/repair is ./scripts/deploy-startup.sh.

set -Eeuo pipefail

FRONTEND="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../frontend" && pwd)"
LIVE="$FRONTEND/dist"
NEXT="$FRONTEND/dist.next"
OLD="$FRONTEND/dist.old"
start=$SECONDS

say() { printf '\n==> %s\n' "$*"; }
fail() { printf '\nERROR: %s\n' "$*" >&2; rm -rf "$NEXT"; exit 1; }

# Install packages only when needed: --fresh, no node_modules yet, or package-lock.json changed.
if [[ "${1:-}" == "--fresh" || ! -d "$FRONTEND/node_modules" ||
      "$FRONTEND/package-lock.json" -nt "$FRONTEND/node_modules/.package-lock.json" ]]; then
    say "Installing npm packages"
    npm --prefix "$FRONTEND" ci
fi

say "Building"
rm -rf "$NEXT"
(cd "$FRONTEND" && npx astro build --outDir "$NEXT") || fail "Build failed; the live site is unchanged"
[[ -f "$NEXT/index.html" ]] || fail "Build made no index.html; the live site is unchanged"

say "Swapping in the new build"
rm -rf "$OLD"
[[ -d "$LIVE" ]] && mv "$LIVE" "$OLD"
mv "$NEXT" "$LIVE"
rm -rf "$OLD"

say "Checking the live site"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1/ || true)
[[ "$code" == "200" ]] || fail "Apache answered $code for / (is apache2 running? ./scripts/status.sh)"
pages=$(find "$LIVE" -name index.html | wc -l)
printf '\nPublished %s pages in %ss. Live at https://cesiumlab.net\n' "$pages" "$((SECONDS - start))"
