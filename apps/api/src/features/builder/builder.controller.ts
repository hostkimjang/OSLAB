import { BadRequestException, Body, Controller, Inject, Post, UseGuards } from "@nestjs/common";
import YAML from "yaml";
import { AuthGuard } from "../../common/guards/auth.guard";
import { WorkspaceService } from "../../infrastructure/workspace/workspace.service";
import {
  FixtureTemplateDto,
  InspectBuilderDto,
  RenderScenarioDto,
  RenderSuiteDto,
  ScenarioTemplateDto,
  SuiteTemplateDto,
  type ScenarioAssertionModel,
  type ScenarioBuilderModel,
  type ScenarioFixtureModel,
  type ScenarioProductStepModel,
  type SuiteBuilderModel,
} from "./dto/builder.dto";

@Controller("api/build")
@UseGuards(AuthGuard)
export class BuilderController {
  constructor(@Inject(WorkspaceService) private readonly workspace: WorkspaceService) {}

  @Post("scenario/template")
  scenarioTemplate(@Body() body: ScenarioTemplateDto) {
    const id = sanitizeScenarioId(body.id || defaultTemplateId(body.kind));
    const osFamily = body.kind === "linux-basic" ? "linux" : "windows";
    const path = this.safeAuthoringPath(sanitizeScenarioPath(body.path || defaultScenarioPath(osFamily, id)), "scenario");
    const name = body.name?.trim() || defaultTemplateName(body.kind, id);
    const content = YAML.stringify(buildScenarioTemplate(body.kind, id, name), { lineWidth: 0 });
    return { ok: true, path, content };
  }

  @Post("fixture/template")
  fixtureTemplate(@Body() body: FixtureTemplateDto) {
    const id = sanitizeFileStem(body.id || "new-fixture");
    const kind = body.kind === "shell" || body.kind === "linux-shell" ? "shell" : "powershell";
    const path = this.safeAuthoringPath(body.path || defaultFixturePath(kind, id), "fixture");
    const content = kind === "shell" ? buildShellFixtureTemplate() : buildPowerShellFixtureTemplate();
    return { ok: true, path, content };
  }

  @Post("suite/template")
  suiteTemplate(@Body() body: SuiteTemplateDto) {
    const id = sanitizeScenarioId(body.id || "new.suite");
    const path = this.safeAuthoringPath(body.path || defaultSuitePath(id), "suite");
    const name = body.name?.trim() || id;
    const scenarioPaths = normalizeSuiteScenarioPaths(body);
    const maxParallel = normalizePositiveInteger(body.maxParallel, 1);
    const content = YAML.stringify(
      buildSuiteTemplate(id, name, scenarioPaths, {
        kind: body.kind,
        tier: body.tier,
        allowFailure: body.allowFailure,
        enabled: body.enabled,
        maxParallel,
      }),
      { lineWidth: 0 },
    );
    return { ok: true, path, content };
  }

  @Post("scenario/inspect")
  inspectScenario(@Body() body: InspectBuilderDto) {
    const parsed = parseYamlContent(body.content);
    const artifact = parsed.artifact ?? {};
    const artifactCommand = artifact.command ?? {};
    const outputsActual = parsed.outputs?.actual ?? {};
    const cleanup = parsed.cleanup ?? {};
    const fixtures = Array.isArray(parsed.fixtures) ? parsed.fixtures.map(toFixtureModel) : [];
    const productSteps = Array.isArray(parsed.product?.steps) ? parsed.product.steps.map(toProductStepModel) : [];
    const assertions = Array.isArray(parsed.assertions) ? parsed.assertions.map(toAssertionModel) : [];
    const model: ScenarioBuilderModel = {
      schemaVersion: Number(parsed.schemaVersion ?? 1),
      id: String(parsed.id ?? ""),
      name: String(parsed.name ?? ""),
      osFamily: String(parsed.os?.family ?? ""),
      osVersion: String(parsed.os?.version ?? ""),
      template: String(parsed.provider?.template ?? ""),
      templateVmId: asNumberOrNull(parsed.provider?.templateVmId),
      vmIdStart: asNumberOrNull(parsed.provider?.vmIdRange?.start),
      vmIdEnd: asNumberOrNull(parsed.provider?.vmIdRange?.end),
      guestMode: String(parsed.guest?.mode ?? ""),
      windowsOrder: asStringArray(parsed.guest?.windowsOrder),
      linuxOrder: asStringArray(parsed.guest?.linuxOrder),
      artifactType: String(artifact.type ?? ""),
      artifactPathParam: String(artifact.pathParam ?? ""),
      artifactDestination: String(artifact.destination ?? ""),
      artifactTransfer: String(artifact.transfer ?? ""),
      artifactCommand: {
        shell: String(artifactCommand.shell ?? ""),
        template: String(artifactCommand.template ?? ""),
      },
      outputActualPath: String(outputsActual.path ?? ""),
      outputActualAdapter: String(outputsActual.adapter ?? ""),
      reportFormats: Array.isArray(parsed.reports?.formats) ? parsed.reports.formats.map(String) : [],
      cleanupDestroyVm: typeof cleanup.destroyVm === "boolean" ? cleanup.destroyVm : true,
      cleanupKeepVmOnFailure: typeof cleanup.keepVmOnFailure === "boolean" ? cleanup.keepVmOnFailure : false,
      fixtures,
      productSteps,
      assertions,
      fixtureCount: fixtures.length,
      assertionCount: assertions.length,
    };
    return { ok: true, model };
  }

  @Post("scenario/render")
  renderScenario(@Body() body: RenderScenarioDto) {
    const parsed = parseYamlContent(body.content);
    const model = body.model;
    parsed.schemaVersion = numberOrDefault(model.schemaVersion, 1);
    parsed.id = model.id || parsed.id || "";
    parsed.name = model.name || "";
    parsed.os = {
      ...(parsed.os ?? {}),
      family: model.osFamily || "windows",
      version: model.osVersion || "",
    };
    parsed.provider = {
      ...(parsed.provider ?? {}),
      template: model.template || "",
      templateVmId: model.templateVmId ?? null,
      vmIdRange: {
        ...(parsed.provider?.vmIdRange ?? {}),
        start: model.vmIdStart ?? null,
        end: model.vmIdEnd ?? null,
      },
    };
    parsed.guest = {
      ...(parsed.guest ?? {}),
      mode: model.guestMode || "auto",
    };
    if (Array.isArray(model.windowsOrder) && model.windowsOrder.length) {
      parsed.guest.windowsOrder = model.windowsOrder.filter(Boolean);
    } else {
      delete parsed.guest.windowsOrder;
    }
    if (Array.isArray(model.linuxOrder) && model.linuxOrder.length) {
      parsed.guest.linuxOrder = model.linuxOrder.filter(Boolean);
    } else {
      delete parsed.guest.linuxOrder;
    }
    parsed.artifact = {
      ...(parsed.artifact ?? {}),
      type: model.artifactType || "folder",
      pathParam: model.artifactPathParam || "artifactPath",
      destination: model.artifactDestination || "",
    };
    if (model.artifactTransfer) parsed.artifact.transfer = model.artifactTransfer;
    else delete parsed.artifact.transfer;
    if (model.artifactCommand?.shell || model.artifactCommand?.template) {
      parsed.artifact.command = {
        shell: model.artifactCommand.shell || "powershell",
        template: model.artifactCommand.template || "",
      };
    } else {
      delete parsed.artifact.command;
    }
    parsed.outputs = {
      ...(parsed.outputs ?? {}),
      actual: {
        ...(parsed.outputs?.actual ?? {}),
        path: model.outputActualPath || "",
        adapter: model.outputActualAdapter || "",
      },
    };
    parsed.reports = {
      ...(parsed.reports ?? {}),
      formats: Array.isArray(model.reportFormats) ? model.reportFormats.filter(Boolean) : [],
    };
    parsed.cleanup = {
      ...(parsed.cleanup ?? {}),
      destroyVm: Boolean(model.cleanupDestroyVm),
      keepVmOnFailure: Boolean(model.cleanupKeepVmOnFailure),
    };
    parsed.fixtures = (Array.isArray(model.fixtures) ? model.fixtures : [])
      .filter((fixture) => fixture.id || fixture.source)
      .map(fromFixtureModel);
    const productSteps = (Array.isArray(model.productSteps) ? model.productSteps : [])
      .filter((step) => step.id || step.template)
      .map(fromProductStepModel);
    if (productSteps.length) {
      parsed.product = { ...(parsed.product ?? {}), steps: productSteps };
    } else if (parsed.product?.steps) {
      delete parsed.product.steps;
    }
    parsed.assertions = (Array.isArray(model.assertions) ? model.assertions : [])
      .filter((assertion) => assertion.id || assertion.type || assertion.bodyJson)
      .map(fromAssertionModel);
    return {
      ok: true,
      content: YAML.stringify(parsed, { lineWidth: 0 }),
    };
  }

  @Post("suite/inspect")
  inspectSuite(@Body() body: InspectBuilderDto) {
    const parsed = parseYamlContent(body.content);
    const model: SuiteBuilderModel = {
      schemaVersion: Number(parsed.schemaVersion ?? 1),
      id: String(parsed.id ?? ""),
      name: String(parsed.name ?? ""),
      maxParallel: asNumberOrNull(parsed.maxParallel),
      runs: Array.isArray(parsed.runs)
        ? parsed.runs.map((entry: any) => ({
            id: String(entry?.id ?? ""),
            scenario: String(entry?.scenario ?? ""),
            tier: String(entry?.tier ?? ""),
            allowFailure: Boolean(entry?.allowFailure),
            enabled: typeof entry?.enabled === "boolean" ? entry.enabled : true,
          }))
        : [],
    };
    return { ok: true, model };
  }

  @Post("suite/render")
  renderSuite(@Body() body: RenderSuiteDto) {
    const parsed = parseYamlContent(body.content);
    const model = body.model;
    parsed.schemaVersion = numberOrDefault(model.schemaVersion, 1);
    parsed.id = model.id || parsed.id || "";
    parsed.name = model.name || "";
    if (model.maxParallel && Number.isFinite(model.maxParallel) && model.maxParallel >= 1) {
      parsed.maxParallel = Math.floor(model.maxParallel);
    } else {
      delete parsed.maxParallel;
    }
    parsed.runs = Array.isArray(model.runs)
      ? model.runs
          .filter((entry) => entry.id || entry.scenario)
          .map((entry) => ({
            id: entry.id || deriveSuiteEntryId(entry.scenario),
            scenario: entry.scenario,
            ...(entry.tier ? { tier: entry.tier } : {}),
            ...(entry.allowFailure ? { allowFailure: true } : {}),
            enabled: entry.enabled !== false,
          }))
      : [];
    return {
      ok: true,
      content: YAML.stringify(parsed, { lineWidth: 0 }),
    };
  }

  private safeAuthoringPath(relativePath: string, expectedKind: "scenario" | "suite" | "fixture"): string {
    const policy = this.workspace.enforceAuthoringPolicy(relativePath, "create");
    if (policy.kind !== expectedKind) {
      throw new BadRequestException(`Path must be a ${expectedKind} authoring path`);
    }
    return relativePath.replaceAll("\\", "/").replace(/^\/+/, "");
  }
}

function toFixtureModel(fixture: any): ScenarioFixtureModel {
  return {
    id: String(fixture?.id ?? ""),
    type: String(fixture?.type ?? ""),
    source: String(fixture?.source ?? ""),
    expectedOutput: String(fixture?.expectedOutput ?? ""),
  };
}

function fromFixtureModel(fixture: ScenarioFixtureModel) {
  return {
    id: fixture.id || "",
    type: fixture.type || "powershell",
    source: fixture.source || "",
    ...(fixture.expectedOutput ? { expectedOutput: fixture.expectedOutput } : {}),
  };
}

function toProductStepModel(step: any): ScenarioProductStepModel {
  return {
    id: String(step?.id ?? ""),
    shell: String(step?.command?.shell ?? ""),
    template: String(step?.command?.template ?? ""),
    captureStdoutJson: Boolean(step?.captureStdoutJson),
    expectStdoutJsonJson: stringifyEditorJson(step?.expectStdoutJson ?? {}),
    secretTokensJson: stringifyEditorJson(step?.secretTokens ?? {}),
  };
}

function fromProductStepModel(step: ScenarioProductStepModel) {
  const result: any = {
    id: step.id || "",
    command: {
      shell: step.shell || "powershell",
      template: step.template || "",
    },
  };
  if (step.captureStdoutJson) result.captureStdoutJson = true;
  const expectStdoutJson = parseEditorJson(step.expectStdoutJsonJson, "product step expectStdoutJson");
  if (Object.keys(expectStdoutJson).length) result.expectStdoutJson = expectStdoutJson;
  const secretTokens = parseEditorJson(step.secretTokensJson, "product step secretTokens");
  if (Object.keys(secretTokens).length) result.secretTokens = secretTokens;
  return result;
}

function toAssertionModel(assertion: any): ScenarioAssertionModel {
  const body = { ...(assertion ?? {}) };
  delete body.id;
  delete body.type;
  return {
    id: String(assertion?.id ?? ""),
    type: String(assertion?.type ?? ""),
    bodyJson: stringifyEditorJson(body),
  };
}

function fromAssertionModel(assertion: ScenarioAssertionModel) {
  return {
    id: assertion.id || "",
    type: assertion.type || "command.exitCode",
    ...parseEditorJson(assertion.bodyJson, `assertion ${assertion.id || assertion.type || ""}`),
  };
}

function stringifyEditorJson(value: unknown): string {
  if (!value || (typeof value === "object" && !Array.isArray(value) && Object.keys(value as Record<string, unknown>).length === 0)) return "{}";
  return JSON.stringify(value, null, 2);
}

function parseEditorJson(text: string, label: string): Record<string, unknown> {
  const trimmed = String(text || "").trim();
  if (!trimmed) return {};
  try {
    const parsed = JSON.parse(trimmed);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      throw new Error("must be a JSON object");
    }
    return parsed;
  } catch (error: any) {
    throw new BadRequestException(`${label} JSON is invalid: ${error.message || String(error)}`);
  }
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String).filter(Boolean) : [];
}

function parseYamlContent(content = "") {
  try {
    return YAML.parse(content) ?? {};
  } catch (error: any) {
    throw new BadRequestException(error.message || String(error));
  }
}

function asNumberOrNull(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() && /^-?\d+$/.test(value.trim())) return Number(value.trim());
  return null;
}

function numberOrDefault(value: unknown, fallback: number): number {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  return fallback;
}

function deriveSuiteEntryId(scenarioPath: string): string {
  const filename = String(scenarioPath || "").split(/[\\/]/).pop() || "scenario";
  const base = filename.replace(/\.(example\.)?ya?ml$/i, "");
  return base.replace(/[^a-z0-9]+/gi, "-").replace(/^-+|-+$/g, "").toLowerCase() || "scenario";
}

function sanitizeScenarioId(value: string): string {
  return String(value || "new.scenario")
    .trim()
    .replace(/[^a-zA-Z0-9_.-]+/g, ".")
    .replace(/^\.+|\.+$/g, "")
    .toLowerCase() || "new.scenario";
}

function sanitizeScenarioPath(value: string): string {
  const normalized = String(value || "").replaceAll("\\", "/").replace(/^\/+/, "");
  if (!normalized.startsWith("scenarios/") || !/\.ya?ml$/i.test(normalized)) {
    throw new BadRequestException("Scenario path must be under scenarios/** and end with .yaml or .yml");
  }
  if (normalized.includes("..")) {
    throw new BadRequestException("Scenario path cannot include .. segments");
  }
  return normalized;
}

function sanitizeSuiteScenarioPath(value: string): string {
  const normalized = String(value || "").replaceAll("\\", "/").replace(/^\/+/, "");
  if (!normalized.startsWith("scenarios/") || !/\.ya?ml$/i.test(normalized)) {
    throw new BadRequestException("Suite scenario path must be under scenarios/** and end with .yaml or .yml");
  }
  if (normalized.split("/").some((segment) => segment === "..")) {
    throw new BadRequestException("Suite scenario path cannot include .. segments");
  }
  return normalized;
}

function normalizeSuiteScenarioPaths(body: SuiteTemplateDto): string[] {
  const rawPaths = Array.isArray(body.scenarioPaths) && body.scenarioPaths.length
    ? body.scenarioPaths
    : [body.scenarioPath || "scenarios/windows/demo-powershell-system.example.yaml"];
  const paths = rawPaths.map(sanitizeSuiteScenarioPath);
  return Array.from(new Set(paths));
}

function normalizePositiveInteger(value: unknown, fallback: number): number {
  const parsed = Number(value);
  if (Number.isFinite(parsed) && parsed >= 1) return Math.floor(parsed);
  return fallback;
}

function sanitizeFileStem(value: string): string {
  return String(value || "new-file")
    .trim()
    .replace(/[^a-zA-Z0-9_.-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .toLowerCase() || "new-file";
}

function defaultScenarioPath(osFamily: string, id: string): string {
  const slug = id.replace(/[^a-z0-9]+/gi, "-").replace(/^-+|-+$/g, "").toLowerCase() || "new-scenario";
  return `scenarios/${osFamily === "linux" ? "linux" : "windows"}/${slug}.example.yaml`;
}

function defaultFixturePath(kind: string, id: string): string {
  const slug = sanitizeFileStem(id);
  return `validation/fixtures/${kind === "shell" ? "linux" : "windows"}/${slug}.${kind === "shell" ? "sh" : "ps1"}`;
}

function defaultSuitePath(id: string): string {
  const slug = id.replace(/[^a-z0-9]+/gi, "-").replace(/^-+|-+$/g, "").toLowerCase() || "new-suite";
  return `validation/suites/${slug}.yaml`;
}

function defaultTemplateId(kind: string): string {
  if (kind === "linux-basic") return "new.linux.smoke";
  if (kind === "inventory-basic") return "inventory.agent.smoke.windows";
  return "new.windows.smoke";
}

function defaultTemplateName(kind: string, id: string): string {
  if (kind === "linux-basic") return "New Linux smoke";
  if (kind === "inventory-basic") return "Inventory agent smoke";
  return id;
}

function buildScenarioTemplate(kind: string, id: string, name: string) {
  if (kind === "linux-basic") {
    return {
      schemaVersion: 1,
      id,
      name,
      os: { family: "linux" },
      provider: { type: "proxmox", template: "ubuntu-2404-base-template", vmIdRange: { start: 9200, end: 9299 } },
      isolation: { mode: "ephemeralClone" },
      guest: { mode: "auto", linuxOrder: ["ssh", "qemuAgent"] },
      fixtures: [],
      assertions: [
        { type: "command.exitCode", id: "uname-linux", command: { shell: "sh", template: "uname -s" }, expected: 0 },
      ],
      reports: { formats: ["junit", "json", "html"] },
      cleanup: { destroyVm: true, keepVmOnFailure: false },
    };
  }
  const base: any = {
    schemaVersion: 1,
    id,
    name,
    os: { family: "windows", version: "11" },
    provider: { type: "proxmox", template: "windows11-template-qga-9101", templateVmId: 9101, vmIdRange: { start: 9102, end: 9199 } },
    isolation: { mode: "ephemeralClone" },
    guest: { mode: "auto", windowsOrder: ["qemuAgent", "winrm"] },
    artifact: { type: "folder", pathParam: "artifactPath", destination: "C:\\Oslab\\artifact", transfer: "archive" },
    outputs: { actual: { path: "C:\\Oslab\\command-result.json", adapter: "canonical.command" } },
    assertions: [{ type: "command.exitCode", id: "exit-zero", exitCode: 0 }],
    reports: { formats: ["junit", "json", "html"] },
    cleanup: { destroyVm: true, keepVmOnFailure: false },
  };
  if (kind === "inventory-basic") {
    base.artifact.destination = "C:\\Oslab\\inventory-agent";
    base.artifact.command = { shell: "powershell", template: '& "{ArtifactDir}\\run-inventory.ps1" -OutputPath "{OutputPath}"' };
    base.outputs.actual = { path: "C:\\Oslab\\inventory-result.json", adapter: "canonical.inventory" };
    base.assertions = [{ type: "inventory.sourcePresent", id: "registry-source", source: "Registry" }];
  } else {
    base.artifact.command = { shell: "powershell", template: '& "{ArtifactDir}\\run-demo.ps1" -OutputPath "{OutputPath}"' };
  }
  return base;
}

function buildPowerShellFixtureTemplate(): string {
  return [
    "param(",
    "  [string]$OutputPath = \"C:\\Oslab\\fixture-result.json\"",
    ")",
    "",
    "$result = @{",
    "  ok = $true",
    "  checkedAt = (Get-Date).ToUniversalTime().ToString(\"o\")",
    "}",
    "",
    "$result | ConvertTo-Json -Depth 8 | Set-Content -Path $OutputPath -Encoding UTF8",
    "",
  ].join("\n");
}

function buildShellFixtureTemplate(): string {
  return [
    "#!/usr/bin/env sh",
    "set -eu",
    "",
    "output_path=\"${1:-/tmp/oslab-fixture-result.json}\"",
    "printf '{\"ok\":true,\"checkedAt\":\"%s\"}\\n' \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\" > \"$output_path\"",
    "",
  ].join("\n");
}

function buildSuiteTemplate(
  id: string,
  name: string,
  scenarioPaths: string[],
  options: { kind?: string; tier?: string; allowFailure?: boolean; enabled?: boolean; maxParallel?: number } = {},
) {
  const tier = options.tier?.trim() || (options.kind === "matrix-suite" ? "exploratory" : "ci");
  const allowFailure = typeof options.allowFailure === "boolean" ? options.allowFailure : options.kind === "matrix-suite";
  const enabled = typeof options.enabled === "boolean" ? options.enabled : true;
  const seenIds = new Map<string, number>();
  const runs = scenarioPaths.map((scenarioPath) => {
    const baseId = deriveSuiteEntryId(scenarioPath);
    const nextCount = (seenIds.get(baseId) ?? 0) + 1;
    seenIds.set(baseId, nextCount);
    const entryId = nextCount === 1 ? baseId : `${baseId}-${nextCount}`;
    return {
      id: entryId,
      scenario: scenarioPath,
      tier,
      allowFailure,
      enabled,
    };
  });
  return {
    schemaVersion: 1,
    id,
    name,
    maxParallel: normalizePositiveInteger(options.maxParallel, 1),
    runs,
  };
}
