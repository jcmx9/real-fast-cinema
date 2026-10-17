# Contributing

Thanks for your interest in contributing to this project. This guide describes the workflow.

## Prerequisites

- Python >= 3.12
- [uv](https://docs.astral.sh/uv/)
- Git
- A GitHub account

## Setting Up the Development Environment

```bash
# Clone your fork
git clone git@github.com:<your-user>/real-fast-cinema.git
cd real-fast-cinema

# Install dependencies
uv sync

# Activate pre-commit hooks
uv run pre-commit install
```

## Workflow

1. Create a branch from `dev`:
   ```bash
   git checkout dev
   git pull origin dev
   git checkout -b feature/<short-description>
   ```

2. Implement your changes.

3. Make sure all checks pass:
   ```bash
   uv run ruff check --fix . && uv run ruff format .
   uv run mypy src/
   uv run pytest
   ```

4. Commit with a conventional commit message:
   ```
   feat(parser): add CSV import support
   ```

5. Push and create a PR targeting `dev`.

## PR Checklist

Before submitting a PR, verify:

- [ ] All tests pass (`uv run pytest`)
- [ ] No linting errors (`uv run ruff check`, `uv run ruff format --check`)
- [ ] Type checking passes (`uv run mypy src/`)
- [ ] New functionality has tests
- [ ] Documentation updated (if applicable)
- [ ] CHANGELOG.md updated under `[Unreleased]`
- [ ] Commit messages follow Conventional Commits

## Code Standards

- **Type hints** are required for all public functions and methods.
- **Docstrings** in Google style for public functions and classes.
- **Test coverage** for new functionality (target: >= 80 %).
- **Ruff** is the sole linter/formatter – no additional tools.

## Issues

- Use the available issue templates.
- Bug reports should include steps to reproduce.
- Feature requests should describe the use case, not just the desired solution.

## Code of Conduct

We expect respectful, constructive interaction. Harassment, discrimination, or trolling will result in exclusion.
