import { BadRequestException, Inject, Injectable, NotFoundException } from "@nestjs/common";
import type { Job } from "@prisma/client";
import { ChildProcess, spawn } from "child_process";
import { EventEmitter } from "events";
import { createWriteStream, promises as fs } from "fs";
import path from "path";
import type { RunScenarioRequest, RunSuiteRequest } from "@oslab/shared";
import { PrismaService } from "../../infrastructure/prisma/prisma.service";
import { WorkspaceService } from "../../infrastructure/workspace/workspace.service";

@Injectable()
export class JobService {
  private readonly events = new EventEmitter();
  private readonly serviceStartedAt = new Date();
  private readonly activeJobIds = new Set<string>();
  private readonly activeChildren = new Map<string, ChildProcess>();
  private readonly cancelledJobIds = new Set<string>();
  private readonly staleRunAgeMs = 6 * 60 * 60 * 1000;

  constructor(
    @Inject(PrismaService) private readonly prisma: PrismaService,
    @Inject(WorkspaceService) private readonly workspace: WorkspaceService,
  ) {
    this.events.setMaxListeners(200);
  }

  async list() {
    await this.reconcileStaleJobs();
    return this.prisma.job.findMany({ orderBy: { createdAt: "desc" }, take: 100 });
  }

  async get(id: string) {
    const job = await this.prisma.job.findUnique({ where: { id } });
    if (!job) throw new NotFoundException("Job not found");
    return job;
  }

  async cancel(id: string) {
    const job = await this.get(id);
    if (job.status !== "queued" && job.status !== "running") {
      return job;
    }
    const child = this.activeChildren.get(id);
    if (!child?.pid) {
      await this.prisma.job.update({
        where: { id },
        data: {
          status: "cancelled",
          error: "Job was cancelled after the dashboard lost the live process handle.",
          completedAt: new Date(),
        },
      });
      this.events.emit("job-event", { jobId: id, type: "stderr", data: "Cancel requested by dashboard.\n" });
      this.events.emit("job-event", { jobId: id, type: "done", data: "cancelled" });
      return this.get(id);
    }
    this.cancelledJobIds.add(id);
    this.events.emit("job-event", { jobId: id, type: "stderr", data: "Cancel requested by dashboard.\n" });
    await terminateProcessTree(child.pid);
    return this.get(id);
  }

  async runScenario(request: RunScenarioRequest) {
    if (!request.scenarioPath) throw new BadRequestException("scenarioPath is required");
    const scenarioPath = this.workspace.relative(this.workspace.resolveReadable(request.scenarioPath));
    const artifactPath = await this.resolveArtifactPath(request);
    const command = this.buildRunCommand("run", scenarioPath, request, artifactPath);
    return this.startJob("scenario", scenarioPath, command, request.envFilePath);
  }

  async runSuite(request: RunSuiteRequest) {
    if (!request.suitePath) throw new BadRequestException("suitePath is required");
    const suitePath = this.workspace.relative(this.workspace.resolveReadable(request.suitePath));
    const artifactPath = await this.resolveArtifactPath(request);
    const command = this.buildRunCommand("suite-run", suitePath, request, artifactPath);
    return this.startJob("suite", suitePath, command, request.envFilePath);
  }

  async log(id: string) {
    const job = await this.get(id);
    if (!job.logPath) return "";
    try {
      return await fs.readFile(path.resolve(this.workspace.root, job.logPath), "utf8");
    } catch {
      return "";
    }
  }

  async decorateRunSummaries<T extends { id: string; status?: string | null; updatedAt?: string | null; startedAt?: string | null; completedAt?: string | null }>(summaries: T[]): Promise<T[]> {
    if (!summaries.length) return summaries;
    await this.reconcileStaleJobs();
    const latestJobs = await this.latestJobsByRunId(summaries.map((summary) => summary.id));
    return summaries
      .map((summary) => this.applyEffectiveRunStatus(summary, latestJobs.get(summary.id)))
      .sort((a, b) => String(b.updatedAt || "").localeCompare(String(a.updatedAt || "")));
  }

  async decorateRunDetail<T extends { status?: string | null; updatedAt?: string | null; startedAt?: string | null; completedAt?: string | null }>(runId: string, detail: T): Promise<T> {
    await this.reconcileStaleJobs();
    const job = await this.prisma.job.findFirst({ where: { runId }, orderBy: { createdAt: "desc" } });
    return this.applyEffectiveRunStatus({ ...detail, id: runId }, job);
  }

  subscribe(id: string, listener: (event: { type: string; data: string }) => void) {
    const handler = (event: { jobId: string; type: string; data: string }) => {
      if (event.jobId === id) listener({ type: event.type, data: event.data });
    };
    this.events.on("job-event", handler);
    return () => this.events.off("job-event", handler);
  }

  private async startJob(kind: string, title: string, command: string[], envFilePath?: string) {
    await fs.mkdir(path.join(this.workspace.root, ".web-data", "jobs"), { recursive: true });
    const commandText = command.map((part) => (part.includes(" ") ? `"${part}"` : part)).join(" ");
    const job = await this.prisma.job.create({
      data: {
        kind,
        title,
        status: "queued",
        command: commandText,
        cwd: this.workspace.root,
      },
    });
    const logPath = path.join(".web-data", "jobs", `${job.id}.log`);
    await this.prisma.job.update({ where: { id: job.id }, data: { logPath } });
    const redactor = await this.makeRedactor(envFilePath);
    queueMicrotask(() => this.spawnJob(job.id, command, logPath, redactor));
    return { ...(await this.get(job.id)), logPath };
  }

  private async spawnJob(jobId: string, command: string[], logPath: string, redact: (text: string) => string) {
    const snapshot = await this.prisma.job.findUnique({ where: { id: jobId } });
    if (snapshot?.status === "cancelled") {
      this.cancelledJobIds.delete(jobId);
      return;
    }
    this.activeJobIds.add(jobId);
    await this.prisma.job.update({ where: { id: jobId }, data: { status: "running", startedAt: new Date() } });
    const absoluteLog = path.resolve(this.workspace.root, logPath);
    const stream = createWriteStream(absoluteLog, { flags: "a", encoding: "utf8" });
    const child = spawn(command[0], command.slice(1), {
      cwd: this.workspace.root,
      windowsHide: true,
      shell: false,
      env: {
        ...process.env,
        PYTHONUNBUFFERED: "1",
        PYTHONIOENCODING: "utf-8",
      },
    });
    this.activeChildren.set(jobId, child);
    const emit = (type: string, chunk: Buffer | string) => {
      const text = redact(chunk.toString());
      stream.write(text);
      this.events.emit("job-event", { jobId, type, data: text });
    };
    child.stdout.on("data", (chunk) => emit("stdout", chunk));
    child.stderr.on("data", (chunk) => emit("stderr", chunk));
    child.on("error", async (error) => {
      this.activeJobIds.delete(jobId);
      this.activeChildren.delete(jobId);
      emit("stderr", String(error));
      stream.end();
      const completedAt = new Date();
      const runId = await this.extractRunId(logPath);
      await this.prisma.job.update({
        where: { id: jobId },
        data: {
          status: this.cancelledJobIds.has(jobId) ? "cancelled" : "failed",
          runId,
          error: String(error),
          completedAt,
        },
      });
      const finalStatus = this.cancelledJobIds.has(jobId) ? "cancelled" : "failed";
      if (runId) await this.patchRunArtifactStatus(runId, { status: finalStatus, completedAt, error: String(error), jobId });
      this.cancelledJobIds.delete(jobId);
      this.events.emit("job-event", { jobId, type: "done", data: finalStatus });
    });
    child.on("close", async (code) => {
      this.activeJobIds.delete(jobId);
      this.activeChildren.delete(jobId);
      stream.end();
      const status = this.cancelledJobIds.has(jobId) ? "cancelled" : code === 0 ? "passed" : "failed";
      const runId = await this.extractRunId(logPath);
      const completedAt = new Date();
      await this.prisma.job.update({
        where: { id: jobId },
        data: {
          status,
          exitCode: code ?? null,
          runId,
          completedAt,
          ...(status === "cancelled" ? { error: "Job was cancelled from the dashboard." } : {}),
        },
      });
      if (runId) {
        await this.patchRunArtifactStatus(runId, {
          status,
          completedAt,
          exitCode: code ?? null,
          error: status === "cancelled" ? "Job was cancelled from the dashboard." : undefined,
          jobId,
        });
      }
      this.cancelledJobIds.delete(jobId);
      this.events.emit("job-event", { jobId, type: "done", data: status });
    });
  }

  private async reconcileStaleJobs() {
    const staleJobs = await this.prisma.job.findMany({
      where: {
        status: { in: ["queued", "running"] },
        createdAt: { lt: this.serviceStartedAt },
      },
    });
    for (const job of staleJobs) {
      if (this.activeJobIds.has(job.id)) continue;
      const completedAt = new Date();
      await this.prisma.job.update({
        where: { id: job.id },
        data: {
          status: "failed",
          error: "Job was left running after API restart and is no longer attached to a live dashboard process.",
          completedAt,
        },
      });
      if (job.runId) {
        await this.patchRunArtifactStatus(job.runId, {
          status: "failed",
          completedAt,
          error: "Job was left running after API restart and is no longer attached to a live dashboard process.",
          jobId: job.id,
        });
      }
    }
  }

  private async latestJobsByRunId(runIds: string[]) {
    const latest = new Map<string, Job>();
    const jobs = await this.prisma.job.findMany({
      where: { runId: { in: runIds } },
      orderBy: { createdAt: "desc" },
    });
    for (const job of jobs) {
      if (job.runId && !latest.has(job.runId)) {
        latest.set(job.runId, job);
      }
    }
    return latest;
  }

  private applyEffectiveRunStatus<T extends { id?: string; status?: string | null; updatedAt?: string | null; startedAt?: string | null; completedAt?: string | null }>(run: T, job?: Job | null): T {
    const artifactStatus = normalizeStatus(run.status);
    let status = artifactStatus || "unknown";
    let reason = "";
    let source: "artifact" | "job" | "stale-timeout" = "artifact";
    const result: Record<string, unknown> = { ...run };

    if (job && isTerminalStatus(job.status) && isActiveStatus(artifactStatus)) {
      status = job.status;
      source = "job";
      reason = `Run artifact still says ${artifactStatus}, but dashboard job ${job.id} is ${job.status}.`;
    } else if (!job && isActiveStatus(artifactStatus) && isStaleRun(run, this.staleRunAgeMs)) {
      status = "stale";
      source = "stale-timeout";
      reason = "Run artifact is still active, but no matching live dashboard job exists and the artifact is older than the stale threshold.";
    }

    if (job) {
      result["jobId"] = job.id;
      result["jobStatus"] = job.status;
      if (!result["startedAt"] && job.startedAt) result["startedAt"] = job.startedAt.toISOString();
      if (!result["completedAt"] && job.completedAt) result["completedAt"] = job.completedAt.toISOString();
      const jobUpdatedAt = (job.completedAt || job.startedAt || job.createdAt)?.toISOString();
      if (jobUpdatedAt && (!result["updatedAt"] || jobUpdatedAt > String(result["updatedAt"]))) {
        result["updatedAt"] = jobUpdatedAt;
      }
    }

    if (status !== artifactStatus) {
      result["status"] = status;
      result["artifactStatus"] = artifactStatus || "unknown";
      result["statusMeta"] = {
        source,
        reason,
        artifactStatus: artifactStatus || "unknown",
        effectiveStatus: status,
        jobId: job?.id ?? null,
        jobStatus: job?.status ?? null,
      };
    }

    return result as T;
  }

  private async patchRunArtifactStatus(runId: string, patch: { status: string; completedAt: Date; exitCode?: number | null; error?: string; jobId: string }) {
    for (const fileName of ["run.json", "suite.json"]) {
      const target = this.workspace.resolveRunFile(runId, fileName);
      const exists = await this.workspace.exists(target);
      if (!exists) continue;
      try {
        const payload = JSON.parse(await fs.readFile(target, "utf8"));
        if (!isActiveStatus(normalizeStatus(payload.status))) return;
        payload.status = patch.status;
        payload.completedAt = payload.completedAt ?? patch.completedAt.toISOString();
        if (patch.error) payload.error = payload.error ?? patch.error;
        payload.details = {
          ...(payload.details || {}),
          dashboardJob: {
            id: patch.jobId,
            status: patch.status,
            exitCode: patch.exitCode ?? null,
            completedAt: patch.completedAt.toISOString(),
          },
        };
        await fs.writeFile(target, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
      } catch {
        return;
      }
      return;
    }
  }

  private buildRunCommand(kind: "run" | "suite-run", definitionPath: string, request: RunScenarioRequest | RunSuiteRequest, artifactPath?: string): string[] {
    if (kind === "suite-run" && !artifactPath) throw new BadRequestException("artifactPath is required for suite execution");
    const command = ["uv", "run", "oslab", kind];
    if (kind === "run") command.push("--scenario", definitionPath);
    else command.push("--suite", definitionPath);
    if (request.configPath) command.push("--config", this.safeConfigPath(request.configPath));
    if (request.envFilePath) command.push("--env-file", this.safeEnvPath(request.envFilePath));
    if (request.runId) command.push("--run-id", request.runId);
    if (artifactPath) command.push("--artifact-path", artifactPath);
    if (request.keepVm) command.push("--keep-vm");
    if (request.fullClone) command.push("--full-clone");
    const timeouts = request.timeouts ?? {};
    if (timeouts.boot) command.push("--boot-timeout-seconds", String(timeouts.boot));
    if (timeouts.guest) command.push("--guest-timeout-seconds", String(timeouts.guest));
    if (timeouts.command) command.push("--command-timeout-seconds", String(timeouts.command));
    if (timeouts.pollInterval) command.push("--poll-interval-seconds", String(timeouts.pollInterval));
    if (kind === "suite-run" && "maxParallel" in request && request.maxParallel) {
      command.push("--max-parallel", String(request.maxParallel));
    }
    return command;
  }

  private async resolveArtifactPath(request: RunScenarioRequest | RunSuiteRequest): Promise<string | undefined> {
    if (request.uploadedArtifactId) {
      const upload = await this.prisma.artifactUpload.findUnique({ where: { id: request.uploadedArtifactId } });
      if (!upload) throw new BadRequestException("uploadedArtifactId does not exist");
      return upload.path;
    }
    const artifactPath = request.artifactPath?.trim();
    return artifactPath || undefined;
  }

  private safeEnvPath(envPath: string): string {
    if (path.isAbsolute(envPath)) throw new BadRequestException("envFilePath must be repository-relative");
    const resolved = path.resolve(this.workspace.root, envPath);
    if (!resolved.startsWith(path.resolve(this.workspace.root, "config") + path.sep)) {
      throw new BadRequestException("envFilePath must live under config/");
    }
    return envPath;
  }

  private safeConfigPath(configPath: string): string {
    if (path.isAbsolute(configPath)) throw new BadRequestException("configPath must be repository-relative");
    const resolved = path.resolve(this.workspace.root, configPath);
    const configRoot = path.resolve(this.workspace.root, "config");
    if (!resolved.startsWith(configRoot + path.sep)) {
      throw new BadRequestException("configPath must live under config/");
    }
    if (!configPath.endsWith(".yaml") && !configPath.endsWith(".yml") && !configPath.endsWith(".json")) {
      throw new BadRequestException("configPath must be a YAML or JSON file");
    }
    return configPath;
  }

  private async makeRedactor(envFilePath?: string) {
    const secrets: string[] = [];
    if (envFilePath) {
      try {
        const content = await fs.readFile(path.resolve(this.workspace.root, envFilePath), "utf8");
        for (const line of content.split(/\r?\n/)) {
          const [key, ...rest] = line.split("=");
          const value = rest.join("=").trim().replace(/^['"]|['"]$/g, "");
          if (value && /SECRET|TOKEN|PASSWORD|SABUN|SERVER_URL/i.test(key)) secrets.push(value);
        }
      } catch {
        // The spawned oslab process will surface missing env file errors.
      }
    }
    return (text: string) => secrets.reduce((result, secret) => result.split(secret).join("<redacted>"), text);
  }

  private async extractRunId(logPath: string): Promise<string | null> {
    const content = await fs.readFile(path.resolve(this.workspace.root, logPath), "utf8").catch(() => "");
    const matches = [...content.matchAll(/runId:\s*([^\s]+)/g)];
    if (matches.length) return matches[matches.length - 1][1];
    const skeleton = content.match(/skeleton run complete:\s*([^\s]+)/);
    return skeleton?.[1] ?? null;
  }
}

async function terminateProcessTree(pid: number): Promise<void> {
  await new Promise<void>((resolve, reject) => {
    const child = spawn("taskkill", ["/PID", String(pid), "/T", "/F"], {
      windowsHide: true,
      shell: false,
    });
    child.on("error", reject);
    child.on("close", (code) => {
      if (code === 0 || code === 128) {
        resolve();
        return;
      }
      reject(new Error(`taskkill exited with code ${code}`));
    });
  });
}

function normalizeStatus(status: unknown): string {
  return String(status || "").trim().toLowerCase();
}

function isActiveStatus(status: string): boolean {
  return status === "queued" || status === "running" || status === "pending" || status === "in_progress";
}

function isTerminalStatus(status: string): boolean {
  return status === "passed" || status === "failed" || status === "cancelled";
}

function isStaleRun(run: { updatedAt?: string | null; startedAt?: string | null }, staleRunAgeMs: number): boolean {
  const timestamp = Date.parse(String(run.updatedAt || run.startedAt || ""));
  if (Number.isNaN(timestamp)) return false;
  return Date.now() - timestamp > staleRunAgeMs;
}
