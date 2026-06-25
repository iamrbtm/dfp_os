# Production Database — jeremyguill.com

This file documents the production database configuration for Dude Fish OS.

> **DO NOT** include this connection string in `.env` for local development.
> Only reference it on the production server or CI/CD pipeline.

## Connection

| Field       | Value                                            |
|-------------|--------------------------------------------------|
| Host        | jeremyguill.com                                  |
| Port        | 3306                                             |
| Database    | onlymyli_dfp_tn                                  |
| User        | onlymyli_rbtm2006                                |
| Password    | Braces4me##                                      |

## DATABASE_URL

```env
DATABASE_URL=mysql+pymysql://onlymyli_rbtm2006:Braces4me%23%23@jeremyguill.com:3306/onlymyli_dfp_tn
```

## Usage

On the production server, set `DATABASE_URL` in the environment or `.env` to the
value above. Never commit it to version control.

## Migrations

Before deploying a new version to production, run:

```bash
uv run flask --app app:create_app db upgrade
```

Or, if running inside Docker on the production server:

```bash
docker compose exec web uv run flask --app app:create_app db upgrade
```

## Seeding

To seed production with demo/admin data:

```bash
uv run flask --app app:create_app seed admin
uv run flask --app app:create_app seed demo
uv run flask --app app:create_app seed events-2026
```
