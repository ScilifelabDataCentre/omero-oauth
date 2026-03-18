# GitHub Workflows Overview

This directory contains GitHub Actions workflows used for CI, release automation, Docker publishing, and PR policy checks.

## Workflow files

| File                  | Purpose                                                                                                      | Trigger(s)                                                          |
| --------------------- | ------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------- |
| `ci.yaml`             | Runs test and type-check jobs for Python code quality.                                                       | `push`, `pull_request`, `workflow_dispatch`                         |
| `docker-dev.yaml`     | Builds and publishes dev Docker images to GHCR (from manual run, optionally targeting a branch).             | `workflow_dispatch`                                                 |
| `docker-release.yaml` | Validates Docker builds for PRs and publishes release images/tags to GHCR on `main` pushes and version tags. | `workflow_dispatch`, `pull_request` (`main`), `push` (`main`, `v*`) |
| `release-please.yaml` | Runs Release Please to manage release PRs, changelog updates, and version tagging for `main`.                | `workflow_dispatch`, `push` (`main`)                                |
| `pr-title-check.yaml` | Enforces Conventional Commit style PR titles using semantic PR title validation.                             | `pull_request` (`opened`, `edited`, `synchronize`)                  |

## Notes

- `release-please.yaml` uses:
  - config: `.github/release-please-config.json`
  - manifest: `.github/.release-please-manifest.json`
- Docker images are published to GHCR (`ghcr.io/${{ github.repository }}`) by the Docker workflows.
- Docker release image tags in `docker-release.yaml` follow this policy:
  - `main`, `main-<sha>` for integration builds from `main`
  - `vX.Y.Z`, `X.Y`, `X`, `sha-<sha>`, and `latest` for version tag releases (`v*`)
- PR runs of `docker-release.yaml` are build-only validation (no image push).
- Most workflows use `concurrency` groups to avoid overlapping runs on the same ref.
