#!/usr/bin/env bash
# Commit and push development in nested repositories before recording their catalog pins.
set -euo pipefail

usage() {
  printf 'Usage: %s "Commit message"\n' "$(basename "$0")"
  printf 'Commits all non-ignored changes and pushes development in submodules before the catalog.\n'
}

fail() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

if [[ $# -eq 1 && ( "$1" == --help || "$1" == -h ) ]]; then
  usage
  exit 0
fi
if [[ $# -ne 1 || -z "${1//[[:space:]]/}" ]]; then
  usage >&2
  exit 1
fi

message=$1
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
repositories=()

# Validate the entire tree before staging anything. A missing submodule must not
# accidentally resolve to the parent repository through Git's directory search.
collect_repositories() {
  local repository=$1 actual_root git_directory state
  local entry module_path child
  actual_root=$(git -C "$repository" rev-parse --show-toplevel 2>/dev/null) || fail "Not a Git repository: $repository"
  [[ "$actual_root" == "$repository" ]] || fail "Initialize submodules first: git submodule update --init --recursive"
  git -C "$repository" remote get-url origin >/dev/null || fail "No origin remote: $repository"
  git_directory=$(git -C "$repository" rev-parse --absolute-git-dir)
  for state in MERGE_HEAD CHERRY_PICK_HEAD REVERT_HEAD rebase-merge rebase-apply; do
    [[ ! -e "$git_directory/$state" ]] || fail "Finish the in-progress Git operation in $repository first."
  done
  [[ -z "$(git -C "$repository" ls-files --unmerged)" ]] || fail "Resolve conflicts in $repository first."
  [[ $(git -C "$repository" symbolic-ref --quiet HEAD) == refs/heads/development ]] ||
    fail "Switch $repository to development before publishing."

  if [[ -f "$repository/.gitmodules" ]]; then
    git config --file "$repository/.gitmodules" --list >/dev/null
    while IFS= read -r -d '' entry; do
      module_path=${entry#*$'\n'}
      child=$(cd -- "$repository/$module_path" 2>/dev/null && pwd -P) || fail "Missing submodule: $module_path. Run git submodule update --init --recursive."
      collect_repositories "$child"
    done < <(git config --null --file "$repository/.gitmodules" --get-regexp '^submodule\..*\.path$' || [[ $? -eq 1 ]])
  fi

  repositories[${#repositories[@]}]=$repository
}

collect_repositories "$root"
for repository in "${repositories[@]}"; do
  printf '\nPublishing %s (development)\n' "$repository"
  git -C "$repository" add --all
  if ! git -C "$repository" diff --cached --quiet; then
    git -C "$repository" commit -m "$message"
  fi
  git -C "$repository" push --no-follow-tags --recurse-submodules=no origin \
    refs/heads/development:refs/heads/development
done

printf '\nPublished all blueprint repositories and the catalog.\n'
