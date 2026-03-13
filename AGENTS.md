# Repository Guidelines

## Project Structure & Module Organization

`src/` is the application root. Keep HTTP entrypoints in `src/api/`, request/response schemas in `src/models/`, orchestration and policies in `src/application/`, runtime entities in `src/domain/`, and OS-facing adapters in `src/infrastructure/`. Shared environment and queue setup live in `src/core/`. Legacy shell wrappers remain in `action/` and should stay thin; move decision logic into Python first. Operational notes and setup docs belong in `docs/`. Local bootstrap helpers live in `scripts/`.

## Build, Test, and Development Commands

- `make bootstrap`: prepares the macOS dev environment, creates `venv`, and seeds `.env`.
- `make run`: starts the FastAPI server with `uvicorn` on port `8000`.
- `make doctor`: runs `python -m compileall src` and shell syntax checks for `action/*.sh` and `local_run.sh`.
- `make tunnel`: opens `ngrok` for GitHub webhook testing.

Use `curl http://localhost:8000/diagnostics` after startup to confirm env readiness before triggering builds.

## Coding Style & Naming Conventions

Use 4-space indentation in Python and `snake_case` for modules, functions, and variables. Prefer small classes with single responsibilities; this repo is being refactored toward SOLID boundaries. Shell scripts should start with `set -euo pipefail`, use quoted variables, and avoid `eval`. Keep orchestration in Python and leave shell scripts to direct tool execution such as `fvm`, `bundle exec fastlane`, or `pod install`.

## Testing Guidelines

There is no formal automated test suite yet. For every change, run `make doctor` at minimum. When adding Python tests, place them under `tests/` and name files `test_<feature>.py`. Focus first on application-layer policies, validators, and repository/workspace preparation logic because they are easiest to verify without external services.

## Commit & Pull Request Guidelines

Recent history uses short conventional-style commits such as `fix: git credential 수정` and `docs: rbenv 추가`. Continue with `<type>: <summary>` (`fix`, `docs`, `refactor`, `chore`). Keep PRs scoped to one operational concern, describe env or build impact, and include sample commands or API calls when behavior changes. For webhook, build, or iOS workflow changes, note any required `.env` keys explicitly.

## Security & Configuration Tips

Do not commit real secrets. Use `.env` locally and keep `env.template` sanitized. `FLUTTER_VERSION` is only a fallback; prefer project-pinned SDKs from `.fvmrc` or `.tool-versions`. If a pulled branch changes Flutter SDK versions, the Python orchestrator must run `fvm flutter precache --ios` before the build continues.
