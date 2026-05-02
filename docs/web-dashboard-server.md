# Web Dashboard Server Guide

This guide explains how to run the `oslab` web dashboard server. For feature scope and UI behavior, see [Web Dashboard](web-dashboard.md).

## What Runs

The dashboard has two Node apps:

| App | Role | Default URL |
| --- | --- | --- |
| `@oslab/api` | NestJS API, auth, catalog/file APIs, job runner, SQLite job history | `http://127.0.0.1:3001` |
| `@oslab/web` | Next.js dashboard UI | `http://127.0.0.1:3000` |

The root workspace command starts both apps together.

## One-Time Setup

Run these commands from the repository root:

```powershell
corepack pnpm install
Copy-Item apps/api/.env.example apps/api/.env
Copy-Item apps/web/.env.example apps/web/.env
corepack pnpm prisma:generate
```

Set at least these values in `apps/api/.env`:

```text
OSLAB_REPO_ROOT=C:/Users/kysky/Documents/gitlab/product-specific_autorun_test
OSLAB_WEB_ADMIN_USERNAME=admin
OSLAB_WEB_ADMIN_PASSWORD=<strong-password>
```

`apps/web/.env` should point to the API server:

```text
OSLAB_API_PROXY=http://127.0.0.1:3001
```

The API creates the local SQLite tables at startup when they are missing. The development dashboard does not require a separate migration step.

## Local Development Server

Start API and Web together:

```powershell
corepack pnpm dev
```

Open:

```text
http://127.0.0.1:3000
```

Login uses `OSLAB_WEB_ADMIN_USERNAME` and `OSLAB_WEB_ADMIN_PASSWORD` from `apps/api/.env`.

To run each side separately:

```powershell
corepack pnpm dev:api
corepack pnpm dev:web
```

## LAN Access

The Web dev server already binds to `0.0.0.0:3000`, so other machines can use:

```text
http://<dashboard-host-ip>:3000
```

For full LAN operation, make the API reachable too. In `apps/api/.env`:

```text
OSLAB_WEB_HOST=0.0.0.0
OSLAB_API_PORT=3001
OSLAB_WEB_ORIGIN=http://<dashboard-host-ip>:3000
```

Keep `apps/web/.env` pointed at the API from the Next.js server's point of view. When Web and API run on the same host, this can stay:

```text
OSLAB_API_PROXY=http://127.0.0.1:3001
```

Most dashboard API calls use the Next.js rewrite above. Large artifact uploads and job event streams intentionally bypass the rewrite and use the browser page hostname with port `3001`, for example:

```text
http://<dashboard-host-ip>:3001
```

For remote browsers, that means the API must listen on `0.0.0.0:3001`, allow `OSLAB_WEB_ORIGIN=http://<dashboard-host-ip>:3000`, and be reachable through the Windows firewall/private network. Also check the account password and any reverse proxy/WAF rules.

## Production-Like Build Check

Build all workspace packages:

```powershell
corepack pnpm build
```

Start API and Web from built output in separate terminals:

```powershell
corepack pnpm --filter @oslab/api start
corepack pnpm --filter @oslab/web start
```

The Web start command listens on `0.0.0.0:3000`.

## Smoke Checks

Check the API:

```powershell
Invoke-WebRequest http://127.0.0.1:3001/api/me -UseBasicParsing
```

An unauthenticated response is acceptable for this endpoint smoke; the important check is that the API server answers.

Check the Web server:

```powershell
Invoke-WebRequest http://127.0.0.1:3000 -UseBasicParsing
```

For browser regression work, follow [Browser Debug Checklist](devs/browser-debug-checklist.md).

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `corepack pnpm dev` is not found | Corepack or pnpm shim unavailable | Use `corepack enable`, then retry `corepack pnpm install`; on locked-down Windows shells, keep using `corepack pnpm ...` instead of `pnpm ...` |
| Web loads but API calls fail | `OSLAB_API_PROXY` or API bind/origin mismatch | Check `apps/web/.env`, `apps/api/.env`, and confirm `http://127.0.0.1:3001/api/me` responds |
| LAN browser opens Web but uploads/events fail | API is still loopback-only or blocked by firewall | Set `OSLAB_WEB_HOST=0.0.0.0`, set `OSLAB_WEB_ORIGIN=http://<dashboard-host-ip>:3000`, and open port `3001` |
| Login fails | Wrong dashboard credentials | Check `OSLAB_WEB_ADMIN_USERNAME` and `OSLAB_WEB_ADMIN_PASSWORD` in `apps/api/.env`, then restart the API |
| Next.js runtime error after build/dev switching | Stale `.next` cache | Stop the Web server, remove `apps/web/.next`, then restart `corepack pnpm dev` |
| Job launch fails but Web login works | Python runner/provider config issue | Run the same scenario with `uv run oslab preflight ...` or `uv run oslab run ...` from the repository root |
