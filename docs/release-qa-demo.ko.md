# Dispatch Board로 Windows 릴리스 검증하기

[English](release-qa-demo.md) | 한국어

Dispatch Board는 배송 건을 관리하는 Windows 데스크톱 예제 앱입니다. 실제 MSI로 버전을 설치하고 샘플 데이터를 가져온 뒤, 앱에 저장된 상태와 내보낸 CSV를 확인합니다. OSLab MCP는 Windows VM의 화면을 캡처하고 클릭·키 입력을 보냅니다. 별도 PowerShell 검증 스크립트는 결과 파일을 읽어 JSON과 HTML 보고서를 만듭니다.

| 시나리오 | 검증 항목 |
| --- | --- |
| 새로 설치하고 첫 작업 수행 | `1.0.0`에서 정상 배송 건 7개를 가져오고 수량이 잘못된 `SHP-1048`을 반려합니다. `SHP-1041`에 지정한 보류 상태는 CSV에도 남습니다. |
| 기존 데이터가 있는 상태에서 업그레이드 | `2.0.0`에서 같은 작업 공간을 열면 보류 상태와 실행 기록이 유지됩니다. 업그레이드 전에 저장한 CSV의 SHA-256도 같습니다. |
| 릴리스 검증에서 데이터 누락 탐지 | `2.0.0`에서 CSV를 다시 내보내면 7건 중 6건만 기록되고 `SHP-1047`이 빠집니다. 릴리스 판정은 `FAIL`입니다. |
| 수정 버전에서 정상 내보내기 확인 | `2.0.1`에서 보류 건을 포함한 정상 7건이 순서대로 기록됩니다. 릴리스 판정은 `PASS`입니다. |

## Windows VM 준비

64비트 Windows 11 테스트 VM을 준비하고 관리자 계정으로 데스크톱에 로그인합니다. 아티팩트 폴더를 VM에 복사한 뒤 그 폴더에서 관리자 권한으로 Windows PowerShell을 엽니다. Windows 기본 구성 요소로 패키지를 빌드하고, 앱에서는 폴더에 포함된 샘플 CSV를 사용합니다. [Dispatch Board 아티팩트](../validation/artifacts/release-qa-windows)

```powershell
$sample = (Get-Location).Path
$workspace = Join-Path $env:LOCALAPPDATA ('OSLab\DispatchQA-' + [guid]::NewGuid())
$packages = Join-Path $workspace 'packages'
$data = Join-Path $workspace 'shipments'
$evidence = Join-Path $workspace 'evidence'
New-Item -Path $packages, $data, $evidence -ItemType Directory -Force | Out-Null
Copy-Item (Join-Path $sample 'input.csv') $data

powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\package-release.ps1 -OutputDir $packages
if ($LASTEXITCODE -ne 0) { throw 'MSI build failed.' }

$launcher = Join-Path ${env:ProgramFiles(x86)} 'OSLab\Dispatch Board\Start-DispatchBoard.ps1'
$baseline = Join-Path $evidence 'dispatch-before-upgrade.csv'

function Open-DispatchBoard {
    $arguments = '-NoProfile -ExecutionPolicy Bypass -STA -File "{0}" -DataDir "{1}"' -f $launcher, $data
    Start-Process powershell.exe -ArgumentList $arguments -WindowStyle Hidden
}

function Test-DispatchGate {
    param([string]$Mode, [string]$BaselinePath)

    $options = @()
    if ($BaselinePath) { $options += @('-Baseline', $BaselinePath) }
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Verify-Dispatch.ps1 `
        -Mode $Mode -DataDir $data @options `
        -ReportPath (Join-Path $evidence "$Mode.html") `
        -ResultPath (Join-Path $evidence "$Mode.json")
    if ($LASTEXITCODE -ne 0) { throw "Unexpected result in $Mode. See $evidence." }
}
```

Codex 또는 Claude에서 이 VM의 VMID로 연결합니다. `screenshot`으로 버튼을 찾고 최신 `frame_id`로 `click`을 호출합니다. 단축키는 `press_key`로 보냅니다. 조작한 뒤 다시 캡처하면 바뀐 화면을 확인할 수 있습니다. [OSLab MCP 등록과 도구 사용법](computer-use-mcp.ko.md)

## 시나리오 실행

아래 명령은 준비 단계와 같은 PowerShell 세션에서 실행합니다. 버튼과 단축키는 Dispatch Board 창에서 조작합니다.

1. **설치하고 데이터 가져오기.** Windows Installer 마법사를 열어 설치를 마친 뒤 앱을 실행합니다.

   ```powershell
   $msi = Join-Path $packages 'DispatchBoard-1.0.0.msi'
   $log = Join-Path $evidence 'install-1.0.0.log'
   $installer = Start-Process msiexec.exe -ArgumentList ('/i "{0}" /l*v "{1}"' -f $msi, $log) -Wait -PassThru
   if ($installer.ExitCode -ne 0) { throw "Installation failed. See $log." }
   Open-DispatchBoard
   ```

   **Import CSV**를 누르거나 **Ctrl+I**를 입력합니다. 화면에 정상 7건과 반려 1건이 표시되면 검증을 실행합니다.

   ```powershell
   Test-DispatchGate fresh-import
   ```

2. **배송 보류를 저장하고 내보내기.** `SHP-1041`을 선택한 뒤 **Hold / release**를 누르거나 **Ctrl+H**를 입력합니다. **Export manifest**를 누르거나 **Ctrl+E**를 입력해 CSV를 만듭니다. 결과를 검증하고 업그레이드 전 CSV를 복사한 뒤 Dispatch Board를 닫습니다.

   ```powershell
   Test-DispatchGate export
   Copy-Item (Join-Path $data 'dispatch-export.csv') $baseline
   ```

3. **업그레이드하고 기존 데이터 열기.** `2.0.0`을 설치하고 같은 데이터 폴더를 엽니다. `SHP-1041`이 보류 상태인지 확인합니다. CSV가 설치 전 상태로 보존되었는지 검증하려면 새로 내보내기 전에 `upgrade` 검사를 실행합니다.

   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install-release.ps1 `
       -Package (Join-Path $packages 'DispatchBoard-2.0.0.msi') `
       -LogPath (Join-Path $evidence 'install-2.0.0.log')
   if ($LASTEXITCODE -ne 0) { throw 'Upgrade to 2.0.0 failed.' }
   Open-DispatchBoard
   ```

   ```powershell
   Test-DispatchGate upgrade $baseline
   ```

4. **내보내기 결함 재현.** `2.0.0`에서 **Export manifest**를 다시 누릅니다. 보고서에서 행 개수와 내용 검사 두 항목이 실패하고 어떤 배송 건이 누락됐는지 확인합니다.

   ```powershell
   Test-DispatchGate regression
   Copy-Item (Join-Path $data 'dispatch-export.csv') (Join-Path $evidence 'dispatch-2.0.0.csv')
   Invoke-Item (Join-Path $evidence 'regression.html')
   ```

   의도한 결함만 정확히 감지하면 검증 스크립트의 종료 코드는 0입니다. HTML과 JSON의 릴리스 판정은 실제 결과인 `FAIL`로 표시됩니다.

5. **수정 확인.** Dispatch Board를 닫고 `2.0.1`을 설치합니다. 같은 데이터 폴더를 다시 열고 **Export manifest**를 누릅니다. 검증 스크립트는 CSV의 모든 값과 행 순서, 보류 상태를 대조합니다.

   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install-release.ps1 `
       -Package (Join-Path $packages 'DispatchBoard-2.0.1.msi') `
       -LogPath (Join-Path $evidence 'install-2.0.1.log')
   if ($LASTEXITCODE -ne 0) { throw 'Installation of 2.0.1 failed.' }
   Open-DispatchBoard
   ```

   ```powershell
   Test-DispatchGate fixed
   $fixed = Join-Path $data 'dispatch-export.csv'
   if ((Get-FileHash $baseline -Algorithm SHA256).Hash -ne (Get-FileHash $fixed -Algorithm SHA256).Hash) {
       throw 'The patched export differs from the 1.0.0 baseline.'
   }
   Invoke-Item (Join-Path $evidence 'fixed.html')
   ```

결과 폴더에는 MSI 로그, 업그레이드 전 CSV, 배송 건이 누락된 CSV, JSON과 HTML 보고서가 남습니다. 데이터 폴더에서는 `dispatch-state.json`으로 앱 동작 기록을, `dispatch-export.csv`로 마지막 내보내기를 확인할 수 있습니다. 보존할 파일은 VM을 정리하기 전에 복사합니다.
