import type { RunSummary } from "@oslab/shared";
import { ResultDetail } from "../components";
import { formatHumanDateTime, relativeTime } from "../lib";
import type { DashboardText, Lang, ProgressEvent, ResultEvidenceFilter, ResultFilter, ResultIssueFilter, ResultKindFilter, RunDetail } from "../model";

const resultFilters: ResultFilter[] = ["all", "failed", "passed", "running", "stale"];

function isActiveRunStatus(status?: string | null) {
  return ["queued", "running", "pending", "in_progress"].includes(String(status || "").toLowerCase());
}

function filterLabel(value: ResultFilter, t: DashboardText) {
  if (value === "all") return t.resultFilterAll;
  if (value === "failed") return t.resultFilterFailed;
  if (value === "passed") return t.resultFilterPassed;
  if (value === "running") return t.resultFilterRunning;
  return t.resultFilterStale;
}

export function ResultsExplorer({
  t,
  lang,
  runs,
  query,
  filter,
  kindFilter,
  issueFilter,
  evidenceFilter,
  selectedRunId,
  detail,
  progressEvents,
  listCollapsed,
  onQuery,
  onFilter,
  onKindFilter,
  onIssueFilter,
  onEvidenceFilter,
  onToggleList,
  onSelectRun,
}: {
  t: DashboardText;
  lang: Lang;
  runs: RunSummary[];
  query: string;
  filter: ResultFilter;
  kindFilter: ResultKindFilter;
  issueFilter: ResultIssueFilter;
  evidenceFilter: ResultEvidenceFilter;
  selectedRunId: string;
  detail: RunDetail | null;
  progressEvents: ProgressEvent[];
  listCollapsed: boolean;
  onQuery: (query: string) => void;
  onFilter: (filter: ResultFilter) => void;
  onKindFilter: (filter: ResultKindFilter) => void;
  onIssueFilter: (filter: ResultIssueFilter) => void;
  onEvidenceFilter: (filter: ResultEvidenceFilter) => void;
  onToggleList: () => void;
  onSelectRun: (runId: string) => void;
}) {
  const selectedParentRunId = String(detail?.parentRunId || detail?.parentSuiteRunId || "");
  return (
    <section className={`resultsGrid ${listCollapsed ? "resultsGridCollapsed" : ""}`}>
      <div className={`resultList ${listCollapsed ? "collapsed" : ""}`}>
        {listCollapsed ? (
          <div className="resultListRail">
            <button
              type="button"
              className="iconButton resultListToggle"
              onClick={onToggleList}
              aria-label={t.resultListExpand}
              title={t.resultListExpand}
              aria-expanded={false}
            >
              <span aria-hidden="true">›</span>
            </button>
            <span className="resultListRailCount" title={t.resultListCollapsed}>
              {runs.length}
            </span>
          </div>
        ) : (
          <>
        <div className="resultListHeader">
          <div>
            <strong>{t.resultList}</strong>
            <span>{runs.length} {t.results}</span>
          </div>
          <button
            type="button"
            className="iconButton resultListToggle"
            onClick={onToggleList}
            aria-label={t.resultListCollapse}
            title={t.resultListCollapse}
            aria-expanded={true}
          >
            <span aria-hidden="true">‹</span>
          </button>
        </div>
        <div className="resultToolbar">
          <input placeholder={t.resultSearch} value={query} onChange={(event) => onQuery(event.target.value)} />
          <div className="segmented resultFilter">
            {resultFilters.map((value) => (
              <button key={value} type="button" className={filter === value ? "active" : ""} aria-pressed={filter === value} onClick={() => onFilter(value)}>
                {filterLabel(value, t)}
              </button>
            ))}
          </div>
          <div className="resultAdvancedFilters" aria-label={t.resultIssueFilter}>
            <label>
              <span>{t.resultKindFilter}</span>
              <select value={kindFilter} onChange={(event) => onKindFilter(event.target.value as ResultKindFilter)}>
                <option value="all">{t.resultKindAll}</option>
                <option value="run">{t.resultKindRuns}</option>
                <option value="suite">{t.resultKindSuites}</option>
              </select>
            </label>
            <label>
              <span>{t.resultIssueFilter}</span>
              <select value={issueFilter} onChange={(event) => onIssueFilter(event.target.value as ResultIssueFilter)}>
                <option value="all">{t.resultIssueAll}</option>
                <option value="provider_failure">{t.resultIssueProvider}</option>
                <option value="preflight_failure">{t.resultIssuePreflight}</option>
                <option value="assertion_failure">{t.resultIssueAssertion}</option>
                <option value="run_failure">{t.resultIssueRunFailure}</option>
                <option value="suite_entry_failure">{t.resultIssueSuiteEntry}</option>
                <option value="required_failed">{t.resultIssueRequiredFailed}</option>
                <option value="allowed_failed">{t.resultIssueAllowedFailed}</option>
                <option value="cancelled">{t.resultIssueCancelled}</option>
                <option value="contract_gaps">{t.resultIssueContractGaps}</option>
              </select>
            </label>
            <label>
              <span>{t.resultEvidenceFilter}</span>
              <select value={evidenceFilter} onChange={(event) => onEvidenceFilter(event.target.value as ResultEvidenceFilter)}>
                <option value="all">{t.resultEvidenceAll}</option>
                <option value="clean">{t.resultEvidenceClean}</option>
                <option value="contract_gaps">{t.resultEvidenceGaps}</option>
              </select>
            </label>
          </div>
        </div>
        <div className="resultListBody">
          {runs.length ? (
            runs.map((run) => {
              const contractGaps = Number(run.evidenceSummary?.contractGaps || 0);
              const evidencePending = isActiveRunStatus(run.status) && contractGaps > 0;
              const visibleContractGaps = evidencePending ? 0 : contractGaps;
              const failureMeta = run.failureClasses?.length ? run.failureClasses.join(", ") : run.failureClass;
              const suiteMeta = run.kind === "suite" ? `${run.suiteId || `${run.entries || 0} entries`}${Number(run.requiredFailed || 0) || Number(run.allowedFailed || 0) ? ` · required ${run.requiredFailed || 0} / allowed ${run.allowedFailed || 0}` : ""}` : "";
              const lineageMeta = run.kind === "suite" ? suiteMeta : run.scenarioId || run.scenarioPath;
              const isSelected = selectedRunId === run.id || selectedParentRunId === run.id || Boolean(selectedRunId && selectedRunId.startsWith(`${run.id}-`));
              return (
                <button key={run.id} className={`resultRow ${isSelected ? "selected" : ""}`} onClick={() => onSelectRun(run.id)}>
                  <span className={`dot ${run.status ?? "unknown"}`} />
                  <span className="resultMain">
                    <strong title={run.id}>{run.id}</strong>
                    <small title={run.statusMeta?.reason || formatHumanDateTime(run.updatedAt, lang)}>
                      {run.kind} · {run.status ?? "unknown"} · {relativeTime(run.updatedAt)} · {formatHumanDateTime(run.updatedAt, lang)}
                    </small>
                    {(lineageMeta || failureMeta || evidencePending || visibleContractGaps > 0) && (
                      <span className="resultMetaLine">
                        {lineageMeta && <span className="metaPill" title={run.scenarioPath || run.suiteId || lineageMeta}>{lineageMeta}</span>}
                        {failureMeta && <span className="metaPill warning">{failureMeta}</span>}
                        {evidencePending && <span className="metaPill pending">{contractGaps} {t.evidencePending}</span>}
                        {visibleContractGaps > 0 && <span className="metaPill danger">{visibleContractGaps} {t.evidenceContractGap}</span>}
                      </span>
                    )}
                    {run.artifactStatus && run.artifactStatus !== run.status && <small className="statusCorrection">{t.resultStatusCorrected}: {run.artifactStatus} -&gt; {run.status}</small>}
                  </span>
                  <span className={`rowBadge ${run.status ?? "unknown"}`}>{run.status ?? "unknown"}</span>
                </button>
              );
            })
          ) : (
            <div className="resultEmpty" role="status">
              <strong>{t.noResults}</strong>
              <small>{t.noResultsHint}</small>
            </div>
          )}
        </div>
          </>
        )}
      </div>
      <ResultDetail runId={selectedRunId} detail={detail} progressEvents={progressEvents} t={t} lang={lang} onSelectRun={onSelectRun} />
    </section>
  );
}
