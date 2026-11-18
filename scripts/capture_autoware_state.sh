#!/usr/bin/env bash
# Read-only snapshot of a locally installed Autoware.AI source workspace.
# Usage: bash scripts/capture_autoware_state.sh ~/autoware.ai
# Review generated files for paths, personal data and secrets before publishing.
set -euo pipefail

workspace_path="${1:-$HOME/autoware.ai}"
source_dir="${workspace_path%/}/src"
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
output_dir="$project_root/docs/local-autoware-state"

if [[ ! -d "$source_dir" ]]; then
  printf 'ERROR: Source directory not found: %s\n' "$source_dir" >&2
  exit 1
fi

if [[ -e "$output_dir" ]]; then
  printf 'ERROR: Output already exists: %s\n' "$output_dir" >&2
  printf 'Review and move the existing snapshot before running again.\n' >&2
  exit 1
fi

mkdir -p "$output_dir/patches"

if command -v vcs >/dev/null 2>&1; then
  if ! vcs export --exact "$source_dir" > "$output_dir/autoware.local.lock.repos"; then
    printf 'WARNING: vcs export --exact failed; the lock manifest is incomplete.\n' >&2
  fi
else
  printf 'WARNING: vcstool unavailable; only per-repository details will be captured.\n' >&2
fi

printf 'Autoware source: %s\n' "$source_dir" > "$output_dir/revisions.txt"
printf 'Captured at (UTC): %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" >> "$output_dir/revisions.txt"

repository_count=0
while IFS= read -r -d '' git_dir; do
  source_repo="${git_dir%/.git}"
  relative_repo="${source_repo#"$source_dir"/}"
  safe_name="${relative_repo//\//__}"

  if [[ "$relative_repo" == "$source_repo" || "$safe_name" == *..* ]]; then
    printf 'WARNING: Skipping unexpected path: %s\n' "$source_repo" >&2
    continue
  fi

  repository_count=$((repository_count + 1))
  {
    printf '\nRepository: %s\n' "$relative_repo"
    git -C "$source_repo" rev-parse HEAD
    git -C "$source_repo" status --short
  } >> "$output_dir/revisions.txt"

  # Includes staged and unstaged changes to tracked files; excludes untracked files.
  git -C "$source_repo" diff --binary HEAD > "$output_dir/patches/${safe_name}.patch"
done < <(find "$source_dir" -type d -name .git -print0)

printf 'Captured %s Git repositories.\n' "$repository_count"
printf 'Snapshot directory: %s\n' "$output_dir"
printf 'IMPORTANT: Review revisions, patches, remotes and any untracked files before sharing.\n'
