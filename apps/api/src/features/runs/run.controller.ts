import { BadRequestException, Controller, Get, Inject, NotFoundException, Param, Query, Res, UseGuards } from "@nestjs/common";
import type { Response } from "express";
import { promises as fs } from "fs";
import path from "path";
import type { RunEvidenceChecklist, RunEvidenceGroup, RunEvidenceItem, RunEvidenceStatus, RunFileGroup, RunFileItem } from "@oslab/shared";
import { AuthGuard } from "../../common/guards/auth.guard";
import { WorkspaceService } from "../../infrastructure/workspace/workspace.service";
import { JobService } from "../jobs/job.service";

interface EvidenceSpec {
  key: string;
  label: string;
  group: RunEvidenceGroup;
  relativePath?: string;
  required: boolean;
  description: string;
  status?: RunEvidenceStatus;
  reason?: string;
}

const previewableRunFilePattern = /\.(json|jsonl|log|xml|html?|txt|csv|md|yaml|yml|ps1|sh|cmd|bat)$/i;
const runFileGroupOrder: Record<RunFileGroup, number> = {
  core: 0,
  timeline: 1,
  outputs: 2,
  reports: 3,
  cleanup: 4,
  other: 5,
};

@Controller("api/runs")
@UseGuards(AuthGuard)
export class RunController {
  constructor(
    @Inject(WorkspaceService) private readonly workspace: WorkspaceService,
    @Inject(JobService) private readonly jobs: JobService,
  ) {}

  @Get()
  async list() {
    const summaries = await this.jobs.decorateRunSummaries(await this.workspace.listRuns());
    return Promise.all(summaries.map(async (summary) => {
      const loaded = await this.loadDetail(summary.id).catch(() => null);
      if (!loaded) return summary;
      const evidence = await buildEvidence(loaded.dir, loaded.kind, loaded.detail);
      return { ...summary, evidenceSummary: summarizeEvidence(evidence) };
    }));
  }

  @Get(":runId")
  async get(@Param("runId") runId: string) {
    const loaded = await this.loadDetail(runId);
    const detail = await this.jobs.decorateRunDetail(runId, loaded.detail);
    const evidence = await buildEvidence(loaded.dir, loaded.kind, detail);
    return { ...detail, evidence, files: await listRunFiles(loaded.dir, evidence.items) };
  }

  @Get(":runId/evidence")
  async evidence(@Param("runId") runId: string) {
    const loaded = await this.loadDetail(runId);
    return buildEvidence(loaded.dir, loaded.kind, loaded.detail);
  }

  @Get(":runId/file")
  async file(@Param("runId") runId: string, @Query("path") relativePath: string, @Res() response: Response) {
    if (!relativePath) {
      throw new BadRequestException("Run file path is required");
    }
    const target = this.workspace.resolveRunFile(runId, relativePath);
    const stat = await fs.stat(target).catch(() => null);
    if (!stat?.isFile()) {
      throw new NotFoundException("Run file not found");
    }
    const ext = path.extname(target).toLowerCase();
    if (ext === ".html") response.type("text/html");
    else if (ext === ".json") response.type("application/json");
    else if (ext === ".xml") response.type("application/xml");
    else response.type("text/plain");
    response.send(await fs.readFile(target));
  }

  private async loadDetail(runId: string): Promise<{ dir: string; kind: "run" | "suite"; detail: any }> {
    const dir = this.workspace.resolveRunFile(runId);
    const parentRunId = parentRunIdForDir(this.workspace, dir);
    const suiteJson = path.join(dir, "suite.json");
    const runJson = path.join(dir, "run.json");
    if (await this.workspace.exists(suiteJson)) {
      const detail = JSON.parse(await fs.readFile(suiteJson, "utf8"));
      return { dir, kind: "suite", detail: parentRunId ? { ...detail, parentRunId, parentSuiteRunId: parentRunId } : detail };
    }
    if (await this.workspace.exists(runJson)) {
      const detail = JSON.parse(await fs.readFile(runJson, "utf8"));
      return { dir, kind: "run", detail: parentRunId ? { ...detail, parentRunId, parentSuiteRunId: parentRunId } : detail };
    }
    return { dir, kind: "run", detail: { id: runId, status: "unknown", ...(parentRunId ? { parentRunId, parentSuiteRunId: parentRunId } : {}) } };
  }
}

function summarizeEvidence(checklist: RunEvidenceChecklist) {
  return {
    total: checklist.total,
    present: checklist.present,
    missingRequired: checklist.missingRequired,
    contractGaps: checklist.contractGaps,
  };
}

function parentRunIdForDir(workspace: WorkspaceService, dir: string): string | null {
  const relative = workspace.relative(dir);
  const parts = relative.split("/");
  if (parts.length >= 4 && parts[0] === "runs" && parts[2] === "scenarios") {
    return parts[1] || null;
  }
  return null;
}

async function buildEvidence(dir: string, kind: "run" | "suite", detail: any): Promise<RunEvidenceChecklist> {
  const specs = kind === "suite" ? suiteEvidenceSpecs() : runEvidenceSpecs(detail);
  const items = await Promise.all(specs.map(async (spec): Promise<RunEvidenceItem> => {
    if (!spec.relativePath || spec.status === "notApplicable") {
      return {
        key: spec.key,
        label: spec.label,
        group: spec.group,
        relativePath: spec.relativePath,
        required: spec.required,
        status: spec.status ?? "notApplicable",
        size: null,
        modifiedAt: null,
        reason: spec.reason,
        description: spec.description,
        previewable: false,
      };
    }
    const target = path.join(dir, spec.relativePath);
    try {
      const stat = await fs.stat(target);
      return evidenceItem(spec, "present", stat.isFile() ? stat.size : null, stat.mtime.toISOString());
    } catch {
      return evidenceItem(spec, spec.required ? "contractGap" : "missing", null, null);
    }
  }));
  const applicable = items.filter((item) => item.status !== "notApplicable");
  return {
    total: applicable.length,
    present: applicable.filter((item) => item.status === "present").length,
    missingRequired: applicable.filter((item) => item.required && item.status === "contractGap").length,
    contractGaps: applicable.filter((item) => item.status === "contractGap").length,
    items,
  };
}

function evidenceItem(spec: EvidenceSpec, status: RunEvidenceStatus, size: number | null, modifiedAt: string | null): RunEvidenceItem {
  return {
    key: spec.key,
    label: spec.label,
    group: spec.group,
    relativePath: spec.relativePath,
    required: spec.required,
    status,
    size,
    modifiedAt,
    reason: spec.reason,
    description: spec.description,
    previewable: Boolean(spec.relativePath && previewableRunFilePattern.test(spec.relativePath)),
  };
}

async function listRunFiles(dir: string, evidenceItems: RunEvidenceItem[]): Promise<RunFileItem[]> {
  const evidenceByPath = new Map<string, RunEvidenceItem>();
  for (const item of evidenceItems) {
    const relativePath = normalizeRunPath(item.relativePath);
    if (relativePath) evidenceByPath.set(relativePath, item);
  }
  const knownPaths = new Set(
    evidenceItems
      .map((item) => normalizeRunPath(item.relativePath))
      .filter((relativePath): relativePath is string => Boolean(relativePath)),
  );
  const files = await walkRunFiles(dir);
  const items = await Promise.all(files.map(async (absolutePath): Promise<RunFileItem | null> => {
    const relativePath = normalizeRunPath(path.relative(dir, absolutePath));
    if (!relativePath) return null;
    const stat = await fs.stat(absolutePath).catch(() => null);
    if (!stat?.isFile()) return null;
    const evidence = evidenceByPath.get(relativePath);
    return {
      label: evidence?.label ?? path.basename(relativePath),
      group: evidence?.group ?? inferRunFileGroup(relativePath),
      relativePath,
      status: "present",
      required: Boolean(evidence?.required),
      size: stat.size,
      modifiedAt: stat.mtime.toISOString(),
      previewable: previewableRunFilePattern.test(relativePath),
      discovered: !knownPaths.has(relativePath),
      reason: evidence?.reason,
      description: evidence?.description,
    };
  }));
  const presentPaths = new Set(items.map((item) => item?.relativePath).filter(Boolean));
  const expectedMissingItems = evidenceItems
    .filter((item) => item.relativePath && (item.status === "missing" || item.status === "contractGap"))
    .filter((item) => !presentPaths.has(normalizeRunPath(item.relativePath) ?? ""))
    .map((item): RunFileItem => ({
      label: item.label,
      group: item.group,
      relativePath: normalizeRunPath(item.relativePath) ?? item.relativePath!,
      status: item.status,
      required: item.required,
      size: null,
      modifiedAt: null,
      previewable: false,
      discovered: false,
      reason: item.reason,
      description: item.description,
    }));
  return items
    .filter((item): item is RunFileItem => Boolean(item))
    .concat(expectedMissingItems)
    .sort((a, b) => {
      const groupDelta = runFileGroupOrder[a.group] - runFileGroupOrder[b.group];
      if (groupDelta) return groupDelta;
      return a.relativePath.localeCompare(b.relativePath);
    });
}

async function walkRunFiles(dir: string): Promise<string[]> {
  const entries = await fs.readdir(dir, { withFileTypes: true }).catch(() => []);
  const files: string[] = [];
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...(await walkRunFiles(fullPath)));
    } else if (entry.isFile()) {
      files.push(fullPath);
    }
  }
  return files;
}

function inferRunFileGroup(relativePath: string): RunFileGroup {
  if (relativePath === "run.json" || relativePath === "suite.json") return "core";
  if (relativePath.startsWith("logs/")) return "timeline";
  if (relativePath.startsWith("raw/") || relativePath.startsWith("normalized/")) return "outputs";
  if (relativePath.startsWith("reports/")) return "reports";
  if (relativePath.startsWith("cleanup/")) return "cleanup";
  return "other";
}

function normalizeRunPath(value?: string): string | null {
  if (!value) return null;
  const normalized = value.replaceAll("\\", "/").replace(/^\/+/, "");
  return normalized || null;
}

function suiteEvidenceSpecs(): EvidenceSpec[] {
  return [
    { key: "suite-json", label: "suite.json", group: "core", relativePath: "suite.json", required: true, description: "Suite aggregate contract" },
    { key: "suite-html", label: "suite.html", group: "reports", relativePath: "reports/suite.html", required: false, description: "Human-readable suite report" },
    { key: "suite-junit", label: "suite.junit.xml", group: "reports", relativePath: "reports/suite.junit.xml", required: false, description: "CI-compatible suite report" },
    { key: "suite-child-evidence", label: "Child run evidence", group: "outputs", required: false, status: "notApplicable", reason: "Child evidence drill-down is not part of this MVP.", description: "Per-entry evidence is available through each child run result." },
  ];
}

function runEvidenceSpecs(detail: any): EvidenceSpec[] {
  const reportFormats = new Set<string>(Array.isArray(detail?.details?.reportFormats) ? detail.details.reportFormats : []);
  const isSkeleton = detail?.details?.mode === "skeleton";
  const outputs = detail?.details?.outputs ?? {};
  const normalizedPath = String(outputs.normalized || "").replaceAll("\\", "/");
  const rawPath = String(outputs.raw || "").replaceAll("\\", "/");
  const hasRawContract = Boolean(rawPath) || detail?.details?.mode === "artifact";
  const expectsInventory = normalizedPath.endsWith("normalized/inventory.json") || normalizedPath.endsWith("inventory.json");
  const expectsCommandResult = normalizedPath.endsWith("normalized/command-result.json") || normalizedPath.endsWith("command-result.json");
  const specs: EvidenceSpec[] = [
    { key: "run-json", label: "run.json", group: "core", relativePath: "run.json", required: true, description: "Run summary and machine-readable contract" },
    { key: "result-json", label: "result.json", group: "reports", relativePath: "reports/result.json", required: true, description: "Report payload used by dashboard and automation" },
  ];

  specs.push(
    isSkeleton
      ? { key: "progress-jsonl", label: "progress.jsonl", group: "timeline", required: false, status: "notApplicable", reason: "Skeleton runs do not emit guest progress events.", description: "Structured execution timeline" }
      : { key: "progress-jsonl", label: "progress.jsonl", group: "timeline", relativePath: "logs/progress.jsonl", required: true, description: "Structured execution timeline" },
    isSkeleton
      ? { key: "progress-log", label: "progress.log", group: "timeline", required: false, status: "notApplicable", reason: "Skeleton runs do not emit guest progress logs.", description: "Human-readable progress log" }
      : { key: "progress-log", label: "progress.log", group: "timeline", relativePath: "logs/progress.log", required: false, description: "Human-readable progress log" },
    isSkeleton
      ? { key: "actual-output", label: "actual-output.json", group: "outputs", required: false, status: "notApplicable", reason: "Skeleton runs have no product output.", description: "Raw collected product output" }
      : { key: "actual-output", label: "actual-output.json", group: "outputs", relativePath: "raw/actual-output.json", required: hasRawContract, description: "Raw collected product output" },
    expectsInventory
      ? { key: "inventory-json", label: "inventory.json", group: "outputs", relativePath: "normalized/inventory.json", required: true, description: "Normalized inventory output" }
      : { key: "inventory-json", label: "inventory.json", group: "outputs", relativePath: "normalized/inventory.json", required: false, description: "Normalized inventory output" },
    expectsCommandResult
      ? { key: "command-result", label: "command-result.json", group: "outputs", relativePath: "normalized/command-result.json", required: true, description: "Normalized command result output" }
      : { key: "command-result", label: "command-result.json", group: "outputs", relativePath: "normalized/command-result.json", required: false, description: "Normalized command result output" },
    { key: "product-steps", label: "product-steps.json", group: "outputs", relativePath: "raw/product-steps.json", required: false, description: "Product step detail payload" },
    { key: "stdout-log", label: "stdout.log", group: "outputs", relativePath: "logs/product.stdout.log", required: false, description: "Product stdout sidecar" },
    { key: "stderr-log", label: "stderr.log", group: "outputs", relativePath: "logs/product.stderr.log", required: false, description: "Product stderr sidecar" },
    { key: "inventory-analysis", label: "inventory.analysis.json", group: "reports", relativePath: "reports/inventory.analysis.json", required: expectsInventory, description: "Inventory quality analysis" },
    cleanupEvidenceSpec(detail),
  );

  if (reportFormats.has("html")) {
    specs.push({ key: "result-html", label: "result.html", group: "reports", relativePath: "reports/result.html", required: true, description: "Human-readable run report" });
  }
  if (reportFormats.has("junit")) {
    specs.push({ key: "result-junit", label: "result.junit.xml", group: "reports", relativePath: "reports/result.junit.xml", required: true, description: "CI-compatible run report" });
  }
  return specs;
}

function cleanupEvidenceSpec(detail: any): EvidenceSpec {
  const vm = detail?.details?.vm ?? {};
  if (detail?.details?.mode === "skeleton") {
    return { key: "cleanup-state", label: "Cleanup state", group: "cleanup", required: true, status: "present", reason: "Skeleton run did not create a VM.", description: "VM cleanup contract" };
  }
  if (vm.destroyed === true) {
    return { key: "cleanup-state", label: "Cleanup state", group: "cleanup", required: true, status: "present", reason: `VM ${vm.id ?? "<unknown>"} was destroyed.`, description: "VM cleanup contract" };
  }
  if (vm.kept === true) {
    return { key: "cleanup-state", label: "Cleanup state", group: "cleanup", required: true, status: "missing", reason: `VM ${vm.id ?? "<unknown>"} was intentionally kept.`, description: "VM cleanup contract" };
  }
  return { key: "cleanup-state", label: "Cleanup state", group: "cleanup", required: true, status: "contractGap", reason: "No destroyed/kept cleanup state was recorded.", description: "VM cleanup contract" };
}
