import type { JobSummary, LabStatus } from "@oslab/shared";
import type { DashboardText } from "../model";
import { labStatusLabel } from "../lib";
import { InfoTooltip, StatusCell, StatusList } from "./common";

export function GlobalRunBanner({
  jobs,
  t,
  onOpenRun,
  onOpenResults,
  onCancel,
}: {
  jobs: JobSummary[];
  t: DashboardText;
  onOpenRun: () => void;
  onOpenResults: () => void;
  onCancel: () => void;
}) {
  const lead = jobs[0];
  return (
    <section className="globalRunBanner">
      <div className="globalRunLeft">
        <span className="spinner" aria-hidden="true" />
        <div>
          <strong>{t.globalRunBanner}</strong>
          <p>{t.runningNow} {jobs.length} · {lead.title}</p>
        </div>
      </div>
      <div className="globalRunActions">
        <button className="secondary" onClick={onOpenRun}>{t.openRunTab}</button>
        <button onClick={onOpenResults}>{t.openResultsTab}</button>
        <button type="button" className="secondary" onClick={onCancel}>{t.cancelJob}</button>
      </div>
    </section>
  );
}

export function LabStatusPanel({
  status,
  loading,
  t,
  onRefresh,
  onCleanup,
  compact = false,
}: {
  status: LabStatus | null;
  loading: boolean;
  t: DashboardText;
  onRefresh: () => void;
  onCleanup: () => void;
  compact?: boolean;
}) {
  const level = status?.status ?? "blocked";
  const statusLabel = status ? labStatusLabel(status.status, t) : loading ? "Checking" : "Unknown";
  const checks = status?.checks;
  const vms = status?.vms ?? { running: [], stale: [] };
  return (
    <section className={`labStatus panel ${compact ? "compact" : ""}`}>
      <div className="labHeader">
        <div>
          <h3 className="sectionTitleLine">
            <span>{t.labStatus}</span>
            <InfoTooltip text={t.labStatusTooltip} label={t.infoTooltipLabel} />
          </h3>
          <p className="muted">{status?.scenarioPath || "scenario pending"}</p>
        </div>
        <div className="labActions">
          <span className={`statusBadge ${level}`}>{statusLabel}</span>
          <button className="secondary" onClick={onRefresh} disabled={loading}>{loading ? "..." : t.refreshLab}</button>
          {!!vms.stale.length && <button type="button" onClick={onCleanup}>{t.cleanupStale}</button>}
        </div>
      </div>
      <div className="labGrid">
        <StatusCell label={t.provider} ok={checks?.connectivity?.ok} value={status?.provider.version ? `Proxmox ${status.provider.version}` : checks?.connectivity?.message || "<unknown>"} />
        <StatusCell label="Node" ok={checks?.node?.ok} value={status?.provider.node || checks?.node?.message || "<missing>"} />
        <StatusCell label={t.template} ok={checks?.template?.ok} value={status?.template?.vmId ? `${status.template.vmId} · ${status.template.name || status.template.expectedName || "<unknown>"}` : "<missing>"} />
        <StatusCell label={t.vmidPool} ok={checks?.vmidRange?.ok} value={status?.vmidRange?.start ? `${status.vmidRange.start}-${status.vmidRange.end} · free ${status.vmidRange.freeCount ?? "?"}` : "<missing>"} />
        <StatusCell label={t.runningVms} ok={vms.running.length === 0} value={String(vms.running.length)} />
        <StatusCell label={t.staleVms} ok={vms.stale.length === 0} value={String(vms.stale.length)} />
        <StatusCell label={t.recommendedVmId} ok={Boolean(status?.vmidRange?.recommendedVmId)} value={status?.vmidRange?.recommendedVmId ? String(status.vmidRange.recommendedVmId) : "<none>"} />
        <StatusCell label={t.checkedAt} ok={Boolean(status?.checkedAt)} value={status?.checkedAt ? new Date(status.checkedAt).toLocaleString() : "<pending>"} />
      </div>
      {!!status?.issues.length && <StatusList title={t.issues} items={status.issues} kind="issue" />}
      {!!status?.warnings.length && <StatusList title={t.warnings} items={status.warnings} kind="warning" />}
    </section>
  );
}
