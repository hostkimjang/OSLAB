import { BadRequestException, Injectable } from "@nestjs/common";
import { execFile, spawn, type ChildProcessWithoutNullStreams } from "child_process";
import { existsSync, mkdirSync } from "fs";
import path from "path";
import { pathToFileURL } from "url";
import { parseDocument } from "yaml";
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

const SUPPORTED_LANGUAGES: ArtifactLanguageKind[] = ["powershell", "shell", "python", "json", "yaml", "javascript", "typescript", "html", "css", "markdown", "dockerfile", "bat", "c", "csharp", "plaintext"];
const OSLAB_PLACEHOLDERS = ["ArtifactDir", "OutputPath", "ScenarioId", "RunId"];
const TOOL_CACHE_TTL_MS = 30_000;
// PSES and clangd cold-start needs more headroom than pyright/bash; completion calls stay short.
const LSP_INIT_TIMEOUT_MS = 8_000;
const LSP_COMPLETION_TIMEOUT_MS = 2_500;
const LSP_DIAGNOSTIC_TIMEOUT_MS = 1_200;
const LSP_ITEM_LIMIT = 200;
const FINAL_ITEM_LIMIT = 250;
const LSP_TRIGGER_CHARACTERS = new Set([".", "(", ":", "/", "\\", "$", "@", "<", ">", "-", "[", "\"", "'"]);
const LSP_LANGUAGES_WITH_SERVER: ArtifactLanguageKind[] = ["python", "shell", "json", "yaml", "javascript", "typescript", "html", "css", "markdown", "dockerfile", "c", "csharp", "powershell"];
const LSP_IDLE_DISPOSE_MS = process.env.NODE_ENV === "test" || process.execArgv.includes("--test") ? 500 : 30_000;
const LANGUAGE_ASSIST_ROOTS = ["validation/artifacts/", "scenarios/", "validation/suites/", "validation/fixtures/"];
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
    const trigger = detectTriggerInfo(request.content, request.line, request.column);
    const mode = status.mode || "internal";
    // The API exposes one LSP-shaped surface; unavailable language servers fall back to OSLAB internal providers.
    const lspItems = mode === "lsp" ? await this.completeFromLanguageServer(language, artifactPath, request, trigger).catch(() => []) : [];
    const fallbackItems = languageCompletions(language);
    // After a trigger character (e.g. `os.`) the LSP returns context-specific members that don't share the literal prefix; preserve LSP order instead of re-ranking by prefix.
    const lspRanked = trigger.triggerCharacter ? lspItems : rankCompletionItems(lspItems, prefix);
    const items = mergeCompletionItems([
      ...lspRanked.slice(0, LSP_ITEM_LIMIT),
      ...rankCompletionItems(fallbackItems, prefix),
    ]);
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
    const staticIssues = inspectContent(artifactPath, request.content || "", language);
    const lspIssues = status.mode === "lsp"
      ? await this.diagnosticsFromLanguageServer(language, artifactPath, request.content || "").catch(() => [])
      : [];
    const issues = mergeAssistIssues([...staticIssues, ...lspIssues]);
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
    if (language === "yaml") {
      const bin = findPackageBin("yaml-language-server");
      return summarizeStatus(language, "YAML", bin ? "lsp" : "setupNeeded", "Repo-managed YAML language server provides VS Code YAML-style completion and parse diagnostics.", [
        bin ? toolDetail("yaml-language-server", "YAML Language Server", "available", bin, "Repo-managed YAML language server.") : toolDetail("yaml-language-server", "YAML Language Server", "missing", undefined, "Run pnpm install to restore repo-managed yaml-language-server."),
      ]);
    }
    if (language === "javascript" || language === "typescript") {
      const server = findPackageBin("typescript-language-server");
      const tsserver = findPackageBin("tsserver");
      const ready = Boolean(server && tsserver);
      return summarizeStatus(language, language === "typescript" ? "TypeScript" : "JavaScript", ready ? "lsp" : "setupNeeded", "Repo-managed typescript-language-server plus TypeScript provides VS Code-style JS/TS completion.", [
        server ? toolDetail("typescript-language-server", "TypeScript Language Server", "available", server, "Repo-managed JS/TS LSP.") : toolDetail("typescript-language-server", "TypeScript Language Server", "missing", undefined, "Run pnpm install to restore repo-managed TypeScript LSP."),
        tsserver ? toolDetail("tsserver", "TypeScript server", "available", tsserver, "TypeScript SDK used by the language server.") : toolDetail("tsserver", "TypeScript server", "missing", undefined, "Run pnpm install to restore the TypeScript SDK."),
      ]);
    }
    if (language === "html") {
      const bin = findPackageBin("vscode-html-language-server");
      return summarizeStatus(language, "HTML", bin ? "lsp" : "setupNeeded", "Repo-managed VS Code HTML language server provides HTML completion.", [
        bin ? toolDetail("vscode-html-language-server", "VS Code HTML LSP", "available", bin, "Repo-managed HTML language server.") : toolDetail("vscode-html-language-server", "VS Code HTML LSP", "missing", undefined, "Run pnpm install to restore repo-managed HTML LSP."),
      ]);
    }
    if (language === "css") {
      const bin = findPackageBin("vscode-css-language-server");
      return summarizeStatus(language, "CSS", bin ? "lsp" : "setupNeeded", "Repo-managed VS Code CSS language server provides CSS completion.", [
        bin ? toolDetail("vscode-css-language-server", "VS Code CSS LSP", "available", bin, "Repo-managed CSS language server.") : toolDetail("vscode-css-language-server", "VS Code CSS LSP", "missing", undefined, "Run pnpm install to restore repo-managed CSS LSP."),
      ]);
    }
    if (language === "markdown") {
      const bin = findPackageBin("vscode-markdown-language-server");
      return summarizeStatus(language, "Markdown", bin ? "lsp" : "setupNeeded", "Repo-managed VS Code Markdown language server provides Markdown completion.", [
        bin ? toolDetail("vscode-markdown-language-server", "VS Code Markdown LSP", "available", bin, "Repo-managed Markdown language server.") : toolDetail("vscode-markdown-language-server", "VS Code Markdown LSP", "missing", undefined, "Run pnpm install to restore repo-managed Markdown LSP."),
      ]);
    }
    if (language === "dockerfile") {
      const bin = findPackageBin("docker-langserver");
      return summarizeStatus(language, "Dockerfile", bin ? "lsp" : "setupNeeded", "Repo-managed Dockerfile language server provides Dockerfile completion.", [
        bin ? toolDetail("docker-langserver", "Dockerfile Language Server", "available", bin, "Repo-managed Dockerfile language server.") : toolDetail("docker-langserver", "Dockerfile Language Server", "missing", undefined, "Run pnpm install to restore repo-managed Dockerfile LSP."),
      ]);
    }
    if (language === "powershell") {
      const pwsh = await commandVersion("pwsh", ["--version"]);
      const windowsPowerShell = await commandVersion("powershell", ["-NoProfile", "-Command", "$PSVersionTable.PSVersion.ToString()"]);
      const editorServicesBundle = findPowerShellEditorServicesBundle();
      const hasHost = Boolean(pwsh || windowsPowerShell);
      // PSES needs both the bundle (with Start-EditorServices.ps1) AND a pwsh/powershell host to launch.
      const lspReady = Boolean(editorServicesBundle) && hasHost;
      return summarizeStatus(language, "PowerShell", lspReady ? "lsp" : "setupNeeded", "Drop the PowerShell Editor Services bundle into .oslab-tools/powershell-editor-services to enable richer PowerShell completion. Internal completion stays active otherwise.", [
        editorServicesBundle ? toolDetail("powershell-editor-services", "PowerShell Editor Services", "available", editorServicesBundle, "Project-local PowerShell LSP bundle.") : toolDetail("powershell-editor-services", "PowerShell Editor Services", "missing", undefined, "Place the Microsoft PSES bundle (containing Start-EditorServices.ps1) under .oslab-tools/powershell-editor-services."),
        pwsh ? toolDetail("pwsh", "PowerShell 7", "available", "pwsh", pwsh) : toolDetail("pwsh", "PowerShell 7", "missing", undefined, "Recommended host for PSES."),
        windowsPowerShell ? toolDetail("powershell", "Windows PowerShell", "available", "powershell", windowsPowerShell) : toolDetail("powershell", "Windows PowerShell", "missing", undefined, "Windows fallback host."),
      ]);
    }
    if (language === "c") {
      const projectClangd = findClangdBinary();
      const pathClangd = !projectClangd ? await commandVersion("clangd", ["--version"]) : null;
      const clangdLocation = projectClangd || pathClangd;
      return summarizeStatus(language, "C", clangdLocation ? "lsp" : "setupNeeded", "Install clangd on PATH or vendor it into .oslab-tools/clangd to enable VSCode-grade C completion. Internal C snippets stay active otherwise.", [
        clangdLocation
          ? toolDetail("clangd", "clangd", "available", projectClangd || "clangd", projectClangd ? "Project-local clangd binary." : String(pathClangd).split(/\r?\n/)[0])
          : toolDetail("clangd", "clangd", "missing", undefined, "Install via 'winget install LLVM.LLVM' (Windows) or your package manager."),
      ]);
    }
    if (language === "csharp") {
      const projectCSharpLs = findCSharpLsBinary();
      const pathCSharpLs = !projectCSharpLs ? await commandVersion("csharp-ls", ["--version"]) : null;
      const dotnet = await commandVersion("dotnet", ["--version"]);
      const csharpLsLocation = projectCSharpLs || pathCSharpLs;
      return summarizeStatus(language, "C#", csharpLsLocation ? "lsp" : "setupNeeded", "Install csharp-ls as a dotnet tool or vendor it into .oslab-tools/csharp-ls to enable C# LSP completion. Internal C# snippets stay active otherwise.", [
        csharpLsLocation
          ? toolDetail("csharp-ls", "csharp-ls", "available", projectCSharpLs || "csharp-ls", projectCSharpLs ? "Project-local C# language server." : String(pathCSharpLs).split(/\r?\n/)[0])
          : toolDetail("csharp-ls", "csharp-ls", "missing", undefined, "Install with 'dotnet tool install -g csharp-ls' or place the binary under .oslab-tools/csharp-ls."),
        dotnet ? toolDetail("dotnet", ".NET SDK", "available", "dotnet", dotnet) : toolDetail("dotnet", ".NET SDK", "missing", undefined, "Install .NET SDK 8+ before using csharp-ls."),
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

  private async completeFromLanguageServer(language: ArtifactLanguageKind, artifactPath: string, request: ArtifactAssistCompletionRequest, trigger: { triggerKind: 1 | 2; triggerCharacter?: string }): Promise<ArtifactAssistCompletionItem[]> {
    if (!LSP_LANGUAGES_WITH_SERVER.includes(language)) return [];
    const session = await this.getLanguageServerSession(language);
    if (!session) return [];
    const uri = artifactUri(artifactPath);
    const rawItems = await session.complete(uri, language, request.content || "", request.line, request.column, trigger);
    return rawItems.map((item, index) => mapLspCompletionItem(item, index, language)).filter((item): item is ArtifactAssistCompletionItem => Boolean(item));
  }

  private async diagnosticsFromLanguageServer(language: ArtifactLanguageKind, artifactPath: string, content: string): Promise<ArtifactAssistIssue[]> {
    if (!LSP_LANGUAGES_WITH_SERVER.includes(language)) return [];
    const session = await this.getLanguageServerSession(language);
    if (!session) return [];
    const uri = artifactUri(artifactPath);
    const rawItems = await session.diagnostics(uri, language, content);
    return rawItems.map((item, index) => mapLspDiagnostic(item, index)).filter((item): item is ArtifactAssistIssue => Boolean(item));
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
  private diagnosticsByUri = new Map<string, any[]>();
  private diagnosticsWaiters = new Map<string, Array<(items: any[]) => void>>();
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
    connection.onRequest("workspace/configuration", (params: any) => languageServerConfiguration(this.language, params));
    connection.onNotification("textDocument/publishDiagnostics", (params: any) => {
      const uri = typeof params?.uri === "string" ? params.uri : "";
      if (!uri) return;
      const diagnostics = Array.isArray(params?.diagnostics) ? params.diagnostics : [];
      this.diagnosticsByUri.set(uri, diagnostics);
      const waiters = this.diagnosticsWaiters.get(uri) || [];
      this.diagnosticsWaiters.delete(uri);
      for (const resolve of waiters) resolve(diagnostics);
    });
    connection.listen();
    await withTimeout(connection.sendRequest(InitializeRequest, {
      processId: process.pid,
      rootUri: pathToFileURL(languageRepoRoot()).toString(),
      capabilities: {
        textDocument: {
          completion: {
            completionItem: {
              snippetSupport: true,
              documentationFormat: ["markdown", "plaintext"],
              resolveSupport: { properties: ["documentation", "detail"] },
            },
            contextSupport: true,
          },
        },
        workspace: { configuration: true },
      },
    }), LSP_INIT_TIMEOUT_MS);
    connection.sendNotification("initialized", {});
    this.initialized = true;
  }

  async complete(uri: string, language: ArtifactLanguageKind, content: string, line: number, column: number, trigger: { triggerKind: 1 | 2; triggerCharacter?: string }): Promise<any[]> {
    if (!this.connection || this.disposed) return [];
    await this.start();
    this.syncDocument(uri, language, content);
    const context: { triggerKind: 1 | 2; triggerCharacter?: string } = trigger.triggerCharacter
      ? { triggerKind: 2, triggerCharacter: trigger.triggerCharacter }
      : { triggerKind: 1 };
    const result = await withTimeout(this.connection.sendRequest(CompletionRequest, {
      textDocument: { uri },
      position: { line: Math.max(0, line - 1), character: Math.max(0, column - 1) },
      context,
    }), LSP_COMPLETION_TIMEOUT_MS);
    const items = Array.isArray(result) ? result : Array.isArray(result?.items) ? result.items : [];
    this.scheduleIdleDispose();
    return items.slice(0, LSP_ITEM_LIMIT);
  }

  async diagnostics(uri: string, language: ArtifactLanguageKind, content: string): Promise<any[]> {
    if (!this.connection || this.disposed) return [];
    await this.start();
    this.diagnosticsByUri.delete(uri);
    this.syncDocument(uri, language, content);
    const diagnostics = await this.waitForDiagnostics(uri, LSP_DIAGNOSTIC_TIMEOUT_MS);
    this.scheduleIdleDispose();
    return diagnostics;
  }

  private syncDocument(uri: string, language: ArtifactLanguageKind, content: string): number {
    if (!this.connection || this.disposed) return 0;
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
    return version;
  }

  private waitForDiagnostics(uri: string, timeoutMs: number): Promise<any[]> {
    const existing = this.diagnosticsByUri.get(uri);
    if (existing) return Promise.resolve(existing);
    return new Promise((resolve) => {
      const timer = setTimeout(() => {
        const waiters = this.diagnosticsWaiters.get(uri) || [];
        this.diagnosticsWaiters.set(uri, waiters.filter((waiter) => waiter !== resolveOnce));
        resolve(this.diagnosticsByUri.get(uri) || []);
      }, timeoutMs);
      const resolveOnce = (items: any[]) => {
        clearTimeout(timer);
        resolve(items);
      };
      const waiters = this.diagnosticsWaiters.get(uri) || [];
      waiters.push(resolveOnce);
      this.diagnosticsWaiters.set(uri, waiters);
    });
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.clearIdleTimer();
    try { this.connection?.dispose(); } catch {}
    try { this.process?.kill(); } catch {}
    this.connection = null;
    this.process = null;
    for (const waiters of this.diagnosticsWaiters.values()) {
      for (const resolve of waiters) resolve([]);
    }
    this.diagnosticsWaiters.clear();
    this.diagnosticsByUri.clear();
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

function languageServerConfiguration(language: ArtifactLanguageKind, params: any): any[] {
  const items = Array.isArray(params?.items) ? params.items : [];
  const config = configurationForLanguage(language);
  return items.map((item: any) => {
    const section = typeof item?.section === "string" ? item.section : "";
    if (section && Object.prototype.hasOwnProperty.call(config, section)) {
      return (config as Record<string, unknown>)[section];
    }
    return config;
  });
}

function configurationForLanguage(language: ArtifactLanguageKind): Record<string, unknown> {
  if (language === "yaml") {
    return {
      yaml: {
        validate: true,
        hover: true,
        completion: true,
        format: { enable: true },
        schemaStore: { enable: false },
        schemas: {
          [artifactYamlSchemaUri()]: ["validation/artifacts/**/*.yaml", "validation/artifacts/**/*.yml"],
          [scenarioYamlSchemaUri()]: ["scenarios/**/*.yaml", "scenarios/**/*.yml"],
          [suiteYamlSchemaUri()]: ["validation/suites/**/*.yaml", "validation/suites/**/*.yml"],
        },
      },
    };
  }
  if (language === "javascript" || language === "typescript") {
    return {
      typescript: { inlayHints: {}, suggest: { completeFunctionCalls: false } },
      javascript: { inlayHints: {}, suggest: { completeFunctionCalls: false } },
    };
  }
  return {};
}

function artifactYamlSchemaUri(): string {
  return pathToFileURL(path.resolve(languageRepoRoot(), "docs", "schemas", "artifact-yaml.schema.json")).toString();
}

function scenarioYamlSchemaUri(): string {
  return pathToFileURL(path.resolve(languageRepoRoot(), "docs", "schemas", "scenario-yaml.schema.json")).toString();
}

function suiteYamlSchemaUri(): string {
  return pathToFileURL(path.resolve(languageRepoRoot(), "docs", "schemas", "suite-yaml.schema.json")).toString();
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
  if (language === "yaml") {
    const command = findPackageBin("yaml-language-server");
    return command ? { command, args: ["--stdio"] } : null;
  }
  if (language === "javascript" || language === "typescript") {
    const command = findPackageBin("typescript-language-server");
    return command ? { command, args: ["--stdio"] } : null;
  }
  if (language === "html") {
    const command = findPackageBin("vscode-html-language-server");
    return command ? { command, args: ["--stdio"] } : null;
  }
  if (language === "css") {
    const command = findPackageBin("vscode-css-language-server");
    return command ? { command, args: ["--stdio"] } : null;
  }
  if (language === "markdown") {
    const command = findPackageBin("vscode-markdown-language-server");
    return command ? { command, args: ["--stdio"] } : null;
  }
  if (language === "dockerfile") {
    const command = findPackageBin("docker-langserver");
    return command ? { command, args: ["--stdio"] } : null;
  }
  if (language === "shell") {
    const command = findPackageBin("bash-language-server");
    return command ? { command, args: ["start"] } : null;
  }
  if (language === "c") {
    return clangdCommand();
  }
  if (language === "csharp") {
    return csharpLsCommand();
  }
  if (language === "powershell") {
    return powerShellEditorServicesCommand();
  }
  return null;
}

function clangdCommand(): { command: string; args: string[] } | null {
  const projectBinary = findClangdBinary();
  // --background-index off keeps memory bounded inside the long-lived API process; --header-insertion=never avoids surprise edits when accepting completions.
  const args = ["--background-index=false", "--header-insertion=never", "--limit-results=200"];
  if (projectBinary) return { command: projectBinary, args };
  // Fall back to the system PATH; spawn() will surface ENOENT if missing and the session marks itself disposed.
  return { command: process.platform === "win32" ? "clangd.exe" : "clangd", args };
}

function findClangdBinary(): string | undefined {
  const exe = process.platform === "win32" ? "clangd.exe" : "clangd";
  const candidates = [
    path.join(process.cwd(), ".oslab-tools", "clangd", "bin", exe),
    path.join(process.cwd(), ".oslab-tools", "clangd", exe),
    path.join(process.cwd(), ".oslab-tools", exe),
    path.join(process.cwd(), "apps", "api", ".oslab-tools", "clangd", "bin", exe),
    path.join(process.cwd(), "apps", "api", ".oslab-tools", "clangd", exe),
  ];
  return candidates.find((candidate) => existsSync(candidate));
}

function powerShellEditorServicesCommand(): { command: string; args: string[] } | null {
  const bundleDir = findPowerShellEditorServicesBundle();
  if (!bundleDir) return null;
  const startScript = path.join(bundleDir, "Start-EditorServices.ps1");
  if (!existsSync(startScript)) return null;
  const host = process.platform === "win32" ? "pwsh.exe" : "pwsh";
  const sessionDir = path.join(process.cwd(), ".oslab-cache", "pses");
  // Lazy-create the cache dir; PSES requires writable LogPath/SessionDetailsPath even with -Stdio.
  try { mkdirSync(sessionDir, { recursive: true }); } catch {}
  const logPath = path.join(sessionDir, "pses.log");
  const sessionPath = path.join(sessionDir, `session-${process.pid}.json`);
  const escape = (value: string) => value.replaceAll("'", "''");
  const command = `& '${escape(startScript)}' -BundledModulesPath '${escape(bundleDir)}' -LogPath '${escape(logPath)}' -SessionDetailsPath '${escape(sessionPath)}' -FeatureFlags @() -HostName 'OSLAB Artifact Studio' -HostProfileId 'oslab.artifact-studio' -HostVersion '1.0.0' -AdditionalModules @() -Stdio -LogLevel Warning`;
  return {
    command: host,
    args: ["-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
  };
}

function findPowerShellEditorServicesBundle(): string | undefined {
  const candidates = [
    path.join(process.cwd(), ".oslab-tools", "powershell-editor-services"),
    path.join(process.cwd(), "apps", "api", ".oslab-tools", "powershell-editor-services"),
  ];
  return candidates.find((candidate) => existsSync(path.join(candidate, "Start-EditorServices.ps1")));
}

function lspLanguageId(language: ArtifactLanguageKind): string {
  if (language === "shell") return "shellscript";
  if (language === "bat") return "bat";
  if (language === "powershell") return "powershell";
  if (language === "dockerfile") return "dockerfile";
  if (language === "markdown") return "markdown";
  if (language === "plaintext") return "plaintext";
  return language;
}

function artifactUri(artifactPath: string): string {
  return pathToFileURL(path.resolve(languageRepoRoot(), artifactPath.replaceAll("/", path.sep))).toString();
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

function mapLspDiagnostic(item: any, index: number): ArtifactAssistIssue | null {
  if (!item || typeof item !== "object") return null;
  const range = item.range || {};
  const start = range.start || {};
  const end = range.end || {};
  const message = typeof item.message === "string" && item.message.trim() ? item.message : null;
  if (!message) return null;
  return {
    severity: mapLspDiagnosticSeverity(item.severity),
    code: `lsp.${String(item.code || item.source || index)}`,
    message,
    line: Number.isFinite(start.line) ? Number(start.line) + 1 : null,
    column: Number.isFinite(start.character) ? Number(start.character) + 1 : null,
    endLine: Number.isFinite(end.line) ? Number(end.line) + 1 : null,
    endColumn: Number.isFinite(end.character) ? Number(end.character) + 1 : null,
  };
}

function mapLspDiagnosticSeverity(severity: number | undefined): ArtifactAssistIssue["severity"] {
  if (severity === 1) return "error";
  if (severity === 2) return "warning";
  return "info";
}

function mergeAssistIssues(items: ArtifactAssistIssue[]): ArtifactAssistIssue[] {
  const seen = new Set<string>();
  return items.filter((item) => {
    const key = [
      item.code,
      item.message,
      item.line ?? "",
      item.column ?? "",
      item.endLine ?? "",
      item.endColumn ?? "",
    ].join("|");
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
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
  }).slice(0, FINAL_ITEM_LIMIT);
}

function detectTriggerInfo(content: string, line: number, column: number): { triggerKind: 1 | 2; triggerCharacter?: string } {
  const lines = content.split(/\r?\n/);
  const lineText = lines[Math.max(0, line - 1)] || "";
  const charBefore = lineText.charAt(Math.max(0, column - 2));
  if (LSP_TRIGGER_CHARACTERS.has(charBefore)) {
    return { triggerKind: 2, triggerCharacter: charBefore };
  }
  return { triggerKind: 1 };
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
  if (language === "yaml") {
    return [
      completion("yaml-schema-version", "schemaVersion", "OSLAB 결과 YAML schema version", "schemaVersion: 1", language, source, "property"),
      completion("yaml-kind", "kind", "결과 artifact 종류", "kind: commandResult", language, source, "property"),
      completion("yaml-output-contract", "commandResult YAML", "YAML로 표현한 commandResult 골격입니다.", "schemaVersion: 1\nkind: commandResult\nexitCode: 0\nstdout: \"ok\\n\"\nstderr: \"\"\n", language, "snippet", "snippet"),
      completion("yaml-artifact-path", "artifact path", "Scenario/Suite에서 쓰는 artifact 경로 예시입니다.", "artifact:\n  path: validation/artifacts/${1:demo}\n", language, "snippet", "snippet"),
      completion("yaml-suite-runs", "runs", "Suite 실행 목록 골격입니다.", "runs:\n  - id: ${1:smoke}\n    scenario: ${2:scenarios/windows/demo.example.yaml}\n    tier: ${3:ci}\n    allowFailure: false\n    enabled: true", language, "snippet", "snippet"),
      completion("yaml-suite-scenario", "scenario", "Suite run이 실행할 scenario 경로입니다.", "scenario: scenarios/${1:windows/demo.example.yaml}", language, source, "property"),
      completion("yaml-scenario-assertions", "assertions", "Scenario assertion 목록 골격입니다.", "assertions:\n  - id: ${1:exit-zero}\n    type: command.exitCode\n    expected: 0", language, "snippet", "snippet"),
      completion("yaml-scenario-provider", "provider", "Scenario provider 설정 골격입니다.", "provider:\n  type: proxmox\n  template: ${1:windows11-template-qga-9101}\n  vmIdRange:\n    start: ${2:9102}\n    end: ${3:9199}", language, "snippet", "snippet"),
      completion("yaml-scenario-guest", "guest", "Scenario guest 접속 모드입니다.", "guest:\n  mode: auto", language, "snippet", "snippet"),
      ...common,
    ];
  }
  if (language === "javascript" || language === "typescript") {
    const langPrefix = language === "typescript" ? "ts" : "js";
    return [
      completion(`${langPrefix}-console-log`, "console.log", "표준 출력에 값을 기록합니다.", "console.log(${1:\"artifact executed\"});", language, source, "function"),
      completion(`${langPrefix}-json-stringify`, "JSON.stringify", "객체를 JSON 문자열로 직렬화합니다.", "JSON.stringify(${1:result}, null, 2)", language, source, "function"),
      completion(`${langPrefix}-command-result`, "commandResult object", "Results가 읽을 수 있는 출력 계약 객체입니다.", "const result = {\n  schemaVersion: 1,\n  kind: \"commandResult\",\n  exitCode: 0,\n  stdout: \"ok\\n\",\n  stderr: \"\",\n};", language, "snippet", "snippet"),
      completion(`${langPrefix}-fs-write-file`, "fs.writeFileSync", "파일을 UTF-8로 저장합니다.", "fs.writeFileSync(${1:\"{{OutputPath}}\"}, ${2:text}, \"utf8\");", language, source, "function"),
      completion(`${langPrefix}-import-fs`, "import fs", "Node fs module import입니다.", "import fs from \"node:fs\";", language, "snippet", "snippet"),
      ...common,
    ];
  }
  if (language === "html") {
    return [
      completion("html-doctype", "<!doctype html>", "HTML 문서 골격입니다.", "<!doctype html>\n<html lang=\"en\">\n  <head>\n    <meta charset=\"utf-8\" />\n    <title>${1:OSLAB Artifact}</title>\n  </head>\n  <body>\n    ${2:artifact executed}\n  </body>\n</html>", language, "snippet", "snippet"),
      completion("html-script", "<script>", "인라인 스크립트 블록입니다.", "<script>\n  ${1:console.log(\"artifact executed\")}\n</script>", language, "snippet", "snippet"),
      completion("html-link-css", "link stylesheet", "CSS 파일 연결입니다.", "<link rel=\"stylesheet\" href=\"${1:style.css}\" />", language, "snippet", "snippet"),
      ...common,
    ];
  }
  if (language === "css") {
    return [
      completion("css-root", ":root", "CSS custom property root입니다.", ":root {\n  ${1:--accent}: ${2:#2563eb};\n}", language, "snippet", "snippet"),
      completion("css-body", "body", "기본 body 스타일입니다.", "body {\n  font-family: system-ui, sans-serif;\n  margin: 0;\n}", language, "snippet", "snippet"),
      completion("css-media", "@media", "반응형 media query입니다.", "@media (max-width: ${1:768px}) {\n  ${2:.target} {\n    ${3:display: block;}\n  }\n}", language, "snippet", "snippet"),
      ...common,
    ];
  }
  if (language === "markdown") {
    return [
      completion("md-heading", "# Heading", "Markdown heading입니다.", "# ${1:Artifact Notes}", language, "snippet", "snippet"),
      completion("md-checklist", "- [ ] checklist", "검증 체크리스트입니다.", "- [ ] ${1:Verify artifact output}", language, "snippet", "snippet"),
      completion("md-code-fence", "code fence", "코드 블록입니다.", "```text\n${1:artifact executed}\n```", language, "snippet", "snippet"),
      ...common,
    ];
  }
  if (language === "dockerfile") {
    return [
      completion("docker-from", "FROM", "Base image 선언입니다.", "FROM ${1:alpine:3.20}", language, source, "keyword"),
      completion("docker-workdir", "WORKDIR", "작업 디렉터리 설정입니다.", "WORKDIR ${1:/artifact}", language, source, "keyword"),
      completion("docker-run", "RUN", "이미지 build 명령입니다.", "RUN ${1:apk add --no-cache bash}", language, source, "keyword"),
      completion("docker-cmd", "CMD", "기본 실행 명령입니다.", "CMD [\"${1:sh}\", \"${2:-c}\", \"${3:printf '%s\\\\n' artifact executed}\"]", language, "snippet", "snippet"),
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
  if (language === "csharp") {
    return [
      completion("cs-console-write-line", "Console.WriteLine", "C# 표준 출력입니다.", "Console.WriteLine(${1:\"artifact executed\"});", language, source, "function"),
      completion("cs-using-system", "using System", "Console과 기본 타입을 사용할 때 필요한 namespace입니다.", "using System;", language, "snippet", "snippet"),
      completion("cs-using-json", "using System.Text.Json", "commandResult 객체를 JSON으로 직렬화합니다.", "using System.Text.Json;", language, "snippet", "snippet"),
      completion("cs-json-serialize", "JsonSerializer.Serialize", "C# 객체를 JSON 문자열로 직렬화합니다.", "JsonSerializer.Serialize(${1:result})", language, source, "function"),
      completion("cs-command-result", "commandResult object", "Results가 읽을 수 있는 C# 출력 계약입니다.", "var result = new {\n  schemaVersion = 1,\n  kind = \"commandResult\",\n  exitCode = 0,\n  stdout = \"ok\\n\",\n  stderr = \"\"\n};\nConsole.WriteLine(JsonSerializer.Serialize(result));", language, "snippet", "snippet"),
      completion("cs-main", "static int Main", "명시적인 C# entrypoint입니다.", "static int Main(string[] args) {\n  Console.WriteLine(\"artifact executed\");\n  return 0;\n}", language, "snippet", "snippet"),
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
  return scored.map((entry) => entry.item);
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
  if (language === "yaml") {
    const parsed = parseDocument(content || "");
    if (parsed.errors.length) {
      const error = parsed.errors[0];
      issues.push({ severity: "error", code: "yaml.parse", message: error?.message || "Invalid YAML", line: 1, column: 1 });
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
  if (["powershell", "python", "shell", "javascript", "typescript", "bat"].includes(language) && !/\{\{OutputPath\}\}|OutputPath|command-result|result\.json|console\.log/i.test(content)) {
    issues.push({ severity: "info", code: "output.contract", message: "Consider writing a stable output JSON so Results can verify the artifact.", line: 1, column: 1 });
  }
  if (/([A-Za-z]:\\Users\\|\/home\/|\/Users\/)/i.test(content)) {
    issues.push({ severity: "info", code: "local.path", message: "Local user paths may not exist inside the VM. Prefer {{ArtifactDir}} or {{OutputPath}}.", line: findFirstLine(content, /([A-Za-z]:\\Users\\|\/home\/|\/Users\/)/i) });
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
  if (language === "csharp") {
    return [
      { pattern: "\\bProcess\\.Start\\s*\\(", flags: "i", severity: "warning", code: "csharp.process-start", message: "Process.Start can hide quoting and exit handling. Prefer explicit ProcessStartInfo with redirected output." },
      { pattern: "\\bEnvironment\\.GetEnvironmentVariable\\s*\\([^\\n)]*(TOKEN|SECRET|PASSWORD|KEY)", flags: "i", severity: "info", code: "csharp.env-secret", message: "Secret-like env reads should stay documented and redacted in run logs." },
      { pattern: "\\bFile\\.Delete\\s*\\(", flags: "i", severity: "warning", code: "csharp.file-delete", message: "File.Delete should be scoped to disposable VM state or {{OutputPath}}-adjacent files." },
      ...common,
    ];
  }
  if (language === "javascript" || language === "typescript") {
    return [
      { pattern: "\\beval\\s*\\(", flags: "i", severity: "warning", code: "js.eval", message: "eval is hard to audit in validation artifacts. Prefer explicit parsing." },
      { pattern: "\\bchild_process\\.(exec|execSync)\\s*\\(", flags: "i", severity: "warning", code: "js.child-process-exec", message: "child_process.exec uses a shell. Prefer spawn/execFile with argument arrays." },
      ...common,
    ];
  }
  if (language === "dockerfile") {
    return [
      { pattern: "^\\s*ADD\\s+https?:\\/\\/", flags: "im", severity: "warning", code: "dockerfile.remote-add", message: "Remote ADD hides download policy. Prefer explicit curl with checksum or vendored assets." },
      { pattern: "^\\s*USER\\s+root\\s*$", flags: "im", severity: "info", code: "dockerfile.root-user", message: "Root container user is sometimes necessary, but call it out in artifact notes." },
      ...common,
    ];
  }
  return common;
}

function normalizeArtifactAssistPath(rawPath: string): string {
  const normalized = (rawPath || "").replaceAll("\\", "/").replace(/^\/+/, "");
  if (!normalized || path.isAbsolute(rawPath) || normalized.split("/").includes("..")) {
    throw new BadRequestException("Artifact Assist path must be a relative authoring path");
  }
  if (!LANGUAGE_ASSIST_ROOTS.some((root) => normalized.startsWith(root))) {
    throw new BadRequestException("Artifact Assist only supports Web authoring roots");
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
  if (lower.endsWith(".yaml") || lower.endsWith(".yml")) return "yaml";
  if (lower.endsWith(".js") || lower.endsWith(".mjs") || lower.endsWith(".cjs")) return "javascript";
  if (lower.endsWith(".ts")) return "typescript";
  if (lower.endsWith(".html") || lower.endsWith(".htm")) return "html";
  if (lower.endsWith(".css")) return "css";
  if (lower.endsWith(".md") || lower.endsWith(".markdown")) return "markdown";
  if (lower.endsWith(".dockerfile") || path.basename(lower) === "dockerfile") return "dockerfile";
  if (lower.endsWith(".c")) return "c";
  if (lower.endsWith(".cs")) return "csharp";
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

function csharpLsCommand(): { command: string; args: string[] } | null {
  const projectBinary = findCSharpLsBinary();
  if (projectBinary) return { command: projectBinary, args: [] };
  return { command: process.platform === "win32" ? "csharp-ls.exe" : "csharp-ls", args: [] };
}

function findCSharpLsBinary(): string | undefined {
  const exe = process.platform === "win32" ? "csharp-ls.exe" : "csharp-ls";
  const userProfile = process.env.USERPROFILE || process.env.HOME;
  const candidates = [
    userProfile ? path.join(userProfile, ".dotnet", "tools", exe) : "",
    path.join(process.cwd(), ".oslab-tools", "csharp-ls", exe),
    path.join(process.cwd(), ".oslab-tools", "csharp-ls", "bin", exe),
    path.join(process.cwd(), ".oslab-tools", exe),
    path.join(process.cwd(), "apps", "api", ".oslab-tools", "csharp-ls", exe),
    path.join(process.cwd(), "apps", "api", ".oslab-tools", "csharp-ls", "bin", exe),
  ].filter(Boolean);
  return candidates.find((candidate) => existsSync(candidate));
}

function languageRepoRoot(): string {
  return path.resolve(process.env.OSLAB_REPO_ROOT ?? findLanguageRepoRoot(process.cwd()));
}

function findLanguageRepoRoot(start: string): string {
  let current = path.resolve(start);
  while (true) {
    if (existsSync(path.join(current, "pnpm-workspace.yaml")) || existsSync(path.join(current, "docs", "schemas"))) {
      return current;
    }
    const parent = path.dirname(current);
    if (parent === current) return path.resolve(start);
    current = parent;
  }
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
