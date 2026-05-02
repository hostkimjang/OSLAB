import { BadRequestException, Injectable, NotFoundException } from "@nestjs/common";
import { promises as fs, readdirSync } from "fs";
import path from "path";

export type CatalogKind = "scenario" | "suite" | "fixture" | "artifact";
export type AuthoringKind = "scenario" | "suite" | "fixture" | "artifactText";
export type AuthoringOperation = "read" | "create" | "write";
export const TEXT_AUTHORING_MAX_BYTES = 1024 * 1024;

const WINDOWS_RESERVED_DEVICE_NAMES = new Set([
  "CON",
  "PRN",
  "AUX",
  "NUL",
  ...Array.from({ length: 9 }, (_, index) => `COM${index + 1}`),
  ...Array.from({ length: 9 }, (_, index) => `LPT${index + 1}`),
]);

type AuthoringRule = {
  root: string;
  extensions: Set<string>;
};

@Injectable()
export class WorkspaceService {
  readonly root = path.resolve(process.env.OSLAB_REPO_ROOT ?? findRepoRoot(process.cwd()));
  readonly webDataDir = path.join(this.root, ".web-data");
  readonly artifactDir = path.join(this.root, ".web-artifacts");

  private readonly authoringRules: Record<AuthoringKind, AuthoringRule> = {
    scenario: { root: "scenarios", extensions: new Set([".yaml", ".yml"]) },
    suite: { root: path.join("validation", "suites"), extensions: new Set([".yaml", ".yml"]) },
    fixture: { root: path.join("validation", "fixtures"), extensions: new Set([".ps1", ".sh"]) },
    artifactText: { root: path.join("validation", "artifacts"), extensions: new Set([".ps1", ".sh", ".py", ".c", ".json", ".txt", ".cmd", ".bat"]) },
  };
  private readonly editableRoots = Object.values(this.authoringRules).map((rule) => rule.root);
  private readonly readableRoots = [...this.editableRoots, "runs"];

  resolveEditable(relativePath: string): string {
    return this.resolveAllowed(relativePath, this.editableRoots);
  }

  resolveReadable(relativePath: string): string {
    if (this.isBlockedSecretPath(relativePath)) {
      throw new BadRequestException("Secret files are not readable through the web API");
    }
    return this.resolveAllowed(relativePath, this.readableRoots);
  }

  enforceAuthoringPolicy(relativePath: string, operation: AuthoringOperation): { kind: AuthoringKind; path: string } {
    if (this.isBlockedSecretPath(relativePath)) {
      throw new BadRequestException("Secret files are not available through the authoring API");
    }
    const normalized = this.normalizeRepositoryPath(relativePath);
    this.enforceSafeAuthoringSegments(normalized);
    const kind = this.authoringKindForPath(normalized);
    if (!kind) {
      throw new BadRequestException("Path is outside authoring roots");
    }
    const extension = path.extname(normalized).toLowerCase();
    const rule = this.authoringRules[kind];
    if (!rule.extensions.has(extension)) {
      throw new BadRequestException(`${kind} files must end with ${Array.from(rule.extensions).join(" or ")}`);
    }
    const target = this.resolveAllowed(normalized, operation === "read" ? this.readableRoots : this.editableRoots);
    return { kind, path: target };
  }

  resolveRunFile(runId: string, relativePath = ""): string {
    const runRoot = this.resolveRunRoot(runId);
    const target = path.resolve(runRoot, relativePath);
    if (target !== runRoot && !target.startsWith(runRoot + path.sep)) {
      throw new BadRequestException("Path escapes run directory");
    }
    return target;
  }

  async readText(relativePath: string): Promise<string> {
    const target = this.enforceAuthoringPolicy(relativePath, "read").path;
    try {
      return await fs.readFile(target, "utf8");
    } catch (error) {
      throw new NotFoundException(`File not found: ${relativePath}`);
    }
  }

  async writeText(relativePath: string, content: string): Promise<void> {
    const target = this.enforceAuthoringPolicy(relativePath, "write").path;
    this.enforceTextAuthoringSize(content);
    await fs.mkdir(path.dirname(target), { recursive: true });
    await fs.writeFile(target, content, "utf8");
  }

  async createText(relativePath: string, content: string): Promise<void> {
    const target = this.enforceAuthoringPolicy(relativePath, "create").path;
    this.enforceTextAuthoringSize(content);
    if (await this.exists(target)) {
      throw new BadRequestException(`File already exists: ${relativePath}`);
    }
    await fs.mkdir(path.dirname(target), { recursive: true });
    await fs.writeFile(target, content, { encoding: "utf8", flag: "wx" });
  }

  resolveArtifactProjectDirectory(relativePath: string): string {
    if (this.isBlockedSecretPath(relativePath)) {
      throw new BadRequestException("Secret files are not available through the authoring API");
    }
    const normalized = this.normalizeRepositoryPath(relativePath);
    this.enforceSafeAuthoringSegments(normalized);
    const artifactRoot = path.join("validation", "artifacts").replaceAll("\\", "/");
    if (normalized === artifactRoot || !normalized.startsWith(`${artifactRoot}/`)) {
      throw new BadRequestException("Artifact projects must be created under validation/artifacts/**");
    }
    return this.resolveAllowed(normalized, this.editableRoots);
  }

  async listCatalog(kind: CatalogKind) {
    const rootByKind: Record<CatalogKind, string> = {
      scenario: "scenarios",
      suite: path.join("validation", "suites"),
      fixture: path.join("validation", "fixtures"),
      artifact: path.join("validation", "artifacts"),
    };
    const root = path.join(this.root, rootByKind[kind]);
    const extensionsByKind: Record<CatalogKind, Set<string>> = {
      scenario: new Set([".yaml", ".yml"]),
      suite: new Set([".yaml", ".yml"]),
      fixture: new Set([".ps1", ".sh"]),
      artifact: new Set([".ps1", ".sh", ".zip", ".exe", ".msi", ".cmd", ".bat", ".py", ".c", ".json", ".txt"]),
    };
    if (kind === "artifact") {
      const artifactRoots = [path.join(this.root, rootByKind.artifact), this.artifactDir];
      const entries = (
        await Promise.all(artifactRoots.map((artifactRoot) => this.walkArtifacts(artifactRoot, extensionsByKind.artifact)))
      ).flat().sort();
      return entries.map((file) => ({
        path: this.relative(file),
        name: path.basename(file),
        kind,
      }));
    }
    const entries = await this.walk(root, extensionsByKind[kind]);
    return entries.map((file) => ({
      path: this.relative(file),
      name: path.basename(file),
      kind,
    }));
  }

  async listRuns() {
    const runsRoot = path.join(this.root, "runs");
    try {
      const entries = await fs.readdir(runsRoot, { withFileTypes: true });
      const summaries = [];
      for (const entry of entries) {
        if (!entry.isDirectory()) continue;
        const dir = path.join(runsRoot, entry.name);
        const suiteJson = path.join(dir, "suite.json");
        const runJson = path.join(dir, "run.json");
        const updatedAt = await this.runUpdatedAt(dir);
        if (await this.exists(suiteJson)) {
          const payload = JSON.parse(await fs.readFile(suiteJson, "utf8"));
          summaries.push({
            id: entry.name,
            kind: "suite",
            status: payload.status,
            path: this.relative(dir),
            startedAt: payload.startedAt ?? null,
            completedAt: payload.completedAt ?? null,
            updatedAt,
            ...suiteSummaryFields(payload),
          });
        } else if (await this.exists(runJson)) {
          const payload = JSON.parse(await fs.readFile(runJson, "utf8"));
          summaries.push({
            id: entry.name,
            kind: "run",
            status: payload.status,
            path: this.relative(dir),
            startedAt: payload.startedAt ?? null,
            completedAt: payload.completedAt ?? null,
            updatedAt,
            ...runSummaryFields(payload),
          });
        }
      }
      return summaries.sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
    } catch {
      return [];
    }
  }

  relative(absolutePath: string): string {
    return path.relative(this.root, absolutePath).replaceAll(path.sep, "/");
  }

  isBlockedSecretPath(relativePath: string): boolean {
    const normalized = relativePath.replaceAll("\\", "/").toLowerCase();
    return normalized.endsWith(".env") || normalized.includes(".local.") || normalized.includes(".private.") || normalized.includes("oslab.local.env");
  }

  private resolveAllowed(relativePath: string, roots: string[]): string {
    const normalized = this.normalizeRepositoryPath(relativePath);
    const target = path.resolve(this.root, normalized);
    const allowed = roots.some((root) => {
      const absoluteRoot = path.resolve(this.root, root);
      return target === absoluteRoot || target.startsWith(absoluteRoot + path.sep);
    });
    if (!allowed) {
      throw new BadRequestException("Path is outside allowed workspace roots");
    }
    return target;
  }

  private normalizeRepositoryPath(relativePath: string): string {
    if (!relativePath || path.isAbsolute(relativePath)) {
      throw new BadRequestException("Path must be repository-relative");
    }
    const normalized = relativePath.replaceAll("\\", "/").replace(/^\/+/, "");
    if (normalized.split("/").some((segment) => segment === "..")) {
      throw new BadRequestException("Path cannot include .. segments");
    }
    return normalized;
  }

  private enforceSafeAuthoringSegments(relativePath: string): void {
    for (const segment of relativePath.split("/")) {
      if (!segment) {
        throw new BadRequestException("Path cannot include empty segments");
      }
      if (/[\x00-\x1F\x7F]/.test(segment)) {
        throw new BadRequestException("Path cannot include control characters");
      }
      if (/[. ]$/.test(segment)) {
        throw new BadRequestException("Path segments cannot end with a dot or space");
      }
      const reservedBase = segment.split(".")[0]?.toUpperCase();
      if (WINDOWS_RESERVED_DEVICE_NAMES.has(reservedBase)) {
        throw new BadRequestException("Path cannot use Windows reserved device names");
      }
    }
  }

  private enforceTextAuthoringSize(content: string): void {
    const size = Buffer.byteLength(content ?? "", "utf8");
    if (size > TEXT_AUTHORING_MAX_BYTES) {
      throw new BadRequestException(`Authoring file is too large. Limit is ${TEXT_AUTHORING_MAX_BYTES} bytes.`);
    }
  }

  private authoringKindForPath(relativePath: string): AuthoringKind | null {
    for (const [kind, rule] of Object.entries(this.authoringRules) as Array<[AuthoringKind, AuthoringRule]>) {
      const root = rule.root.replaceAll("\\", "/");
      if (relativePath === root || relativePath.startsWith(`${root}/`)) return kind;
    }
    return null;
  }

  private resolveRunRoot(runId: string): string {
    if (!runId || runId.includes("/") || runId.includes("\\") || path.isAbsolute(runId)) {
      throw new BadRequestException("Invalid run id");
    }
    const direct = path.join(this.root, "runs", runId);
    if (existsSync(direct)) return direct;

    const runsRoot = path.join(this.root, "runs");
    try {
      for (const entry of readdirSync(runsRoot, { withFileTypes: true })) {
        if (!entry.isDirectory()) continue;
        const nested = path.join(runsRoot, entry.name, "scenarios", runId);
        if (existsSync(nested)) return nested;
      }
    } catch {
      // If runs/ is absent or unreadable, fall through to the direct path so callers return their usual not-found state.
    }
    return direct;
  }

  private async walk(root: string, extensions: Set<string>): Promise<string[]> {
    if (!(await this.exists(root))) return [];
    const results: string[] = [];
    const entries = await fs.readdir(root, { withFileTypes: true });
    for (const entry of entries) {
      const full = path.join(root, entry.name);
      if (entry.isDirectory()) {
        results.push(...(await this.walk(full, extensions)));
      } else if (extensions.has(path.extname(entry.name).toLowerCase()) && !entry.name.endsWith(".local.yaml")) {
        results.push(full);
      }
    }
    return results.sort();
  }

  private async walkArtifacts(root: string, extensions: Set<string>): Promise<string[]> {
    if (!(await this.exists(root))) return [];
    const results: string[] = [];
    const entries = await fs.readdir(root, { withFileTypes: true });
    for (const entry of entries) {
      const full = path.join(root, entry.name);
      if (entry.isDirectory()) {
        results.push(full);
        results.push(...(await this.walkArtifacts(full, extensions)));
      } else if (extensions.has(path.extname(entry.name).toLowerCase())) {
        results.push(full);
      }
    }
    return results.sort();
  }

  async exists(target: string): Promise<boolean> {
    try {
      await fs.access(target);
      return true;
    } catch {
      return false;
    }
  }

  private async runUpdatedAt(dir: string): Promise<string> {
    const candidates = [
      dir,
      path.join(dir, "run.json"),
      path.join(dir, "suite.json"),
      path.join(dir, "logs", "progress.jsonl"),
      path.join(dir, "logs", "progress.log"),
      path.join(dir, "reports", "result.json"),
      path.join(dir, "reports", "suite.json"),
    ];
    let newest = 0;
    for (const candidate of candidates) {
      try {
        const stat = await fs.stat(candidate);
        newest = Math.max(newest, stat.mtimeMs);
      } catch {
        // Optional artifacts are absent for skeleton and partial runs.
      }
    }
    return new Date(newest || Date.now()).toISOString();
  }
}

function findRepoRoot(start: string): string {
  let current = path.resolve(start);
  while (true) {
    if (existsSync(path.join(current, "pyproject.toml")) || existsSync(path.join(current, ".git"))) {
      return current;
    }
    const parent = path.dirname(current);
    if (parent === current) return path.resolve(start);
    current = parent;
  }
}

function existsSync(target: string): boolean {
  try {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    require("fs").accessSync(target);
    return true;
  } catch {
    return false;
  }
}

function runSummaryFields(payload: any) {
  return {
    scenarioId: asOptionalString(payload.scenarioId),
    scenarioPath: asOptionalString(payload.details?.scenarioPath),
    failureClass: asOptionalString(payload.failureClass),
    failureClasses: uniqueStrings([payload.failureClass]),
  };
}

function suiteSummaryFields(payload: any) {
  const entries = Array.isArray(payload.entries) ? payload.entries : [];
  const failedEntries = entries.filter((entry: any) => entry?.status === "failed");
  const requiredFailed = failedEntries.filter((entry: any) => !entry?.allowFailure);
  const allowedFailed = failedEntries.filter((entry: any) => entry?.allowFailure);
  return {
    suiteId: asOptionalString(payload.suiteId ?? payload.id),
    failureClass: asOptionalString(failedEntries.find((entry: any) => entry?.failureClass)?.failureClass),
    failureClasses: uniqueStrings(failedEntries.map((entry: any) => entry?.failureClass)),
    entries: entries.length,
    failedEntries: failedEntries.length,
    requiredFailed: payload.summary?.requiredFailed ?? requiredFailed.length,
    allowedFailed: payload.summary?.allowedFailed ?? allowedFailed.length,
  };
}

function asOptionalString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function uniqueStrings(values: unknown[]): string[] {
  return Array.from(new Set(values.filter((value): value is string => typeof value === "string" && Boolean(value.trim()))));
}
