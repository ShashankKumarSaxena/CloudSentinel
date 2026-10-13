#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
if [[ ! -e .git ]]; then git init -b main; fi
if [[ "$(git rev-parse --show-toplevel)" != "$PROJECT_ROOT" ]]; then
  printf 'Refusing to stage files in a different repository.\n' >&2
  exit 1
fi
git add --all
if ! git diff --cached --quiet; then
  git commit -m "feat: implement Phase 1 multi-cloud security prototype"
fi
printf '\nLocal Git repository is ready. To create a private GitHub repository later:\n'
printf 'gh auth login -h github.com\n'
printf 'gh repo create Cloud-Vulnerability-Detector-MP --private --source=. --remote=origin --push\n'
