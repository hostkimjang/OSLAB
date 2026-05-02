import { useEffect, useRef, useState } from "react";
import type { RunEvidenceChecklist, RunEvidenceGroup, RunEvidenceItem, RunFileGroup, RunFileItem } from "@oslab/shared";
import type { DashboardText, Lang, ProgressEvent, RunDetail } from "../model";
import { apiText, buildResultSummary, formatBytes, formatDuration, formatHumanDateTime, formatPreviewContent, parseRunIdTimestamp } from "../lib";
import { InfoTooltip, StatusCell } from "./common";

const evidenceGroups: RunEvidenceGroup[] = ["core", "timeline", "outputs", "reports", "cleanup"];
const fileGroups: RunFileGroup[] = ["core", "timeline", "outputs", "reports", "cleanup", "other"];
const previewableFilePattern = /\.(json|jsonl|log|xml|html?|txt|csv|md|yaml|yml|ps1|sh|cmd|bat)$/i;

function isActiveRunStatus(status?: string | null) {
  return ["queued", "running", "pending", "in_progress"].includes(String(status || "").toLowerCase());
}

export function ResultDetail({
  runId,
  detail,
  progressEvents,
  t,
  lang,
  onSelectRun,
}: {
  runId: string;
  detail: RunDetail | null;
  progressEvents: ProgressEvent[];
  t: DashboardText;
  lang: Lang;
  onSelectRun: (runId: string) => void;
}) {
  const detailRef = useRef<HTMLDivElement | null>(null);
  const [previewPath, setPreviewPath] = useState<string>("");
  const isSuite = Boolean(detail && Array.isArray(detail.entries));

  useEffect(() => {
    setPreviewPath("");
  }, [runId]);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      detailRef.current?.scrollTo({ top: 0, left: 0 });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [runId, detail?.id]);

  if (!runId) {
    return <div className="panel"><h3>{t.resultDetail}</h3><p className="muted">{t.selectFile}</p></div>;
  }
  if (!detail) {
    return <div className="panel"><h3>{t.resultDetail}</h3><p className="muted">Loading...</p></div>;
  }
  const status = String(detail.status ?? "unknown");
  const statusMeta = detail.statusMeta || {};
  const summary = detail.summary || {};
  const entries = Array.isArray(detail.entries) ? [...detail.entries] : [];
  const sortedEntries = entries.sort((a, b) => Number(a.status === "passed") - Number(b.status === "passed"));
  const details = detail.details || {};
  const vm = details.vm || {};
  const assertions = details.assertions || {};
  const preflight = details.preflight || {};
  const fixtures = details.fixtures || {};
  const artifact = details.artifact || {};
  const outputs = details.outputs || {};
  const summaryCard = buildResultSummary(detail, progressEvents, t);
  const evidence = detail.evidence as RunEvidenceChecklist | undefined;
  const files = buildVisibleRunFiles(detail, isSuite);
  const evidencePending = isActiveRunStatus(status);
  const runIdDate = parseRunIdTimestamp(runId);
  const startedAt = detail.startedAt || detail.details?.startedAt || runIdDate;
  const completedAt = detail.completedAt || detail.details?.completedAt || null;
  const parentSuiteRunId = String(detail.parentSuiteRunId || detail.parentRunId || "");
  const isSuiteChildDetail = Boolean(parentSuiteRunId && parentSuiteRunId !== runId);
  const childScenarioLabel = detail.scenarioId || detail.scenarioPath || runId;
  return (
    <div ref={detailRef} className="panel resultDetail">
      <div className="detailHeader">
        <div>
          <h3>{t.resultDetail}</h3>
          <p className="muted">{runId}</p>
          {statusMeta.artifactStatus && statusMeta.artifactStatus !== status && (
            <p className="statusCorrection">{t.resultStatusCorrected}: {statusMeta.artifactStatus} -&gt; {status}</p>
          )}
        </div>
        <span className={`statusBadge ${status === "passed" ? "ready" : status === "failed" ? "blocked" : "degraded"}`}>{status}</span>
      </div>
      {isSuiteChildDetail && (
        <section className="suiteContextBanner" aria-label={t.suiteChildContext}>
          <div>
            <span className="eyebrow">{t.suiteChildContext}</span>
            <strong title={childScenarioLabel}>{childScenarioLabel}</strong>
            <small>{t.parentSuite}: {parentSuiteRunId}</small>
          </div>
          <button type="button" className="secondary" onClick={() => onSelectRun(parentSuiteRunId)}>
            {t.backToSuite}
          </button>
        </section>
      )}
      <section className="resultTimePanel" aria-label={t.resultTime}>
        <div className="resultTimeHeader">
          <h4 className="sectionTitleLine">
            <span>{t.resultTime}</span>
            <InfoTooltip text={t.resultTimeTooltip} label={t.infoTooltipLabel} />
          </h4>
          <p className="muted">{t.resultTimeHint}</p>
        </div>
        <div className="resultTimeGrid">
          <div className="resultTimeCell">
            <span>{t.resultStartedAt}</span>
            <strong>{formatHumanDateTime(startedAt, lang)}</strong>
          </div>
          <div className="resultTimeCell">
            <span>{t.resultCompletedAt}</span>
            <strong>{formatHumanDateTime(completedAt, lang)}</strong>
          </div>
          <div className="resultTimeCell">
            <span>{t.resultDuration}</span>
            <strong>{formatDuration(startedAt, completedAt, lang)}</strong>
          </div>
        </div>
      </section>
      <div className="summaryCallout">
        <div>
          <strong>{t.keyTakeaway}</strong>
          <p>{summaryCard.summary}</p>
        </div>
        <div>
          <strong>{t.nextAction}</strong>
          <p>{summaryCard.nextAction}</p>
        </div>
      </div>

      <EvidenceChecklistPanel checklist={evidence} t={t} onPreview={setPreviewPath} pending={evidencePending} />

      {isSuite ? (
        <>
          <h4>{t.suiteSummary}</h4>
          <div className="summaryGrid">
            {["total", "passed", "failed", "requiredFailed", "allowedFailed"].map((key) => (
              <StatusCell key={key} label={key} ok={key === "failed" ? Number(summary[key] || 0) === 0 : true} value={String(summary[key] ?? 0)} />
            ))}
          </div>
          <h4>{t.entries}</h4>
          <div className="entryList">
            {sortedEntries.map((entry: any) => (
              <div key={entry.id} className={`entryItem ${entry.status}`}>
                <strong>{entry.id}</strong>
                <span>{entry.status} · allowFailure={String(Boolean(entry.allowFailure))}</span>
                <small>{entry.failureClass || entry.error || entry.scenarioId || entry.scenarioPath}</small>
              </div>
            ))}
          </div>
          <Timeline events={progressEvents} t={t} />
        </>
      ) : (
        <>
          <div className="summaryGrid">
            <StatusCell label="scenario" ok value={detail.scenarioId || "<unknown>"} />
            <StatusCell label="failureClass" ok={!detail.failureClass} value={detail.failureClass || "<none>"} />
            <StatusCell label="guest" ok value={detail.selectedGuestChannel || "<none>"} />
            <StatusCell label="mode" ok value={details.mode || "<unknown>"} />
            <StatusCell label="vm" ok={Boolean(vm.destroyed || details.mode === "skeleton")} value={vm.id ? `${vm.id} · destroyed=${String(Boolean(vm.destroyed))}` : "<none>"} />
            <StatusCell label="preflight" ok={Number(preflight.failed || 0) === 0} value={preflight.total !== undefined ? `${preflight.total} total, ${preflight.failed || 0} failed` : "<none>"} />
            <StatusCell label="fixtures" ok={Number(fixtures.failed || 0) === 0} value={fixtures.total !== undefined ? `${fixtures.total} total, ${fixtures.failed || 0} failed` : "<none>"} />
            <StatusCell label="assertions" ok={Number(assertions.failed || 0) === 0} value={assertions.total !== undefined ? `${assertions.total} total, ${assertions.failed || 0} failed` : "<none>"} />
            <StatusCell label="artifact" ok value={artifact.uploadedBytes !== undefined ? `${artifact.uploadedFiles || 0} files, ${formatBytes(Number(artifact.uploadedBytes || 0))}` : details.artifactPath || "<none>"} />
            <StatusCell label="output" ok={Boolean(outputs.raw || outputs.normalized || details.mode === "skeleton")} value={outputs.collectedBytes !== undefined ? `${formatBytes(Number(outputs.collectedBytes || 0))}` : "<none>"} />
          </div>
          <Timeline events={progressEvents} t={t} />
        </>
      )}

      <h4 className="sectionTitleLine">
        <span>{t.files}</span>
        <InfoTooltip text={t.resultFilesTooltip} label={t.infoTooltipLabel} />
      </h4>
      <RunFileGrid runId={runId} files={files} t={t} isSuite={isSuite} onPreview={setPreviewPath} onSelectRun={onSelectRun} pending={evidencePending} />
      {previewPath && <ResultPreviewDialog runId={runId} relativePath={previewPath} t={t} onClose={() => setPreviewPath("")} />}
    </div>
  );
}

function RunFileGrid({
  runId,
  files,
  t,
  isSuite = false,
  onPreview,
  onSelectRun,
  pending = false,
}: {
  runId: string;
  files: RunFileItem[];
  t: DashboardText;
  isSuite?: boolean;
  onPreview: (relativePath: string) => void;
  onSelectRun?: (runId: string) => void;
  pending?: boolean;
}) {
  const groupLabel: Record<RunFileGroup, string> = {
    core: t.evidenceGroupCore,
    timeline: t.evidenceGroupTimeline,
    outputs: t.evidenceGroupOutputs,
    reports: t.evidenceGroupReports,
    cleanup: t.evidenceGroupCleanup,
    other: t.fileGroupOther,
  };
  const groupTooltip: Record<RunFileGroup, string> = {
    core: t.fileGroupCoreTooltip,
    timeline: t.fileGroupTimelineTooltip,
    outputs: t.fileGroupOutputsTooltip,
    reports: t.fileGroupReportsTooltip,
    cleanup: t.fileGroupCleanupTooltip,
    other: t.fileGroupOtherTooltip,
  };
  if (!files.length) {
    return <p className="muted">{t.noRunFiles}</p>;
  }
  const suiteChildGroups = isSuite ? groupSuiteChildFiles(files) : [];
  const topLevelFiles = isSuite ? files.filter((file) => !suiteChildRunId(file.relativePath)) : files;
  return (
    <div className="fileGroups">
      {isSuite && topLevelFiles.length > 0 && (
        <div className="suiteFileGroupIntro">
          <strong>{t.suiteRunFiles}</strong>
        </div>
      )}
      {fileGroups.map((group) => {
        const groupFiles = topLevelFiles.filter((file) => file.group === group);
        if (!groupFiles.length) return null;
        return (
          <section key={group} className="fileGroup" aria-label={groupLabel[group]}>
            <div className="fileGroupHeader">
              <strong className="sectionTitleLine">
                <span>{groupLabel[group]}</span>
                <InfoTooltip text={groupTooltip[group]} label={t.infoTooltipLabel} />
              </strong>
              <span>{groupFiles.length}</span>
            </div>
            <div className="fileLinks">
              {groupFiles.map((file) => (
                <RunFileChip key={file.relativePath} runId={runId} file={file} t={t} onPreview={onPreview} pending={pending} />
              ))}
            </div>
          </section>
        );
      })}
      {suiteChildGroups.length > 0 && (
        <section className="suiteChildFilesPanel" aria-label={t.suiteChildFiles}>
          <div className="suiteChildFilesHeader">
            <div>
              <strong className="sectionTitleLine">
                <span>{t.suiteChildFiles}</span>
                <InfoTooltip text={t.suiteChildFilesHint} label={t.infoTooltipLabel} />
              </strong>
              <small>{suiteChildGroups.length} {t.entries}</small>
            </div>
            <span>{files.length - topLevelFiles.length}</span>
          </div>
          <div className="suiteChildFileGroups">
            {suiteChildGroups.map((group) => (
              <section key={group.runId} className="suiteChildFileGroup" aria-label={group.runId}>
                <div className="suiteChildFileGroupHeader">
                  <div>
                    <strong title={group.runId}>{group.runId}</strong>
                    <small>{group.files.length} {t.files}</small>
                  </div>
                  {onSelectRun && (
                    <button type="button" className="secondary" onClick={() => onSelectRun(group.runId)}>
                      {t.openRunDetail}
                    </button>
                  )}
                </div>
                <div className="suiteChildFileLinks">
                  {group.files.map((file) => (
                    <RunFileChip
                      key={file.relativePath}
                      runId={runId}
                      file={file}
                      t={t}
                      onPreview={onPreview}
                      displayPath={suiteChildRelativePath(file.relativePath)}
                      compact
                      pending={pending}
                    />
                  ))}
                </div>
              </section>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function groupSuiteChildFiles(files: RunFileItem[]) {
  const groups = new Map<string, RunFileItem[]>();
  for (const file of files) {
    const childRunId = suiteChildRunId(file.relativePath);
    if (!childRunId) continue;
    const bucket = groups.get(childRunId) || [];
    bucket.push(file);
    groups.set(childRunId, bucket);
  }
  return Array.from(groups.entries())
    .map(([runId, groupFiles]) => ({ runId, files: groupFiles.sort(compareRunFiles) }))
    .sort((a, b) => a.runId.localeCompare(b.runId));
}

function suiteChildRunId(relativePath: string) {
  const parts = relativePath.replaceAll("\\", "/").split("/");
  return parts.length >= 3 && parts[0] === "scenarios" ? parts[1] : "";
}

function suiteChildRelativePath(relativePath: string) {
  const parts = relativePath.replaceAll("\\", "/").split("/");
  return parts.length >= 3 && parts[0] === "scenarios" ? parts.slice(2).join("/") : relativePath;
}

function RunFileChip({
  runId,
  file,
  t,
  onPreview,
  displayPath,
  compact = false,
  pending = false,
}: {
  runId: string;
  file: RunFileItem;
  t: DashboardText;
  onPreview: (relativePath: string) => void;
  displayPath?: string;
  compact?: boolean;
  pending?: boolean;
}) {
  const isPresent = file.status === "present";
  const displayStatus = pending && (file.status === "contractGap" || file.status === "missing") ? "pending" : file.status;
  const statusText =
    displayStatus === "present"
      ? t.evidencePresent
      : displayStatus === "pending"
        ? t.evidencePending
      : displayStatus === "contractGap"
        ? t.evidenceContractGap
        : displayStatus === "notApplicable"
          ? t.evidenceNotApplicable
          : t.evidenceMissing;
  return (
    <div className={`fileChip ${displayStatus} ${file.discovered ? "discovered" : ""} ${compact ? "compact" : ""}`}>
      <div className="fileChipHeader">
        <span className="fileTypeLabel">{isPresent ? (file.previewable ? t.preview : t.previewUnavailableShort) : statusText}</span>
        <span className="fileExpectedBadge">{file.required ? t.evidenceRequired : t.evidenceOptional}</span>
        {file.discovered && <span className="fileDiscoveredBadge">{t.fileDiscovered}</span>}
      </div>
      {isPresent ? (
        <button type="button" className="fileChipBody fileChipAction" onClick={() => onPreview(file.relativePath)} title={file.previewable ? t.preview : t.previewUnavailable}>
          <strong>{file.label}</strong>
          <small>{displayPath || file.relativePath}{file.size !== undefined && file.size !== null ? ` · ${formatBytes(file.size)}` : ""}</small>
        </button>
      ) : (
        <div className="fileChipBody" role="note" title={file.reason || file.description || t.fileMissingHint}>
          <strong>{file.label}</strong>
          <small>{displayPath || file.relativePath} · {file.reason || file.description || t.fileMissingHint}</small>
        </div>
      )}
    </div>
  );
}

function buildVisibleRunFiles(detail: RunDetail, isSuite: boolean): RunFileItem[] {
  if (Array.isArray(detail.files)) {
    return detail.files
      .map(normalizeRunFile)
      .filter((file): file is RunFileItem => Boolean(file))
      .sort(compareRunFiles);
  }
  const fallbackPaths = isSuite
    ? [
        ["suite.json", "suite.json"],
        ["suite.html", "reports/suite.html"],
        ["suite.junit.xml", "reports/suite.junit.xml"],
      ]
    : [
        ["run.json", "run.json"],
        ["result.json", "reports/result.json"],
        ["progress.log", "logs/progress.log"],
        ["progress.jsonl", "logs/progress.jsonl"],
        ["actual-output.json", "raw/actual-output.json"],
        ["inventory.json", "normalized/inventory.json"],
        ["command-result.json", "normalized/command-result.json"],
        ["inventory.analysis.json", "reports/inventory.analysis.json"],
        ["result.html", "reports/result.html"],
      ];
  return fallbackPaths.map(([label, relativePath]) => ({
    label,
    group: inferRunFileGroup(relativePath),
    relativePath,
    status: "present",
    required: false,
    size: 0,
    modifiedAt: "",
    previewable: previewableFilePattern.test(relativePath),
    discovered: false,
  }));
}

function normalizeRunFile(value: any): RunFileItem | null {
  const relativePath = String(value?.relativePath || "").replaceAll("\\", "/").replace(/^\/+/, "");
  if (!relativePath) return null;
  return {
    label: String(value?.label || relativePath.split("/").pop() || relativePath),
    group: fileGroups.includes(value?.group) ? value.group : inferRunFileGroup(relativePath),
    relativePath,
    status: ["present", "missing", "notApplicable", "contractGap"].includes(value?.status) ? value.status : "present",
    required: Boolean(value?.required),
    size: value?.size === null || value?.size === undefined ? null : Number(value.size || 0),
    modifiedAt: value?.modifiedAt === null || value?.modifiedAt === undefined ? null : String(value.modifiedAt || ""),
    previewable: value?.previewable !== undefined ? Boolean(value.previewable) : previewableFilePattern.test(relativePath),
    discovered: Boolean(value?.discovered),
    reason: typeof value?.reason === "string" ? value.reason : undefined,
    description: typeof value?.description === "string" ? value.description : undefined,
  };
}

function inferRunFileGroup(relativePath: string): RunFileGroup {
  if (relativePath === "run.json" || relativePath === "suite.json") return "core";
  if (relativePath.startsWith("logs/")) return "timeline";
  if (relativePath.startsWith("raw/") || relativePath.startsWith("normalized/")) return "outputs";
  if (relativePath.startsWith("reports/")) return "reports";
  if (relativePath.startsWith("cleanup/")) return "cleanup";
  return "other";
}

function compareRunFiles(a: RunFileItem, b: RunFileItem) {
  const groupDelta = fileGroups.indexOf(a.group) - fileGroups.indexOf(b.group);
  if (groupDelta) return groupDelta;
  return a.relativePath.localeCompare(b.relativePath);
}

function EvidenceChecklistPanel({
  checklist,
  t,
  onPreview,
  pending = false,
}: {
  checklist?: RunEvidenceChecklist;
  t: DashboardText;
  onPreview: (relativePath: string) => void;
  pending?: boolean;
}) {
  if (!checklist?.items?.length) return null;
  const pendingGaps = pending ? checklist.items.filter((item) => item.status === "contractGap").length : 0;
  const visibleContractGaps = pending ? 0 : checklist.contractGaps;
  const groupLabel: Record<RunEvidenceGroup, string> = {
    core: t.evidenceGroupCore,
    timeline: t.evidenceGroupTimeline,
    outputs: t.evidenceGroupOutputs,
    reports: t.evidenceGroupReports,
    cleanup: t.evidenceGroupCleanup,
  };
  const groupTooltip: Record<RunEvidenceGroup, string> = {
    core: t.evidenceGroupCoreTooltip,
    timeline: t.evidenceGroupTimelineTooltip,
    outputs: t.evidenceGroupOutputsTooltip,
    reports: t.evidenceGroupReportsTooltip,
    cleanup: t.evidenceGroupCleanupTooltip,
  };
  return (
    <section className="evidencePanel" aria-label={t.evidenceChecklist}>
      <div className="evidenceHeader">
        <div>
          <h4 className="sectionTitleLine">
            <span>{t.evidenceChecklist}</span>
            <InfoTooltip text={t.evidenceChecklistTooltip} label={t.infoTooltipLabel} />
          </h4>
          <p className="muted">
            {t.evidenceSummary}: {checklist.present}/{checklist.total} {t.evidencePresent}
            {pendingGaps ? ` · ${pendingGaps} ${t.evidencePending}` : ""}
            {visibleContractGaps ? ` · ${visibleContractGaps} ${t.evidenceContractGap}` : ""}
          </p>
        </div>
        <span className={`statusBadge ${pendingGaps ? "degraded" : visibleContractGaps ? "blocked" : "ready"}`}>
          {pendingGaps ? t.evidencePending : visibleContractGaps ? t.evidenceContractGap : t.readyLabel}
        </span>
      </div>
      {evidenceGroups.map((group) => {
        const items = checklist.items.filter((item) => item.group === group);
        if (!items.length) return null;
        return (
          <div key={group} className="evidenceGroup">
            <strong className="sectionTitleLine">
              <span>{groupLabel[group]}</span>
              <InfoTooltip text={groupTooltip[group]} label={t.infoTooltipLabel} />
            </strong>
            <div className="evidenceRows">
              {items.map((item) => <EvidenceRow key={item.key} item={item} t={t} onPreview={onPreview} pending={pending} />)}
            </div>
          </div>
        );
      })}
    </section>
  );
}

function EvidenceRow({ item, t, onPreview, pending = false }: { item: RunEvidenceItem; t: DashboardText; onPreview: (relativePath: string) => void; pending?: boolean }) {
  const canPreview = item.status === "present" && item.previewable && item.relativePath;
  const infoText = evidenceItemInfo(item, t);
  const displayStatus = pending && item.status === "contractGap" ? "pending" : item.status;
  const statusText =
    displayStatus === "present"
      ? t.evidencePresent
      : displayStatus === "pending"
        ? t.evidencePending
      : displayStatus === "contractGap"
        ? t.evidenceContractGap
        : displayStatus === "notApplicable"
          ? t.evidenceNotApplicable
          : t.evidenceMissing;
  return (
    <div className={`evidenceRowWrap ${displayStatus}`}>
      <button
        type="button"
        className={`evidenceRow ${displayStatus}`}
        onClick={() => {
          if (canPreview) onPreview(item.relativePath!);
        }}
        disabled={!canPreview}
        title={item.reason || item.description}
      >
        <span className={`miniDot ${displayStatus === "present" || displayStatus === "notApplicable" ? "ok" : displayStatus === "contractGap" ? "bad" : displayStatus === "pending" ? "pending" : ""}`} />
        <span className="evidenceMain">
          <strong>{item.label}</strong>
          <small>{item.relativePath || item.reason || item.description}</small>
        </span>
        <span className="evidenceMeta">
          <b>{statusText}</b>
          <small>{item.required ? t.evidenceRequired : t.evidenceOptional}{item.size ? ` · ${formatBytes(item.size)}` : ""}</small>
        </span>
      </button>
      <span className="evidenceRowInfo">
        <InfoTooltip text={infoText} label={`${item.label} ${t.evidenceItemTooltipLabel}`} />
      </span>
    </div>
  );
}

function evidenceItemInfo(item: RunEvidenceItem, t: DashboardText) {
  const key = String(item.key || "").toLowerCase();
  const label = String(item.label || "").toLowerCase();
  const path = String(item.relativePath || "").replaceAll("\\", "/").toLowerCase();
  const text = `${key} ${label} ${path}`;
  if (path === "run.json" || text.includes("run.json")) return t.evidenceRunJsonTooltip;
  if (path === "suite.json" || text.includes("suite.json")) return t.evidenceSuiteJsonTooltip;
  if (text.includes("progress.jsonl")) return t.evidenceProgressJsonlTooltip;
  if (text.includes("progress.log")) return t.evidenceProgressLogTooltip;
  if (text.includes("actual-output.json")) return t.evidenceActualOutputTooltip;
  if (text.includes("inventory.analysis.json")) return t.evidenceInventoryAnalysisTooltip;
  if (text.includes("inventory.json")) return t.evidenceInventoryTooltip;
  if (text.includes("command-result.json")) return t.evidenceCommandResultTooltip;
  if (text.includes("product-steps.json")) return t.evidenceProductStepsTooltip;
  if (text.includes("stdout")) return t.evidenceStdoutTooltip;
  if (text.includes("stderr")) return t.evidenceStderrTooltip;
  if (text.includes("result.json")) return t.evidenceResultJsonTooltip;
  if (text.includes("result.html")) return t.evidenceResultHtmlTooltip;
  if (text.includes("result.junit.xml")) return t.evidenceResultJunitTooltip;
  if (text.includes("suite.html")) return t.evidenceSuiteHtmlTooltip;
  if (text.includes("suite.junit.xml")) return t.evidenceSuiteJunitTooltip;
  if (text.includes("cleanup")) return t.evidenceCleanupTooltip;
  if (text.includes("child") || text.includes("entry")) return t.evidenceChildRunsTooltip;
  return t.evidenceDefaultItemTooltip;
}

export function Timeline({ events, t }: { events: ProgressEvent[]; t: DashboardText }) {
  return (
    <div className="timeline">
      <h4 className="sectionTitleLine">
        <span>{t.timeline}</span>
        <InfoTooltip text={t.timelineTooltip} label={t.infoTooltipLabel} />
      </h4>
      {!events.length && <p className="muted">{t.noTimeline}</p>}
      {events.map((event, index) => (
        <div key={`${event.timestamp}-${event.phase}-${index}`} className={`timelineItem ${event.status || "running"}`}>
          <span>{event.status || "running"}</span>
          <strong>{event.message || event.phase}</strong>
          <small>{event.phase} · {event.timestamp ? new Date(event.timestamp).toLocaleTimeString() : ""}</small>
        </div>
      ))}
    </div>
  );
}

export function ResultPreviewDialog({
  runId,
  relativePath,
  t,
  onClose,
}: {
  runId: string;
  relativePath: string;
  t: DashboardText;
  onClose: () => void;
}) {
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(false);
  const dialogRef = useRef<HTMLElement | null>(null);
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);
  const isHtmlPreview = /\.html?$/i.test(relativePath);
  const fileUrl = `/api/runs/${encodeURIComponent(runId)}/file?path=${encodeURIComponent(relativePath)}`;

  useEffect(() => {
    if (!previewableFilePattern.test(relativePath)) {
      setContent(t.previewUnavailable);
      setLoading(false);
      return;
    }
    if (isHtmlPreview) {
      setContent("");
      setLoading(false);
      return;
    }
    let cancelled = false;
    setContent("");
    setLoading(true);
    apiText(fileUrl)
      .then((text) => {
        if (cancelled) return;
        setContent(formatPreviewContent(relativePath, text));
      })
      .catch(() => {
        if (cancelled) return;
        setContent(t.previewUnavailable);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [fileUrl, isHtmlPreview, relativePath, t.previewUnavailable]);

  useEffect(() => {
    const previousActiveElement = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    closeButtonRef.current?.focus();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = Array.from(
        dialogRef.current?.querySelectorAll<HTMLElement>("a[href], button:not([disabled]), [tabindex]:not([tabindex='-1'])") || [],
      ).filter((element) => !element.hasAttribute("disabled"));
      if (!focusable.length) {
        event.preventDefault();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
      previousActiveElement?.focus();
    };
  }, [onClose]);

  return (
    <div
      className="previewOverlay"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section ref={dialogRef} className="previewDialog" role="dialog" aria-modal="true" aria-labelledby="result-preview-title">
        <header className="previewDialogHeader">
          <div>
            <p className="eyebrow">{t.preview}</p>
            <h3 id="result-preview-title">{t.previewPanel}</h3>
            <p className="muted previewPath">{relativePath}</p>
          </div>
          <div className="previewDialogActions">
            <a className="secondary previewOpenLink" href={fileUrl} target="_blank" rel="noreferrer noopener">
              {t.openInNewTab}
            </a>
            <button
              ref={closeButtonRef}
              type="button"
              className="previewCloseButton"
              onClick={onClose}
              aria-label={t.closePreview}
              title={t.closePreview}
            >
              <span aria-hidden="true">×</span>
            </button>
          </div>
        </header>
        <div className="previewBody">
          {loading && <p className="muted">{t.previewLoading}</p>}
          {isHtmlPreview ? (
            <iframe
              className="previewFrame"
              title={`${t.previewPanel}: ${relativePath}`}
              src={fileUrl}
              sandbox=""
              referrerPolicy="no-referrer"
            />
          ) : (
            !loading && <pre>{content || t.previewEmpty}</pre>
          )}
        </div>
      </section>
    </div>
  );
}
