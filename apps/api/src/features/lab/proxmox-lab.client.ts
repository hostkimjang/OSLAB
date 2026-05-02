import { Injectable } from "@nestjs/common";
import http from "http";
import https from "https";
import { URL } from "url";

const PROXMOX_USER_AGENT = "oslab/0.1.0";

export interface ProxmoxLabClientConfig {
  apiUrl: string;
  tokenId: string;
  tokenSecret: string;
  verifyTls: boolean;
  timeoutMs: number;
}

@Injectable()
export class ProxmoxLabClient {
  normalizeApiUrl(value: string): string {
    if (!value) return "";
    const trimmed = value.replace(/\/+$/, "");
    return trimmed.endsWith("/api2/json") ? trimmed : `${trimmed}/api2/json`;
  }

  get<T>(config: ProxmoxLabClientConfig, endpoint: string): Promise<T> {
    return this.request<T>(config, endpoint, "GET");
  }

  request<T>(
    config: ProxmoxLabClientConfig,
    endpoint: string,
    method: "GET" | "POST" | "DELETE",
    query?: Record<string, string>,
  ): Promise<T> {
    const url = new URL(`${config.apiUrl}${endpoint.startsWith("/") ? endpoint : `/${endpoint}`}`);
    if (query) {
      for (const [key, value] of Object.entries(query)) {
        url.searchParams.set(key, value);
      }
    }
    const transport = url.protocol === "http:" ? http : https;
    return new Promise((resolve, reject) => {
      const request = transport.request(
        url,
        {
          method,
          timeout: config.timeoutMs,
          headers: {
            Accept: "application/json",
            Authorization: `PVEAPIToken=${config.tokenId}=${config.tokenSecret}`,
            "User-Agent": PROXMOX_USER_AGENT,
          },
          rejectUnauthorized: config.verifyTls,
        },
        (response) => {
          const chunks: Buffer[] = [];
          response.on("data", (chunk) => chunks.push(Buffer.from(chunk)));
          response.on("end", () => {
            const text = Buffer.concat(chunks).toString("utf8");
            if (!response.statusCode || response.statusCode >= 400) {
              reject(new Error(`HTTP ${response.statusCode}: ${text.slice(0, 500)}`));
              return;
            }
            try {
              const parsed = JSON.parse(text);
              resolve(parsed.data as T);
            } catch (error: any) {
              reject(new Error(`Cannot parse Proxmox response: ${String(error.message ?? error)}`));
            }
          });
        },
      );
      request.on("timeout", () => {
        request.destroy(new Error(`Request timed out after ${config.timeoutMs}ms`));
      });
      request.on("error", reject);
      request.end();
    });
  }

  async waitForVmStopped(config: ProxmoxLabClientConfig, node: string, vmid: number) {
    const deadline = Date.now() + Math.max(5000, config.timeoutMs);
    while (Date.now() < deadline) {
      const status = (await this.get<Record<string, unknown>>(
        config,
        `/nodes/${node}/qemu/${vmid}/status/current`,
      ).catch(() => ({} as Record<string, unknown>))) as Record<string, unknown>;
      if (status.qmpstatus !== "running" && status.status !== "running") {
        return;
      }
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
    throw new Error(`Timed out waiting for VM ${vmid} to stop`);
  }
}
