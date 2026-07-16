# Contributing to DFPos

## Workflow

1. **Create an issue** using a template (Bug Report, Feature Request, or Task)
2. **Label it** with the appropriate type, module, and priority
3. **Create a branch** from `main` named after the issue:
   ```
   git checkout -b issue-123-short-description
   ```
4. **Make your changes** following the conventions in `AGENTS.md` and `DESIGN.md`
5. **Run checks** before committing:
   ```bash
   uv run ruff check .
   uv run ruff format --check .
   uv run pytest -v --tb=long
   ```
6. **Commit** with a descriptive message referencing the issue:
   ```
   git commit -m "Add POS cart auto-save (#123)"
   ```
7. **Push and open a PR** targeting `main` with a reference to the issue:
   ```
   gh pr create --title "Add POS cart auto-save (#123)" --body "Closes #123"
   ```

## Development Setup

See the README for full setup instructions.

## Code Standards

- Python 3.14, type-annotated
- Ruff linting + formatting (line length 100)
- Pytest for testing
- Flask + SQLAlchemy + Jinja2 server-side
- Tailwind CSS for styling
- Audit logging for all meaningful actions

## Pull Request Checklist

- [ ] Issue referenced in title/body
- [ ] Code follows project conventions (AGENTS.md)
- [ ] Design follows DESIGN.md tokens and patterns
- [ ] Database migrations included (if schema change)
- [ ] Tests added/updated and passing
- [ ] Audit logging added for meaningful actions
- [ ] Feature flags enforced (if applicable)
- [ ] Lint passes (`ruff check . && ruff format --check .`)
- [ ] No secrets or credentials committed
