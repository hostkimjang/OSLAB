import { BadRequestException, Inject, Injectable } from "@nestjs/common";
import { createHash } from "crypto";
import { promises as fs } from "fs";
import path from "path";
import YAML from "yaml";
import type { LabCleanupResponse, LabCleanupTarget, LabStatus, LabStatusCheck, LabStatusLevel, LabVmSummary } from "@oslab/shared";
import { WorkspaceService } from "../../infrastructure/workspace/workspace.service";
import { ProxmoxLabClient, type ProxmoxLabClientConfig } from "./proxmox-lab.client";

interface LabStatusOptions {
  scenarioPath?: string;
  configPath?: string;
  envFilePath?: string;
  requiredCapacity?: number;
}

interface LabCleanupOptions extends LabStatusOptions {
  dryRun?: boolean;
  confirmToken?: string;
  includeRunning?: boolean;
}

interface ProxmoxVmResource {
  vmid?: number | string;
  name?: string;
  node?: string;
  status?: string;
  type?: string;
}

@Injectable()
export class LabService {
  constructor(
    @Inject(WorkspaceService) private readonly workspace: WorkspaceService,
    @Inject(ProxmoxLabClient) private readonly proxmoxClient: ProxmoxLabClient,
  ) {}

  async status(options: LabStatusOptions): Promise<LabStatus> {
    const scenarioPath = options.scenarioPath || "scenarios/windows/demo-powershell-system.example.yaml";
    const configPath = options.configPath || "config/oslab.local.yaml";
    const envFilePath = options.envFilePath || "config/oslab.local.env";
    const requiredCapacity = Math.max(1, Number(options.requiredCapacity || 1));
    const checkedAt = new Date().toISOString();
    const checks = {
      configFile: check(false, "Config file was not checked yet"),
      envFile: check(false, "Env file was not checked yet"),
      token: check(false, "Proxmox token was not checked yet"),
      connectivity: check(false, "Proxmox API was not checked yet"),
      node: check(false, "Proxmox node was not checked yet"),
      template: check(false, "Template VM was not checked yet"),
      vmidRange: check(false, "VMID range was not checked yet"),
    };
    const warnings: string[] = [];
    const issues: string[] = [];

    const scenarioText = await this.workspace.readText(scenarioPath);
    const scenario = YAML.parse(scenarioText) ?? {};
    const configFile = this.resolveConfigPath(configPath);
    const envFile = this.resolveEnvPath(envFilePath);

    let config: any = null;
    try {
      config = YAML.parse(await fs.readFile(configFile, "utf8")) ?? {};
      checks.configFile = check(true, "Config file exists", { path: configPath });
    } catch (error: any) {
      checks.configFile = check(false, "Cannot read config file", { path: configPath, error: String(error.message ?? error) });
      issues.push("Cannot read config file");
    }

    let envValues: Record<string, string> = {};
    try {
      envValues = parseEnvFile(await fs.readFile(envFile, "utf8"));
      checks.envFile = check(true, "Env file exists", { path: envFilePath });
    } catch (error: any) {
      checks.envFile = check(false, "Cannot read env file", { path: envFilePath, error: String(error.message ?? error) });
      issues.push("Cannot read env file");
    }

    const proxmox = config?.providerDefaults?.proxmox ?? {};
    const tokenIdName = proxmox?.tokenEnv?.id;
    const tokenSecretName = proxmox?.tokenEnv?.secret;
    const tokenId = resolveEnvValue(tokenIdName, envValues);
    const tokenSecret = resolveEnvValue(tokenSecretName, envValues);
    checks.token = check(Boolean(tokenId && tokenSecret), tokenId && tokenSecret ? "Proxmox token env values are present" : "Proxmox token env values are missing", {
      tokenIdEnv: tokenIdName || "<missing>",
      tokenSecretEnv: tokenSecretName || "<missing>",
      hasTokenId: Boolean(tokenId),
      hasTokenSecret: Boolean(tokenSecret),
    });
    if (!checks.token.ok) issues.push("Proxmox token env values are missing");

    const apiUrl = this.proxmoxClient.normalizeApiUrl(String(proxmox.apiUrl || ""));
    const node = String(proxmox.node || "");
    const verifyTls = proxmox.verifyTls !== false;
    const timeoutMs = Math.max(1000, Number(proxmox.timeoutSeconds || 30) * 1000);
    const proxmoxClientConfig = { apiUrl, tokenId, tokenSecret, verifyTls, timeoutMs };
    const provider: LabStatus["provider"] = { type: "proxmox", apiUrl, node, verifyTls };
    const templateVmId = numberOrUndefined(scenario?.provider?.templateVmId);
    const expectedTemplateName = typeof scenario?.provider?.template === "string" ? scenario.provider.template : undefined;
    const rawRange = scenario?.provider?.vmIdRange ?? {};
    const rangeStart = numberOrUndefined(rawRange.start);
    const rangeEnd = numberOrUndefined(rawRange.end);

    let resources: ProxmoxVmResource[] = [];
    if (apiUrl && tokenId && tokenSecret) {
      try {
        const started = Date.now();
        const version = await this.proxmoxClient.get<any>(proxmoxClientConfig, "/version");
        provider.version = String(version.version ?? "unknown");
        provider.release = String(version.release ?? "unknown");
        provider.elapsedMs = Date.now() - started;
        checks.connectivity = check(true, "Proxmox API reachable", { version: provider.version, release: provider.release, elapsedMs: provider.elapsedMs });
      } catch (error: any) {
        checks.connectivity = check(false, "Cannot reach Proxmox API", { error: String(error.message ?? error) });
        issues.push("Cannot reach Proxmox API");
      }
    } else {
      checks.connectivity = check(false, "Cannot check Proxmox API without apiUrl and token");
    }

    if (checks.connectivity.ok) {
      try {
        const nodes = await this.proxmoxClient.get<any[]>(proxmoxClientConfig, "/nodes");
        const nodeNames = nodes.map((item) => String(item.node ?? "")).filter(Boolean);
        checks.node = check(nodeNames.includes(node), nodeNames.includes(node) ? "Configured node exists" : "Configured node was not found", {
          configuredNode: node,
          availableNodes: nodeNames,
        });
        if (!checks.node.ok) issues.push("Configured Proxmox node was not found");
      } catch (error: any) {
        checks.node = check(false, "Cannot read Proxmox nodes", { error: String(error.message ?? error) });
        issues.push("Cannot read Proxmox nodes");
      }

      try {
        resources = await this.proxmoxClient.get<ProxmoxVmResource[]>(proxmoxClientConfig, "/cluster/resources?type=vm");
      } catch (error: any) {
        warnings.push(`Cannot read VM resources: ${String(error.message ?? error)}`);
      }
    }

    const resource = resources.find((item) => toNumber(item.vmid) === templateVmId);
    const template: LabStatus["template"] = {
      vmId: templateVmId,
      expectedName: expectedTemplateName,
      name: resource?.name,
      node: resource?.node,
      status: resource?.status,
    };
    if (checks.connectivity.ok && templateVmId) {
      if (!resource) {
        checks.template = check(false, "Template VMID was not found", { templateVmId });
        issues.push("Template VMID was not found");
      } else {
        try {
          const configPayload = await this.proxmoxClient.get<Record<string, unknown>>(proxmoxClientConfig, `/nodes/${resource.node || node}/qemu/${templateVmId}/config`);
          template.isTemplate = configPayload.template === 1 || configPayload.template === "1" || configPayload.template === true;
        } catch (error: any) {
          warnings.push(`Cannot confirm template flag: ${String(error.message ?? error)}`);
        }
        const nameOk = !expectedTemplateName || expectedTemplateName === resource.name;
        const templateOk = template.isTemplate === true;
        checks.template = check(Boolean(nameOk && templateOk), nameOk && templateOk ? "Template VM is ready" : "Template VM has warnings", {
          templateVmId,
          templateName: resource.name,
          expectedName: expectedTemplateName,
          isTemplate: template.isTemplate,
          status: resource.status,
        });
        if (!nameOk) warnings.push(`Template name is ${resource.name}, expected ${expectedTemplateName}`);
        if (!templateOk) issues.push("Template VM is not marked as template");
      }
    } else if (!templateVmId) {
      checks.template = check(false, "Scenario does not define provider.templateVmId");
      issues.push("Scenario does not define provider.templateVmId");
    }

    const locks = await this.localLocks(config);
    const usedInRange = rangeStart !== undefined && rangeEnd !== undefined
      ? resources.map((item) => toNumber(item.vmid)).filter((vmid): vmid is number => vmid !== undefined && vmid >= rangeStart && vmid <= rangeEnd).sort((a, b) => a - b)
      : [];
    const reservedLocks = rangeStart !== undefined && rangeEnd !== undefined
      ? locks.filter((vmid) => vmid >= rangeStart && vmid <= rangeEnd).sort((a, b) => a - b)
      : locks;
    const unavailable = new Set([...usedInRange, ...reservedLocks]);
    const total = rangeStart !== undefined && rangeEnd !== undefined ? rangeEnd - rangeStart + 1 : undefined;
    const freeCount = total !== undefined ? Math.max(0, total - unavailable.size) : undefined;
    const recommendedVmId = rangeStart !== undefined && rangeEnd !== undefined ? firstFree(rangeStart, rangeEnd, unavailable) : null;
    const capacityOk = freeCount === undefined ? false : freeCount >= requiredCapacity;
    checks.vmidRange = check(Boolean(rangeStart !== undefined && rangeEnd !== undefined && capacityOk), capacityOk ? "VMID range has capacity" : "VMID range needs attention", {
      range: rangeStart !== undefined && rangeEnd !== undefined ? `${rangeStart}-${rangeEnd}` : "<missing>",
      usedInRange,
      reservedLocks,
      freeCount,
      requiredCapacity,
      recommendedVmId,
    });
    if (rangeStart === undefined || rangeEnd === undefined) issues.push("Scenario does not define provider.vmIdRange");
    else if (!capacityOk) issues.push("Not enough free VMIDs for requested capacity");

    const inRange = (item: ProxmoxVmResource) => {
      const vmid = toNumber(item.vmid);
      return vmid !== undefined && rangeStart !== undefined && rangeEnd !== undefined && vmid >= rangeStart && vmid <= rangeEnd;
    };
    const toSummary = (item: ProxmoxVmResource): LabVmSummary => ({
      vmid: toNumber(item.vmid) ?? 0,
      name: item.name,
      node: item.node,
      status: item.status,
    });
    const oslabVms = resources.filter((item) => inRange(item) && String(item.name || "").toLowerCase().startsWith("oslab-"));
    const running = oslabVms.filter((item) => item.status === "running").map(toSummary);
    const stale = oslabVms.filter((item) => item.status !== "running").map(toSummary);
    if (running.length) warnings.push(`${running.length} oslab VM(s) are currently running`);
    if (stale.length) warnings.push(`${stale.length} stopped oslab VM(s) remain in the VMID range`);

    const status = deriveStatus(issues, warnings);
    return {
      status,
      checkedAt,
      scenarioPath,
      configPath,
      envFilePath,
      checks,
      provider,
      template,
      vmidRange: {
        start: rangeStart,
        end: rangeEnd,
        total,
        usedInRange,
        reservedLocks,
        freeCount,
        recommendedVmId,
        requiredCapacity,
        capacityOk,
      },
      vms: {
        running,
        stale,
        oslab: oslabVms.map(toSummary),
      },
      issues,
      warnings,
    };
  }

  async cleanupStale(options: LabCleanupOptions): Promise<LabCleanupResponse> {
    const scenarioPath = options.scenarioPath || "scenarios/windows/demo-powershell-system.example.yaml";
    const configPath = options.configPath || "config/oslab.local.yaml";
    const envFilePath = options.envFilePath || "config/oslab.local.env";
    const status = await this.status({ ...options, scenarioPath, configPath, envFilePath });
    const includeRunning = options.includeRunning === true;
    const targets = (includeRunning ? status.vms.oslab : status.vms.stale)
      .map<LabCleanupTarget>((vm) => ({
        vmid: vm.vmid,
        name: vm.name,
        node: vm.node,
        status: vm.status,
        stale: vm.status !== "running",
        running: vm.status === "running",
      }))
      .sort((a, b) => a.vmid - b.vmid);
    const wouldDestroy = targets.map((vm) => vm.vmid);
    if (!targets.length) {
      return {
        ok: true,
        dryRun: true,
        confirmationRequired: false,
        targets: [],
        wouldDestroy: [],
        requested: [],
        failed: [],
        message: includeRunning
          ? "No oslab VM remains in the configured range."
          : "No stopped oslab VM remains in the configured range.",
      };
    }

    const confirmToken = cleanupConfirmToken({ scenarioPath, configPath, envFilePath, includeRunning }, targets);
    if (options.dryRun !== false || !options.confirmToken) {
      return {
        ok: true,
        dryRun: true,
        confirmationRequired: true,
        confirmToken,
        targets,
        wouldDestroy,
        requested: [],
        failed: [],
        message: includeRunning
          ? `Dry-run: ${targets.length} oslab VM(s) would be destroyed.`
          : `Dry-run: ${targets.length} stopped oslab VM(s) would be destroyed.`,
      };
    }

    if (options.confirmToken !== confirmToken) {
      throw new BadRequestException("Cleanup confirmation token did not match current VM candidates. Run dry-run again.");
    }

    const config = YAML.parse(await fs.readFile(this.resolveConfigPath(configPath), "utf8")) ?? {};
    const envValues = parseEnvFile(await fs.readFile(this.resolveEnvPath(envFilePath), "utf8"));
    const proxmox = config?.providerDefaults?.proxmox ?? {};
    const apiUrl = this.proxmoxClient.normalizeApiUrl(String(proxmox.apiUrl || ""));
    const tokenId = resolveEnvValue(proxmox?.tokenEnv?.id, envValues);
    const tokenSecret = resolveEnvValue(proxmox?.tokenEnv?.secret, envValues);
    const verifyTls = proxmox.verifyTls !== false;
    const timeoutMs = Math.max(1000, Number(proxmox.timeoutSeconds || 30) * 1000);
    const proxmoxClientConfig: ProxmoxLabClientConfig = { apiUrl, tokenId, tokenSecret, verifyTls, timeoutMs };
    const defaultNode = String(proxmox.node || "");

    if (!apiUrl || !tokenId || !tokenSecret) {
      throw new BadRequestException("Cannot cleanup stale VMs without Proxmox API URL and token values");
    }

    const requested: number[] = [];
    const failed: string[] = [];
    for (const vm of targets) {
      try {
        if (vm.status === "running") {
          await this.proxmoxClient.request(
            proxmoxClientConfig,
            `/nodes/${vm.node || defaultNode}/qemu/${vm.vmid}/status/stop`,
            "POST",
          );
          await this.proxmoxClient.waitForVmStopped(proxmoxClientConfig, vm.node || defaultNode, vm.vmid);
        }
        await this.proxmoxClient.request(
          proxmoxClientConfig,
          `/nodes/${vm.node || defaultNode}/qemu/${vm.vmid}`,
          "DELETE",
          { purge: "1" },
        );
        requested.push(vm.vmid);
      } catch (error: any) {
        failed.push(`${vm.vmid}: ${String(error.message ?? error)}`);
      }
    }

    return {
      ok: failed.length === 0,
      dryRun: false,
      confirmationRequired: false,
      confirmToken,
      targets,
      wouldDestroy,
      requested,
      failed,
      message: failed.length
        ? `Requested cleanup for ${requested.length} ${includeRunning ? "oslab" : "stale"} VM(s), ${failed.length} failed.`
        : `Requested cleanup for ${requested.length} ${includeRunning ? "oslab" : "stale"} VM(s).`,
    };
  }

  private resolveConfigPath(relativePath: string): string {
    if (!relativePath || path.isAbsolute(relativePath)) throw new BadRequestException("configPath must be repository-relative");
    const target = path.resolve(this.workspace.root, relativePath);
    const configRoot = path.resolve(this.workspace.root, "config");
    if (!target.startsWith(configRoot + path.sep)) throw new BadRequestException("configPath must live under config/");
    return target;
  }

  private resolveEnvPath(relativePath: string): string {
    if (!relativePath || path.isAbsolute(relativePath)) throw new BadRequestException("envFilePath must be repository-relative");
    const target = path.resolve(this.workspace.root, relativePath);
    const configRoot = path.resolve(this.workspace.root, "config");
    if (!target.startsWith(configRoot + path.sep)) throw new BadRequestException("envFilePath must live under config/");
    return target;
  }

  private async localLocks(config: any): Promise<number[]> {
    const outputRoot = String(config?.runDefaults?.outputRoot || "runs");
    const lockDir = path.resolve(this.workspace.root, outputRoot, ".locks");
    try {
      const entries = await fs.readdir(lockDir, { withFileTypes: true });
      return entries
        .filter((entry) => entry.isFile() && /^vmid-\d+\.lock$/.test(entry.name))
        .map((entry) => Number(entry.name.match(/\d+/)?.[0]))
        .filter((value) => Number.isInteger(value));
    } catch {
      return [];
    }
  }
}

function check(ok: boolean, message: string, details?: Record<string, unknown>): LabStatusCheck {
  return { ok, message, details };
}

function deriveStatus(issues: string[], warnings: string[]): LabStatusLevel {
  if (issues.length) return "blocked";
  if (warnings.length) return "degraded";
  return "ready";
}

function parseEnvFile(content: string): Record<string, string> {
  const values: Record<string, string> = {};
  for (const rawLine of content.replace(/^\uFEFF/, "").split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    const index = line.indexOf("=");
    if (index < 0) continue;
    const key = line.slice(0, index).trim();
    const value = line.slice(index + 1).trim().replace(/^['"]|['"]$/g, "");
    values[key] = value;
  }
  return values;
}

function resolveEnvValue(name: unknown, envValues: Record<string, string>): string {
  if (typeof name !== "string" || !name) return "";
  return process.env[name] || envValues[name] || "";
}

function numberOrUndefined(value: unknown): number | undefined {
  return Number.isInteger(value) ? Number(value) : undefined;
}

function toNumber(value: unknown): number | undefined {
  if (typeof value === "number" && Number.isInteger(value)) return value;
  if (typeof value === "string" && /^\d+$/.test(value)) return Number(value);
  return undefined;
}

function cleanupConfirmToken(
  scope: { scenarioPath: string; configPath: string; envFilePath: string; includeRunning: boolean },
  targets: LabCleanupTarget[],
): string {
  const payload = JSON.stringify({
    ...scope,
    targets: targets.map((target) => ({
      vmid: target.vmid,
      name: target.name || "",
      node: target.node || "",
      status: target.status || "",
    })),
  });
  return createHash("sha256").update(payload).digest("hex").slice(0, 16);
}

function firstFree(start: number, end: number, unavailable: Set<number>): number | null {
  for (let vmid = start; vmid <= end; vmid += 1) {
    if (!unavailable.has(vmid)) return vmid;
  }
  return null;
}
