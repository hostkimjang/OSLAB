# Project Instructions

- 진행 시 `docs/`와 checklist가 존재하면 계속 확인하고 필요한 수정 사항을 반영합니다.
- 기능 변경/추가/개선 시 관련 문서를 함께 리뉴얼합니다.

## Web Dashboard Rules

- Web Dashboard를 수정할 때는 **항상 실제 브라우저를 띄워서 확인**합니다.
- 브라우저 확인 시 가능한 한 **스크린샷을 남깁니다**.
- Web Dashboard 변경 후에는 `output/web-dashboard/` 아래에 검증 스크린샷/보조 산출물을 남길 수 있습니다.
- Web Dashboard 회귀 검증은 [docs/devs/browser-debug-checklist.md](docs/devs/browser-debug-checklist.md)를 기준으로 진행하고, 새로 확인한 버그/수정 내용은 그 문서에 누적합니다.
- Web Dashboard 브라우저 검증 시 기본 반응형 범위에 mobile, tablet, 1366 desktop뿐 아니라 **Full HD 1920x1080**과 **QHD 2560x1440**을 포함합니다.
- 주요 기능 화면은 해상도별 스크린샷/측정값을 `output/web-dashboard/`에 남겨 디자인 밀도, 여백, clipping, overflow 개선 판단 근거로 사용합니다.
- Web Dashboard 변경 후에는 가능하면 **실제 demo run 하나 이상**을 Web UI에서 실행해 확인합니다.
