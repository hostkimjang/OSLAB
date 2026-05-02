# Web Dashboard 서버 실행 가이드

이 문서는 `oslab` Web Dashboard 서버를 띄우는 방법을 정리합니다. 기능 범위와 UI 동작은 [Web Dashboard](web-dashboard.ko.md)를 봅니다.

## 무엇이 실행되나

Dashboard는 Node 앱 두 개로 구성됩니다.

| App | 역할 | 기본 URL |
| --- | --- | --- |
| `@oslab/api` | NestJS API, auth, catalog/file API, job runner, SQLite job history | `http://127.0.0.1:3001` |
| `@oslab/web` | Next.js dashboard UI | `http://127.0.0.1:3000` |

Repository root의 workspace command는 두 앱을 같이 실행합니다.

## 최초 1회 준비

Repository root에서 실행합니다.

```powershell
corepack pnpm install
Copy-Item apps/api/.env.example apps/api/.env
Copy-Item apps/web/.env.example apps/web/.env
corepack pnpm prisma:generate
```

`apps/api/.env`에는 최소한 아래 값을 설정합니다.

```text
OSLAB_REPO_ROOT=C:/Users/kysky/Documents/gitlab/product-specific_autorun_test
OSLAB_WEB_ADMIN_USERNAME=admin
OSLAB_WEB_ADMIN_PASSWORD=<strong-password>
```

`apps/web/.env`는 API server를 가리킵니다.

```text
OSLAB_API_PROXY=http://127.0.0.1:3001
```

API는 시작 시 local SQLite table이 없으면 자동 생성합니다. Development dashboard에서는 별도 migration step이 필요하지 않습니다.

## Local 개발 서버 실행

API와 Web을 같이 실행합니다.

```powershell
corepack pnpm dev
```

브라우저에서 엽니다.

```text
http://127.0.0.1:3000
```

로그인은 `apps/api/.env`의 `OSLAB_WEB_ADMIN_USERNAME`, `OSLAB_WEB_ADMIN_PASSWORD`를 사용합니다.

API/Web을 따로 실행하려면:

```powershell
corepack pnpm dev:api
corepack pnpm dev:web
```

## LAN 접근

Web dev server는 이미 `0.0.0.0:3000`에 bind하므로 다른 PC에서는 아래 주소로 접속합니다.

```text
http://<dashboard-host-ip>:3000
```

실시간 job event, 대용량 artifact upload까지 LAN에서 쓰려면 API도 LAN에서 접근 가능해야 합니다. `apps/api/.env`:

```text
OSLAB_WEB_HOST=0.0.0.0
OSLAB_API_PORT=3001
OSLAB_WEB_ORIGIN=http://<dashboard-host-ip>:3000
```

`apps/web/.env`는 Next.js server 기준의 API endpoint에 맞춥니다. Web과 API가 같은 host에서 실행되면 기본값으로 충분합니다.

```text
OSLAB_API_PROXY=http://127.0.0.1:3001
```

대부분의 dashboard API 호출은 위 Next.js rewrite를 탑니다. 다만 large artifact upload와 job event stream은 rewrite를 우회하고 브라우저 page hostname의 `3001` port로 직접 접근합니다. 예:

```text
http://<dashboard-host-ip>:3001
```

원격 브라우저에서 이 기능까지 쓰려면 API가 `0.0.0.0:3001`에 listen해야 하고, `OSLAB_WEB_ORIGIN=http://<dashboard-host-ip>:3000`을 허용해야 하며, Windows 방화벽/private network에서 `3001` port가 열려 있어야 합니다. 계정 password, reverse proxy/WAF rule도 같이 확인합니다.

## Production에 가까운 빌드 확인

Workspace package 전체를 build합니다.

```powershell
corepack pnpm build
```

Build output 기준으로 API와 Web을 별도 terminal에서 실행합니다.

```powershell
corepack pnpm --filter @oslab/api start
corepack pnpm --filter @oslab/web start
```

Web start command는 `0.0.0.0:3000`에 listen합니다.

## Smoke Check

API 응답 확인:

```powershell
Invoke-WebRequest http://127.0.0.1:3001/api/me -UseBasicParsing
```

이 endpoint는 인증되지 않은 응답이어도 server가 응답하면 smoke 관점에서는 충분합니다.

Web 응답 확인:

```powershell
Invoke-WebRequest http://127.0.0.1:3000 -UseBasicParsing
```

브라우저 회귀 검증이 필요하면 [Browser Debug Checklist](devs/browser-debug-checklist.md)를 기준으로 진행합니다.

## Troubleshooting

| 증상 | 가능성 높은 원인 | 조치 |
| --- | --- | --- |
| `corepack pnpm dev`를 찾지 못함 | Corepack 또는 pnpm shim 미준비 | `corepack enable` 후 `corepack pnpm install` 재시도. Windows 권한이 막히면 계속 `pnpm ...` 대신 `corepack pnpm ...` 사용 |
| Web은 뜨는데 API 호출 실패 | `OSLAB_API_PROXY` 또는 API bind/origin 불일치 | `apps/web/.env`, `apps/api/.env` 확인 후 `http://127.0.0.1:3001/api/me` 응답 확인 |
| LAN에서 Web은 열리는데 upload/event 실패 | API가 loopback 전용이거나 방화벽 차단 | `OSLAB_WEB_HOST=0.0.0.0`, `OSLAB_WEB_ORIGIN=http://<dashboard-host-ip>:3000` 설정, `3001` port 허용 |
| Login 실패 | Dashboard credential 불일치 | `apps/api/.env`의 `OSLAB_WEB_ADMIN_USERNAME`, `OSLAB_WEB_ADMIN_PASSWORD` 확인 후 API 재시작 |
| Build/dev 전환 후 Next.js runtime error | 오래된 `.next` cache | Web server 중지, `apps/web/.next` 삭제, `corepack pnpm dev` 재실행 |
| Web login은 되는데 job launch 실패 | Python runner/provider config 문제 | Repository root에서 같은 scenario를 `uv run oslab preflight ...` 또는 `uv run oslab run ...`으로 확인 |
