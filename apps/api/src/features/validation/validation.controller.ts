import { Body, Controller, Inject, Post, UseGuards } from "@nestjs/common";
import { execFile } from "child_process";
import path from "path";
import { promisify } from "util";
import type { SyntaxValidationIssue, SyntaxValidationResult } from "@oslab/shared";
import YAML from "yaml";
import { AuthGuard } from "../../common/guards/auth.guard";
import { WorkspaceService } from "../../infrastructure/workspace/workspace.service";
import { ValidateContentDto } from "./dto/validate-content.dto";
import { ValidatePathDto } from "./dto/validate-path.dto";

const execFileAsync = promisify(execFile);

@Controller("api/validate")
@UseGuards(AuthGuard)
export class ValidationController {
  constructor(@Inject(WorkspaceService) private readonly workspace: WorkspaceService) {}

  @Post("scenario")
  async scenario(@Body() body: ValidatePathDto) {
    const policy = this.workspace.enforceAuthoringPolicy(body.path, "read");
    if (policy.kind !== "scenario") {
      return { ok: false, stdout: "", stderr: "scenario path must be under scenarios/** and end with .yaml or .yml" };
    }
    const scenarioPath = policy.path;
    try {
      const result = await execFileAsync("uv", ["run", "oslab", "validate-scenario", "--scenario", scenarioPath], {
        cwd: this.workspace.root,
        windowsHide: true,
      });
      return { ok: true, stdout: result.stdout, stderr: result.stderr };
    } catch (error: any) {
      return { ok: false, stdout: error.stdout ?? "", stderr: error.stderr ?? String(error) };
    }
  }

  @Post("suite")
  async suite(@Body() body: ValidatePathDto) {
    const policy = this.workspace.enforceAuthoringPolicy(body.path, "read");
    if (policy.kind !== "suite") {
      return { ok: false, errors: ["suite path must be under validation/suites/** and end with .yaml or .yml"] };
    }
    const text = await this.workspace.readText(body.path);
    try {
      const parsed = YAML.parse(text) ?? {};
      return validateSuiteSchema(parsed);
    } catch (error: any) {
      return { ok: false, errors: [String(error.message ?? error)] };
    }
  }

  @Post("content")
  async content(@Body() body: ValidateContentDto): Promise<SyntaxValidationResult> {
    this.workspace.enforceAuthoringPolicy(body.path, "write");
    const extension = path.extname(body.path).toLowerCase();
    if (extension === ".yaml" || extension === ".yml") {
      return validateYaml(body.content);
    }
    if (extension === ".ps1") {
      return validatePowerShell(body.content);
    }
    return {
      ok: true,
      kind: "unsupported",
      checkedAt: new Date().toISOString(),
      issues: [],
      skipped: true,
      message: "No syntax checker is configured for this file type.",
    };
  }

  @Post("scenario-content")
  async scenarioContent(@Body() body: ValidateContentDto) {
    const policy = this.workspace.enforceAuthoringPolicy(body.path, "write");
    if (policy.kind !== "scenario") {
      return { ok: false, errors: ["scenario content path must be under scenarios/** and end with .yaml or .yml"] };
    }
    const syntax = validateYaml(body.content);
    if (!syntax.ok) {
      return { ok: false, errors: syntax.issues.map((issue) => issue.message), syntax };
    }
    try {
      const parsed = YAML.parse(body.content) ?? {};
      return validateScenarioSchema(parsed);
    } catch (error: any) {
      return { ok: false, errors: [error.message || String(error)] };
    }
  }

  @Post("suite-content")
  async suiteContent(@Body() body: ValidateContentDto) {
    const policy = this.workspace.enforceAuthoringPolicy(body.path, "write");
    if (policy.kind !== "suite") {
      return { ok: false, errors: ["suite content path must be under validation/suites/** and end with .yaml or .yml"] };
    }
    const syntax = validateYaml(body.content);
    if (!syntax.ok) {
      return { ok: false, errors: syntax.issues.map((issue) => issue.message), syntax };
    }
    try {
      const parsed = YAML.parse(body.content) ?? {};
      return validateSuiteSchema(parsed);
    } catch (error: any) {
      return { ok: false, errors: [error.message || String(error)] };
    }
  }
}

function validateScenarioSchema(raw: any): { ok: boolean; errors: string[] } {
  const errors: string[] = [];
  const requireString = (value: unknown, label: string) => {
    if (typeof value !== "string" || !value.trim()) errors.push(`${label} must be a non-empty string.`);
  };
  const requireNumber = (value: unknown, label: string) => {
    if (typeof value !== "number" || !Number.isFinite(value)) errors.push(`${label} must be a number.`);
  };
  if (raw?.schemaVersion !== 1) errors.push("schemaVersion must be 1.");
  requireString(raw?.id, "id");
  requireString(raw?.os?.family, "os.family");
  if (raw?.os?.family && !["windows", "linux"].includes(raw.os.family)) errors.push("os.family must be windows or linux.");
  requireString(raw?.provider?.type, "provider.type");
  if (raw?.provider?.vmIdRange) {
    requireNumber(raw.provider.vmIdRange.start, "provider.vmIdRange.start");
    requireNumber(raw.provider.vmIdRange.end, "provider.vmIdRange.end");
    if (typeof raw.provider.vmIdRange.start === "number" && typeof raw.provider.vmIdRange.end === "number" && raw.provider.vmIdRange.start > raw.provider.vmIdRange.end) {
      errors.push("provider.vmIdRange.start must be less than or equal to end.");
    }
  }
  requireString(raw?.guest?.mode, "guest.mode");
  if (raw?.guest?.mode && !["auto", "qemuAgent", "winrm", "ssh"].includes(raw.guest.mode)) errors.push("guest.mode must be auto, qemuAgent, winrm, or ssh.");
  if (!Array.isArray(raw?.assertions) || !raw.assertions.length) errors.push("assertions must contain at least one assertion.");
  if (Array.isArray(raw?.reports?.formats)) {
    for (const item of raw.reports.formats) {
      if (!["junit", "json", "html"].includes(item)) errors.push(`Unsupported report format: ${item}.`);
    }
  }
  for (const boolField of ["destroyVm", "keepVmOnFailure"]) {
    if (raw?.cleanup && boolField in raw.cleanup && typeof raw.cleanup[boolField] !== "boolean") {
      errors.push(`cleanup.${boolField} must be a boolean.`);
    }
  }
  return { ok: errors.length === 0, errors };
}

export function validateSuiteSchema(raw: any): { ok: boolean; errors: string[] } {
  const errors: string[] = [];
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    return { ok: false, errors: ["suite must be a YAML object."] };
  }
  if (raw.schemaVersion !== 1) errors.push("schemaVersion must be 1.");
  if (typeof raw.id !== "string" || !raw.id.trim()) errors.push("id must be a non-empty string.");
  if ("name" in raw && typeof raw.name !== "string") errors.push("name must be a string.");
  if ("maxParallel" in raw && (!Number.isInteger(raw.maxParallel) || raw.maxParallel < 1)) errors.push("maxParallel must be a positive integer.");
  if (!Array.isArray(raw.runs)) {
    errors.push("runs must be an array.");
    return { ok: false, errors };
  }
  if (raw.runs.length === 0) errors.push("runs must contain at least one run.");

  const seenRunIds = new Set<string>();
  raw.runs.forEach((entry: any, index: number) => {
    const label = `runs[${index}]`;
    if (!entry || typeof entry !== "object" || Array.isArray(entry)) {
      errors.push(`${label} must be an object.`);
      return;
    }
    if (typeof entry.id !== "string" || !entry.id.trim()) {
      errors.push(`${label}.id must be a non-empty string.`);
    } else if (seenRunIds.has(entry.id)) {
      errors.push(`${label}.id duplicates another run id: ${entry.id}.`);
    } else {
      seenRunIds.add(entry.id);
    }
    if (typeof entry.scenario !== "string" || !entry.scenario.trim()) {
      errors.push(`${label}.scenario must be a non-empty string.`);
    } else {
      const scenarioError = validateSuiteScenarioPath(entry.scenario);
      if (scenarioError) errors.push(`${label}.scenario ${scenarioError}`);
    }
    if ("tier" in entry && typeof entry.tier !== "string") errors.push(`${label}.tier must be a string.`);
    if ("allowFailure" in entry && typeof entry.allowFailure !== "boolean") errors.push(`${label}.allowFailure must be a boolean.`);
    if ("enabled" in entry && typeof entry.enabled !== "boolean") errors.push(`${label}.enabled must be a boolean.`);
  });
  return { ok: errors.length === 0, errors };
}

function validateSuiteScenarioPath(value: string): string | null {
  if (path.isAbsolute(value)) return "must be repository-relative.";
  const normalized = value.replaceAll("\\", "/").replace(/^\/+/, "");
  if (normalized.split("/").some((segment) => segment === "..")) return "cannot include .. segments.";
  if (!normalized.startsWith("scenarios/")) return "must be under scenarios/**.";
  if (!/\.ya?ml$/i.test(normalized)) return "must end with .yaml or .yml.";
  return null;
}

function validateYaml(content: string): SyntaxValidationResult {
  const doc = YAML.parseDocument(content, { prettyErrors: false });
  const issues = doc.errors.map((error: any) => {
    const start = Array.isArray(error.linePos) ? error.linePos[0] : undefined;
    const end = Array.isArray(error.linePos) ? error.linePos[1] : undefined;
    const startFromOffset = start ? null : offsetToLineColumn(content, Array.isArray(error.pos) ? error.pos[0] : undefined);
    const endFromOffset = end ? null : offsetToLineColumn(content, Array.isArray(error.pos) ? error.pos[1] : undefined);
    return {
      message: error.message || String(error),
      line: start?.line ?? startFromOffset?.line ?? null,
      column: start?.col ?? startFromOffset?.column ?? null,
      endLine: end?.line ?? endFromOffset?.line ?? null,
      endColumn: end?.col ?? endFromOffset?.column ?? null,
    };
  });
  return {
    ok: issues.length === 0,
    kind: "yaml",
    checkedAt: new Date().toISOString(),
    issues,
    message: issues.length === 0 ? "YAML syntax is valid." : `YAML syntax has ${issues.length} issue(s).`,
  };
}

async function validatePowerShell(content: string): Promise<SyntaxValidationResult> {
  const command = process.platform === "win32" ? "powershell.exe" : "pwsh";
  const script = [
    "$code = [Console]::In.ReadToEnd()",
    "$tokens = $null",
    "$parseErrors = $null",
    "[System.Management.Automation.Language.Parser]::ParseInput($code, [ref]$tokens, [ref]$parseErrors) | Out-Null",
    "$items = @($parseErrors | ForEach-Object { [pscustomobject]@{ message = $_.Message; line = $_.Extent.StartLineNumber; column = $_.Extent.StartColumnNumber; endLine = $_.Extent.EndLineNumber; endColumn = $_.Extent.EndColumnNumber } })",
    "if ($items.Count -eq 0) { '[]' } else { Microsoft.PowerShell.Utility\\ConvertTo-Json -InputObject $items -Compress }",
  ].join("; ");

  try {
    const { stdout } = await execFileWithInput(command, ["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script], content, 6000);
    const parsed = stdout.trim() ? JSON.parse(stdout.trim()) : [];
    const issues = normalizePowerShellIssues(parsed);
    return {
      ok: issues.length === 0,
      kind: "powershell",
      checkedAt: new Date().toISOString(),
      issues,
      message: issues.length === 0 ? "PowerShell syntax is valid." : `PowerShell syntax has ${issues.length} issue(s).`,
    };
  } catch (error: any) {
    return {
      ok: false,
      kind: "powershell",
      checkedAt: new Date().toISOString(),
      issues: [{ message: error.message || String(error) }],
      message: "PowerShell syntax check failed.",
    };
  }
}

function execFileWithInput(command: string, args: string[], input: string, timeoutMs: number): Promise<{ stdout: string; stderr: string }> {
  return new Promise((resolve, reject) => {
    const child = execFile(command, args, { timeout: timeoutMs, windowsHide: true }, (error, stdout, stderr) => {
      if (error) {
        reject(Object.assign(error, { stdout, stderr }));
        return;
      }
      resolve({ stdout, stderr });
    });
    child.stdin?.end(input);
  });
}

function normalizePowerShellIssues(value: unknown): SyntaxValidationIssue[] {
  const items = Array.isArray(value) ? value : value ? [value] : [];
  return items.map((item: any) => ({
    message: String(item.message || item.Message || item || "PowerShell syntax error"),
    line: toNullableNumber(item.line ?? item.Line),
    column: toNullableNumber(item.column ?? item.Column),
    endLine: toNullableNumber(item.endLine ?? item.EndLine),
    endColumn: toNullableNumber(item.endColumn ?? item.EndColumn),
  }));
}

function toNullableNumber(value: unknown): number | null {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function offsetToLineColumn(content: string, offset: unknown): { line: number; column: number } | null {
  const target = Number(offset);
  if (!Number.isFinite(target) || target < 0) return null;
  let line = 1;
  let column = 1;
  const limit = Math.min(target, content.length);
  for (let index = 0; index < limit; index += 1) {
    if (content[index] === "\n") {
      line += 1;
      column = 1;
    } else {
      column += 1;
    }
  }
  return { line, column };
}
