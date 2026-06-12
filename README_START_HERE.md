# Dude Fish OS Flask/Codex Starter - uv + Python 3.14

Copy these files into the root of a fresh GitHub repo before starting Codex:

- `AGENTS.md`
- `DESIGN.md`
- `codex_build_prompt.md`
- `.env.example`
- `.env` local starter, do not commit this
- `.gitignore`
- `.python-version`

## Recommended first commands

```bash
git checkout -b fresh-flask-build
uv python install 3.14
uv python pin 3.14
```

Then start Codex from the repo root and paste the contents of `codex_build_prompt.md`.

## Important

The included `.env` uses local-only database details for development. Change the password before production and never commit `.env`.

The `.env.example` file contains safe placeholders only.

## POS note

The main app should stay Flask/Jinja/Tailwind. The POS is allowed to use a small isolated Preact + TypeScript + Vite frontend island if Codex decides that is cleaner and faster for high-volume market checkout.

Do not let Codex turn the whole system into a SPA. POS only.
