# Release Workflow

Versions follow CalVer `YY.M.MICRO`; pre-releases on `dev` carry `.devN`.

| Command | Effect |
|---|---|
| `scripts/release.sh dev` | On `dev`: bump `.devN`, commit, tag `vX.devN`, push. The tag triggers a GitHub pre-release and a GHCR image tagged with the version. |
| `scripts/release.sh prod` | On `dev`: strip `.devN`, commit, open PR `dev -> main`, wait for CI, rebase-merge, tag `main`, push. The tag triggers a GitHub release and GHCR images `vX` and `latest`. |
| `scripts/release.sh prod --new-month` | Like `prod`, but the release version starts the current month (`YY.M.0`). |
| `scripts/release.sh tag` | Tag the current release version on `main` (use after a manual merge). |

Before `prod`: move the entries under `## [Unreleased]` in `CHANGELOG.md` to a new
version section and commit on `dev`.

Requirements: `uv`, `gh` (authenticated), a clean working tree.
PyPI is intentionally not used: the service is distributed as a Docker image.
