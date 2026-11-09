#!/usr/bin/env bash
# Publish the reviewed development commits with submodules before their catalogs.
set -euo pipefail

usage() {
  printf 'Usage: %s [--dry-run]\n' "$(basename "$0")"
  printf 'Fast-forward local main and origin/main from clean development checkouts.\n'
  printf 'Use --dry-run to check all repositories before publishing.\n'
}

fail() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

dry_run=false
case "$#:${1-}" in
  0:) ;;
  1:--dry-run) dry_run=true ;;
  1:--help|1:-h) usage; exit 0 ;;
  *) usage >&2; exit 1 ;;
esac

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
development=refs/heads/development
production=refs/heads/main
repositories=()
commits=()

collect_repositories() {
  local repository=$1 expected_pin=$2 actual_root commit changes main_worktree git_directory state
  local entry child pin enumerated=false
  actual_root=$(git -C "$repository" rev-parse --show-toplevel 2>/dev/null) || actual_root=
  [[ "$actual_root" == "$repository" ]] ||
    fail "Missing checkout at $repository. Initialize the catalog submodules before promoting."
  [[ $(git -C "$repository" symbolic-ref --quiet HEAD) == "$development" ]] ||
    fail "Switch $repository to development before promoting."
  commit=$(git -C "$repository" rev-parse --verify "$development")
  [[ -z "$expected_pin" || "$commit" == "$expected_pin" ]] ||
    fail "Commit the updated submodule pin for $repository on development before promoting."
  git_directory=$(git -C "$repository" rev-parse --absolute-git-dir)
  for state in MERGE_HEAD CHERRY_PICK_HEAD REVERT_HEAD rebase-merge rebase-apply; do
    [[ ! -e "$git_directory/$state" ]] || fail "Finish the in-progress Git operation in $repository first."
  done
  main_worktree=$(git -C "$repository" for-each-ref --format='%(worktreepath)' "$production")
  [[ -z "$main_worktree" ]] || fail "Switch $main_worktree off main before promoting."
  git -C "$repository" merge-base --is-ancestor "$production" "$commit" ||
    fail "Local main cannot fast-forward to development in $repository."

  # Read gitlinks from the exact commit being released. An empty record marks
  # successful enumeration because process substitution hides the exit status.
  while IFS= read -r -d '' entry; do
    if [[ -z "$entry" ]]; then
      enumerated=true
      break
    fi
    [[ "$entry" == '160000 '* ]] || continue
    child=${entry#*$'\t'}
    pin=${entry%%$'\t'*}
    collect_repositories "$repository/$child" "${pin##* }"
  done < <(git -C "$repository" ls-tree -rz "$commit" && printf '\0')
  "$enumerated" || fail "Couldn't list submodules in $repository."

  changes=$(git -C "$repository" status --porcelain=v1 --untracked-files=normal --ignore-submodules=none)
  [[ -z "$changes" ]] || fail "Commit or stash changes in $repository before promoting."
  repositories+=("$repository")
  commits+=("$commit")
}

collect_repositories "$root" ''

# Check each push destination before changing any production branch. Use the
# recorded commit IDs throughout so the release cannot pick up later commits.
for ((index=0; index<${#repositories[@]}; index++)); do
  repository=${repositories[$index]}
  commit=${commits[$index]}
  printf 'Checking %s at %.12s\n' "$repository" "$commit"
  git -C "$repository" push --dry-run --quiet --no-verify --no-follow-tags --recurse-submodules=no \
    origin "$commit:$production" || fail "Couldn't fast-forward origin/main in $repository."
done

if "$dry_run"; then
  printf 'Dry run passed.\n'
  exit 0
fi

for ((index=0; index<${#repositories[@]}; index++)); do
  repository=${repositories[$index]}
  commit=${commits[$index]}
  printf '\nPromoting %s at %.12s\n' "$repository" "$commit"
  git -C "$repository" push --no-follow-tags --recurse-submodules=no origin "$commit:$production"
  # Fetch from the local repository to enforce fast-forward and worktree checks.
  git -C "$repository" fetch --no-tags --no-recurse-submodules --no-write-fetch-head . "$commit:$production"
done

printf '\nPublished all blueprint repositories and the catalog to main.\n'
