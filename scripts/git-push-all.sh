#!/usr/bin/env bash
# Commit and publish nested repositories before recording their pins in the catalog.
set -euo pipefail

usage() {
  printf 'Usage: %s "Commit message"\n' "$(basename "$0")"
  printf 'Commits all non-ignored changes and pushes submodules before the catalog.\n'
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
branches=()

# Validate the entire tree before staging anything. A missing submodule must not
# accidentally resolve to the parent repository through Git's directory search.
collect_repositories() {
  local repository=$1 configured_branch=$2 actual_root branch git_directory state
  local entry key module_path module_name module_branch child
  actual_root=$(git -C "$repository" rev-parse --show-toplevel 2>/dev/null) || fail "Not a Git repository: $repository"
  [[ "$actual_root" == "$repository" ]] || fail "Initialize submodules first: git submodule update --init --recursive"
  git -C "$repository" remote get-url origin >/dev/null || fail "No origin remote: $repository"
  git_directory=$(git -C "$repository" rev-parse --absolute-git-dir)
  for state in MERGE_HEAD CHERRY_PICK_HEAD REVERT_HEAD rebase-merge rebase-apply; do
    [[ ! -e "$git_directory/$state" ]] || fail "Finish the in-progress Git operation in $repository first."
  done
  [[ -z "$(git -C "$repository" ls-files --unmerged)" ]] || fail "Resolve conflicts in $repository first."
  branch=$(git -C "$repository" symbolic-ref --quiet --short HEAD) || branch=$configured_branch
  [[ -n "$branch" && "$branch" != . ]] || fail "Check out a branch in $repository before publishing."
  git check-ref-format "refs/heads/$branch" >/dev/null || fail "Invalid branch in $repository: $branch"

  if [[ -f "$repository/.gitmodules" ]]; then
    git config --file "$repository/.gitmodules" --list >/dev/null
    while IFS= read -r -d '' entry; do
      key=${entry%%$'\n'*}
      module_path=${entry#*$'\n'}
      module_name=${key#submodule.}
      module_name=${module_name%.path}
      module_branch=$(git config --file "$repository/.gitmodules" --get "submodule.$module_name.branch") || module_branch=
      [[ "$module_branch" != . ]] || module_branch=$branch
      child=$(cd -- "$repository/$module_path" 2>/dev/null && pwd -P) || fail "Missing submodule: $module_path. Run git submodule update --init --recursive."
      collect_repositories "$child" "$module_branch"
    done < <(git config --null --file "$repository/.gitmodules" --get-regexp '^submodule\..*\.path$' || [[ $? -eq 1 ]])
  fi

  repositories[${#repositories[@]}]=$repository
  branches[${#branches[@]}]=$branch
}

collect_repositories "$root" ''
for ((position=0; position<${#repositories[@]}; position++)); do
  repository=${repositories[$position]}
  branch=${branches[$position]}
  printf '\nPublishing %s (%s)\n' "$repository" "$branch"
  git -C "$repository" add --all
  if ! git -C "$repository" diff --cached --quiet; then
    git -C "$repository" commit -m "$message"
  fi
  # Explicit refspecs also publish commits made from a detached submodule pin.
  # Normal fast-forward checks protect remote commits; no force push is used.
  git -C "$repository" push origin "HEAD:refs/heads/$branch"
done

printf '\nPublished all blueprint repositories and the catalog.\n'
