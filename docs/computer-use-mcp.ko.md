# VM 화면 조작 MCP

[English](computer-use-mcp.md) | 한국어

`oslab-mcp`는 실행 중인 Proxmox QEMU VM의 화면을 캡처하고 해당 VM에 클릭과 키 입력을 보냅니다. VM 콘솔 창을 닫아도 VM이 켜져 있으면 동작합니다. 호스트에서 마우스와 키보드를 계속 사용할 수 있으며, GUI 제어는 QEMU Guest Agent 설치 여부와 무관합니다.

OSLab CLI의 시나리오 실행은 테스트용 VM을 복제하고 부팅할 수 있습니다. MCP는 지정한 실행 중 VM에 연결하며, Windows 안에 Computer Use 프로그램을 설치할 필요가 없습니다. 로그인 화면도 캡처하고 조작할 수 있습니다. 메모장처럼 데스크톱에서 실행하는 작업은 게스트에 로그인한 뒤 시작합니다.

## 준비와 등록

- 그래픽 콘솔이 있는 테스트 VM을 실행하고 VMID를 확인합니다. 픽셀 좌표로 클릭하려면 VM에 절대 좌표 포인팅 장치가 필요합니다. Proxmox QEMU의 기본 USB 태블릿이 이 역할을 합니다. 시나리오를 마친 뒤 복제 VM에 연결하려면 실행할 때 `--keep-vm`을 지정합니다. [OSLab 시작하기](getting-started.ko.md)
- 기존 OSLab config와 env 파일을 사용합니다. 토큰 변수를 이미 환경에 설정했다면 `--env-file`은 생략할 수 있습니다. Proxmox API 토큰에는 대상 VM을 조회할 권한과 `VM.Console` 권한이 필요합니다. 프록시를 거친다면 Proxmox 콘솔 WebSocket 연결도 가능해야 합니다. [Proxmox 연결 안내](proxmox-connection.ko.md)
- MCP 도구가 반환하는 이미지를 모델에 전달할 수 있는 로컬 stdio MCP 클라이언트를 사용합니다.

Codex에서는 README의 [CLI 등록과 메모장 데모](../README.ko.md#codex-mcp)를 따릅니다. 등록 후 이미 열려 있던 채팅의 도구 목록에 `oslab`이 보이지 않으면 데스크톱 앱을 재시작하고 같은 채팅의 `/mcp`에서 확인합니다. [Codex MCP 설정](https://learn.chatgpt.com/docs/extend/mcp#configure-in-the-chatgpt-desktop-app)

<a id="claude-code"></a>
### Claude Code

`--scope user`로 등록하면 같은 OS 계정에서 어느 프로젝트를 열어도 OSLab을 사용할 수 있습니다. Claude Desktop의 로컬 Code 세션에서도 이 설정을 읽습니다. Claude는 Codex와 같은 로컬 stdio 서버를 실행하며, 모든 프로젝트에서 등록한 VMID만 제어할 수 있습니다. [Claude Code 사용자 범위](https://code.claude.com/docs/en/mcp#user-scope) · [Claude Desktop Code 탭](https://code.claude.com/docs/en/desktop#mcp-servers-from-the-claude-desktop-chat-app)

OSLab 저장소에서 아래 PowerShell 명령을 실행하고 테스트 VM의 VMID를 입력합니다. 여러 VM에 연결하려면 VMID마다 `--vm-id`를 추가합니다.

```powershell
$repoPath = (Get-Location).Path
$uvPath = (Get-Command uv -CommandType Application).Source
$vmId = Read-Host '테스트 VM의 VMID'
claude mcp add --transport stdio --scope user oslab -- $uvPath --directory $repoPath `
  run --locked --extra computer-use oslab-mcp --config config/oslab.local.yaml `
  --env-file config/oslab.local.env --vm-id $vmId
claude mcp get oslab
```

Claude Code를 열고 `/mcp`에서 `oslab`이 연결되었는지 확인합니다.

<a id="claude-desktop"></a>
### Claude Desktop 채팅

Claude Desktop의 **Settings → Developer → Edit Config**를 열고 `claude_desktop_config.json`의 `mcpServers`에 `oslab` 항목을 추가합니다. `command`에는 `uv` 실행 파일의 절대 경로를, `--directory` 뒤에는 OSLab 저장소의 절대 경로를 넣습니다. 예시 VMID `123`, `124`는 제어할 VM의 번호로 바꿉니다. `mcpServers` 형식을 쓰는 다른 로컬 클라이언트에도 같은 설정을 사용할 수 있습니다. [MCP 클라이언트 설정](https://py.sdk.modelcontextprotocol.io/get-started/real-host/)

```json
{
  "mcpServers": {
    "oslab": {
      "command": "C:/path/to/uv.exe",
      "args": [
        "--directory", "C:/path/to/oslab",
        "run", "--locked", "--extra", "computer-use", "oslab-mcp",
        "--config", "config/oslab.local.yaml",
        "--env-file", "config/oslab.local.env",
        "--vm-id", "123",
        "--vm-id", "124"
      ]
    }
  }
}
```

Claude Desktop을 완전히 종료한 뒤 다시 열고 채팅의 도구 목록에서 `oslab`을 확인합니다. [Claude Desktop 설정](https://py.sdk.modelcontextprotocol.io/get-started/real-host/#claude-desktop)

### 연결 확인

Codex, Claude Code, Claude Desktop에서 다음과 같이 요청할 수 있습니다.

> OSLab으로 허용된 VM을 조회해 줘. 테스트 VM의 화면을 캡처하고 이미지에서 실제로 보이는 요소 하나를 알려 줘.

VM 목록이 나오면 Proxmox API 연결을 확인한 것입니다. 화면을 보고 답하면 MCP 이미지가 모델에도 전달된 것입니다.

## 캡처하고 조작하기

| 도구 | 동작 |
| --- | --- |
| `list_vms()` | 허용 목록에서 토큰으로 조회할 수 있고 현재 실행 중인 QEMU VM의 `vm_id`, `name`, `node`를 반환합니다. |
| `screenshot(vm_id)` | VM 콘솔에 연결해 PNG 이미지와 `vm_id`, `frame_id`, `width`, `height`를 반환합니다. |
| `click(vm_id, frame_id, x, y, button="left")` | 같은 VM의 최신 캡처를 기준으로 클릭합니다. 좌표는 왼쪽 위 `(0, 0)`에서 시작하는 픽셀 단위입니다. `left`, `middle`, `right` 버튼을 사용할 수 있습니다. |
| `move_mouse(vm_id, frame_id, x, y)` | 같은 VM의 최신 캡처를 기준으로 클릭 없이 포인터를 옮깁니다. 마우스를 올려 두거나 클릭할 위치로 미리 이동할 때 사용합니다. |
| `press_key(vm_id, keys)` | 캡처로 연결한 VM에 키 또는 조합을 보냅니다. `['Enter']`, `['Win', 'r']`, `['Ctrl', 'a']`처럼 지정합니다. 한 글자 키는 출력 가능한 ASCII 범위를 지원합니다. |
| `close_console(vm_id)` | 해당 콘솔 연결을 닫습니다. VM 전원은 그대로 유지됩니다. |

`list_vms`로 VMID를 확인하고 `screenshot`으로 첫 화면을 가져옵니다. 새 창이 열리거나 화면 배치가 바뀌면 다시 캡처해 버튼 위치와 `frame_id`를 갱신합니다. `press_key` 한 번은 키 하나 또는 동시에 누르는 조합 하나입니다. 문장은 글자마다 호출하고, 결과는 게스트의 키보드 배열과 입력기 상태에 따라 달라집니다.

### Windows에서 입력한 내용을 다시 확인하기

1. 로그인된 테스트 VM을 캡처합니다. `['Win', 'r']`을 누르고 실행 창이 뜨면 `notepad`를 한 글자씩 입력한 뒤 `Enter`를 누릅니다.
2. 메모장 화면을 다시 캡처한 뒤 편집 영역을 클릭하고 `oslab mcp ok`를 입력합니다. `Ctrl+F`로 같은 문구를 찾아 화면에 강조 표시되는지 확인합니다.
3. `Ctrl+S`로 저장 창을 열고 문서 폴더에 새 이름으로 저장합니다. 메모장 탭을 닫은 뒤 `Win+E`로 파일 탐색기를 열고 문서 폴더에서 방금 저장한 파일을 다시 엽니다.
4. 새로 캡처한 메모장 화면에서 파일 이름과 내용을 확인합니다.

사용을 마치면 `close_console`로 연결을 종료합니다. `--keep-vm`으로 보존한 테스트 VM은 VMID와 소유자를 확인한 뒤 기존 복구 절차에 따라 정리합니다. [VM 정리 절차](proxmox-connection.ko.md#stale-vm-and-vmid-range-recovery)

## 구현 방식

1. **VM 연결.** MCP 클라이언트가 로컬 `oslab-mcp` 프로세스와 stdio로 통신합니다. 서버는 OSLab의 Proxmox 설정을 읽고 `--vm-id` 허용 목록에서 토큰으로 조회할 수 있는 실행 중인 QEMU VM을 찾습니다. 첫 캡처 요청이 들어오면 해당 VM의 콘솔을 연결합니다. [MCP 도구와 세션](../src/oslab/mcp_server.py)
2. **인증과 콘솔.** OSLab의 Proxmox REST 클라이언트가 API 토큰을 사용해 대상 VM의 `vncproxy`에서 단기 콘솔 티켓을 받습니다. 전송 코드가 같은 VM의 `vncwebsocket`에 접속해 VNC 인증을 마칩니다. Proxmox API가 HTTPS이면 콘솔 연결에도 WSS를 사용합니다. [Proxmox 콘솔 전송](../src/oslab/providers/proxmox_console.py)
3. **화면과 입력.** RFB(Remote Framebuffer) 3.7/3.8의 전체 프레임을 PNG로 변환해 MCP 이미지로 반환합니다. 화면 크기가 바뀌면 전송 코드가 새 크기로 프레임을 다시 요청합니다. 클릭의 픽셀 좌표와 키의 누름·뗌은 RFB 포인터 및 키 이벤트로 전달되어 QEMU의 게스트 가상 입력 장치에 도달합니다. [RFB 명세](https://www.rfc-editor.org/rfc/rfc6143.html#section-7.5)

한 MCP 프로세스에서 VM마다 WebSocket, 최신 프레임, 요청을 직렬화하는 잠금을 따로 유지합니다. 서로 다른 VM은 동시에 조작할 수 있습니다. 같은 VM에 수동 콘솔이나 다른 MCP 프로세스도 연결하면 게스트 화면과 입력 장치를 공유합니다.

클릭과 포인터 이동은 해당 VM의 최신 `frame_id`와 화면 안의 좌표를 요구합니다. 연결 오류나 제한 시간 초과로 콘솔이 끊기면 다시 캡처해 연결을 엽니다. 중단된 입력은 자동으로 다시 보내지 않으므로 실제 화면을 확인하고 필요한 동작을 다시 요청합니다. 재연결 때 같은 VMID의 이름이나 노드가 달라졌다면 대상을 확인한 뒤 MCP 서버를 재시작합니다. 콘솔 종료나 MCP 프로세스 종료는 연결만 정리하며 VM 전원은 유지합니다.

### 코드 검증

```powershell
uv run --locked --extra computer-use python -m pytest -q tests/test_mcp_server.py tests/test_proxmox_console.py
```

테스트는 VM 접근 범위와 동시 요청, 재연결, 프레임 디코딩과 입력 이벤트를 가짜 Proxmox 응답으로 확인합니다. 실제 랩에서 콘솔 경로와 게스트 입력을 확인하려면 위의 Windows 절차를 실행합니다.
