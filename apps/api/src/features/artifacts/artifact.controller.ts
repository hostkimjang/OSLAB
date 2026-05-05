import { BadRequestException, Body, Controller, Get, Inject, Post, Put, Query, UploadedFile, UploadedFiles, UseGuards, UseInterceptors } from "@nestjs/common";
import { FileInterceptor, FilesInterceptor } from "@nestjs/platform-express";
import { execFile } from "child_process";
import { createHash } from "crypto";
import { createReadStream, promises as fs } from "fs";
import path from "path";
import { parseDocument } from "yaml";
import type {
  ArtifactAssistCheckResult,
  ArtifactAssistCompletionRequest,
  ArtifactAssistCompletionResponse,
  ArtifactAssistDiagnosticsRequest,
  ArtifactAssistDiagnosticsResponse,
  ArtifactAssistIssue,
  ArtifactLanguageKind,
  ArtifactLanguageToolInstallResponse,
  ArtifactLanguageToolStatus,
  ArtifactManageActionResponse,
  ArtifactManagePreview,
  ArtifactProjectTemplateKind,
  ArtifactProjectTemplateRequest,
  ArtifactProjectTemplateResponse,
  ArtifactTemplateKind,
  ArtifactTreeItem,
  ArtifactTreeResponse,
  ManagedArtifactItem,
  ManagedArtifactSource,
} from "@oslab/shared";
import { AuthGuard } from "../../common/guards/auth.guard";
import { PrismaService } from "../../infrastructure/prisma/prisma.service";
import { WorkspaceService } from "../../infrastructure/workspace/workspace.service";
import { ArtifactLanguageService } from "./artifact-language.service";

const ALLOWED_UPLOAD_EXTENSIONS = new Set([".zip", ".exe", ".msi", ".ps1", ".sh", ".cmd", ".bat", ".py", ".c", ".cs", ".json", ".yaml", ".yml", ".js", ".mjs", ".cjs", ".ts", ".html", ".htm", ".css", ".md", ".markdown", ".dockerfile", ".txt"]);
const TEXT_ARTIFACT_EXTENSIONS = new Set([".ps1", ".sh", ".py", ".c", ".cs", ".json", ".yaml", ".yml", ".js", ".mjs", ".cjs", ".ts", ".html", ".htm", ".css", ".md", ".markdown", ".dockerfile", ".txt", ".cmd", ".bat"]);
const MAX_UPLOAD_BYTES = 512 * 1024 * 1024;
const MAX_DIRECTORY_FILES = 5000;
const MAX_TREE_ITEMS = 500;
const MAX_DIRECTORY_SUMMARY_FILES = 10000;
const ARCHIVE_ROOT = ".artifact-archive";
const TEMPLATE_EXTENSION_BY_KIND: Record<ArtifactTemplateKind, string> = {
  powershell: ".ps1",
  shell: ".sh",
  python: ".py",
  c: ".c",
  csharp: ".cs",
  json: ".json",
  yaml: ".yaml",
  javascript: ".js",
  typescript: ".ts",
  html: ".html",
  css: ".css",
  markdown: ".md",
  dockerfile: ".dockerfile",
  txt: ".txt",
  cmd: ".cmd",
  bat: ".bat",
};
const PROJECT_TEMPLATE_KINDS = new Set<ArtifactProjectTemplateKind>(["script-project", "inventory-agent", "install-profile"]);
const OSLAB_PLACEHOLDERS = ["ArtifactDir", "OutputPath", "ScenarioId", "RunId"];
const LANGUAGE_TOOL_CACHE_TTL_MS = 30_000;
const languageToolCache = new Map<ArtifactLanguageKind, { checkedAt: number; status: ArtifactLanguageToolStatus }>();

@Controller("api/artifacts")
@UseGuards(AuthGuard)
export class ArtifactController {
  constructor(
    @Inject(PrismaService) private readonly prisma: PrismaService,
    @Inject(WorkspaceService) private readonly workspace: WorkspaceService,
    @Inject(ArtifactLanguageService) private readonly languageService: ArtifactLanguageService,
  ) {}

  @Post("upload")
  @UseInterceptors(FileInterceptor("file", { limits: { fileSize: MAX_UPLOAD_BYTES } }))
  async upload(@UploadedFile() file: Express.Multer.File) {
    if (!file) {
      throw new BadRequestException("artifact file is required");
    }
    const originalName = path.basename(file.originalname || "artifact");
    const extension = path.extname(originalName).toLowerCase();
    if (!ALLOWED_UPLOAD_EXTENSIONS.has(extension)) {
      throw new BadRequestException(`Unsupported artifact extension: ${extension || "<none>"}`);
    }
    await fs.mkdir(this.workspace.artifactDir, { recursive: true });
    const filename = `${Date.now()}-${originalName.replace(/[^A-Za-z0-9._-]/g, "_")}`;
    const target = path.join(this.workspace.artifactDir, filename);
    await fs.writeFile(target, file.buffer);
    const saved = await this.prisma.artifactUpload.create({
      data: {
        filename: originalName,
        path: this.workspace.relative(target),
        size: file.size,
      },
    });
    return saved;
  }

  @Post("upload-directory")
  @UseInterceptors(FilesInterceptor("files", MAX_DIRECTORY_FILES, { limits: { fileSize: MAX_UPLOAD_BYTES, files: MAX_DIRECTORY_FILES } }))
  async uploadDirectory(@UploadedFiles() files: Express.Multer.File[], @Body("paths") paths?: string | string[]) {
    if (!files?.length) {
      throw new BadRequestException("artifact directory files are required");
    }
    const uploadPaths = Array.isArray(paths) ? paths : paths ? [paths] : [];
    const totalSize = files.reduce((sum, file) => sum + file.size, 0);
    if (totalSize > MAX_UPLOAD_BYTES) {
      throw new BadRequestException(`Artifact directory is too large: ${totalSize} bytes`);
    }
    const firstRelativePath = safeRelativeUploadPath(uploadPaths[0] || files[0].originalname || files[0].fieldname || "folder");
    const rootName = firstRelativePath.split("/")[0] || "folder";
    const folderName = `${Date.now()}-${safePathSegment(rootName)}`;
    const targetRoot = path.join(this.workspace.artifactDir, folderName);
    const targetRootResolved = path.resolve(targetRoot);
    await fs.mkdir(targetRoot, { recursive: true });
    for (let index = 0; index < files.length; index += 1) {
      const file = files[index];
      const relativePath = safeRelativeUploadPath(uploadPaths[index] || file.originalname || file.fieldname || file.originalname);
      const parts = relativePath.split("/").filter(Boolean);
      const withoutRoot = parts.length > 1 ? parts.slice(1) : parts;
      const safeParts = withoutRoot.map(safePathSegment).filter(Boolean);
      const target = path.join(targetRoot, ...(safeParts.length ? safeParts : [safePathSegment(file.originalname || "file")]));
      if (!path.resolve(target).startsWith(targetRootResolved + path.sep)) {
        throw new BadRequestException("Artifact directory path escapes upload root");
      }
      await fs.mkdir(path.dirname(target), { recursive: true });
      await fs.writeFile(target, file.buffer);
    }
    const saved = await this.prisma.artifactUpload.create({
      data: {
        filename: rootName,
        path: this.workspace.relative(targetRoot),
        size: totalSize,
      },
    });
    return { ...saved, fileCount: files.length };
  }

  @Get("uploads")
  async uploads() {
    return this.prisma.artifactUpload.findMany({ orderBy: { createdAt: "desc" }, take: 50 });
  }

  @Get("manage")
  async manage(): Promise<ManagedArtifactItem[]> {
    const artifacts = await this.workspace.listCatalog("artifact");
    const archivePaths = await this.walkManagedArtifacts(path.join(this.workspace.root, ARCHIVE_ROOT));
    const paths = Array.from(new Set([...artifacts.map((artifact) => artifact.path), ...archivePaths]));
    const items = await Promise.all(paths.map((artifactPath) => this.toManagedArtifactItem(artifactPath)));
    return items
      .filter((item): item is ManagedArtifactItem => Boolean(item))
      .sort((a, b) => a.source.localeCompare(b.source) || a.path.localeCompare(b.path));
  }

  @Get("tree")
  async tree(@Query("path") artifactPath: string): Promise<ArtifactTreeResponse> {
    if (!artifactPath?.trim()) {
      throw new BadRequestException("artifact path is required");
    }
    const target = this.resolveManagedArtifactPath(artifactPath);
    const stat = await this.statManagedArtifact(target, artifactPath);
    if (!stat.isDirectory()) {
      return {
        path: artifactPath.replaceAll("\\", "/"),
        items: [await this.toTreeItem(target, artifactPath.replaceAll("\\", "/"), 0, stat)],
        totalItems: 1,
        truncated: false,
      };
    }
    const items: ArtifactTreeItem[] = [];
    let totalItems = 0;
    await this.walkTree(target, artifactPath.replaceAll("\\", "/"), 0, items, () => {
      totalItems += 1;
    });
    return {
      path: artifactPath.replaceAll("\\", "/"),
      items,
      totalItems,
      truncated: totalItems > items.length || items.length >= MAX_TREE_ITEMS,
    };
  }

  @Get("content")
  async content(@Query("path") artifactPath: string) {
    if (!artifactPath?.trim()) {
      throw new BadRequestException("artifact path is required");
    }
    this.assertArtifactTextPath(artifactPath, "read");
    const content = await this.workspace.readText(artifactPath);
    return { path: artifactPath, content };
  }

  @Post("template")
  async template(@Body() body: { kind?: ArtifactTemplateKind; path?: string }) {
    const kind = body?.kind;
    const artifactPath = body?.path?.trim();
    if (!kind || !TEMPLATE_EXTENSION_BY_KIND[kind]) {
      throw new BadRequestException("Unsupported artifact template kind");
    }
    if (!artifactPath) {
      throw new BadRequestException("artifact path is required");
    }
    const expectedExtension = TEMPLATE_EXTENSION_BY_KIND[kind];
    if (path.extname(artifactPath).toLowerCase() !== expectedExtension) {
      throw new BadRequestException(`${kind} artifacts must end with ${expectedExtension}`);
    }
    this.assertArtifactTextPath(artifactPath, "create");
    const content = artifactTemplate(kind);
    await this.workspace.createText(artifactPath, content);
    return { path: artifactPath, content };
  }

  @Post("project-template")
  async projectTemplate(@Body() body: ArtifactProjectTemplateRequest): Promise<ArtifactProjectTemplateResponse> {
    const kind = body?.kind;
    const projectPath = body?.path?.trim();
    if (!kind || !PROJECT_TEMPLATE_KINDS.has(kind)) {
      throw new BadRequestException("Unsupported artifact project template kind");
    }
    if (!projectPath) {
      throw new BadRequestException("artifact project path is required");
    }
    const targetDir = this.workspace.resolveArtifactProjectDirectory(projectPath);
    if (await this.workspace.exists(targetDir)) {
      throw new BadRequestException(`Artifact project already exists: ${projectPath}`);
    }
    const files = artifactProjectTemplate(kind, projectPath.replaceAll("\\", "/"), body?.shell, body?.name);
    for (const file of files) {
      this.assertArtifactTextPath(file.path, "create");
    }
    for (const file of files) {
      await this.workspace.createText(file.path, file.content);
    }
    return { path: projectPath.replaceAll("\\", "/"), files: files.map((file) => file.path) };
  }

  @Post("assist/check")
  async assistCheck(@Body() body: { path?: string; content?: string }): Promise<ArtifactAssistCheckResult> {
    const artifactPath = body?.path?.trim() || "validation/artifacts/draft.ps1";
    this.assertArtifactTextPath(artifactPath, "write");
    const content = body?.content ?? "";
    const language = languageForArtifactPath(artifactPath);
    const issues = inspectArtifactContent(artifactPath, content, language);
    const toolStatus = await this.languageService.toolStatus(language);
    const snippets = artifactAssistSnippets(language);
    return {
      ok: !issues.some((issue) => issue.severity === "error"),
      checkedAt: new Date().toISOString(),
      language,
      toolStatus,
      issues,
      snippets,
      suggestedSnippets: snippets,
      firstRunTips: firstRunTipsForLanguage(language),
    };
  }

  @Post("assist/complete")
  async assistComplete(@Body() body: ArtifactAssistCompletionRequest): Promise<ArtifactAssistCompletionResponse> {
    const artifactPath = body?.path?.trim();
    if (!artifactPath) {
      throw new BadRequestException("artifact path is required");
    }
    this.assertLanguageAssistPath(artifactPath);
    return this.languageService.complete({
      path: artifactPath,
      language: body.language,
      content: body.content ?? "",
      line: Number(body.line || 1),
      column: Number(body.column || 1),
    });
  }

  @Post("assist/diagnostics")
  async assistDiagnostics(@Body() body: ArtifactAssistDiagnosticsRequest): Promise<ArtifactAssistDiagnosticsResponse> {
    const artifactPath = body?.path?.trim();
    if (!artifactPath) {
      throw new BadRequestException("artifact path is required");
    }
    this.assertLanguageAssistPath(artifactPath);
    return this.languageService.diagnostics({
      path: artifactPath,
      language: body.language,
      content: body.content ?? "",
    });
  }

  @Get("language-tools")
  async languageTools(): Promise<ArtifactLanguageToolStatus[]> {
    return this.languageService.languageTools();
  }

  @Post("language-tools/install")
  async installLanguageTool(@Body() body: { language?: ArtifactLanguageKind }): Promise<ArtifactLanguageToolInstallResponse> {
    const language = normalizeArtifactLanguageKind(body?.language);
    const status = await this.languageService.toolStatus(language, true);
    return {
      ok: false,
      language,
      status,
      message: status.installHint,
    };
  }

  @Put("content")
  async saveContent(@Body() body: { path?: string; content?: string }) {
    const artifactPath = body?.path?.trim();
    if (!artifactPath) {
      throw new BadRequestException("artifact path is required");
    }
    this.assertArtifactTextPath(artifactPath, "write");
    await this.workspace.writeText(artifactPath, body?.content ?? "");
    return { ok: true, path: artifactPath };
  }

  @Post("archive")
  async archive(@Body() body: { path?: string; dryRun?: boolean; confirmToken?: string }): Promise<ArtifactManageActionResponse> {
    return this.manageDestructiveAction("archive", body);
  }

  @Post("delete")
  async delete(@Body() body: { path?: string; dryRun?: boolean; confirmToken?: string }): Promise<ArtifactManageActionResponse> {
    return this.manageDestructiveAction("delete", body);
  }

  @Get("check")
  async check(@Query("path") artifactPath: string) {
    if (!artifactPath?.trim()) {
      return { ok: false, exists: false, message: "artifact path is empty" };
    }
    const target = path.isAbsolute(artifactPath)
      ? path.resolve(artifactPath)
      : path.resolve(this.workspace.root, artifactPath);
    try {
      const stat = await fs.stat(target);
      return {
        ok: true,
        exists: true,
        path: artifactPath,
        kind: stat.isDirectory() ? "directory" : stat.isFile() ? "file" : "other",
        size: stat.isDirectory() ? null : stat.size,
        modifiedAt: stat.mtime.toISOString(),
        message: "artifact path exists",
      };
    } catch (error: any) {
      if (String(error?.code) === "ENOENT") {
        return { ok: false, exists: false, path: artifactPath, message: "artifact path does not exist" };
      }
      throw new BadRequestException(`Cannot inspect artifact path: ${String(error.message ?? error)}`);
    }
  }

  private async toManagedArtifactItem(relativePath: string): Promise<ManagedArtifactItem | null> {
    const target = this.resolveManagedArtifactPath(relativePath);
    try {
      const stat = await fs.lstat(target);
      if (stat.isSymbolicLink()) return null;
      const normalizedPath = relativePath.replaceAll("\\", "/");
      const source = sourceForManagedArtifact(normalizedPath);
      const extension = path.extname(relativePath).toLowerCase();
      const kind = stat.isDirectory() ? "directory" : stat.isFile() ? "file" : "other";
      const artifactType = kind === "directory" ? "directory" : isTextArtifactPath(normalizedPath) ? "text" : ALLOWED_UPLOAD_EXTENSIONS.has(extension) ? "binary" : "other";
      const directorySummary = stat.isDirectory() ? await summarizeDirectory(target, MAX_DIRECTORY_SUMMARY_FILES) : null;
      return {
        path: normalizedPath,
        name: path.basename(relativePath),
        source,
        kind,
        artifactType,
        editable: source === "repo" && artifactType === "text",
        previewable: source === "repo" && artifactType === "text",
        size: directorySummary ? directorySummary.totalBytes : stat.isFile() ? stat.size : null,
        totalBytes: directorySummary ? directorySummary.totalBytes : stat.isFile() ? stat.size : null,
        fileCount: directorySummary?.fileCount ?? (stat.isFile() ? 1 : null),
        modifiedAt: new Date(directorySummary?.modifiedMs || stat.mtimeMs).toISOString(),
        hash: stat.isFile() ? await sha256File(target) : null,
        archivable: source !== "archive",
        deletable: source !== "repo",
        archiveOnly: source === "repo",
        truncated: directorySummary?.truncated ?? false,
      };
    } catch {
      return null;
    }
  }

  private assertArtifactTextPath(relativePath: string, operation: "read" | "create" | "write") {
    const policy = this.workspace.enforceAuthoringPolicy(relativePath, operation);
    if (policy.kind !== "artifactText") {
      throw new BadRequestException("Only validation/artifacts text files are available through artifact authoring");
    }
  }

  private assertLanguageAssistPath(relativePath: string) {
    this.workspace.enforceAuthoringPolicy(relativePath, "write");
  }

  private resolveManagedArtifactPath(relativePath: string): string {
    if (!relativePath?.trim() || path.isAbsolute(relativePath)) {
      throw new BadRequestException("artifact path must be repository-relative");
    }
    const normalized = relativePath.replaceAll("\\", "/").replace(/^\/+/, "");
    if (normalized.split("/").some((segment) => segment === ".." || !segment)) {
      throw new BadRequestException("artifact path cannot include empty or .. segments");
    }
    if (this.workspace.isBlockedSecretPath(normalized)) {
      throw new BadRequestException("Secret files are not available through artifact management");
    }
    const allowedRoots = ["validation/artifacts", ".web-artifacts", ARCHIVE_ROOT];
    if (!allowedRoots.some((root) => normalized === root || normalized.startsWith(`${root}/`))) {
      throw new BadRequestException("artifact path is outside managed artifact roots");
    }
    const target = path.resolve(this.workspace.root, normalized);
    if (target !== this.workspace.root && !target.startsWith(this.workspace.root + path.sep)) {
      throw new BadRequestException("artifact path escapes workspace root");
    }
    return target;
  }

  private async statManagedArtifact(target: string, displayPath: string) {
    try {
      const stat = await fs.lstat(target);
      if (stat.isSymbolicLink()) {
        throw new BadRequestException("Symbolic links are not followed through artifact management");
      }
      return stat;
    } catch (error: any) {
      if (error instanceof BadRequestException) throw error;
      if (String(error?.code) === "ENOENT") throw new BadRequestException(`Artifact not found: ${displayPath}`);
      throw new BadRequestException(`Cannot inspect artifact: ${String(error.message ?? error)}`);
    }
  }

  private async manageDestructiveAction(action: "archive" | "delete", body: { path?: string; dryRun?: boolean; confirmToken?: string }): Promise<ArtifactManageActionResponse> {
    const artifactPath = body?.path?.trim();
    if (!artifactPath) {
      throw new BadRequestException("artifact path is required");
    }
    const normalizedPath = artifactPath.replaceAll("\\", "/").replace(/^\/+/, "");
    const target = this.resolveManagedArtifactPath(normalizedPath);
    const stat = await this.statManagedArtifact(target, normalizedPath);
    const source = sourceForManagedArtifact(normalizedPath);
    if (action === "archive" && source === "archive") {
      throw new BadRequestException("Archived artifacts cannot be archived again");
    }
    if (action === "delete" && source === "repo") {
      throw new BadRequestException("Repo artifacts must be archived before deletion");
    }
    const extension = path.extname(normalizedPath).toLowerCase();
    const kind = stat.isDirectory() ? "directory" : stat.isFile() ? "file" : "other";
    const artifactType = kind === "directory" ? "directory" : isTextArtifactPath(normalizedPath) ? "text" : ALLOWED_UPLOAD_EXTENSIONS.has(extension) ? "binary" : "other";
    const summary = stat.isDirectory() ? await summarizeDirectory(target, MAX_DIRECTORY_SUMMARY_FILES) : { fileCount: stat.isFile() ? 1 : 0, totalBytes: stat.isFile() ? stat.size : 0, modifiedMs: stat.mtimeMs, truncated: false };
    const archivePath = action === "archive" ? await this.nextArchivePath(normalizedPath, source) : null;
    const confirmToken = confirmTokenFor(action, normalizedPath, source, stat.mtimeMs, summary.fileCount, summary.totalBytes);
    const preview: ArtifactManagePreview = {
      action,
      path: normalizedPath,
      source,
      kind,
      artifactType,
      fileCount: summary.fileCount,
      totalBytes: summary.totalBytes,
      archivePath,
      archiveOnly: source === "repo",
      confirmationRequired: true,
      confirmToken,
      message: action === "archive" ? "Artifact will be moved to the archive." : "Artifact will be permanently deleted.",
    };
    if (body?.dryRun !== false || !body.confirmToken) {
      return { ...preview, ok: false, dryRun: true, completedPath: null };
    }
    if (body.confirmToken !== confirmToken) {
      throw new BadRequestException("Invalid artifact confirmation token");
    }
    if (action === "archive") {
      const archiveTarget = this.resolveManagedArtifactPath(archivePath || "");
      await fs.mkdir(path.dirname(archiveTarget), { recursive: true });
      await movePath(target, archiveTarget);
      return { ...preview, ok: true, dryRun: false, completedPath: archivePath };
    }
    await fs.rm(target, { recursive: true, force: true });
    if (source === "archive") {
      await this.cleanupEmptyArchiveParents(target);
    }
    return { ...preview, ok: true, dryRun: false, completedPath: null };
  }

  private async cleanupEmptyArchiveParents(deletedTarget: string) {
    const archiveRoot = path.resolve(this.workspace.root, ARCHIVE_ROOT);
    let current = path.dirname(deletedTarget);
    while (current !== archiveRoot && isInsidePath(archiveRoot, current)) {
      try {
        await fs.rmdir(current);
      } catch {
        break;
      }
      current = path.dirname(current);
    }
  }

  private async nextArchivePath(relativePath: string, source: string): Promise<string> {
    const stamp = new Date().toISOString().replace(/[-:TZ.]/g, "").slice(0, 14);
    const root = `${ARCHIVE_ROOT}/${stamp}/${source}`;
    const base = `${root}/${relativePath}`;
    let candidate = base;
    let index = 2;
    while (await this.workspace.exists(path.resolve(this.workspace.root, candidate))) {
      candidate = `${base}-${index}`;
      index += 1;
    }
    return candidate;
  }

  private async walkManagedArtifacts(root: string): Promise<string[]> {
    try {
      const stat = await fs.lstat(root);
      if (!stat.isDirectory() || stat.isSymbolicLink()) return [];
    } catch {
      return [];
    }
    const results: string[] = [];
    const entries = await fs.readdir(root, { withFileTypes: true });
    for (const entry of entries) {
      if (entry.isSymbolicLink()) continue;
      const full = path.join(root, entry.name);
      if (entry.isDirectory()) {
        results.push(this.workspace.relative(full));
        results.push(...(await this.walkManagedArtifacts(full)));
      } else if (entry.isFile()) {
        results.push(this.workspace.relative(full));
      }
    }
    return results.sort();
  }

  private async walkTree(root: string, relativePath: string, depth: number, items: ArtifactTreeItem[], onVisit: () => void): Promise<void> {
    if (items.length >= MAX_TREE_ITEMS) return;
    const entries = await fs.readdir(root, { withFileTypes: true });
    for (const entry of entries.sort((a, b) => Number(b.isDirectory()) - Number(a.isDirectory()) || a.name.localeCompare(b.name))) {
      if (entry.isSymbolicLink()) continue;
      const full = path.join(root, entry.name);
      const childRelativePath = `${relativePath}/${entry.name}`.replaceAll("\\", "/");
      const stat = await fs.lstat(full);
      onVisit();
      if (items.length < MAX_TREE_ITEMS) {
        items.push(await this.toTreeItem(full, childRelativePath, depth + 1, stat));
      }
      if (entry.isDirectory()) {
        await this.walkTree(full, childRelativePath, depth + 1, items, onVisit);
      }
      if (items.length >= MAX_TREE_ITEMS) return;
    }
  }

  private async toTreeItem(target: string, relativePath: string, depth: number, stat?: any): Promise<ArtifactTreeItem> {
    const targetStat = stat || await fs.lstat(target);
    const extension = path.extname(relativePath).toLowerCase();
    const kind = targetStat.isDirectory() ? "directory" : targetStat.isFile() ? "file" : "other";
    const artifactType = kind === "directory" ? "directory" : isTextArtifactPath(relativePath) ? "text" : ALLOWED_UPLOAD_EXTENSIONS.has(extension) ? "binary" : "other";
    return {
      path: relativePath,
      name: path.basename(relativePath),
      kind,
      artifactType,
      size: targetStat.isFile() ? targetStat.size : null,
      modifiedAt: new Date(targetStat.mtimeMs).toISOString(),
      depth,
    };
  }
}

async function summarizeDirectory(root: string, maxFiles = Number.POSITIVE_INFINITY): Promise<{ fileCount: number; totalBytes: number; modifiedMs: number; truncated: boolean }> {
  let fileCount = 0;
  let totalBytes = 0;
  let modifiedMs = 0;
  let truncated = false;
  const entries = await fs.readdir(root, { withFileTypes: true });
  for (const entry of entries) {
    if (entry.isSymbolicLink()) continue;
    if (fileCount >= maxFiles) {
      truncated = true;
      break;
    }
    const full = path.join(root, entry.name);
    const stat = await fs.lstat(full);
    modifiedMs = Math.max(modifiedMs, stat.mtimeMs);
    if (entry.isDirectory()) {
      const child = await summarizeDirectory(full, Math.max(0, maxFiles - fileCount));
      fileCount += child.fileCount;
      totalBytes += child.totalBytes;
      modifiedMs = Math.max(modifiedMs, child.modifiedMs);
      truncated = truncated || child.truncated;
    } else if (entry.isFile()) {
      fileCount += 1;
      totalBytes += stat.size;
    }
  }
  return { fileCount, totalBytes, modifiedMs, truncated };
}

function sha256File(target: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const hash = createHash("sha256");
    const stream = createReadStream(target);
    stream.on("data", (chunk) => hash.update(chunk));
    stream.on("error", reject);
    stream.on("end", () => resolve(hash.digest("hex")));
  });
}

function artifactTemplate(kind: ArtifactTemplateKind): string {
  switch (kind) {
    case "powershell":
      return [
        "param(",
        "  [string]$OutputPath = \"C:\\Oslab\\command-result.json\"",
        ")",
        "$lines = @(",
        "  \"oslab powershell system demo\",",
        "  \"artifact executed\",",
        "  \"generatedBy=Artifact Studio\"",
        ")",
        "$result = @{",
        "  schemaVersion = 1",
        "  kind = \"commandResult\"",
        "  command = \"custom powershell artifact\"",
        "  exitCode = 0",
        "  stdout = (($lines -join [Environment]::NewLine) + [Environment]::NewLine)",
        "  stderr = \"\"",
        "}",
        "$result | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 -LiteralPath $OutputPath",
        "Get-Content -LiteralPath $OutputPath -Raw",
        "",
      ].join("\n");
    case "shell":
      return "#!/usr/bin/env sh\nset -eu\necho \"artifact executed\"\n";
    case "python":
      return "print(\"artifact executed\")\n";
    case "c":
      return "#include <stdio.h>\n\nint main(void) {\n  puts(\"artifact executed\");\n  return 0;\n}\n";
    case "csharp":
      return "using System;\nusing System.Text.Json;\n\nvar result = new {\n  schemaVersion = 1,\n  kind = \"commandResult\",\n  exitCode = 0,\n  stdout = \"artifact executed\\n\",\n  stderr = \"\"\n};\n\nConsole.WriteLine(JsonSerializer.Serialize(result));\n";
    case "json":
      return "{\n  \"schemaVersion\": 1,\n  \"kind\": \"artifact\"\n}\n";
    case "yaml":
      return "schemaVersion: 1\nkind: artifact\nmetadata:\n  generatedBy: Artifact Studio\n";
    case "javascript":
      return "const result = {\n  schemaVersion: 1,\n  kind: \"commandResult\",\n  exitCode: 0,\n  stdout: \"artifact executed\\n\",\n  stderr: \"\",\n};\nconsole.log(JSON.stringify(result, null, 2));\n";
    case "typescript":
      return "type CommandResult = {\n  schemaVersion: number;\n  kind: \"commandResult\";\n  exitCode: number;\n  stdout: string;\n  stderr: string;\n};\n\nconst result: CommandResult = {\n  schemaVersion: 1,\n  kind: \"commandResult\",\n  exitCode: 0,\n  stdout: \"artifact executed\\n\",\n  stderr: \"\",\n};\nconsole.log(JSON.stringify(result, null, 2));\n";
    case "html":
      return "<!doctype html>\n<html lang=\"en\">\n  <head>\n    <meta charset=\"utf-8\" />\n    <title>OSLAB Artifact</title>\n  </head>\n  <body>\n    <main>artifact executed</main>\n  </body>\n</html>\n";
    case "css":
      return ":root {\n  color-scheme: light dark;\n}\n\nbody {\n  font-family: system-ui, sans-serif;\n}\n";
    case "markdown":
      return "# Artifact Notes\n\nDescribe what this artifact proves and how Results should inspect it.\n";
    case "dockerfile":
      return "FROM alpine:3.20\nWORKDIR /artifact\nCMD [\"sh\", \"-c\", \"printf '%s\\\\n' artifact executed\"]\n";
    case "cmd":
      return "@echo off\necho artifact executed\n";
    case "bat":
      return "@echo off\necho artifact executed\n";
    case "txt":
    default:
      return "artifact notes\n";
  }
}

function artifactProjectTemplate(kind: ArtifactProjectTemplateKind, projectPath: string, shell = "powershell", name = "Web artifact"): Array<{ path: string; content: string }> {
  const root = projectPath.replace(/\/+$/g, "");
  const normalizedShell = ["powershell", "shell", "python", "cmd", "bat"].includes(shell) ? shell : "powershell";
  if (kind === "inventory-agent") {
    return [
      {
        path: `${root}/run-inventory.ps1`,
        content: [
          "param(",
          "  [string]$OutputPath = \"C:\\Oslab\\inventory-result.json\",",
          "  [string]$ArtifactDir = $PSScriptRoot",
          ")",
          "$ErrorActionPreference = \"Stop\"",
          "$result = @{",
          "  schemaVersion = 1",
          "  kind = \"inventory\"",
          "  records = @(",
          "    @{",
          "      name = \"Example App\"",
          "      version = \"1.0.0\"",
          "      publisher = \"Example Publisher\"",
          "      sources = @(\"Registry\")",
          "      confidence = \"demo\"",
          "      evidence = @(@{ type = \"registry\"; source = \"Registry\"; path = \"HKLM\\Software\\Example\" })",
          "      metadata = @{ generatedBy = \"inventory-agent-starter\" }",
          "    }",
          "  )",
          "}",
          "$result | ConvertTo-Json -Depth 10 | Set-Content -Encoding UTF8 -LiteralPath $OutputPath",
          "Get-Content -LiteralPath $OutputPath -Raw",
          "",
        ].join("\n"),
      },
      {
        path: `${root}/expected-output.json`,
        content: "{\n  \"schemaVersion\": 1,\n  \"kind\": \"inventory\",\n  \"records\": []\n}\n",
      },
      {
        path: `${root}/README.txt`,
        content: "Inventory agent starter artifact. Replace run-inventory.ps1 with your product command or wrap your scanner executable, then select this folder in Run Launcher.\n",
      },
    ];
  }
  if (kind === "install-profile") {
    return [
      {
        path: `${root}/profile-notes.json`,
        content: "{\n  \"schemaVersion\": 1,\n  \"kind\": \"installProfile\",\n  \"name\": \"profile starter\",\n  \"channels\": [\"exe\", \"msi\", \"winget\", \"chocolatey\", \"appx\"]\n}\n",
      },
      {
        path: `${root}/prepare-profile.ps1`,
        content: [
          "$ErrorActionPreference = \"Stop\"",
          "New-Item -ItemType Directory -Force -Path C:\\Oslab\\profile | Out-Null",
          "\"profile prepared\" | Set-Content -Encoding UTF8 C:\\Oslab\\profile\\state.txt",
          "Write-Output \"Install profile starter prepared\"",
          "",
        ].join("\n"),
      },
      {
        path: `${root}/README.txt`,
        content: "Install profile starter. Expand this folder with setup scripts for EXE/MSI, winget, Chocolatey, or Appx validation.\n",
      },
    ];
  }
  const entry = entrypointForProject(normalizedShell);
  return [
    { path: `${root}/${entry.filename}`, content: entry.content(name) },
    { path: `${root}/expected-output.json`, content: "{\n  \"schemaVersion\": 1,\n  \"kind\": \"commandResult\",\n  \"exitCode\": 0\n}\n" },
    { path: `${root}/README.txt`, content: `${name}\n\nGenerated by Artifact Studio. Edit the entrypoint, then select this folder in Run Launcher.\n` },
  ];
}

function entrypointForProject(shell: string): { filename: string; content: (name: string) => string } {
  if (shell === "shell") {
    return { filename: "run-artifact.sh", content: (name) => `#!/usr/bin/env sh\nset -eu\necho "${name} executed"\n` };
  }
  if (shell === "python") {
    return { filename: "run_artifact.py", content: (name) => `print("${name} executed")\n` };
  }
  if (shell === "cmd" || shell === "bat") {
    return { filename: "run-artifact.cmd", content: (name) => `@echo off\necho ${name} executed\n` };
  }
  return {
    filename: "run-artifact.ps1",
    content: (name) => [
      "param(",
      "  [string]$OutputPath = \"C:\\Oslab\\command-result.json\"",
      ")",
      "$result = @{",
      "  schemaVersion = 1",
      "  kind = \"commandResult\"",
      `  command = "${name}"`,
      "  exitCode = 0",
      "  stdout = \"artifact executed`n\"",
      "  stderr = \"\"",
      "}",
      "$result | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 -LiteralPath $OutputPath",
      "Get-Content -LiteralPath $OutputPath -Raw",
      "",
    ].join("\n"),
  };
}

function languageForArtifactPath(artifactPath: string): ArtifactLanguageKind {
  const extension = path.extname(artifactPath).toLowerCase();
  const basename = path.basename(artifactPath).toLowerCase();
  if (extension === ".ps1") return "powershell";
  if (extension === ".sh") return "shell";
  if (extension === ".py") return "python";
  if (extension === ".json") return "json";
  if (extension === ".yaml" || extension === ".yml") return "yaml";
  if (extension === ".js" || extension === ".mjs" || extension === ".cjs") return "javascript";
  if (extension === ".ts") return "typescript";
  if (extension === ".html" || extension === ".htm") return "html";
  if (extension === ".css") return "css";
  if (extension === ".md" || extension === ".markdown") return "markdown";
  if (extension === ".dockerfile" || basename === "dockerfile") return "dockerfile";
  if (extension === ".cmd" || extension === ".bat") return "bat";
  if (extension === ".c") return "c";
  if (extension === ".cs") return "csharp";
  return "plaintext";
}

function inspectArtifactContent(artifactPath: string, content: string, language: ArtifactLanguageKind): ArtifactAssistIssue[] {
  const issues: ArtifactAssistIssue[] = [];
  if (language === "json") {
    try {
      JSON.parse(content || "{}");
    } catch (error: any) {
      issues.push({ severity: "error", code: "json.parse", message: `JSON parse error: ${String(error.message ?? error)}` });
    }
  }
  if (language === "yaml") {
    const parsed = parseDocument(content || "");
    if (parsed.errors.length) {
      issues.push({ severity: "error", code: "yaml.parse", message: `YAML parse error: ${parsed.errors[0]?.message || "Invalid YAML"}` });
    }
  }
  const placeholderMatches = content.match(/\{\{[^}]+\}\}/g) || [];
  for (const token of placeholderMatches) {
    const name = token.replace(/[{}]/g, "");
    if (!OSLAB_PLACEHOLDERS.includes(name)) {
      issues.push({ severity: "warning", code: "placeholder.unknown", message: `Unknown OSLAB placeholder: ${token}` });
    }
  }
  for (const item of artifactLintRules(language)) {
    const line = lineForMatch(content, item.pattern);
    if (line) issues.push({ severity: item.severity, code: item.code, message: item.message, line });
  }
  if (/(api[_-]?key|password|secret|token)\s*[:=]\s*['"]?[A-Za-z0-9_\-.]{8,}/i.test(content)) {
    issues.push({ severity: "warning", code: "secret.pattern", message: "Possible secret value found. Use env/config references instead of hardcoding secrets." });
  }
  if (/^[A-Za-z]:\\Users\\/im.test(content) || /\/home\/[^/\s]+/i.test(content)) {
    issues.push({ severity: "warning", code: "local.absolute.path", message: "Local user-specific absolute paths may not exist inside the VM." });
  }
  if (["powershell", "shell", "python", "javascript", "typescript", "csharp", "bat"].includes(language) && !/(OutputPath|command-result|ConvertTo-Json|JsonSerializer|json|Set-Content|echo|print|Console\.WriteLine|console\.log)/i.test(content)) {
    issues.push({ severity: "info", code: "output.contract", message: "Consider writing a machine-readable output file so assertions can inspect the result." });
  }
  if (!content.trim()) {
    issues.push({ severity: "info", code: "empty", message: `${path.basename(artifactPath)} is empty. Insert a starter snippet before saving.` });
  }
  return issues;
}

function artifactLintRules(language: ArtifactLanguageKind): Array<{ pattern: RegExp; severity: ArtifactAssistIssue["severity"]; code: string; message: string }> {
  const common = [
    { pattern: /(api[_-]?key|password|secret|token)\s*[:=]\s*['"]?[A-Za-z0-9_\-.]{8,}/i, severity: "warning" as const, code: "secret.pattern", message: "Possible secret value found. Use env/config references instead of hardcoding secrets." },
  ];
  if (language === "powershell") {
    return [
      { pattern: /Remove-Item\b[\s\S]*-Recurse/i, severity: "warning", code: "dangerous.pattern", message: "Remove-Item -Recurse can remove many files. Review before saving." },
      { pattern: /\bInvoke-Expression\b|\biex\b/i, severity: "warning", code: "powershell.invoke-expression", message: "Invoke-Expression is hard to audit. Prefer explicit commands or argument arrays." },
      { pattern: /\bSet-ExecutionPolicy\b/i, severity: "warning", code: "powershell.execution-policy", message: "Changing execution policy can hide environment problems in automated runs." },
      { pattern: /Start-Process\b[\s\S]*-Verb\s+RunAs/i, severity: "warning", code: "powershell.elevation", message: "RunAs elevation is interactive and usually breaks automated VM runs." },
      ...common,
    ];
  }
  if (language === "shell") {
    return [
      { pattern: /\brm\s+-rf\b/i, severity: "warning", code: "dangerous.pattern", message: "rm -rf can remove many files. Review before saving." },
      { pattern: /\bcurl\b[\s\S]*\|\s*(sh|bash)\b|\bwget\b[\s\S]*\|\s*(sh|bash)\b/i, severity: "warning", code: "shell.pipe-install", message: "curl/wget piped to shell is risky. Pin or vendor setup assets into the artifact." },
      { pattern: /\bsudo\b/i, severity: "info", code: "shell.sudo", message: "sudo may prompt inside the VM. Prefer prepared templates or explicit fixture setup." },
      { pattern: /\bchmod\s+-R\s+777\b/i, severity: "warning", code: "shell.chmod-777", message: "chmod -R 777 is overly broad. Narrow the path and mode." },
      ...common,
    ];
  }
  if (language === "python") {
    return [
      { pattern: /subprocess\.[A-Za-z_]+\([^\n)]*shell\s*=\s*True/i, severity: "warning", code: "python.subprocess-shell", message: "subprocess shell=True is harder to quote safely. Prefer argument arrays." },
      { pattern: /\bos\.system\s*\(/i, severity: "warning", code: "python.os-system", message: "os.system hides exit/output details. Prefer subprocess.run(..., check=True)." },
      { pattern: /\bshutil\.rmtree\s*\(/i, severity: "warning", code: "dangerous.pattern", message: "shutil.rmtree can remove whole directories. Review before saving." },
      { pattern: /\beval\s*\(|\bexec\s*\(/i, severity: "warning", code: "python.eval-exec", message: "eval/exec is hard to audit in validation scripts. Prefer explicit parsing." },
      ...common,
    ];
  }
  if (language === "bat") {
    return [
      { pattern: /\bdel\s+\/s\b/i, severity: "warning", code: "dangerous.pattern", message: "del /s can remove many files. Review before saving." },
      { pattern: /\brd\s+\/s\b|\brmdir\s+\/s\b/i, severity: "warning", code: "dangerous.pattern", message: "rmdir /s can remove whole directories. Review before saving." },
      { pattern: /\bformat\s+[A-Z]:/i, severity: "warning", code: "bat.format", message: "format is destructive and should not be used in dashboard-authored artifacts." },
      { pattern: /\breg\s+delete\b/i, severity: "warning", code: "bat.reg-delete", message: "Registry deletion should be isolated to an explicit fixture path." },
      ...common,
    ];
  }
  if (language === "c") {
    return [
      { pattern: /\bgets\s*\(/i, severity: "warning", code: "c.gets", message: "gets is unsafe. Use fgets with an explicit buffer size." },
      { pattern: /\bstrcpy\s*\(/i, severity: "info", code: "c.strcpy", message: "strcpy can overflow buffers. Prefer bounded copy patterns." },
      { pattern: /\bsystem\s*\(/i, severity: "warning", code: "c.system", message: "system() hides quoting and exit detail. Prefer explicit process setup in the scenario command." },
      ...common,
    ];
  }
  if (language === "csharp") {
    return [
      { pattern: /\bProcess\.Start\s*\(/i, severity: "warning", code: "csharp.process-start", message: "Process.Start can hide quoting and exit handling. Prefer explicit ProcessStartInfo with redirected output." },
      { pattern: /\bEnvironment\.GetEnvironmentVariable\s*\([^\n)]*(TOKEN|SECRET|PASSWORD|KEY)/i, severity: "info", code: "csharp.env-secret", message: "Secret-like env reads should stay documented and redacted in run logs." },
      { pattern: /\bFile\.Delete\s*\(/i, severity: "warning", code: "csharp.file-delete", message: "File.Delete should be scoped to disposable VM state or {{OutputPath}}-adjacent files." },
      ...common,
    ];
  }
  if (language === "javascript" || language === "typescript") {
    return [
      { pattern: /\beval\s*\(/i, severity: "warning", code: "js.eval", message: "eval is hard to audit in validation artifacts. Prefer explicit parsing." },
      { pattern: /\bchild_process\.(exec|execSync)\s*\(/i, severity: "warning", code: "js.child-process-exec", message: "child_process.exec uses a shell. Prefer spawn/execFile with argument arrays." },
      { pattern: /\bprocess\.env\.[A-Z0-9_]*(TOKEN|SECRET|PASSWORD|KEY)/i, severity: "info", code: "js.env-secret", message: "Secret-like env reads should stay documented and redacted in run logs." },
      ...common,
    ];
  }
  if (language === "dockerfile") {
    return [
      { pattern: /^\s*ADD\s+https?:\/\//im, severity: "warning", code: "dockerfile.remote-add", message: "Remote ADD hides download policy. Prefer explicit curl with checksum or vendored assets." },
      { pattern: /^\s*USER\s+root\s*$/im, severity: "info", code: "dockerfile.root-user", message: "Root container user is sometimes necessary, but call it out in artifact notes." },
      ...common,
    ];
  }
  return common;
}

function lineForMatch(content: string, pattern: RegExp): number | null {
  const lines = content.split(/\r?\n/);
  const index = lines.findIndex((line) => pattern.test(line));
  return index >= 0 ? index + 1 : null;
}

function artifactAssistSnippets(language: ArtifactLanguageKind) {
  const common = [
    {
      id: "placeholder-artifact-dir",
      label: "{{ArtifactDir}}",
      detail: "Artifact directory placeholder.",
      language,
      insertText: "{{ArtifactDir}}",
    },
    {
      id: "placeholder-output-path",
      label: "{{OutputPath}}",
      detail: "Output JSON path placeholder.",
      language,
      insertText: "{{OutputPath}}",
    },
    {
      id: "placeholder-scenario-id",
      label: "{{ScenarioId}}",
      detail: "Current scenario id placeholder.",
      language,
      insertText: "{{ScenarioId}}",
    },
    {
      id: "placeholder-run-id",
      label: "{{RunId}}",
      detail: "Current run id placeholder.",
      language,
      insertText: "{{RunId}}",
    },
    {
      id: "output-contract-json",
      label: "command-result JSON",
      detail: "Emit a stable commandResult object for assertions.",
      language: "json",
      insertText: "{\n  \"schemaVersion\": 1,\n  \"kind\": \"commandResult\",\n  \"exitCode\": 0,\n  \"stdout\": \"\",\n  \"stderr\": \"\"\n}\n",
    },
    {
      id: "inventory-agent-runner",
      label: "Inventory agent runner",
      detail: "Run an inventory wrapper and write canonical inventory JSON.",
      language: "powershell",
      insertText: "& \"{{ArtifactDir}}\\run-inventory.ps1\" -OutputPath \"{{OutputPath}}\"\n",
    },
  ];
  if (language === "powershell") {
    return [
      {
        id: "powershell-oslab-demo",
        label: "PowerShell OSLAB demo runner",
        detail: "Runnable demo-powershell-system script with OutputPath.",
        language,
        insertText: [
          "param(",
          "  [string]$OutputPath = \"C:\\Oslab\\command-result.json\"",
          ")",
          "$lines = @(",
          "  \"oslab powershell system demo\",",
          "  \"artifactDir=$PSScriptRoot\",",
          "  \"generatedBy=Artifact Studio\"",
          ")",
          "$result = @{",
          "  schemaVersion = 1",
          "  kind = \"commandResult\"",
          "  command = \"artifact studio powershell demo\"",
          "  exitCode = 0",
          "  stdout = (($lines -join [Environment]::NewLine) + [Environment]::NewLine)",
          "  stderr = \"\"",
          "}",
          "$result | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 -LiteralPath $OutputPath",
          "Get-Content -LiteralPath $OutputPath -Raw",
          "",
        ].join("\n"),
      },
      {
        id: "powershell-result",
        label: "PowerShell result writer",
        detail: "Create commandResult JSON and write it to a script OutputPath parameter.",
        language,
        insertText: [
          "param(",
          "  [string]$OutputPath = \"C:\\Oslab\\command-result.json\"",
          ")",
          "$result = @{ schemaVersion = 1; kind = \"commandResult\"; exitCode = 0; stdout = \"ok`n\"; stderr = \"\" }",
          "$result | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 -LiteralPath $OutputPath",
          "Get-Content -LiteralPath $OutputPath -Raw",
          "",
        ].join("\n"),
      },
      ...common,
    ];
  }
  if (language === "shell") {
    return [
      { id: "shell-strict", label: "Shell strict mode", detail: "Safe shell starter.", language, insertText: "#!/usr/bin/env sh\nset -eu\necho \"artifact executed\"\n" },
      ...common,
    ];
  }
  if (language === "python") {
    return [
      { id: "python-json", label: "Python JSON output", detail: "Write commandResult JSON.", language, insertText: "import json\nprint(json.dumps({\"schemaVersion\": 1, \"kind\": \"commandResult\", \"exitCode\": 0}))\n" },
      ...common,
    ];
  }
  if (language === "csharp") {
    return [
      { id: "csharp-command-result", label: "C# commandResult writer", detail: "Serialize a commandResult object to stdout.", language, insertText: "using System;\nusing System.Text.Json;\n\nvar result = new {\n  schemaVersion = 1,\n  kind = \"commandResult\",\n  exitCode = 0,\n  stdout = \"artifact executed\\n\",\n  stderr = \"\"\n};\n\nConsole.WriteLine(JsonSerializer.Serialize(result));\n" },
      ...common,
    ];
  }
  return common;
}

function firstRunTipsForLanguage(language: ArtifactLanguageKind): string[] {
  const common = [
    "Artifact is copied into the VM, then the scenario command runs it or inspects its output.",
    "Prefer writing a stable JSON result to {{OutputPath}} so assertions can verify it.",
    "Use {{ArtifactDir}} instead of local user paths because the VM path is different from the dashboard machine.",
  ];
  if (language === "powershell") {
    return ["Start with a param block for OutputPath.", "Use ConvertTo-Json and Set-Content -Encoding UTF8 for machine-readable output.", ...common];
  }
  if (language === "python") {
    return ["Use json.dump/json.dumps for output contracts.", "Keep dependencies explicit because the VM Python environment may differ.", ...common];
  }
  if (language === "shell") {
    return ["Use set -eu for predictable failures.", "Avoid local absolute paths; prefer {{ArtifactDir}} and {{OutputPath}}.", ...common];
  }
  if (language === "bat") {
    return ["Use @echo off for readable logs.", "Keep file paths quoted and write result files explicitly.", ...common];
  }
  if (language === "c") {
    return ["Compile the C program as part of the artifact workflow or include a compiled binary separately.", ...common];
  }
  if (language === "csharp") {
    return ["Use System.Text.Json for machine-readable commandResult output.", "Run it with a prepared dotnet SDK/runtime in the VM or include a publish/build step.", ...common];
  }
  if (language === "json") {
    return ["Keep JSON valid; comments are not allowed.", "Use this for expected output or configuration metadata.", ...common];
  }
  return common;
}

function normalizeArtifactLanguageKind(language?: string): ArtifactLanguageKind {
  if (language === "powershell" || language === "shell" || language === "python" || language === "json" || language === "yaml" || language === "javascript" || language === "typescript" || language === "html" || language === "css" || language === "markdown" || language === "dockerfile" || language === "bat" || language === "c" || language === "csharp" || language === "plaintext") {
    return language;
  }
  throw new BadRequestException("Unsupported artifact language tool");
}

async function languageToolStatusCached(language: ArtifactLanguageKind, force = false): Promise<ArtifactLanguageToolStatus> {
  const cached = languageToolCache.get(language);
  const now = Date.now();
  if (!force && cached && now - cached.checkedAt < LANGUAGE_TOOL_CACHE_TTL_MS) {
    return cached.status;
  }
  const status = await inspectLanguageToolStatus(language);
  languageToolCache.set(language, { checkedAt: now, status });
  return status;
}

async function inspectLanguageToolStatus(language: ArtifactLanguageKind): Promise<ArtifactLanguageToolStatus> {
  if (language === "json") {
    return {
      language,
      label: "JSON",
      state: "available",
      installable: false,
      installHint: "JSON validation is built into Artifact Studio.",
      nextAction: "Use the editor check panel for parse errors.",
      tools: [{ id: "json-parser", label: "Built-in JSON parser", state: "available", hint: "No external tool required." }],
    };
  }
  if (language === "plaintext") {
    return {
      language,
      label: "Plain text",
      state: "unsupported",
      installable: false,
      installHint: "Plain text artifacts do not have a language tool.",
      nextAction: "Use snippets only when a structured output is needed.",
      tools: [{ id: "plaintext", label: "Plain text", state: "unsupported", hint: "No language diagnostics are available." }],
    };
  }
  if (language === "bat") {
    const cmd = process.platform === "win32" ? await commandVersion("cmd.exe", ["/d", "/c", "ver"]) : null;
    return summarizeToolStatus(language, "Batch/CMD", "Use Windows cmd.exe syntax checks manually when needed.", [
      cmd ? toolDetail("cmd", "cmd.exe", cmd, "Batch execution host detected.") : missingTool("cmd", "cmd.exe", "cmd.exe is normally available on Windows hosts."),
    ]);
  }
  if (language === "powershell") {
    const pwsh = await commandVersion("pwsh", ["--version"]);
    const powershell = process.platform === "win32" ? await commandVersion("powershell.exe", ["-NoProfile", "-Command", "$PSVersionTable.PSVersion.ToString()"]) : null;
    return summarizeToolStatus(language, "PowerShell", "Install PowerShell 7 (`pwsh`) for the best editor and validation path, or use Windows PowerShell on Windows hosts.", [
      toolDetail("pwsh", "PowerShell 7", pwsh, "Recommended modern PowerShell host."),
      powershell ? toolDetail("powershell", "Windows PowerShell", powershell, "Windows fallback host.") : missingTool("powershell", "Windows PowerShell", "Available by default on Windows."),
    ]);
  }
  if (language === "python") {
    const python = await commandVersion("python", ["--version"]);
    const pyLauncher = process.platform === "win32" ? await commandVersion("py", ["-3", "--version"]) : null;
    const pyright = await commandVersion("pyright", ["--version"]);
    return summarizeToolStatus(language, "Python", "Install Python and optionally Pyright for richer diagnostics. Artifact Studio will not execute your script during checks.", [
      toolDetail("python", "Python", python, "Python interpreter for local environment checks."),
      pyLauncher ? toolDetail("py", "Python launcher", pyLauncher, "Windows Python launcher.") : missingTool("py", "Python launcher", "Optional Windows helper."),
      toolDetail("pyright", "Pyright", pyright, "Optional static type checker."),
    ]);
  }
  if (language === "shell") {
    const sh = await commandVersion("sh", ["--version"]);
    const bash = await commandVersion("bash", ["--version"]);
    const shellcheck = await commandVersion("shellcheck", ["--version"]);
    return summarizeToolStatus(language, "Shell", "Install shellcheck for stronger shell diagnostics. Artifact Studio static checks still work without it.", [
      toolDetail("sh", "sh", sh, "POSIX shell host."),
      toolDetail("bash", "bash", bash, "Optional shell host."),
      toolDetail("shellcheck", "shellcheck", shellcheck, "Optional shell lint tool."),
    ]);
  }
  const cl = process.platform === "win32" ? await commandVersion("cl", []) : null;
  const gcc = await commandVersion("gcc", ["--version"]);
  const clang = await commandVersion("clang", ["--version"]);
  return summarizeToolStatus(language, "C", "Install Visual Studio Build Tools, gcc, or clang if you want to compile C artifacts locally.", [
    cl ? toolDetail("cl", "MSVC cl", cl, "Visual Studio C compiler.") : missingTool("cl", "MSVC cl", "Optional on Windows with Visual Studio Build Tools."),
    toolDetail("gcc", "gcc", gcc, "GNU C compiler."),
    toolDetail("clang", "clang", clang, "LLVM C compiler."),
  ]);
}

function summarizeToolStatus(language: ArtifactLanguageKind, label: string, installHint: string, tools: ArtifactLanguageToolStatus["tools"]): ArtifactLanguageToolStatus {
  const requiredTools = tools.filter((tool) => !["pyright", "shellcheck"].includes(tool.id));
  const available = tools.filter((tool) => tool.state === "available").length;
  const availableById = new Set(tools.filter((tool) => tool.state === "available").map((tool) => tool.id));
  const requiredAvailable =
    (language === "powershell" && (availableById.has("pwsh") || availableById.has("powershell"))) ||
    (language === "python" && (availableById.has("python") || availableById.has("py"))) ||
    (language === "shell" && (availableById.has("sh") || availableById.has("bash"))) ||
    (language === "c" && (availableById.has("cl") || availableById.has("gcc") || availableById.has("clang"))) ||
    (!["powershell", "python", "shell", "c"].includes(language) && requiredTools.some((tool) => tool.state === "available"));
  const state: ArtifactLanguageToolStatus["state"] = requiredAvailable ? (available === tools.length ? "available" : "partial") : "missing";
  return {
    language,
    label,
    state,
    installable: state !== "available",
    installHint,
    nextAction: state === "missing" ? "Install or configure the language tool, or continue with built-in static checks only." : "Built-in checks are available; optional tools can improve diagnostics.",
    tools,
  };
}

function toolDetail(id: string, label: string, result: CommandVersionResult | null, hint: string): ArtifactLanguageToolStatus["tools"][number] {
  if (!result?.ok) return missingTool(id, label, hint);
  return {
    id,
    label,
    state: "available",
    command: result.command,
    version: result.output,
    hint,
  };
}

function missingTool(id: string, label: string, hint: string): ArtifactLanguageToolStatus["tools"][number] {
  return { id, label, state: "missing", hint };
}

type CommandVersionResult = { ok: boolean; command: string; output?: string };

function commandVersion(command: string, args: string[]): Promise<CommandVersionResult> {
  return new Promise((resolve) => {
    execFile(command, args, { timeout: 3000, windowsHide: true }, (error, stdout, stderr) => {
      const output = `${stdout || stderr}`.trim().split(/\r?\n/).filter(Boolean).slice(0, 2).join(" · ");
      if (error) {
        if (output && (error as NodeJS.ErrnoException).code !== "ENOENT") {
          resolve({ ok: true, command, output });
          return;
        }
        resolve({ ok: false, command });
        return;
      }
      resolve({ ok: true, command, output: output || command });
    });
  });
}

function safeRelativeUploadPath(value: string): string {
  const normalized = value.replaceAll("\\", "/").replace(/^\/+/, "");
  const parts = normalized.split("/").filter(Boolean);
  if (!parts.length || parts.some((part) => part === "." || part === "..")) {
    throw new BadRequestException("Invalid artifact directory path");
  }
  return parts.join("/");
}

function safePathSegment(value: string): string {
  const cleaned = value.replace(/[^A-Za-z0-9가-힣._ -]/g, "_").replace(/[. ]+$/g, "").trim();
  return cleaned || "artifact";
}

function sourceForManagedArtifact(relativePath: string): ManagedArtifactSource {
  if (relativePath.startsWith(".web-artifacts/") || relativePath === ".web-artifacts") return "uploaded";
  if (relativePath.startsWith(`${ARCHIVE_ROOT}/`) || relativePath === ARCHIVE_ROOT) return "archive";
  return "repo";
}

function isTextArtifactPath(relativePath: string): boolean {
  return TEXT_ARTIFACT_EXTENSIONS.has(path.extname(relativePath).toLowerCase()) || path.basename(relativePath).toLowerCase() === "dockerfile";
}

function isInsidePath(parent: string, child: string): boolean {
  const relative = path.relative(parent, child);
  return !!relative && !relative.startsWith("..") && !path.isAbsolute(relative);
}

function confirmTokenFor(action: string, relativePath: string, source: string, modifiedMs: number, fileCount: number, totalBytes: number) {
  return createHash("sha256").update(`${action}\n${relativePath}\n${source}\n${modifiedMs}\n${fileCount}\n${totalBytes}`).digest("hex").slice(0, 32);
}

async function movePath(source: string, target: string): Promise<void> {
  try {
    await fs.rename(source, target);
  } catch (error: any) {
    if (String(error?.code) !== "EXDEV") throw error;
    await fs.cp(source, target, { recursive: true, force: false, errorOnExist: true });
    await fs.rm(source, { recursive: true, force: true });
  }
}
