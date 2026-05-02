import type { LabStatus } from "@oslab/shared";
import type { DashboardText, Tab } from "../model";

export function labStatusLabel(status: LabStatus["status"], t: DashboardText) {
  if (status === "ready") return t.labReady;
  if (status === "degraded") return t.labDegraded;
  return t.labBlocked;
}

export function tabTitle(tab: Tab, t: DashboardText) {
  return t[tab];
}

export function parseEventData(event: Event): string {
  try {
    return JSON.parse((event as MessageEvent).data);
  } catch {
    return String((event as MessageEvent).data ?? "");
  }
}

export function stableStringify(value: unknown): string {
  return JSON.stringify(sortValue(value));
}

export function sortValue(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(sortValue);
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, entryValue]) => [key, sortValue(entryValue)]),
    );
  }
  return value;
}
