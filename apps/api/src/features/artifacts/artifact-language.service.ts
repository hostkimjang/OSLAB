import { BadRequestException, Injectable } from "@nestjs/common";
import { execFile, spawn, type ChildProcessWithoutNullStreams } from "child_process";
import { existsSync } from "fs";
import path from "path";
import { pathToFileURL } from "url";
import {
  createMessageConnection,
  RequestType,
  StreamMessageReader,
  StreamMessageWriter,
  type MessageConnection,
} from "vscode-jsonrpc/node";
import type {
  ArtifactAssistCompletionItem,
  ArtifactAssistCompletionRequest,
  ArtifactAssistCompletionResponse,
  ArtifactAssistDiagnosticsRequest,
  ArtifactAssistDiagnosticsResponse,
  ArtifactAssistIssue,
  ArtifactLanguageKind,
  ArtifactLanguageToolDetail,
  ArtifactLanguageToolMode,
  ArtifactLanguageToolState,
  ArtifactLanguageToolStatus,
} from "@oslab/shared";

const SUPPORTED_LANGUAGES: ArtifactLanguageKind[] = ["powershell", "shell", "python", "json", "bat", "c", "plaintext"];
const OSLAB_PLACEHOLDERS = ["ArtifactDir", "OutputPath", "ScenarioId", "RunId"];
const TOOL_CACHE_TTL_MS = 30_000;
const LSP_COMPLETION_TIMEOUT_MS = 1_500;
const LSP_IDLE_DISPOSE_MS = process.env.NODE_ENV === "test" || process.execArgv.includes("--test") ? 500 : 30_000;
const InitializeRequest = new RequestType<any, any, void>("initialize");
const CompletionRequest = new RequestType<any, any, void>("textDocument/completion");

@Injectable()
export class ArtifactLanguageService {
  private readonly statusCache = new Map<ArtifactLanguageKind, { checkedAt: number; status: ArtifactLanguageToolStatus }>();
  private readonly lspSessions = new Map<ArtifactLanguageKind, LanguageServerSession>();

  async languageTools(force = false): Promise<ArtifactLanguageToolStatus[]> {
    return Promise.all(SUPPORTED_LANGUAGES.map((language) => this.toolStatus(language, force)));
  }

  async toolStatus(language: ArtifactLanguageKind, force = false): Promise<ArtifactLanguageToolStatus> {
    const normalized = normalizeLanguage(language);
    const cached = this.statusCache.get(normalized);
    if (!force && cached && Date.now() - cached.checkedAt < TOOL_CACHE_TTL_MS) return cached.status;
    const status = await this.inspectToolStatus(normalized);
    this.statusCache.set(normalized, { checkedAt: Date.now(), status });
    return status;
  }

  async complete(request: ArtifactAssistCompletionRequest): Promise<ArtifactAssistCompletionResponse> {
    const artifactPath = normalizeArtifactAssistPath(request.path);
    const language = normalizeLanguage(request.language || languageForArtifactPath(artifactPath));
    const status = await this.toolStatus(language);
    const prefix = extractCompletionPrefix(request.content, request.line, request.column);
    const mode = status.mode || "internal";
    // The API exposes one LSP-shaped surface; unavailable language servers fall back to OSLAB internal providers.
    const lspItems = mode === "lsp" ? await this.completeFromLanguageServer(language, artifactPath, request).catch(() => []) : [];
    const fallbackItems = languageCompletions(language);
    const items = mergeCompletionItems([...rankCompletionItems(lspItems, prefix).slice(0, 30), ...rankCompletionItems(fallbackItems, prefix)]);
    return {
      ok: true,
      language,
      mode,
      checkedAt: new Date().toISOString(),
      items,
      toolStatus: status,
      fallbackReason: mode === "setupNeeded" || mode === "internal" ? "Using OSLAB internal provider until a dedicated LSP server is available." : null,
    };
  }

  async diagnostics(request: ArtifactAssistDiagnosticsRequest): Promise<ArtifactAssistDiagnosticsResponse> {
    const artifactPath = normalizeArtifactAssistPath(request.path);
    const language = normalizeLanguage(request.language || languageForArtifactPath(artifactPath));
    const status = await this.toolStatus(language);
    const issues = inspectContent(artifactPath, request.content || "", language);
    return {
      ok: !issues.some((issue) => issue.severity === "error"),
      language,
      mode: status.mode || "internal",
      checkedAt: new Date().toISOString(),
      issues,
      toolStatus: status,
      fallbackReason: status.mode === "setupNeeded" ? "Dedicated LSP setup is not complete; static diagnostics are still active." : null,
    };
  }

  private async inspectToolStatus(language: ArtifactLanguageKind): Promise<ArtifactLanguageToolStatus> {
    if (language === "python") {
      const bin = findPackageBin("pyright-langserver");
      return summarizeStatus(language, "Python", bin ? "lsp" : "setupNeeded", "Repo-managed Pyright provides Python completion and diagnostics.", [
        bin ? toolDetail("pyright-langserver", "Pyright LSP", "available", bin, "Repo-managed Python language server.") : toolDetail("pyright-langserver", "Pyright LSP", "missing", undefined, "Run pnpm install to restore repo-managed Pyright."),
      ]);
    }
    if (language === "shell") {
      const bin = findPackageBin("bash-language-server");
      return summarizeStatus(language, "Shell", bin ? "lsp" : "setupNeeded", "Repo-managed bash-language-server provides shell completion and diagnostics.", [
        bin ? toolDetail("bash-language-server", "Bash Language Server", "available", bin, "Repo-managed shell language server.") : toolDetail("bash-language-server", "Bash Language Server", "missing", undefined, "Run pnpm install to restore repo-managed bash-language-server."),
      ]);
    }
    if (language === "json") {
      const bin = findPackageBin("vscode-json-language-server");
      return summarizeStatus(language, "JSON", bin ? "lsp" : "setupNeeded", "Repo-managed VS Code JSON language server provides JSON completion and diagnostics.", [
        bin ? toolDetail("vscode-json-language-server", "VS Code JSON LSP", "available", bin, "Repo-managed JSON language server.") : toolDetail("vscode-json-language-server", "VS Code JSON LSP", "missing", undefined, "Run pnpm install to restore repo-managed JSON language server."),
      ]);
    }
    if (language === "powershell") {
      const pwsh = await commandVersion("pwsh", ["--version"]);
      const windowsPowerShell = await commandVersion("powershell", ["-NoProfile", "-Command", "$PSVersionTable.PSVersion.ToString()"]);
      const editorServices = findProjectTool("powershell-editor-services");
      return summarizeStatus(language, "PowerShell", editorServices ? "lsp" : "setupNeeded", "PowerShell Editor Services is project-local when enabled; internal completion stays active without it.", [
        editorServices ? toolDetail("powershell-editor-services", "PowerShell Editor Services", "available", editorServices, "Project-local PowerShell LSP.") : toolDetail("powershell-editor-services", "PowerShell Editor Services", "missing", undefined, "Project-local LSP package is not prepared yet."),
        pwsh ? toolDetail("pwsh", "PowerShell 7", "available", "pwsh", pwsh) : toolDetail("pwsh", "PowerShell 7", "missing", undefined, "Optional execution host."),
        windowsPowerShell ? toolDetail("powershell", "Windows PowerShell", "available", "powershell", windowsPowerShell) : toolDetail("powershell", "Windows PowerShell", "missing", undefined, "Windows fallback host."),
      ]);
    }
    if (language === "c") {
      const clangd = findProjectTool("clangd") || await commandVersion("clangd", ["--version"]);
      return summarizeStatus(language, "C", clangd ? "lsp" : "setupNeeded", "clangd can be attached from the project tool cache; internal C completion stays active without it.", [
        clangd ? toolDetail("clangd", "clangd", "available", "clangd", String(clangd).split(/\r?\n/)[0]) : toolDetail("clangd", "clangd", "missing", undefined, "Project-local clangd is not prepared yet."),
      ]);
    }
    if (language === "bat") {
      return summarizeStatus(language, "Batch/CMD", "internal", "Batch/CMD uses the OSLAB internal LSP-compatible provider.", [
        toolDetail("oslab-bat-provider", "OSLAB Batch provider", "available", "internal", "Completion and warnings are provided by Artifact Studio."),
      ]);
    }
    return summarizeStatus(language, "Plain text", "internal", "Plain text uses placeholder completion only.", [
      toolDetail("oslab-text-provider", "OSLAB text provider", "available", "internal", "Placeholder completion is provided by Artifact Studio."),
    ]);
  }

  private async completeFromLanguageServer(language: ArtifactLanguageKind, artifactPath: string, request: ArtifactAssistCompletionRequest): Promise<ArtifactAssistCompletionItem[]> {
    if (!["python", "shell", "json"].includes(language)) return [];
    const session = await this.getLanguageServerSession(language);
    if (!session) return [];
    const uri = artifactUri(artifactPath);
    const rawItems = await session.complete(uri, language, request.content || "", request.line, request.column);
    return rawItems.map((item, index) => mapLspCompletionItem(item, index, language)).filter((item): item is ArtifactAssistCompletionItem => Boolean(item));
  }

  private async getLanguageServerSession(language: ArtifactLanguageKind): Promise<LanguageServerSession | null> {
    const existing = this.lspSessions.get(language);
    if (existing && !existing.disposed) return existing;
    const command = languageServerCommand(language);
    if (!command) return null;
    const session = new LanguageServerSession(language, command.command, command.args);
    this.lspSessions.set(language, session);
    try {
      await session.start();
      return session;
    } catch {
      session.dispose();
      this.lspSessions.delete(language);
      return null;
    }
  }
}

class LanguageServerSession {
  private process: ChildProcessWithoutNullStreams | null = null;
  private connection: MessageConnection | null = null;
  private initialized = false;
  private documentVersions = new Map<string, number>();
  private openedDocuments = new Set<string>();
  private idleTimer: NodeJS.Timeout | null = null;
  disposed = false;

  constructor(
    private readonly language: ArtifactLanguageKind,
    private readonly command: string,
    private readonly args: string[],
  ) {}

  async start(): Promise<void> {
    if (this.initialized) return;
    this.clearIdleTimer();
    const spawnTarget = lspSpawnTarget(this.command, this.args);
    const child = spawn(spawnTarget.command, spawnTarget.args, {
      cwd: process.cwd(),
      shell: spawnTarget.shell,
      stdio: "pipe",
      windowsHide: true,
    });
    child.unref();
    (child.stdout as any).unref?.();
    (child.stderr as any).unref?.();
    this.process = child;
    child.on("exit", () => this.dispose());
    const connection = createMessageConnection(new StreamMessageReader(child.stdout), new StreamMessageWriter(child.stdin));
    this.connection = connection;
    connection.listen();
    await withTimeout(connection.sendRequest(InitializeRequest, {
      processId: process.pid,
      rootUri: pathToFileURL(process.cwd()).toString(),
      capabilities: {
        textDocument: {
          completion: {
            completionItem: {
              snippetSupport: true,
              documentationFormat: ["markdown", "plaintext"],
            },
          },
        },
        workspace: { configuration: true },
      },
    }), LSP_COMPLETION_TIMEOUT_MS);
    connection.sendNotification("initialized", {});
    this.initialized = true;
  }

  async complete(uri: string, language: ArtifactLanguageKind, content: string, line: number, column: number): Promise<any[]> {
    if (!this.connection || this.disposed) return [];
    await this.start();
    const version = (this.documentVersions.get(uri) || 0) + 1;
    this.documentVersions.set(uri, version);
    const languageId = lspLanguageId(language);
    if (!this.openedDocuments.has(uri)) {
      this.connection.sendNotification("textDocument/didOpen", {
        textDocument: { uri, languageId, version, text: content },
      });
      this.openedDocuments.add(uri);
    } else {
      this.connection.sendNotification("textDocument/didChange", {
        textDocument: { uri, version },
        contentChanges: [{ text: content }],
      });
    }
    const result = await withTimeout(this.connection.sendRequest(CompletionRequest, {
      textDocument: { uri },
      position: { line: Math.max(0, line - 1), character: Math.max(0, column - 1) },
      context: { triggerKind: 1 },
    }), LSP_COMPLETION_TIMEOUT_MS);
    const items = Array.isArray(result) ? result : Array.isArray(result?.items) ? result.items : [];
    this.scheduleIdleDispose();
    return items.slice(0, 80);
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.clearIdleTimer();
    try { this.connection?.dispose(); } catch {}
    try { this.process?.kill(); } catch {}
    this.connection = null;
    this.process = null;
  }

  private scheduleIdleDispose(): void {
    this.clearIdleTimer();
    this.idleTimer = setTimeout(() => this.dispose(), LSP_IDLE_DISPOSE_MS);
    this.idleTimer.unref?.();
  }

  private clearIdleTimer(): void {
    if (!this.idleTimer) return;
    clearTimeout(this.idleTimer);
    this.idleTimer = null;
  }
}

function lspSpawnTarget(command: string, args: string[]): { command: string; args: string[]; shell: boolean } {
  if (process.platform !== "win32" || !command.toLowerCase().endsWith(".cmd")) {
    return { command, args, shell: false };
  }
  // npm package bins are .CMD wrappers on Windows; pass one quoted command string to avoid shell+args warnings.
  const script = [`"${command}"`, ...args.map(quoteCmdArg)].join(" ");
  return { command: script, args: [], shell: true };
}

function quoteCmdArg(value: string): string {
  return /^[A-Za-z0-9_./:-]+$/.test(value) ? value : `"${value.replaceAll("\"", "\\\"")}"`;
}

function summarizeStatus(language: ArtifactLanguageKind, label: string, mode: ArtifactLanguageToolMode, installHint: string, tools: ArtifactLanguageToolDetail[]): ArtifactLanguageToolStatus {
  const hasMissing = tools.some((tool) => tool.state === "missing" || tool.state === "error");
  const hasAvailable = tools.some((tool) => tool.state === "available");
  const state: ArtifactLanguageToolState = mode === "lsp"
    ? "available"
    : mode === "setupNeeded" && hasAvailable
      ? "partial"
      : mode === "setupNeeded"
        ? "missing"
        : "available";
  return {
    language,
    label,
    state: hasMissing && hasAvailable && mode !== "internal" ? "partial" : state,
    mode,
    serverManaged: mode === "lsp" || mode === "internal",
    installable: mode === "setupNeeded",
    installHint,
    nextAction: mode === "lsp"
      ? "LSP-backed completion is available from the dashboard API server."
      : mode === "setupNeeded"
        ? "Internal completion is active. Prepare the project-local LSP tool for richer diagnostics."
        : "Internal OSLAB completion is active.",
    tools,
  };
}

function toolDetail(id: string, label: string, state: Exclude<ArtifactLanguageToolState, "partial">, command?: string, hint?: string): ArtifactLanguageToolDetail {
  return { id, label, state, command, version: state === "available" && hint && !hint.includes(" ") ? hint : undefined, hint };
}

function languageServerCommand(language: ArtifactLanguageKind): { command: string; args: string[] } | null {
  if (language === "python") {
    const command = findPackageBin("pyright-langserver");
    return command ? { command, args: ["--stdio"] } : null;
  }
  if (language === "json") {
    const command = findPackageBin("vscode-json-language-server");
    return command ? { command, args: ["--stdio"] } : null;
  }
  if (language === "shell") {
    const command = findPackageBin("bash-language-server");
    return command ? { command, args: ["start"] } : null;
  }
  return null;
}

function lspLanguageId(language: ArtifactLanguageKind): string {
  if (language === "shell") return "shellscript";
  if (language === "bat") return "bat";
  if (language === "powershell") return "powershell";
  if (language === "plaintext") return "plaintext";
  return language;
}

function artifactUri(artifactPath: string): string {
  return pathToFileURL(path.resolve(process.cwd(), artifactPath.replaceAll("/", path.sep))).toString();
}

function mapLspCompletionItem(item: any, index: number, language: ArtifactLanguageKind): ArtifactAssistCompletionItem | null {
  const label = typeof item?.label === "string" ? item.label : null;
  if (!label) return null;
  const insertText = typeof item.insertText === "string"
    ? item.insertText
    : typeof item.textEdit?.newText === "string"
      ? item.textEdit.newText
      : label;
  const detail = typeof item.detail === "string" ? item.detail : "Open language service completion";
  const documentation = typeof item.documentation === "string"
    ? item.documentation
    : typeof item.documentation?.value === "string"
      ? item.documentation.value
      : detail;
  return {
    id: `lsp-${language}-${index}-${label}`,
    label,
    detail,
    documentation,
    language,
    insertText,
    source: "lsp",
    kind: mapLspCompletionKind(item.kind),
  };
}

function mapLspCompletionKind(kind: number | undefined): ArtifactAssistCompletionItem["kind"] {
  if (kind === 3) return "function";
  if (kind === 4) return "function";
  if (kind === 5) return "property";
  if (kind === 6) return "variable";
  if (kind === 9) return "module";
  if (kind === 14) return "keyword";
  if (kind === 15) return "snippet";
  if (kind === 17) return "file";
  return "text";
}

function withTimeout<T>(promise: Promise<T>, timeoutMs: number): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`LSP request timed out after ${timeoutMs}ms`)), timeoutMs);
    promise.then((value) => {
      clearTimeout(timer);
      resolve(value);
    }, (error) => {
      clearTimeout(timer);
      reject(error);
    });
  });
}

function mergeCompletionItems(items: ArtifactAssistCompletionItem[]): ArtifactAssistCompletionItem[] {
  const seen = new Set<string>();
  return items.filter((item) => {
    const key = item.label.toLowerCase();
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  }).slice(0, 60);
}

function languageCompletions(language: ArtifactLanguageKind): ArtifactAssistCompletionItem[] {
  const source = "internal";
  const common: ArtifactAssistCompletionItem[] = OSLAB_PLACEHOLDERS.map((placeholder) => ({
    id: `placeholder-${placeholder}`,
    label: `{{${placeholder}}}`,
    detail: `${placeholder} OSLAB placeholder`,
    documentation: "VM 실행 시 대시보드가 치환하는 OSLAB placeholder입니다.",
    language,
    insertText: `{{${placeholder}}}`,
    source: "snippet",
    kind: "variable",
  }));
  if (language === "python") {
    return [
      completion("python-print", "print", "Python 출력 함수", "print(${1:\"artifact executed\"})", language, source, "function"),
      completion("python-range", "range", "반복문에서 정수 구간을 만듭니다.", "range(${1:3})", language, source, "function"),
      completion("python-for-range", "for i in range", "가장 흔한 Python 반복문 골격입니다.", "for ${1:i} in range(${2:3}):\n    ${3:print($1)}", language, "snippet", "snippet"),
      completion("python-if-name-main", "if __name__ == \"__main__\"", "직접 실행될 때만 main 함수를 호출하는 Python 골격입니다.", "if __name__ == \"__main__\":\n    ${1:main()}", language, "snippet", "snippet"),
      completion("python-def-main", "def main", "스크립트 진입점을 함수로 분리합니다.", "def main() -> int:\n    ${1:return 0}", language, "snippet", "snippet"),
      completion("python-len", "len", "컬렉션 길이를 계산합니다.", "len(${1:value})", language, source, "function"),
      completion("python-enumerate", "enumerate", "index와 값을 함께 순회합니다.", "enumerate(${1:items})", language, source, "function"),
      completion("python-open", "open", "파일을 열 때 쓰는 내장 함수입니다.", "open(${1:path}, ${2:\"r\"}, encoding=\"utf-8\")", language, source, "function"),
      completion("python-subprocess-run", "subprocess.run", "외부 명령 실행 결과를 명시적으로 확인합니다.", "subprocess.run(${1:[\"cmd\"]}, check=True, capture_output=True, text=True)", language, source, "function"),
      completion("python-path-write-text", "Path.write_text", "UTF-8 텍스트 파일을 저장합니다.", "Path(${1:r\"{{OutputPath}}\"}).write_text(${2:text}, encoding=\"utf-8\")", language, source, "function"),
      completion("python-path-read-text", "Path.read_text", "UTF-8 텍스트 파일을 읽습니다.", "Path(${1:path}).read_text(encoding=\"utf-8\")", language, source, "function"),
      completion("python-json-dumps", "json.dumps", "dict를 JSON 문자열로 직렬화합니다.", "json.dumps(${1:result}, indent=2)", language, source, "function"),
      completion("python-json-dump", "json.dump", "dict를 파일 객체로 JSON 저장합니다.", "json.dump(${1:result}, ${2:file}, indent=2)", language, source, "function"),
      completion("python-json-loads", "json.loads", "JSON 문자열을 Python 객체로 읽습니다.", "json.loads(${1:text})", language, source, "function"),
      completion("python-json-load", "json.load", "JSON 파일 객체를 Python 객체로 읽습니다.", "json.load(${1:file})", language, source, "function"),
      completion("python-path", "Path", "pathlib.Path 객체를 만듭니다.", "Path(${1:r\"{{OutputPath}}\"})", language, source, "function"),
      completion("python-import-json", "import json", "commandResult 출력 계약 작성에 자주 씁니다.", "import json", language, "snippet", "snippet"),
      completion("python-import-subprocess", "import subprocess", "외부 명령 실행 helper입니다.", "import subprocess", language, "snippet", "snippet"),
      completion("python-import-os", "import os", "환경 변수와 경로 정보를 읽을 때 씁니다.", "import os", language, "snippet", "snippet"),
      completion("python-from-pathlib", "from pathlib import Path", "파일 경로를 다룰 때 필요한 import입니다.", "from pathlib import Path", language, "snippet", "snippet"),
      completion("python-output-contract", "OSLAB commandResult JSON", "Results가 읽을 수 있는 안정적인 출력 계약입니다.", "result = {\n    \"schemaVersion\": 1,\n    \"kind\": \"commandResult\",\n    \"exitCode\": 0,\n    \"stdout\": \"ok\\n\",\n    \"stderr\": \"\",\n}", language, "snippet", "snippet"),
      ...common,
    ];
  }
  if (language === "powershell") {
    return [
      completion("ps-write-output", "Write-Output", "PowerShell 표준 출력", "Write-Output ${1:\"artifact executed\"}", language, source, "function"),
      completion("ps-write-host", "Write-Host", "사용자가 보는 콘솔 메시지 출력입니다.", "Write-Host ${1:\"artifact executed\"}", language, source, "function"),
      completion("ps-write-error", "Write-Error", "명시적인 오류 메시지를 출력합니다.", "Write-Error ${1:\"failed\"}", language, source, "function"),
      completion("ps-convert-json", "ConvertTo-Json", "PowerShell 객체를 JSON으로 변환합니다.", "${1:$result} | ConvertTo-Json -Depth 8", language, source, "function"),
      completion("ps-convert-from-json", "ConvertFrom-Json", "JSON 문자열을 PowerShell 객체로 읽습니다.", "${1:$json} | ConvertFrom-Json", language, source, "function"),
      completion("ps-set-content", "Set-Content", "텍스트 파일을 UTF-8로 저장합니다.", "Set-Content -Encoding UTF8 -LiteralPath ${1:$OutputPath} -Value ${2:$json}", language, source, "function"),
      completion("ps-get-content", "Get-Content", "파일 내용을 읽습니다.", "Get-Content -LiteralPath ${1:$OutputPath} -Raw", language, source, "function"),
      completion("ps-test-path", "Test-Path", "파일/폴더 존재 여부를 확인합니다.", "Test-Path -LiteralPath ${1:$path}", language, source, "function"),
      completion("ps-join-path", "Join-Path", "경로를 안전하게 결합합니다.", "Join-Path -Path ${1:$PSScriptRoot} -ChildPath ${2:\"file.txt\"}", language, source, "function"),
      completion("ps-param-output", "param OutputPath", "OSLAB 출력 파일 경로 파라미터", "param(\n  [string]$OutputPath = \"C:\\\\Oslab\\\\command-result.json\"\n)", language, "snippet", "snippet"),
      completion("ps-cim-os", "Get-CimInstance Win32_OperatingSystem", "Windows OS 정보를 가져옵니다.", "Get-CimInstance -ClassName Win32_OperatingSystem", language, source, "function"),
      completion("ps-get-child-item", "Get-ChildItem", "파일 목록을 조회합니다.", "Get-ChildItem -LiteralPath ${1:$PSScriptRoot}", language, source, "function"),
      completion("ps-try-catch", "try/catch", "오류를 잡고 result JSON에 반영합니다.", "try {\n  ${1:# work}\n} catch {\n  Write-Error $_\n  exit 1\n}", language, "snippet", "snippet"),
      ...common,
    ];
  }
  if (language === "shell") {
    return [
      completion("sh-set-eu", "set -eu", "실패를 빠르게 드러내는 shell 안전 옵션", "set -eu", language, "snippet", "snippet"),
      completion("sh-printf", "printf", "portable shell 출력", "printf '%s\\n' ${1:\"artifact executed\"}", language, source, "function"),
      completion("sh-echo", "echo", "간단한 shell 출력", "echo ${1:\"artifact executed\"}", language, source, "function"),
      completion("sh-test-file", "test -f", "파일 존재 여부 확인", "test -f ${1:\"{{OutputPath}}\"}", language, source, "function"),
      completion("sh-if-test", "if test -f", "파일 존재 여부에 따라 분기합니다.", "if test -f ${1:\"{{OutputPath}}\"}; then\n  ${2:printf '%s\\n' ok}\nfi", language, "snippet", "snippet"),
      completion("sh-cat", "cat", "파일 내용을 출력합니다.", "cat ${1:\"{{OutputPath}}\"}", language, source, "function"),
      completion("sh-grep", "grep", "텍스트에서 패턴을 찾습니다.", "grep -n ${1:\"pattern\"} ${2:file}", language, source, "function"),
      completion("sh-sed", "sed", "텍스트를 변환합니다.", "sed -n '${1:1,20}p' ${2:file}", language, source, "function"),
      completion("sh-find", "find", "파일/폴더를 검색합니다.", "find ${1:.} -maxdepth ${2:2} -type ${3:f}", language, source, "function"),
      completion("sh-mkdir", "mkdir -p", "폴더를 생성합니다.", "mkdir -p ${1:\"$(dirname \"{{OutputPath}}\")\"}", language, source, "function"),
      completion("sh-command-result", "commandResult JSON", "shell에서 안정적인 결과 JSON을 작성하는 골격입니다.", "cat > \"{{OutputPath}}\" <<'JSON'\n{\n  \"schemaVersion\": 1,\n  \"kind\": \"commandResult\",\n  \"exitCode\": 0,\n  \"stdout\": \"ok\\n\",\n  \"stderr\": \"\"\n}\nJSON", language, "snippet", "snippet"),
      ...common,
    ];
  }
  if (language === "json") {
    return [
      completion("json-schema-version", "schemaVersion", "OSLAB 결과 JSON schema version", "\"schemaVersion\": 1", language, source, "property"),
      completion("json-kind", "kind", "결과 artifact 종류", "\"kind\": \"commandResult\"", language, source, "property"),
      completion("json-exit-code", "exitCode", "명령 종료 코드", "\"exitCode\": 0", language, source, "property"),
      completion("json-stdout", "stdout", "표준 출력 문자열", "\"stdout\": \"ok\\n\"", language, source, "property"),
      completion("json-stderr", "stderr", "표준 오류 문자열", "\"stderr\": \"\"", language, source, "property"),
      completion("json-metadata", "metadata", "검증에 참고할 부가 정보", "\"metadata\": {\n  \"key\": \"value\"\n}", language, source, "property"),
      completion("json-files", "metadata.files", "파일 상태 assertion에 사용할 metadata", "\"files\": [\n  { \"path\": \"C:\\\\Oslab\\\\file.txt\", \"exists\": true }\n]", language, source, "property"),
      completion("json-command-result", "commandResult object", "Results가 읽는 기본 출력 계약", "{\n  \"schemaVersion\": 1,\n  \"kind\": \"commandResult\",\n  \"exitCode\": 0,\n  \"stdout\": \"ok\\n\",\n  \"stderr\": \"\"\n}", language, "snippet", "snippet"),
      ...common,
    ];
  }
  if (language === "c") {
    return [
      completion("c-printf", "printf", "C formatted stdout", "printf(\"%s\\n\", ${1:\"artifact executed\"});", language, source, "function"),
      completion("c-puts", "puts", "간단한 문자열 출력", "puts(${1:\"artifact executed\"});", language, source, "function"),
      completion("c-fprintf", "fprintf", "stderr 또는 파일 출력", "fprintf(${1:stderr}, \"%s\\n\", ${2:\"message\"});", language, source, "function"),
      completion("c-fopen", "fopen", "파일을 엽니다.", "fopen(${1:\"{{OutputPath}}\"}, ${2:\"w\"})", language, source, "function"),
      completion("c-fclose", "fclose", "파일을 닫습니다.", "fclose(${1:fp});", language, source, "function"),
      completion("c-return-zero", "return 0", "성공 종료 코드", "return 0;", language, source, "keyword"),
      completion("c-main", "int main(void)", "C entrypoint", "int main(void) {\n  puts(\"artifact executed\");\n  return 0;\n}", language, "snippet", "snippet"),
      completion("c-stdio", "#include <stdio.h>", "stdio 함수 include", "#include <stdio.h>", language, "snippet", "snippet"),
      completion("c-stdlib", "#include <stdlib.h>", "exit/system 등 stdlib 선언", "#include <stdlib.h>", language, "snippet", "snippet"),
      ...common,
    ];
  }
  if (language === "bat") {
    return [
      completion("bat-echo", "echo", "Batch stdout", "echo ${1:artifact executed}", language, source, "function"),
      completion("bat-echo-off", "@echo off", "Batch 출력 noise를 줄입니다.", "@echo off", language, source, "keyword"),
      completion("bat-set", "set", "환경 변수 설정", "set ${1:NAME}=${2:value}", language, source, "keyword"),
      completion("bat-if-exist", "if exist", "파일/폴더 존재 여부 분기", "if exist ${1:\"{{OutputPath}}\"} (\n  ${2:echo exists}\n)", language, source, "keyword"),
      completion("bat-for-files", "for %%F in", "파일 반복 처리", "for %%F in (${1:*.*}) do (\n  echo %%F\n)", language, "snippet", "snippet"),
      completion("bat-errorlevel", "if errorlevel", "명령 실패 분기", "if errorlevel 1 exit /b %ERRORLEVEL%", language, source, "keyword"),
      completion("bat-exit-b", "exit /b", "현재 batch 종료", "exit /b ${1:0}", language, source, "keyword"),
      completion("bat-call", "call", "다른 batch/script 호출", "call ${1:script.cmd}", language, source, "function"),
      completion("bat-script-dir", "%~dp0", "현재 batch 파일 폴더", "%~dp0", language, source, "variable"),
      ...common,
    ];
  }
  return [
    completion("text-note", "artifact note", "Artifact 목적을 설명하는 텍스트", "Artifact purpose: ${1:describe this test file}", language, "snippet", "text"),
    ...common,
  ];
}

function completion(id: string, label: string, detail: string, insertText: string, language: ArtifactLanguageKind, source: "lsp" | "internal" | "snippet", kind: ArtifactAssistCompletionItem["kind"]): ArtifactAssistCompletionItem {
  return { id, label, detail, documentation: detail, language, insertText, source, kind };
}

function rankCompletionItems(items: ArtifactAssistCompletionItem[], prefix: string): ArtifactAssistCompletionItem[] {
  const needle = prefix.trim().toLowerCase();
  const scored = items
    .map((item) => {
      const label = item.label.toLowerCase();
      let score = 3;
      if (!needle) score = 2;
      else if (label === needle) score = 0;
      else if (label.startsWith(needle)) score = 1;
      else if (label.includes(needle)) score = 2;
      else score = 4;
      return { item, score };
    })
    .filter((entry) => entry.score < 4 || needle.length < 2)
    .sort((a, b) => a.score - b.score || a.item.label.localeCompare(b.item.label));
  return scored.map((entry) => entry.item).slice(0, 40);
}

function inspectContent(artifactPath: string, content: string, language: ArtifactLanguageKind): ArtifactAssistIssue[] {
  const issues: ArtifactAssistIssue[] = [];
  if (language === "json") {
    try {
      JSON.parse(content || "{}");
    } catch (error: any) {
      issues.push({ severity: "error", code: "json.parse", message: error.message || "Invalid JSON", line: 1, column: 1 });
    }
  }
  for (const rule of diagnosticRulesForLanguage(language)) {
    const pattern = new RegExp(rule.pattern, rule.flags || "i");
    const line = findFirstLineOrNull(content, pattern);
    if (line !== null) {
      issues.push({ severity: rule.severity, code: rule.code, message: rule.message, line });
    }
  }
  const placeholders = [...content.matchAll(/\{\{([A-Za-z0-9_]+)\}\}/g)];
  for (const match of placeholders) {
    if (!OSLAB_PLACEHOLDERS.includes(match[1])) {
      issues.push({ severity: "warning", code: "placeholder.unknown", message: `Unknown OSLAB placeholder: ${match[0]}`, line: lineForIndex(content, match.index || 0), column: columnForIndex(content, match.index || 0) });
    }
  }
  if (["powershell", "python", "shell", "bat"].includes(language) && !/\{\{OutputPath\}\}|OutputPath|command-result|result\.json/i.test(content)) {
    issues.push({ severity: "info", code: "output.contract", message: "Consider writing a stable output JSON so Results can verify the artifact.", line: 1, column: 1 });
  }
  if (/([A-Za-z]:\\Users\\|\/home\/|\/Users\/)/i.test(content)) {
    issues.push({ severity: "info", code: "local.path", message: "Local user paths may not exist inside the VM. Prefer {{ArtifactDir}} or {{OutputPath}}.", line: findFirstLine(content, /([A-Za-z]:\\Users\\|\/home\/|\/Users\/)/i) });
  }
  if (!artifactPath.startsWith("validation/artifacts/")) {
    issues.push({ severity: "error", code: "path.root", message: "Artifact Assist only supports validation/artifacts/** paths.", line: 1, column: 1 });
  }
  return issues;
}

function diagnosticRulesForLanguage(language: ArtifactLanguageKind): Array<{ pattern: string; flags?: string; severity: ArtifactAssistIssue["severity"]; code: string; message: string }> {
  const common = [
    { pattern: "(api[_-]?key|password|secret|token)\\s*[:=]\\s*['\\\"]?[A-Za-z0-9_\\-.]{8,}", flags: "i", severity: "warning" as const, code: "secret.pattern", message: "Possible hardcoded secret. Use env/config references and dashboard redaction instead." },
  ];
  if (language === "powershell") {
    return [
      { pattern: "Remove-Item\\b[\\s\\S]*-Recurse", flags: "i", severity: "warning", code: "dangerous.pattern", message: "Remove-Item -Recurse can remove many files. Confirm the path is disposable VM-only state." },
      { pattern: "\\bInvoke-Expression\\b|\\biex\\b", flags: "i", severity: "warning", code: "powershell.invoke-expression", message: "Invoke-Expression is hard to audit. Prefer explicit commands or argument arrays." },
      { pattern: "\\bSet-ExecutionPolicy\\b", flags: "i", severity: "warning", code: "powershell.execution-policy", message: "Changing execution policy inside validation scripts can hide environment problems." },
      { pattern: "Start-Process\\b[\\s\\S]*-Verb\\s+RunAs", flags: "i", severity: "warning", code: "powershell.elevation", message: "RunAs elevation is interactive and usually breaks automated VM runs." },
      ...common,
    ];
  }
  if (language === "shell") {
    return [
      { pattern: "\\brm\\s+-rf\\b", flags: "i", severity: "warning", code: "dangerous.pattern", message: "rm -rf can remove many files. Confirm the path is disposable VM-only state." },
      { pattern: "\\bcurl\\b[\\s\\S]*\\|\\s*(sh|bash)\\b|\\bwget\\b[\\s\\S]*\\|\\s*(sh|bash)\\b", flags: "i", severity: "warning", code: "shell.pipe-install", message: "curl/wget piped to shell is risky. Pin or vendor setup assets into the artifact." },
      { pattern: "\\bsudo\\b", flags: "i", severity: "info", code: "shell.sudo", message: "sudo may prompt inside the VM. Prefer prepared templates or explicit fixture setup." },
      { pattern: "\\bchmod\\s+-R\\s+777\\b", flags: "i", severity: "warning", code: "shell.chmod-777", message: "chmod -R 777 is overly broad. Narrow the path and mode." },
      ...common,
    ];
  }
  if (language === "python") {
    return [
      { pattern: "subprocess\\.[A-Za-z_]+\\([^\\n)]*shell\\s*=\\s*True", flags: "i", severity: "warning", code: "python.subprocess-shell", message: "subprocess shell=True is harder to quote safely. Prefer argument arrays." },
      { pattern: "\\bos\\.system\\s*\\(", flags: "i", severity: "warning", code: "python.os-system", message: "os.system hides exit/output details. Prefer subprocess.run(..., check=True)." },
      { pattern: "\\bshutil\\.rmtree\\s*\\(", flags: "i", severity: "warning", code: "dangerous.pattern", message: "shutil.rmtree can remove whole directories. Confirm the path is disposable VM-only state." },
      { pattern: "\\beval\\s*\\(|\\bexec\\s*\\(", flags: "i", severity: "warning", code: "python.eval-exec", message: "eval/exec is hard to audit in validation scripts. Prefer explicit parsing." },
      ...common,
    ];
  }
  if (language === "bat") {
    return [
      { pattern: "\\bdel\\s+\\/s\\b", flags: "i", severity: "warning", code: "dangerous.pattern", message: "del /s can remove many files. Confirm the path is disposable VM-only state." },
      { pattern: "\\brd\\s+\\/s\\b|\\brmdir\\s+\\/s\\b", flags: "i", severity: "warning", code: "dangerous.pattern", message: "rmdir /s can remove whole directories. Confirm the path is disposable VM-only state." },
      { pattern: "\\bformat\\s+[A-Z]:", flags: "i", severity: "warning", code: "bat.format", message: "format is destructive and should not be used in dashboard-authored artifacts." },
      { pattern: "\\breg\\s+delete\\b", flags: "i", severity: "warning", code: "bat.reg-delete", message: "Registry deletion should be isolated to an explicit fixture path." },
      ...common,
    ];
  }
  if (language === "c") {
    return [
      { pattern: "\\bgets\\s*\\(", flags: "i", severity: "warning", code: "c.gets", message: "gets is unsafe. Use fgets with an explicit buffer size." },
      { pattern: "\\bstrcpy\\s*\\(", flags: "i", severity: "info", code: "c.strcpy", message: "strcpy can overflow buffers. Prefer bounded copy patterns." },
      { pattern: "\\bsystem\\s*\\(", flags: "i", severity: "warning", code: "c.system", message: "system() hides quoting and exit detail. Prefer explicit process setup in the scenario command." },
      ...common,
    ];
  }
  return common;
}

function normalizeArtifactAssistPath(rawPath: string): string {
  const normalized = (rawPath || "").replaceAll("\\", "/").replace(/^\/+/, "");
  if (!normalized || path.isAbsolute(rawPath) || normalized.split("/").includes("..")) {
    throw new BadRequestException("Artifact Assist path must be a relative validation/artifacts path");
  }
  if (!normalized.startsWith("validation/artifacts/")) {
    throw new BadRequestException("Artifact Assist only supports validation/artifacts/** paths");
  }
  return normalized;
}

function normalizeLanguage(language: ArtifactLanguageKind | undefined): ArtifactLanguageKind {
  if (!language || !SUPPORTED_LANGUAGES.includes(language)) {
    throw new BadRequestException(`Unsupported artifact language: ${language || "<empty>"}`);
  }
  return language;
}

function languageForArtifactPath(artifactPath: string): ArtifactLanguageKind {
  const lower = artifactPath.toLowerCase();
  if (lower.endsWith(".ps1")) return "powershell";
  if (lower.endsWith(".sh")) return "shell";
  if (lower.endsWith(".py")) return "python";
  if (lower.endsWith(".json")) return "json";
  if (lower.endsWith(".c")) return "c";
  if (lower.endsWith(".cmd") || lower.endsWith(".bat")) return "bat";
  return "plaintext";
}

function extractCompletionPrefix(content: string, line: number, column: number): string {
  const lines = content.split(/\r?\n/);
  const lineText = lines[Math.max(0, line - 1)] || "";
  const beforeCursor = lineText.slice(0, Math.max(0, column - 1));
  return beforeCursor.match(/[A-Za-z0-9_.$%{}-]*$/)?.[0] || "";
}

function findPackageBin(name: string): string | undefined {
  const executable = process.platform === "win32" ? `${name}.CMD` : name;
  const candidates = [
    path.join(process.cwd(), "node_modules", ".bin", executable),
    path.join(process.cwd(), "node_modules", ".pnpm", "node_modules", ".bin", executable),
    path.join(process.cwd(), "apps", "api", "node_modules", ".bin", executable),
    path.resolve(__dirname, "..", "..", "..", "..", "node_modules", ".bin", executable),
    path.resolve(__dirname, "..", "..", "..", "..", "node_modules", ".pnpm", "node_modules", ".bin", executable),
  ];
  return candidates.find((candidate) => existsSync(candidate));
}

function findProjectTool(name: string): string | undefined {
  const candidates = [
    path.join(process.cwd(), ".oslab-tools", name),
    path.join(process.cwd(), "apps", "api", ".oslab-tools", name),
  ];
  return candidates.find((candidate) => existsSync(candidate));
}

function commandVersion(command: string, args: string[]): Promise<string | null> {
  return new Promise((resolve) => {
    execFile(command, args, { timeout: 2500, windowsHide: true }, (error, stdout, stderr) => {
      if (error) {
        if ((error as NodeJS.ErrnoException).code === "ENOENT") resolve(null);
        else resolve((stdout || stderr || error.message || "").trim());
        return;
      }
      resolve((stdout || stderr || "").trim());
    });
  });
}

function findFirstMatchingLine(content: string, patterns: RegExp[]): number {
  const lines = content.split(/\r?\n/);
  const index = lines.findIndex((line) => patterns.some((pattern) => pattern.test(line)));
  return index >= 0 ? index + 1 : 1;
}

function findFirstLine(content: string, pattern: RegExp): number {
  const lines = content.split(/\r?\n/);
  const index = lines.findIndex((line) => pattern.test(line));
  return index >= 0 ? index + 1 : 1;
}

function findFirstLineOrNull(content: string, pattern: RegExp): number | null {
  const lines = content.split(/\r?\n/);
  const index = lines.findIndex((line) => pattern.test(line));
  return index >= 0 ? index + 1 : null;
}

function lineForIndex(content: string, index: number): number {
  return content.slice(0, index).split(/\r?\n/).length;
}

function columnForIndex(content: string, index: number): number {
  const before = content.slice(0, index);
  const lastBreak = Math.max(before.lastIndexOf("\n"), before.lastIndexOf("\r"));
  return index - lastBreak;
}
