# Web/API 구조 리뷰

이 문서는 `oslab` Web Dashboard의 Next.js / NestJS 코드 구조를 중간 점검한 결과와, 이번 리팩터링에서 채택한 방향을 정리합니다.

## 왜 손봤는가

리팩터링 전 상태는 다음 문제가 있었습니다.

- Next.js:
  - 초기 구현은 `apps/web/src/app/page.tsx`에 너무 많은 UI/상태가 몰려 있었고, 1차 분리 후에도 `DashboardPage.tsx`, `components.tsx`, `lib.ts`가 다시 커졌습니다.
  - App Router entrypoint는 얇아졌지만, dashboard feature 내부의 책임 경계가 흐려져 diff review와 회귀 분석이 어려웠습니다.

- NestJS:
  - controller/service/guard/prisma/workspace가 앱 모듈에 직접 연결되어 있어 feature ownership이 약했습니다.
  - `ValidationPipe`를 켜 둔 것에 비해 일부 controller boundary DTO가 부족해서 runtime validation 이점을 충분히 못 쓰고 있었습니다.

## 리뷰 기준

이번 정리는 “한 번에 이상적인 최종 구조”보다 아래 기준을 우선했습니다.

1. URL / API contract / CLI contract는 바꾸지 않는다.
2. import 경계와 feature ownership을 먼저 만든다.
3. DTO는 controller boundary부터 도입한다.
4. 브라우저 동작과 빌드가 계속 유지되는 선에서 점진적으로 간다.

## 채택한 현재 구조

### Frontend

```text
apps/web/src/
  app/
    layout.tsx
    page.tsx                # thin app-router entry
    styles.css
  features/dashboard/
    DashboardPage.tsx       # stateful screen/controller
    components/
      authoring.tsx         # catalog editor, scenario/suite builders
      common.tsx            # small presentational atoms
      lab-status.tsx        # lab status and running-job banner
      results.tsx           # result detail, timeline, file preview
    lib/
      api.ts                # fetch wrappers and API base URL
      commands.ts           # CLI preview builder
      formatting.ts         # bytes/time/preview formatting
      result-summary.ts     # result summary decision text
      ui-state.ts           # tab/lab labels, event parsing, stable stringify
    sections/
      DashboardHome.tsx
      LoginScreens.tsx
      ResultsExplorer.tsx
    model.ts                # compatibility barrel for existing imports
    defaults.ts
    i18n.ts
    types.ts
```

의도:

- `app/page.tsx`는 entrypoint만 담당
- dashboard 구현은 `features/dashboard` 아래로 모음
- helper/component를 `DashboardPage.tsx` 밖으로 분리
- 화면 섹션과 작은 presentational component를 분리해 파일 크기와 import 책임을 줄임

### Backend

```text
apps/api/src/
  main.ts
  app.module.ts
  common/
    guards/
      auth.guard.ts
  infrastructure/
    prisma/
      prisma.service.ts
    workspace/
      workspace.service.ts
  features/
    auth/
      auth.module.ts
      auth.controller.ts
      auth.service.ts
      dto/login.dto.ts
    artifacts/
      artifact.module.ts
      artifact.controller.ts
    builder/
      builder.module.ts
      builder.controller.ts
      dto/builder.dto.ts
    catalog/
      catalog.module.ts
      catalog.controller.ts
    files/
      file.module.ts
      file.controller.ts
      dto/file-read-query.dto.ts
      dto/file-write.dto.ts
    jobs/
      job.module.ts
      job.controller.ts
      job.service.ts
      dto/job-timeouts.dto.ts
      dto/run-scenario.dto.ts
      dto/run-suite.dto.ts
    lab/
      lab.module.ts
      lab.controller.ts
      lab.service.ts
      dto/lab-status-query.dto.ts
      dto/cleanup-stale.dto.ts
    runs/
      run.module.ts
      run.controller.ts
    validation/
      validation.module.ts
      validation.controller.ts
      dto/validate-path.dto.ts
```

의도:

- auth guard는 `common`
- prisma/workspace는 `infrastructure`
- route surface는 `features/*`
- DTO는 HTTP boundary가 명확한 곳부터 도입
- feature module을 두어 `AppModule`이 controller/service를 직접 나열하지 않게 함
- `PrismaModule`, `WorkspaceModule`, `AuthModule`은 shared infrastructure로 export

## 이번 단계에서 일부러 안 한 것

- Next.js dashboard state를 custom hook 여러 개로 더 잘게 쪼개는 작업
- 모든 endpoint response/request를 shared transport model로 재정의
- builder / lab / jobs service 내부를 더 세분화하는 작업

이번 단계는 “폴더 경계와 책임 위치를 먼저 맞추는 것”에 집중했습니다. 특히 화면/컴포넌트/helper/module 경계는 만들었지만, state machine과 API orchestration 분리는 다음 단계로 남겼습니다.

## 다음 구조 개선 후보

### 2026-04-26 반영

- Run Launcher에는 full state machine 분리 전 단계로 `RunReadinessFlow` presentational component를 추가했습니다.
- Authoring editor에는 저장 전 diff preview를 `CatalogEditor` 내부에 붙였습니다.
- Web `LabService`의 Proxmox HTTP 요청에 CLI provider와 같은 `User-Agent`를 추가하고, HTTP transport / URL normalization / VM stop polling을 `ProxmoxLabClient`로 분리했습니다. 다음 단계에서는 Python CLI provider와 Web client의 상위 계약을 더 좁힙니다.
- 두 변경 모두 API/CLI contract를 바꾸지 않는 UI safety 개선이며, 다음 구조 개선 때 custom hook 분리 대상으로 남깁니다.

### Frontend

1. `DashboardPage.tsx`를 다음 hook 단위로 추가 분리
   - `useDashboardAuth`
   - `useDashboardCatalog`
   - `useDashboardRuns`
   - `useDashboardJobs`
   - `useDashboardEditors`
   - `useDashboardBuilders`
2. `DashboardPage.tsx` render branch를 화면별 container로 추가 분리
   - `sections/AuthoringSection`
   - `sections/RunLauncher`
   - `sections/AppShell`
3. `components/authoring.tsx` 안의 builder를 더 세분화
   - `components/authoring/CatalogEditor.tsx`
   - `components/authoring/ScenarioBuilderPanel.tsx`
   - `components/authoring/SuiteBuilderPanel.tsx`

### Backend

1. `JobService`에서 process orchestration / stream / command factory 분리
2. `LabService`에서 config parsing / cleanup orchestration 추가 분리
3. `BuilderController`의 YAML parse/render 로직을 service로 이동
4. response DTO와 shared transport model 정리
5. `ValidationController` suite 검증을 Python suite model 또는 CLI `validate-suite`와 단일화

## 리스크 메모

- DTO 추가는 `ValidationPipe` 때문에 곧바로 runtime behavior를 바꿀 수 있습니다.
- `@Res()`를 쓰는 SSE / file download endpoint는 작은 refactor도 깨지기 쉽습니다.
- Web 구조 분리는 브라우저 smoke와 함께 가야 합니다. compile-only로는 부족합니다.
