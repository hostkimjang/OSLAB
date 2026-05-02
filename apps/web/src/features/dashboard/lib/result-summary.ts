import type { DashboardText, ProgressEvent, RunDetail } from "../model";

export function buildResultSummary(detail: RunDetail, progressEvents: ProgressEvent[], t: DashboardText) {
  const status = String(detail.status || "unknown").toLowerCase();
  const failureClass = detail.failureClass || detail.entries?.find?.((entry: any) => entry.failureClass)?.failureClass || null;
  const lastEvent = [...progressEvents].reverse().find((event) => event.message || event.phase || event.status);
  if (["queued", "running", "pending", "in_progress"].includes(status)) {
    return {
      summary: `${t.runningSummary}${lastEvent?.message ? ` · ${lastEvent.message}` : ""}`,
      nextAction: t.runningAction,
    };
  }
  if (status === "passed") {
    return {
      summary: `${t.successSummary}${lastEvent?.message ? ` · ${lastEvent.message}` : ""}`,
      nextAction: t.successAction,
    };
  }
  if (status === "cancelled") {
    return {
      summary: t.cancelledSummary,
      nextAction: t.cancelledAction,
    };
  }
  if (status === "stale") {
    return {
      summary: t.staleSummary,
      nextAction: t.staleAction,
    };
  }
  if (status === "unknown") {
    return {
      summary: t.unknownSummary,
      nextAction: t.unknownAction,
    };
  }
  if (failureClass === "provider_failure") {
    return {
      summary: t.providerFailureSummary,
      nextAction: t.providerFailureAction,
    };
  }
  if (failureClass === "preflight_failure") {
    return {
      summary: t.preflightFailureSummary,
      nextAction: t.preflightFailureAction,
    };
  }
  if (failureClass === "assertion_failure") {
    return {
      summary: t.assertionFailureSummary,
      nextAction: t.assertionFailureAction,
    };
  }
  return {
    summary: `${t.genericFailureSummary}${failureClass ? ` · ${failureClass}` : ""}`,
    nextAction: t.genericFailureAction,
  };
}
