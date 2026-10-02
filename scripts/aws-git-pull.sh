#!/bin/bash
# Fast-forward the station checkout. Refuse when tracked files are modified.
# Untracked files do not block the pull. This script does not restart anything.
set -u

REPO="/home/ubuntu/US-Mainland-Server-2"

cd "$REPO" || exit 1

dirty="$(git status --porcelain | awk '$1 != "??" { print }')"
if [[ -n "$dirty" ]]; then
  echo "aws-git-pull: dirty checkout, skip"
  printf '%s\n' "$dirty"
  exit 1
fi

git pull --ff-only
