#!/bin/sh
set -eu

lockfile=/app/package-lock.json
modules_dir=/app/node_modules
stamp_file="$modules_dir/.matching-outfit-package-lock.sha256"

if [ ! -f "$lockfile" ]; then
  echo "frontend-entrypoint: missing $lockfile" >&2
  exit 1
fi

current_hash="$(sha256sum "$lockfile" | cut -d ' ' -f 1)"
installed_hash=""
if [ -f "$stamp_file" ]; then
  installed_hash="$(cat "$stamp_file")"
fi

if [ "$current_hash" != "$installed_hash" ] \
  || [ ! -x "$modules_dir/.bin/vite" ] \
  || ! npm ls --depth=0 >/dev/null 2>&1; then
  echo "frontend-entrypoint: dependency state is stale; synchronizing dependencies"
  npm ci
  printf '%s\n' "$current_hash" > "$stamp_file"
fi

exec "$@"
