#!/usr/bin/env bash
# Release helper for CalVer YY.M.MICRO with .devN pre-releases.
set -euo pipefail

readonly VERSION_RE='^([0-9]{2})\.([0-9]{1,2})\.([0-9]+)(\.dev([0-9]+))?$'

die() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<'USAGE'
Usage:
  scripts/release.sh dev                 bump .devN on dev, tag and push
  scripts/release.sh prod [--new-month]  release dev -> main via PR, then tag main
  scripts/release.sh tag                 tag the release version on main and push
USAGE
}

require_clean_branch() {
  local branch="$1"
  [[ "$(git rev-parse --abbrev-ref HEAD)" == "${branch}" ]] || die "must be on ${branch}"
  if ! git diff --quiet || ! git diff --cached --quiet; then
    die "working tree not clean"
  fi
  git pull --ff-only origin "${branch}"
}

current_version() {
  uv run bump-my-version show current_version
}

calendar_base() {
  printf '%s.%s' "$(date +%y)" "$((10#$(date +%m)))"
}

next_dev_version() {
  local current="$1"
  [[ "${current}" =~ ${VERSION_RE} ]] || die "cannot parse version ${current}"
  local year="${BASH_REMATCH[1]}" month="${BASH_REMATCH[2]}"
  local micro="${BASH_REMATCH[3]}" dev="${BASH_REMATCH[5]:-}"
  if [[ -n "${dev}" ]]; then
    printf '%s.%s.%s.dev%s' "${year}" "${month}" "${micro}" "$((dev + 1))"
  elif [[ "${year}.${month}" == "$(calendar_base)" ]]; then
    printf '%s.%s.%s.dev1' "${year}" "${month}" "$((micro + 1))"
  else
    printf '%s.0.dev1' "$(calendar_base)"
  fi
}

next_prod_version() {
  local current="$1" new_month="$2"
  [[ "${current}" =~ ${VERSION_RE} ]] || die "cannot parse version ${current}"
  [[ -n "${BASH_REMATCH[5]:-}" ]] || die "${current} is not a dev version"
  if [[ "${new_month}" == "true" ]]; then
    printf '%s.0' "$(calendar_base)"
  else
    printf '%s.%s.%s' "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}" "${BASH_REMATCH[3]}"
  fi
}

cmd_dev() {
  require_clean_branch dev
  local new
  new="$(next_dev_version "$(current_version)")"
  uv run bump-my-version bump --new-version "${new}"
  git push origin dev --follow-tags
  printf 'Released dev version %s\n' "${new}"
}

cmd_tag() {
  git checkout main
  git pull --ff-only origin main
  local version
  version="$(current_version)"
  [[ "${version}" =~ ${VERSION_RE} ]] || die "cannot parse version ${version}"
  [[ -z "${BASH_REMATCH[5]:-}" ]] || die "main is on dev version ${version}"
  git tag -a "v${version}" -m "Release ${version}"
  git push origin "v${version}"
  git checkout dev
  printf 'Tagged v%s\n' "${version}"
}

cmd_prod() {
  local new_month="false"
  if [[ "${1:-}" == "--new-month" ]]; then
    new_month="true"
  fi
  command -v gh >/dev/null 2>&1 || die "GitHub CLI (gh) is required"
  require_clean_branch dev
  grep -q '^## \[Unreleased\]' CHANGELOG.md || die "CHANGELOG.md lacks [Unreleased]"
  local new pr_url
  new="$(next_prod_version "$(current_version)" "${new_month}")"
  uv run bump-my-version bump --new-version "${new}" --no-tag
  git push origin dev
  pr_url="$(gh pr create --base main --head dev --title "release: ${new}" --body "Release ${new}")"
  sleep 15
  gh pr checks "${pr_url}" --watch --fail-fast || die "CI failed for ${pr_url}"
  gh pr merge "${pr_url}" --rebase \
    || die "merge failed: merge ${pr_url} manually, then run scripts/release.sh tag"
  cmd_tag
}

main() {
  case "${1:-}" in
    dev) cmd_dev ;;
    prod) shift; cmd_prod "$@" ;;
    tag) cmd_tag ;;
    -h | --help | "") usage ;;
    *) usage >&2; exit 2 ;;
  esac
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
