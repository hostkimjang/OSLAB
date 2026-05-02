import type { CatalogItem, JobSummary, LabStatus, RunSummary } from "@oslab/shared";
import { LabStatusPanel, List, Metric } from "../components";
import type { DashboardText } from "../model";

export function DashboardHome({
  t,
  catalog,
  jobs,
  activeJobs,
  runs,
  labStatus,
  labStatusLoading,
  onRefreshLab,
  onCleanupStale,
}: {
  t: DashboardText;
  catalog: { scenarios: CatalogItem[]; suites: CatalogItem[]; fixtures: CatalogItem[]; artifacts: CatalogItem[] };
  jobs: JobSummary[];
  activeJobs: JobSummary[];
  runs: RunSummary[];
  labStatus: LabStatus | null;
  labStatusLoading: boolean;
  onRefreshLab: () => void;
  onCleanupStale: () => void;
}) {
  return (
    <>
      <LabStatusPanel status={labStatus} loading={labStatusLoading} t={t} onRefresh={onRefreshLab} onCleanup={onCleanupStale} />
      <section className="grid">
        <Metric label={t.scenarioCount} value={catalog.scenarios.length} info={t.scenarioCountTooltip} t={t} />
        <Metric label={t.fixtureCount} value={catalog.fixtures.length} info={t.fixtureCountTooltip} t={t} />
        <Metric label={t.suiteCount} value={catalog.suites.length} info={t.suiteCountTooltip} t={t} />
        <Metric label={t.runningJobs} value={activeJobs.length} info={t.runningJobsTooltip} t={t} />
        <Metric label={t.runCount} value={runs.length} info={t.runCountTooltip} t={t} />
        <List title={t.recentJobs} items={jobs.slice(0, 8).map((job) => `${job.status} · ${job.title}`)} info={t.recentJobsTooltip} t={t} />
        <List title={t.recentRuns} items={runs.slice(0, 8).map((run) => `${run.status ?? "unknown"} · ${run.id}`)} info={t.recentRunsTooltip} t={t} />
      </section>
    </>
  );
}
