"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { ArtifactPathCheck, ArtifactUploadSummary, CatalogItem, JobSummary, LabCleanupResponse, LabStatus, RunSummary, SyntaxValidationResult } from "@oslab/shared";
import { ArtifactManagerDialog, ArtifactStatus, ArtifactStudio, CatalogEditor, CommandPreview, FixtureCreateDialog, GlobalRunBanner, InfoTooltip, LabStatusPanel, LanguageSwitch, RunReadinessFlow, RunStepSection, ScenarioBuilderPanel, ScenarioCreateDialog, SuiteBuilderPanel, SuiteCreateDialog, type FixtureCreateDraft, type ScenarioCreateDraft, type SuiteCreateDraft } from "./components";
import { apiGet, apiPost, apiText, apiUploadFiles, apiUploadWithProgress, buildCommandPreview, formatBytes, getApiBaseUrl, parseEventData, stableStringify, tabTitle } from "./lib";
import { CUSTOM_ARTIFACT, RECENT_ARTIFACTS_KEY, defaultRequest, text, type EditorState, type EditorTab, type Lang, type ProgressEvent, type ResultEvidenceFilter, type ResultFilter, type ResultIssueFilter, type ResultKindFilter, type RunDetail, type ScenarioBuilderModel, type SuiteBuilderModel, type SuiteBuilderRun, type Tab } from "./model";
import { DashboardHome } from "./sections/DashboardHome";
import { LoadingScreen, LoginScreen } from "./sections/LoginScreens";
import { ResultsExplorer } from "./sections/ResultsExplorer";

const SCENARIO_ARTIFACT_HINTS: Record<string, string[]> = {
  "demo-agent-steps": ["demo-agent-cli"],
  "demo-c-hello": ["hello-c"],
  "demo-c-unit": ["c-unit"],
  "demo-fixture-state": ["fixture-state-reader"],
  "demo-powershell-system": ["powershell-system"],
  "demo-python-hello": ["hello-python"],
  "demo-python-http-service": ["python-http-service"],
  "demo-python-unittest": ["python-unittest"],
  "fake-agent-cli-smoke": ["fake-agent-installer"],
  "fake-artifact-smoke": ["fake-scanner"],
  "fake-installer-smoke": ["fake-installer"],
};

const GENERIC_SCENARIO_TOKENS = new Set(["demo", "example", "fake", "failure", "intentional", "local", "smoke", "windows"]);

type ArtifactUploadUiState = {
  kind: "file" | "folder";
  phase: "selected" | "uploading" | "uploaded" | "failed";
  name: string;
  fileCount: number;
  size: number;
  loaded?: number;
  total?: number;
  percent?: number | null;
  path?: string;
  message?: string;
};

function basename(value: string) {
  return value.replaceAll("\\", "/").split("/").pop() || value;
}

function normalizeArtifactKey(value: string) {
  return basename(value)
    .replace(/\.(example|local)\.ya?ml$/i, "")
    .replace(/\.(ps1|zip|exe|msi|cmd|bat|py|c|json|txt)$/i, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function tokenSet(value: string) {
  return normalizeArtifactKey(value)
    .split("-")
    .filter((token) => token && !GENERIC_SCENARIO_TOKENS.has(token));
}

function fileRelativePath(file: File): string {
  return (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name;
}

function folderUploadSummary(files: File[]) {
  const firstPath = files[0] ? fileRelativePath(files[0]) : "";
  const rootName = firstPath.split("/")[0] || "folder";
  const size = files.reduce((sum, file) => sum + file.size, 0);
  return { rootName, size };
}

function recommendArtifactsForScenario(scenarioPath: string, artifacts: CatalogItem[]) {
  const scenarioKey = normalizeArtifactKey(scenarioPath);
  if (!scenarioKey) return [];

  const preferredKeys = SCENARIO_ARTIFACT_HINTS[scenarioKey] || [];
  const requiresExplicitMatch = preferredKeys.length > 0;
  const scenarioTokens = tokenSet(scenarioPath);
  const scenarioCompact = scenarioTokens.join("-");

  return artifacts
    .map((item) => {
      const artifactKey = normalizeArtifactKey(item.path);
      const artifactTokens = tokenSet(item.path);
      const artifactCompact = artifactTokens.join("-");
      const exactHint = preferredKeys.includes(artifactKey);
      const hintMatch = preferredKeys.some((key) => artifactKey === key || artifactKey.endsWith(`-${key}`));
      const overlap = scenarioTokens.filter((token) => artifactTokens.includes(token)).length;
      let score = hintMatch ? 100 : 0;
      score += overlap * 12;
      if (scenarioCompact && artifactCompact && scenarioCompact.includes(artifactCompact)) score += 30;
      if (scenarioCompact && artifactCompact && artifactCompact.includes(scenarioCompact)) score += 30;
      if (exactHint) score += 20;
      return { ...item, score };
    })
    .filter((item) => (requiresExplicitMatch ? item.score >= 100 : item.score >= 18))
    .sort((a, b) => b.score - a.score || a.path.localeCompare(b.path))
    .slice(0, 3);
}

function isActiveRunStatus(status?: string | null) {
  return ["queued", "running", "pending", "in_progress"].includes(String(status || "").toLowerCase());
}

function progressEventsFromJobLog(log: string): ProgressEvent[] {
  const lines = log
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  return lines.slice(-80).map((line) => {
    const tagMatch = line.match(/^\[(OK|FAIL|ERROR|WARN|INFO|\.\.)\]\s*(.*)$/i);
    const tag = tagMatch?.[1]?.toUpperCase();
    const rawMessage = tagMatch?.[2]?.trim() || line;
    const phaseMatch = rawMessage.match(/^\[([^\]]+)\]\s*(.*)$/);
    const phase = phaseMatch?.[1] || "job";
    const message = phaseMatch?.[2] || rawMessage;
    const status =
      tag === "OK"
        ? "done"
        : tag === "FAIL" || tag === "ERROR"
          ? "failed"
          : tag === "WARN"
            ? "warning"
            : "running";
    return { phase, status, message };
  });
}

export function DashboardPage() {
  const [lang, setLang] = useState<Lang>("ko");
  const t = text[lang];
  const [me, setMe] = useState<any>(undefined);
  const [login, setLogin] = useState({ username: "", password: "" });
  const [tab, setTab] = useState<Tab>("dashboard");
  const [notice, setNotice] = useState("");
  const [catalog, setCatalog] = useState<{ scenarios: CatalogItem[]; suites: CatalogItem[]; fixtures: CatalogItem[]; artifacts: CatalogItem[] }>({
    scenarios: [],
    suites: [],
    fixtures: [],
    artifacts: [],
  });
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [labStatus, setLabStatus] = useState<LabStatus | null>(null);
  const [labStatusLoading, setLabStatusLoading] = useState(false);
  const [artifactCheck, setArtifactCheck] = useState<ArtifactPathCheck | null>(null);
  const [artifactChecking, setArtifactChecking] = useState(false);
  const [selectedRunId, setSelectedRunId] = useState("");
  const [runDetail, setRunDetail] = useState<RunDetail | null>(null);
  const [progressEvents, setProgressEvents] = useState<ProgressEvent[]>([]);
  const selectedRunIdRef = useRef("");
  const [resultQuery, setResultQuery] = useState("");
  const [resultFilter, setResultFilter] = useState<ResultFilter>("all");
  const [resultKindFilter, setResultKindFilter] = useState<ResultKindFilter>("all");
  const [resultIssueFilter, setResultIssueFilter] = useState<ResultIssueFilter>("all");
  const [resultEvidenceFilter, setResultEvidenceFilter] = useState<ResultEvidenceFilter>("all");
  const [resultListCollapsed, setResultListCollapsed] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [suitePolicy, setSuitePolicy] = useState<{ allowFailure: number; disabled: number; entries: number; maxParallel: number | null } | null>(null);
  const [editors, setEditors] = useState<Record<EditorTab, EditorState>>({
    scenarios: { selectedPath: "", content: "", originalContent: "", query: "", isEditing: false },
    fixtures: { selectedPath: "", content: "", originalContent: "", query: "", isEditing: false },
    suites: { selectedPath: "", content: "", originalContent: "", query: "", isEditing: false },
  });
  const [editorListCollapsed, setEditorListCollapsed] = useState<Record<EditorTab, boolean>>({
    scenarios: false,
    fixtures: false,
    suites: false,
  });
  const [syntaxChecks, setSyntaxChecks] = useState<Record<EditorTab, SyntaxValidationResult | null>>({
    scenarios: null,
    fixtures: null,
    suites: null,
  });
  const [syntaxChecking, setSyntaxChecking] = useState<Record<EditorTab, boolean>>({
    scenarios: false,
    fixtures: false,
    suites: false,
  });
  const [runForm, setRunForm] = useState(defaultRequest);
  const [selectedScenarioPath, setSelectedScenarioPath] = useState("");
  const [selectedSuitePath, setSelectedSuitePath] = useState("");
  const [selectedArtifactPath, setSelectedArtifactPath] = useState(CUSTOM_ARTIFACT);
  const [recentArtifacts, setRecentArtifacts] = useState<string[]>([]);
  const [artifactUploadFile, setArtifactUploadFile] = useState<File | null>(null);
  const [artifactUploadFolderFiles, setArtifactUploadFolderFiles] = useState<File[]>([]);
  const [artifactUploadStatus, setArtifactUploadStatus] = useState<ArtifactUploadUiState | null>(null);
  const [artifactUploading, setArtifactUploading] = useState(false);
  const [artifactFolderUploading, setArtifactFolderUploading] = useState(false);
  const [artifactManagerOpen, setArtifactManagerOpen] = useState(false);
  const artifactUploadInputRef = useRef<HTMLInputElement | null>(null);
  const artifactFolderInputRef = useRef<HTMLInputElement | null>(null);
  const [selectedJob, setSelectedJob] = useState<string | null>(null);
  const [jobLog, setJobLog] = useState("");
  const [isLaunching, setIsLaunching] = useState(false);
  const [scenarioBuilder, setScenarioBuilder] = useState<ScenarioBuilderModel | null>(null);
  const [scenarioBuilderError, setScenarioBuilderError] = useState("");
  const [scenarioBuilderBaseline, setScenarioBuilderBaseline] = useState("");
  const [scenarioBuilderExpanded, setScenarioBuilderExpanded] = useState(false);
  const [scenarioCreateOpen, setScenarioCreateOpen] = useState(false);
  const [fixtureCreateOpen, setFixtureCreateOpen] = useState(false);
  const [suiteBuilder, setSuiteBuilder] = useState<SuiteBuilderModel | null>(null);
  const [suiteBuilderError, setSuiteBuilderError] = useState("");
  const [suiteBuilderBaseline, setSuiteBuilderBaseline] = useState("");
  const [suiteAddScenarioPath, setSuiteAddScenarioPath] = useState("");
  const [suiteCreateOpen, setSuiteCreateOpen] = useState(false);
  const consoleRef = useRef<HTMLPreElement | null>(null);
  const syntaxRequestRef = useRef<Record<EditorTab, number>>({ scenarios: 0, fixtures: 0, suites: 0 });
  const builderInspectRequestRef = useRef({ scenarios: 0, suites: 0 });
  const activeJobs = useMemo(() => jobs.filter((job) => job.status === "running" || job.status === "queued"), [jobs]);
  const selectedJobSummary = useMemo(() => jobs.find((job) => job.id === selectedJob), [jobs, selectedJob]);
  const effectiveJobSummary = selectedJobSummary || activeJobs[0] || null;
  const effectiveJobId = selectedJob || effectiveJobSummary?.id || null;
  const selectedRunParentId = String(runDetail?.parentRunId || runDetail?.parentSuiteRunId || "");
  const liveJobProgressEvents = useMemo(() => progressEventsFromJobLog(jobLog), [jobLog]);
  const resultProgressEvents = useMemo(() => {
    if (progressEvents.length) return progressEvents;
    if (!runDetail || !liveJobProgressEvents.length) return progressEvents;
    const detailStatus = String(runDetail.status || "");
    const detailRunId = String(runDetail.id || selectedRunId || "");
    const parentRunId = String(runDetail.parentRunId || runDetail.parentSuiteRunId || "");
    const jobMatchesDetail =
      Boolean(effectiveJobSummary) &&
      (effectiveJobSummary?.runId === selectedRunId ||
        effectiveJobSummary?.runId === detailRunId ||
        (parentRunId && effectiveJobSummary?.runId === parentRunId) ||
        effectiveJobSummary?.id === runDetail.jobId ||
        (isActiveRunStatus(detailStatus) && isActiveRunStatus(effectiveJobSummary?.status)));
    return jobMatchesDetail ? liveJobProgressEvents : progressEvents;
  }, [effectiveJobSummary, liveJobProgressEvents, progressEvents, runDetail, selectedRunId]);
  const scenarioBuilderDirty = useMemo(
    () => Boolean(scenarioBuilder && stableStringify(scenarioBuilder) !== scenarioBuilderBaseline),
    [scenarioBuilder, scenarioBuilderBaseline],
  );
  const suiteBuilderDirty = useMemo(
    () => Boolean(suiteBuilder && stableStringify(suiteBuilder) !== suiteBuilderBaseline),
    [suiteBuilder, suiteBuilderBaseline],
  );
  const dirtyEditorTabs = useMemo(() => {
    const dirty = new Set<EditorTab>();
    (Object.keys(editors) as EditorTab[]).forEach((kind) => {
      if (editors[kind].content !== editors[kind].originalContent) {
        dirty.add(kind);
      }
    });
    if (scenarioBuilderDirty) dirty.add("scenarios");
    if (suiteBuilderDirty) dirty.add("suites");
    return dirty;
  }, [editors, scenarioBuilderDirty, suiteBuilderDirty]);
  const hasDirtyEditors = dirtyEditorTabs.size > 0;
  const filteredRuns = useMemo(() => {
    return runs.filter((run) => {
      const matchesFilter =
        resultFilter === "all" ||
        (resultFilter === "failed" && run.status === "failed") ||
        (resultFilter === "passed" && run.status === "passed") ||
        (resultFilter === "running" && run.status === "running") ||
        (resultFilter === "stale" && run.status === "stale");
      const contractGaps = Number(run.evidenceSummary?.contractGaps || 0);
      const finalizedContractGaps = isActiveRunStatus(run.status) ? 0 : contractGaps;
      const failureClasses = run.failureClasses?.length ? run.failureClasses : run.failureClass ? [run.failureClass] : [];
      const matchesKind = resultKindFilter === "all" || run.kind === resultKindFilter;
      const matchesIssue =
        resultIssueFilter === "all" ||
        (resultIssueFilter === "cancelled" && run.status === "cancelled") ||
        (resultIssueFilter === "contract_gaps" && finalizedContractGaps > 0) ||
        (resultIssueFilter === "required_failed" && Number(run.requiredFailed || 0) > 0) ||
        (resultIssueFilter === "allowed_failed" && Number(run.allowedFailed || 0) > 0) ||
        failureClasses.includes(resultIssueFilter);
      const matchesEvidence =
        resultEvidenceFilter === "all" ||
        (resultEvidenceFilter === "clean" && finalizedContractGaps === 0) ||
        (resultEvidenceFilter === "contract_gaps" && finalizedContractGaps > 0);
      const searchable = [
        run.id,
        run.kind,
        run.status,
        run.artifactStatus,
        run.scenarioId,
        run.scenarioPath,
        run.suiteId,
        run.failureClass,
        ...(run.failureClasses || []),
      ].filter(Boolean).join(" ").toLowerCase();
      const matchesQuery = !resultQuery.trim() || searchable.includes(resultQuery.trim().toLowerCase());
      return matchesFilter && matchesKind && matchesIssue && matchesEvidence && matchesQuery;
    });
  }, [runs, resultEvidenceFilter, resultFilter, resultIssueFilter, resultKindFilter, resultQuery]);
  const labRunBlocked = labStatus?.status === "blocked";
  const artifactPath = runForm.artifactPath.trim();
  const artifactRecommendations = useMemo(
    () => recommendArtifactsForScenario(selectedScenarioPath, catalog.artifacts),
    [catalog.artifacts, selectedScenarioPath],
  );
  const maxParallelReady = Number(runForm.maxParallel) >= 1;
  const artifactReady = !artifactPath || (!artifactChecking && Boolean(artifactCheck?.exists));
  const canRunSuite = Boolean(selectedSuitePath && artifactPath && !artifactChecking && artifactCheck?.exists && !labRunBlocked && !isLaunching && maxParallelReady);
  const canRunScenario = Boolean(selectedScenarioPath && !isLaunching && (artifactPath ? artifactReady && !labRunBlocked : true));
  const suiteRunBlockReason = !selectedSuitePath
    ? t.selectSuiteFirst
    : !artifactPath
      ? t.suiteArtifactRequired
      : artifactChecking
        ? t.runBlockedArtifactChecking
        : !artifactCheck?.exists
          ? t.artifactMissing
          : labRunBlocked
            ? t.labBlockedRun
            : !maxParallelReady
              ? t.runBlockedMaxParallel
              : isLaunching
                ? t.runBlockedLaunching
                : "";
  const scenarioRunBlockReason = !selectedScenarioPath
    ? t.selectScenarioFirst
    : artifactPath && artifactChecking
      ? t.runBlockedArtifactChecking
      : artifactPath && !artifactCheck?.exists
        ? t.artifactMissing
        : artifactPath && labRunBlocked
          ? t.labBlockedRun
          : isLaunching
            ? t.runBlockedLaunching
            : "";
  const runReadinessStages = useMemo(
    () => [
      {
        label: t.runStageSelection,
        status: selectedScenarioPath || selectedSuitePath ? "ok" as const : "blocked" as const,
        detail: selectedSuitePath ? t.selectedSuite : selectedScenarioPath ? t.selectedScenario : t.needsInputLabel,
      },
      {
        label: t.runStageArtifact,
        status: artifactPath ? (artifactChecking ? "warning" as const : artifactCheck?.exists ? "ok" as const : "blocked" as const) : selectedSuitePath ? "blocked" as const : "warning" as const,
        detail: artifactPath ? (artifactChecking ? t.artifactChecking : artifactCheck?.exists ? t.artifactReady : t.artifactMissing) : selectedSuitePath ? t.needsInputLabel : t.optionalLabel,
      },
      {
        label: t.runStageLab,
        status: labStatus?.status === "blocked" ? "blocked" as const : labStatus?.status === "ready" ? "ok" as const : "warning" as const,
        detail: labStatus?.status === "ready" ? t.readyLabel : labStatus?.status === "blocked" ? t.blockedLabel : t.labDegraded,
      },
      {
        label: t.runStageOptions,
        status: maxParallelReady ? "ok" as const : "blocked" as const,
        detail: maxParallelReady ? `${t.maxParallel}: ${runForm.maxParallel}` : t.runBlockedMaxParallel,
      },
      {
        label: t.runStageCommand,
        status: selectedScenarioPath || selectedSuitePath ? "ok" as const : "blocked" as const,
        detail: selectedSuitePath ? "suite-run" : selectedScenarioPath ? "run" : t.needsInputLabel,
      },
    ],
    [artifactCheck?.exists, artifactChecking, artifactPath, labStatus?.status, maxParallelReady, runForm.maxParallel, selectedScenarioPath, selectedSuitePath, t],
  );

  useEffect(() => {
    const saved = window.localStorage.getItem("oslab.lang");
    if (saved === "en" || saved === "ko") setLang(saved);
    refreshMe();
  }, []);

  useEffect(() => {
    window.localStorage.setItem("oslab.lang", lang);
  }, [lang]);

  useEffect(() => {
    try {
      const saved = JSON.parse(window.localStorage.getItem(RECENT_ARTIFACTS_KEY) || "[]");
      if (Array.isArray(saved)) {
        setRecentArtifacts(saved.filter((item): item is string => typeof item === "string"));
      }
    } catch {
      setRecentArtifacts([]);
    }
  }, []);

  useEffect(() => {
    if (!hasDirtyEditors) return;
    const handler = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [hasDirtyEditors]);

  useEffect(() => {
    if (me) refreshAll();
  }, [me]);

  useEffect(() => {
    if (!me) return;
    const runtimeTimer = window.setInterval(() => refreshRuntime(), 5000);
    const labTimer = window.setInterval(() => refreshLabStatus(), 30000);
    return () => {
      window.clearInterval(runtimeTimer);
      window.clearInterval(labTimer);
    };
  }, [me, selectedScenarioPath, runForm.configPath, runForm.envFilePath, runForm.maxParallel]);

  useEffect(() => {
    if (!catalog.scenarios.length && !catalog.suites.length) return;
    setSelectedScenarioPath((current) => current || catalog.scenarios.find((item) => item.path.includes("demo-powershell-system"))?.path || catalog.scenarios.find((item) => item.path.includes("clean-baseline"))?.path || catalog.scenarios[0]?.path || "");
    setSelectedSuitePath((current) => current);
  }, [catalog]);

  useEffect(() => {
    if (!me) return;
    refreshLabStatus();
  }, [me, selectedScenarioPath, runForm.configPath, runForm.envFilePath, runForm.maxParallel]);

  useEffect(() => {
    setSelectedRunId((current) => {
      if (!filteredRuns.length) return "";
      if (!current) return filteredRuns[0]?.id || "";
      if (filteredRuns.some((run) => run.id === current)) return current;
      if (selectedRunParentId && filteredRuns.some((run) => run.id === selectedRunParentId)) return current;
      if (filteredRuns.some((run) => current.startsWith(`${run.id}-`))) return current;
      return filteredRuns[0]?.id || "";
    });
  }, [filteredRuns, selectedRunParentId]);

  useEffect(() => {
    selectedRunIdRef.current = selectedRunId;
    if (!selectedRunId) {
      setRunDetail(null);
      setProgressEvents([]);
      return;
    }
    setRunDetail(null);
    setProgressEvents([]);
    refreshRunDetail(selectedRunId);
  }, [selectedRunId]);

  useEffect(() => {
    if (!me) return;
    if (!selectedRunId) return;
    const activeDetail =
      isActiveRunStatus(runDetail?.status) ||
      Boolean(effectiveJobSummary?.runId === selectedRunId && isActiveRunStatus(effectiveJobSummary.status));
    if (!activeDetail) return;
    const timer = window.setInterval(() => {
      const currentRunId = selectedRunIdRef.current;
      if (currentRunId) refreshRunDetail(currentRunId);
    }, 2000);
    return () => window.clearInterval(timer);
  }, [me, selectedRunId, runDetail?.status, effectiveJobSummary?.runId, effectiveJobSummary?.status]);

  useEffect(() => {
    if (!selectedSuitePath) {
      setSuitePolicy(null);
      return;
    }
    refreshSuitePolicy(selectedSuitePath);
  }, [selectedSuitePath]);

  useEffect(() => {
    const artifactPath = runForm.artifactPath.trim();
    if (!artifactPath) {
      setArtifactCheck(null);
      setArtifactChecking(false);
      return;
    }
    setArtifactChecking(true);
    const timer = window.setTimeout(() => {
      checkArtifactPath(artifactPath);
    }, 500);
    return () => window.clearTimeout(timer);
  }, [runForm.artifactPath]);

  useEffect(() => {
    if (selectedArtifactPath === CUSTOM_ARTIFACT) return;
    setRunForm((current) => ({ ...current, artifactPath: selectedArtifactPath }));
  }, [selectedArtifactPath]);

  useEffect(() => {
    const editor = editors.scenarios;
    if (!editor.selectedPath || !editor.content.trim()) {
      setScenarioBuilder(null);
      setScenarioBuilderBaseline("");
      setScenarioBuilderError("");
      return;
    }
    if (editor.isEditing && syntaxChecking.scenarios) return;
    if (editor.isEditing && syntaxChecks.scenarios?.ok === false) {
      setScenarioBuilder(null);
      setScenarioBuilderBaseline("");
      setScenarioBuilderError("syntax-invalid");
      return;
    }
    const timer = window.setTimeout(() => inspectScenarioBuilder(editor.content), 250);
    return () => window.clearTimeout(timer);
  }, [editors.scenarios.content, editors.scenarios.isEditing, editors.scenarios.selectedPath, syntaxChecking.scenarios, syntaxChecks.scenarios?.ok]);

  useEffect(() => {
    const editor = editors.suites;
    if (!editor.selectedPath || !editor.content.trim()) {
      setSuiteBuilder(null);
      setSuiteBuilderBaseline("");
      setSuiteBuilderError("");
      return;
    }
    if (editor.isEditing && syntaxChecking.suites) return;
    if (editor.isEditing && syntaxChecks.suites?.ok === false) {
      setSuiteBuilder(null);
      setSuiteBuilderBaseline("");
      setSuiteBuilderError("syntax-invalid");
      return;
    }
    const timer = window.setTimeout(() => inspectSuiteBuilder(editor.content), 250);
    return () => window.clearTimeout(timer);
  }, [editors.suites.content, editors.suites.isEditing, editors.suites.selectedPath, syntaxChecking.suites, syntaxChecks.suites?.ok]);

  useEffect(() => {
    const editor = editors.scenarios;
    if (!editor.selectedPath || !editor.isEditing) {
      setSyntaxChecking((current) => ({ ...current, scenarios: false }));
      setSyntaxChecks((current) => ({ ...current, scenarios: null }));
      return;
    }
    setSyntaxChecking((current) => ({ ...current, scenarios: true }));
    const timer = window.setTimeout(() => {
      validateEditorSyntax("scenarios", editor.selectedPath, editor.content);
    }, 350);
    return () => window.clearTimeout(timer);
  }, [editors.scenarios.content, editors.scenarios.isEditing, editors.scenarios.selectedPath]);

  useEffect(() => {
    const editor = editors.fixtures;
    if (!editor.selectedPath || !editor.isEditing) {
      setSyntaxChecking((current) => ({ ...current, fixtures: false }));
      setSyntaxChecks((current) => ({ ...current, fixtures: null }));
      return;
    }
    setSyntaxChecking((current) => ({ ...current, fixtures: true }));
    const timer = window.setTimeout(() => {
      validateEditorSyntax("fixtures", editor.selectedPath, editor.content);
    }, 350);
    return () => window.clearTimeout(timer);
  }, [editors.fixtures.content, editors.fixtures.isEditing, editors.fixtures.selectedPath]);

  useEffect(() => {
    const editor = editors.suites;
    if (!editor.selectedPath || !editor.isEditing) {
      setSyntaxChecking((current) => ({ ...current, suites: false }));
      setSyntaxChecks((current) => ({ ...current, suites: null }));
      return;
    }
    setSyntaxChecking((current) => ({ ...current, suites: true }));
    const timer = window.setTimeout(() => {
      validateEditorSyntax("suites", editor.selectedPath, editor.content);
    }, 350);
    return () => window.clearTimeout(timer);
  }, [editors.suites.content, editors.suites.isEditing, editors.suites.selectedPath]);

  useEffect(() => {
    if (!effectiveJobId) return;
    loadJobLog(effectiveJobId);
    const source = new EventSource(`${getApiBaseUrl()}/api/jobs/${effectiveJobId}/events`, { withCredentials: true });
    let closedByDone = false;
    const append = (event: Event) => appendJobLog(parseEventData(event));
    source.addEventListener("log", append);
    source.addEventListener("stdout", append);
    source.addEventListener("stderr", append);
    source.addEventListener("done", (event) => {
      closedByDone = true;
      const status = parseEventData(event);
      setNotice(`Job ${status}`);
      setIsLaunching(false);
      refreshRuntime();
      apiGet<JobSummary>(`/api/jobs/${effectiveJobId}`)
        .then((job) => {
          if (job.runId) {
            selectedRunIdRef.current = job.runId;
            setSelectedRunId(job.runId);
            refreshRunDetail(job.runId);
          }
        })
        .catch(() => {
          // The normal runtime refresh above still covers transient job lookup failures.
        });
      source.close();
    });
    source.onerror = async () => {
      if (closedByDone) return;
      try {
        const job = await apiGet<JobSummary>(`/api/jobs/${effectiveJobId}`);
        if (job.status !== "queued" && job.status !== "running") {
          setNotice(`Job ${job.status}`);
          setIsLaunching(false);
          refreshRuntime();
          source.close();
          return;
        }
      } catch {
        // Fall through to the connection warning below.
      }
      setNotice(t.reconnecting);
      refreshRuntime();
    };
    return () => source.close();
  }, [effectiveJobId, t.reconnecting]);

  useEffect(() => {
    if (!consoleRef.current) return;
    consoleRef.current.scrollTop = consoleRef.current.scrollHeight;
  }, [jobLog]);

  useEffect(() => {
    if (!selectedJob) return;
    const job = jobs.find((item) => item.id === selectedJob);
    if (job && job.status !== "queued" && job.status !== "running") {
      setIsLaunching(false);
      if (job.runId) {
        setSelectedRunId(job.runId);
      }
    }
  }, [jobs, selectedJob]);

  useEffect(() => {
    if (selectedJob) return;
    const active = jobs.find((job) => job.status === "running" || job.status === "queued");
    if (active) setSelectedJob(active.id);
  }, [jobs, selectedJob]);

  function confirmDiscardAllEdits() {
    if (!hasDirtyEditors) return true;
    return window.confirm(t.discardChanges);
  }

  function hasDirtyEditor(kind: EditorTab) {
    const editor = editors[kind];
    if (editor.content !== editor.originalContent) return true;
    if (kind === "scenarios" && scenarioBuilderDirty) return true;
    if (kind === "suites" && suiteBuilderDirty) return true;
    return false;
  }

  function requestTabChange(next: Tab) {
    if (next === tab) return;
    if (!confirmDiscardAllEdits()) return;
    setTab(next);
  }

  function rememberArtifactPath(value: string) {
    const nextValue = value.trim();
    if (!nextValue) return;
    setRecentArtifacts((current) => {
      const next = [nextValue, ...current.filter((item) => item !== nextValue)].slice(0, 6);
      window.localStorage.setItem(RECENT_ARTIFACTS_KEY, JSON.stringify(next));
      return next;
    });
  }

  function clearRecentArtifacts() {
    setRecentArtifacts([]);
    window.localStorage.removeItem(RECENT_ARTIFACTS_KEY);
  }

  function applyArtifactPreset(value: string) {
    if (!value) {
      setSelectedArtifactPath("");
      setRunForm((current) => ({ ...current, artifactPath: "" }));
      return;
    }
    const inCatalog = catalog.artifacts.some((item) => item.path === value);
    setSelectedArtifactPath(inCatalog ? value : CUSTOM_ARTIFACT);
    setRunForm((current) => ({ ...current, artifactPath: value }));
  }

  function useManagedArtifact(value: string) {
    const nextValue = value.trim();
    if (!nextValue) return;
    setSelectedArtifactPath(nextValue);
    setRunForm((current) => ({ ...current, artifactPath: nextValue }));
    rememberArtifactPath(nextValue);
    void checkArtifactPath(nextValue);
  }

  async function refreshArtifactCatalog() {
    const artifacts = await apiGet<CatalogItem[]>("/api/catalog/artifacts");
    setCatalog((current) => ({ ...current, artifacts }));
    setSelectedArtifactPath((current) => {
      const activePath = runForm.artifactPath.trim();
      if (activePath && artifacts.some((item) => item.path === activePath)) return activePath;
      return current;
    });
  }

  function selectArtifactUploadFile(file: File | null) {
    setArtifactUploadFile(file);
    if (!file) return;
    setArtifactUploadStatus({
      kind: "file",
      phase: "selected",
      name: file.name,
      fileCount: 1,
      size: file.size,
      message: t.artifactUploadReadyHint,
    });
  }

  function selectArtifactUploadFolder(files: File[]) {
    setArtifactUploadFolderFiles(files);
    if (!files.length) return;
    const summary = folderUploadSummary(files);
    setArtifactUploadStatus({
      kind: "folder",
      phase: "selected",
      name: summary.rootName,
      fileCount: files.length,
      size: summary.size,
      message: t.artifactUploadReadyHint,
    });
  }

  function updateArtifactUploadProgress(kind: "file" | "folder", progress: { loaded: number; total: number; percent: number | null }) {
    setArtifactUploadStatus((current) => {
      if (!current || current.kind !== kind) return current;
      return {
        ...current,
        phase: "uploading",
        loaded: progress.loaded,
        total: progress.total,
        percent: progress.percent,
        message: t.artifactUploadUploadingHint,
      };
    });
  }

  async function uploadSelectedArtifact() {
    if (!artifactUploadFile) return;
    const file = artifactUploadFile;
    setArtifactUploading(true);
    setArtifactUploadStatus({
      kind: "file",
      phase: "uploading",
      name: file.name,
      fileCount: 1,
      size: file.size,
      loaded: 0,
      total: file.size,
      percent: 0,
      message: t.artifactUploadUploadingHint,
    });
    try {
      const upload = await apiUploadWithProgress<ArtifactUploadSummary>("/api/artifacts/upload", file, (progress) => updateArtifactUploadProgress("file", progress));
      const catalogItem: CatalogItem = { path: upload.path, name: upload.filename, kind: "artifact" };
      setCatalog((current) => ({
        ...current,
        artifacts: [catalogItem, ...current.artifacts.filter((item) => item.path !== upload.path)].sort((a, b) => a.path.localeCompare(b.path)),
      }));
      setSelectedArtifactPath(upload.path);
      setRunForm((current) => ({ ...current, artifactPath: upload.path }));
      setArtifactUploadFile(null);
      if (artifactUploadInputRef.current) artifactUploadInputRef.current.value = "";
      rememberArtifactPath(upload.path);
      await checkArtifactPath(upload.path);
      setArtifactUploadStatus({
        kind: "file",
        phase: "uploaded",
        name: upload.filename,
        fileCount: 1,
        size: upload.size,
        loaded: upload.size,
        total: upload.size,
        percent: 100,
        path: upload.path,
        message: t.artifactUploadUploadedHint,
      });
      setNotice(`${t.artifactUploaded}: ${upload.path}`);
    } catch (error: any) {
      setArtifactUploadStatus((current) => current && current.kind === "file" ? { ...current, phase: "failed", message: error.message || String(error) } : current);
      setNotice(`${t.artifactUploadFailed}: ${error.message || String(error)}`);
    } finally {
      setArtifactUploading(false);
    }
  }

  async function uploadSelectedArtifactFolder() {
    if (!artifactUploadFolderFiles.length) return;
    const files = artifactUploadFolderFiles;
    const summary = folderUploadSummary(files);
    setArtifactFolderUploading(true);
    setArtifactUploadStatus({
      kind: "folder",
      phase: "uploading",
      name: summary.rootName,
      fileCount: files.length,
      size: summary.size,
      loaded: 0,
      total: summary.size,
      percent: 0,
      message: t.artifactUploadUploadingHint,
    });
    try {
      const upload = await apiUploadFiles<ArtifactUploadSummary>("/api/artifacts/upload-directory", files, (progress) => updateArtifactUploadProgress("folder", progress));
      const catalogItem: CatalogItem = { path: upload.path, name: upload.filename, kind: "artifact" };
      setCatalog((current) => ({
        ...current,
        artifacts: [catalogItem, ...current.artifacts.filter((item) => item.path !== upload.path)].sort((a, b) => a.path.localeCompare(b.path)),
      }));
      setSelectedArtifactPath(upload.path);
      setRunForm((current) => ({ ...current, artifactPath: upload.path }));
      setArtifactUploadFolderFiles([]);
      if (artifactFolderInputRef.current) artifactFolderInputRef.current.value = "";
      rememberArtifactPath(upload.path);
      await checkArtifactPath(upload.path);
      setArtifactUploadStatus({
        kind: "folder",
        phase: "uploaded",
        name: upload.filename,
        fileCount: upload.fileCount || files.length,
        size: upload.size,
        loaded: upload.size,
        total: upload.size,
        percent: 100,
        path: upload.path,
        message: t.artifactUploadUploadedHint,
      });
      setNotice(`${t.artifactFolderUploaded}: ${upload.path}`);
    } catch (error: any) {
      setArtifactUploadStatus((current) => current && current.kind === "folder" ? { ...current, phase: "failed", message: error.message || String(error) } : current);
      setNotice(`${t.artifactFolderUploadFailed}: ${error.message || String(error)}`);
    } finally {
      setArtifactFolderUploading(false);
    }
  }

  async function inspectScenarioBuilder(content: string) {
    const requestId = builderInspectRequestRef.current.scenarios + 1;
    builderInspectRequestRef.current.scenarios = requestId;
    try {
      const payload = await apiPost<{ ok: boolean; model: ScenarioBuilderModel }>("/api/build/scenario/inspect", { content });
      if (builderInspectRequestRef.current.scenarios !== requestId) return;
      setScenarioBuilder(payload.model);
      setScenarioBuilderBaseline(stableStringify(payload.model));
      setScenarioBuilderError("");
    } catch (error: any) {
      if (builderInspectRequestRef.current.scenarios !== requestId) return;
      setScenarioBuilder(null);
      setScenarioBuilderBaseline("");
      setScenarioBuilderError(error.message || String(error));
    }
  }

  async function inspectSuiteBuilder(content: string) {
    const requestId = builderInspectRequestRef.current.suites + 1;
    builderInspectRequestRef.current.suites = requestId;
    try {
      const payload = await apiPost<{ ok: boolean; model: SuiteBuilderModel }>("/api/build/suite/inspect", { content });
      if (builderInspectRequestRef.current.suites !== requestId) return;
      setSuiteBuilder(payload.model);
      setSuiteBuilderBaseline(stableStringify(payload.model));
      setSuiteBuilderError("");
      setSuiteAddScenarioPath((current) => current || catalog.scenarios[0]?.path || "");
    } catch (error: any) {
      if (builderInspectRequestRef.current.suites !== requestId) return;
      setSuiteBuilder(null);
      setSuiteBuilderBaseline("");
      setSuiteBuilderError(error.message || String(error));
    }
  }

  async function validateEditorSyntax(kind: EditorTab, path: string, content: string) {
    const requestId = syntaxRequestRef.current[kind] + 1;
    syntaxRequestRef.current[kind] = requestId;
    setSyntaxChecking((current) => ({ ...current, [kind]: true }));
    try {
      const payload = await apiPost<SyntaxValidationResult>("/api/validate/content", { path, content });
      if (syntaxRequestRef.current[kind] !== requestId) return payload;
      setSyntaxChecks((current) => ({ ...current, [kind]: payload }));
      return payload;
    } catch (error: any) {
      const fallback: SyntaxValidationResult = {
        ok: false,
        kind: "unsupported",
        checkedAt: new Date().toISOString(),
        issues: [{ message: error.message || String(error) }],
        message: error.message || String(error),
      };
      if (syntaxRequestRef.current[kind] === requestId) {
        setSyntaxChecks((current) => ({ ...current, [kind]: fallback }));
      }
      return fallback;
    } finally {
      if (syntaxRequestRef.current[kind] === requestId) {
        setSyntaxChecking((current) => ({ ...current, [kind]: false }));
      }
    }
  }

  async function applyScenarioBuilder() {
    if (!scenarioBuilder) return;
    try {
      const payload = await apiPost<{ ok: boolean; content: string }>("/api/build/scenario/render", {
        content: editors.scenarios.content,
        model: scenarioBuilder,
      });
      setEditors((current) => ({
        ...current,
        scenarios: {
          ...current.scenarios,
          content: payload.content,
        },
      }));
    } catch (error: any) {
      setNotice(error.message || String(error));
    }
  }

  async function createScenarioFromTemplate(draft: ScenarioCreateDraft) {
    if (dirtyEditorTabs.has("scenarios") && !window.confirm(t.discardChanges)) return;
    try {
      const template = await apiPost<{ ok: boolean; path: string; content: string }>("/api/build/scenario/template", draft);
      await apiPost("/api/files", { path: template.path, content: template.content });
      const item: CatalogItem = { path: template.path, name: basename(template.path), kind: "scenario" };
      setCatalog((current) => ({
        ...current,
        scenarios: [item, ...current.scenarios.filter((scenario) => scenario.path !== template.path)].sort((a, b) => a.path.localeCompare(b.path)),
      }));
      setEditors((current) => ({
        ...current,
        scenarios: {
          ...current.scenarios,
          selectedPath: template.path,
          content: template.content,
          originalContent: template.content,
          isEditing: true,
        },
      }));
      setScenarioCreateOpen(false);
      await inspectScenarioBuilder(template.content);
      setNotice(`${t.scenarioCreated}: ${template.path}`);
      await refreshAll();
    } catch (error: any) {
      setNotice(error.message || String(error));
      throw error;
    }
  }

  async function createFixtureFromTemplate(draft: FixtureCreateDraft) {
    if (dirtyEditorTabs.has("fixtures") && !window.confirm(t.discardChanges)) return;
    try {
      const template = await apiPost<{ ok: boolean; path: string; content: string }>("/api/build/fixture/template", draft);
      await apiPost("/api/files", { path: template.path, content: template.content });
      const item: CatalogItem = { path: template.path, name: basename(template.path), kind: "fixture" };
      setCatalog((current) => ({
        ...current,
        fixtures: [item, ...current.fixtures.filter((fixture) => fixture.path !== template.path)].sort((a, b) => a.path.localeCompare(b.path)),
      }));
      setEditors((current) => ({
        ...current,
        fixtures: {
          ...current.fixtures,
          selectedPath: template.path,
          content: template.content,
          originalContent: template.content,
          isEditing: true,
        },
      }));
      setFixtureCreateOpen(false);
      setNotice(`${t.fixtureCreated}: ${template.path}`);
      await refreshAll();
    } catch (error: any) {
      setNotice(error.message || String(error));
      throw error;
    }
  }

  async function createSuiteFromTemplate(draft: SuiteCreateDraft) {
    if (dirtyEditorTabs.has("suites") && !window.confirm(t.discardChanges)) return;
    try {
      const template = await apiPost<{ ok: boolean; path: string; content: string }>("/api/build/suite/template", draft);
      await apiPost("/api/files", { path: template.path, content: template.content });
      const item: CatalogItem = { path: template.path, name: basename(template.path), kind: "suite" };
      setCatalog((current) => ({
        ...current,
        suites: [item, ...current.suites.filter((suite) => suite.path !== template.path)].sort((a, b) => a.path.localeCompare(b.path)),
      }));
      setEditors((current) => ({
        ...current,
        suites: {
          ...current.suites,
          selectedPath: template.path,
          content: template.content,
          originalContent: template.content,
          isEditing: true,
        },
      }));
      setSuiteCreateOpen(false);
      setSelectedSuitePath(template.path);
      setRunForm((current) => ({ ...current, maxParallel: Math.max(1, Number(draft.maxParallel) || 1) }));
      await inspectSuiteBuilder(template.content);
      setNotice(`${t.suiteCreated}: ${template.path}`);
      await refreshAll();
    } catch (error: any) {
      setNotice(error.message || String(error));
      throw error;
    }
  }

  async function applySuiteBuilder() {
    if (!suiteBuilder) return;
    try {
      const payload = await apiPost<{ ok: boolean; content: string }>("/api/build/suite/render", {
        content: editors.suites.content,
        model: suiteBuilder,
      });
      setEditors((current) => ({
        ...current,
        suites: {
          ...current.suites,
          content: payload.content,
        },
      }));
    } catch (error: any) {
      setNotice(error.message || String(error));
    }
  }

  function updateSuiteRun(index: number, patch: Partial<SuiteBuilderRun>) {
    setSuiteBuilder((current) => {
      if (!current) return current;
      const runs = current.runs.map((entry, currentIndex) => (currentIndex === index ? { ...entry, ...patch } : entry));
      return { ...current, runs };
    });
  }

  function moveSuiteRun(index: number, direction: -1 | 1) {
    setSuiteBuilder((current) => {
      if (!current) return current;
      const nextIndex = index + direction;
      if (nextIndex < 0 || nextIndex >= current.runs.length) return current;
      const runs = [...current.runs];
      const [entry] = runs.splice(index, 1);
      runs.splice(nextIndex, 0, entry);
      return { ...current, runs };
    });
  }

  function removeSuiteRun(index: number) {
    setSuiteBuilder((current) => {
      if (!current) return current;
      return { ...current, runs: current.runs.filter((_, currentIndex) => currentIndex !== index) };
    });
  }

  function addSuiteRun() {
    if (!suiteAddScenarioPath) return;
    setSuiteBuilder((current) => {
      if (!current) return current;
      const basename = suiteAddScenarioPath.split("/").pop()?.replace(/\.(example\.)?ya?ml$/i, "") || "scenario";
      const id = basename.replace(/[^a-z0-9]+/gi, "-").replace(/^-+|-+$/g, "").toLowerCase();
      return {
        ...current,
        runs: [
          ...current.runs,
          {
            id,
            scenario: suiteAddScenarioPath,
            tier: "ci",
            allowFailure: false,
            enabled: true,
          },
        ],
      };
    });
  }

  async function cancelCurrentJob() {
    if (!effectiveJobId) return;
    try {
      await apiPost(`/api/jobs/${effectiveJobId}/cancel`, {});
      setNotice(`${t.cancelJob}: ${effectiveJobId}`);
      await refreshRuntime();
    } catch (error: any) {
      setNotice(error.message || String(error));
    }
  }

  async function cleanupStaleVms() {
    try {
      const dryRun = await apiPost<LabCleanupResponse>("/api/lab/cleanup-stale", {
        scenarioPath: selectedScenarioPath,
        configPath: runForm.configPath,
        envFilePath: runForm.envFilePath,
        dryRun: true,
      });
      if (!dryRun.targets.length || !dryRun.confirmToken) {
        setNotice(dryRun.message || t.cleanupRequested);
        await refreshLabStatus();
        return;
      }
      const targetList = dryRun.targets
        .map((vm) => `VMID ${vm.vmid}${vm.name ? ` · ${vm.name}` : ""}${vm.node ? ` · ${vm.node}` : ""}${vm.status ? ` · ${vm.status}` : ""}`)
        .join("\n");
      if (!window.confirm(`${t.cleanupConfirm}\n\n${targetList}`)) {
        setNotice(t.cleanupCancelled);
        return;
      }
      const payload = await apiPost<LabCleanupResponse>("/api/lab/cleanup-stale", {
        scenarioPath: selectedScenarioPath,
        configPath: runForm.configPath,
        envFilePath: runForm.envFilePath,
        dryRun: false,
        confirmToken: dryRun.confirmToken,
      });
      setNotice(payload.message || t.cleanupRequested);
      await refreshLabStatus();
      await refreshRuntime();
    } catch (error: any) {
      setNotice(error.message || String(error));
    }
  }

  async function refreshMe() {
    const response = await fetch("/api/me", { credentials: "include" });
    if (response.ok) setMe((await response.json()).user);
    else setMe(null);
  }

  async function refreshAll() {
    try {
      const [scenarios, suites, fixtures, artifacts, jobsResponse, runsResponse] = await Promise.all([
        apiGet<CatalogItem[]>("/api/catalog/scenarios"),
        apiGet<CatalogItem[]>("/api/catalog/suites"),
        apiGet<CatalogItem[]>("/api/catalog/fixtures"),
        apiGet<CatalogItem[]>("/api/catalog/artifacts"),
        apiGet<JobSummary[]>("/api/jobs"),
        apiGet<RunSummary[]>("/api/runs"),
      ]);
      setCatalog({ scenarios, suites, fixtures, artifacts });
      setJobs(jobsResponse);
      setRuns(runsResponse);
      refreshLabStatus();
    } catch (error: any) {
      setNotice(error.message || String(error));
    }
  }

  async function refreshRuntime() {
    try {
      const [jobsResponse, runsResponse] = await Promise.all([
        apiGet<JobSummary[]>("/api/jobs"),
        apiGet<RunSummary[]>("/api/runs"),
      ]);
      setJobs(jobsResponse);
      setRuns(runsResponse);
      const currentRunId = selectedRunIdRef.current;
      if (currentRunId) refreshRunDetail(currentRunId);
    } catch (error: any) {
      setNotice(error.message || String(error));
    }
  }

  async function loadJobLog(jobId: string) {
    try {
      const payload = await apiGet<{ log: string }>(`/api/jobs/${jobId}/log`);
      setJobLog((current) => payload.log || current);
    } catch (error: any) {
      setNotice(error.message || String(error));
    }
  }

  async function refreshLabStatus() {
    setLabStatusLoading(true);
    try {
      const params = new URLSearchParams({
        configPath: runForm.configPath,
        envFilePath: runForm.envFilePath,
        requiredCapacity: String(Math.max(1, Number(runForm.maxParallel || 1))),
      });
      if (selectedScenarioPath) params.set("scenarioPath", selectedScenarioPath);
      const status = await apiGet<LabStatus>(`/api/lab/status?${params.toString()}`);
      setLabStatus(status);
    } catch (error: any) {
      setLabStatus(null);
      setNotice(error.message || String(error));
    } finally {
      setLabStatusLoading(false);
    }
  }

  async function checkArtifactPath(artifactPath: string) {
    try {
      const result = await apiGet<ArtifactPathCheck>(`/api/artifacts/check?path=${encodeURIComponent(artifactPath)}`);
      setArtifactCheck(result);
    } catch (error: any) {
      setArtifactCheck({ ok: false, exists: false, message: error.message || String(error) });
    } finally {
      setArtifactChecking(false);
    }
  }

  async function refreshSuitePolicy(path: string) {
    try {
      const payload = await apiGet<{ content: string }>(`/api/files?path=${encodeURIComponent(path)}`);
      const allowFailure = (payload.content.match(/allowFailure:\s*true/g) || []).length;
      const disabled = (payload.content.match(/enabled:\s*false/g) || []).length;
      const entries = (payload.content.match(/^\s*-\s+id:/gm) || []).length;
      const maxParallelMatch = payload.content.match(/^maxParallel:\s*(\d+)/m);
      setSuitePolicy({ allowFailure, disabled, entries, maxParallel: maxParallelMatch ? Number(maxParallelMatch[1]) : null });
    } catch {
      setSuitePolicy(null);
    }
  }

  async function refreshRunDetail(runId: string) {
    try {
      const detail = await apiGet<RunDetail>(`/api/runs/${encodeURIComponent(runId)}`);
      const progressEvidence = detail?.evidence?.items?.find?.((item: any) => item.key === "progress-jsonl");
      if (Array.isArray(detail?.entries) || detail?.details?.mode === "skeleton" || progressEvidence?.status === "notApplicable" || progressEvidence?.status === "missing" || progressEvidence?.status === "contractGap") {
        setProgressEvents([]);
      } else {
        await refreshProgress(runId);
      }
      setRunDetail((current) => {
        if (selectedRunIdRef.current !== runId) return current;
        return detail;
      });
    } catch (error: any) {
      if (selectedRunIdRef.current !== runId) return;
      setRunDetail(null);
      setProgressEvents([]);
      setNotice(error.message || String(error));
    }
  }

  async function refreshProgress(runId: string) {
    try {
      const text = await apiText(`/api/runs/${encodeURIComponent(runId)}/file?path=${encodeURIComponent("logs/progress.jsonl")}`);
      const events = text
        .split(/\r?\n/)
        .filter(Boolean)
        .map((line) => JSON.parse(line) as ProgressEvent)
        .slice(-80);
      setProgressEvents(events);
    } catch {
      setProgressEvents([]);
    }
  }

  async function doLogin() {
    const response = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify(login),
    });
    if (!response.ok) {
      setNotice("Login failed");
      return;
    }
    setNotice("");
    await refreshMe();
  }

  async function logout() {
    if (!confirmDiscardAllEdits()) return;
    await fetch("/api/auth/logout", { method: "POST", credentials: "include" });
    setMe(null);
    setJobLog("");
    setLogin({ username: "", password: "" });
  }

  async function openFile(kind: EditorTab, path: string) {
    const editor = editors[kind];
    if (editor.isEditing && hasDirtyEditor(kind) && !window.confirm(t.discardChanges)) {
      return;
    }
    try {
      const payload = await apiGet<{ path: string; content: string }>(`/api/files?path=${encodeURIComponent(path)}`);
      setEditors((current) => ({
        ...current,
        [kind]: {
          ...current[kind],
          selectedPath: payload.path,
          content: payload.content,
          originalContent: payload.content,
          isEditing: false,
        },
      }));
      setNotice("");
    } catch (error: any) {
      setNotice(error.message || String(error));
    }
  }

  async function saveFile(kind: EditorTab) {
    const editor = editors[kind];
    if (!editor.selectedPath) return;
    try {
      const syntax = await validateEditorSyntax(kind, editor.selectedPath, editor.content);
      if (!syntax.ok) {
        setNotice(t.syntaxSaveBlocked);
        return;
      }
      if (kind === "scenarios") {
        const contract = await apiPost<{ ok: boolean; errors: string[] }>("/api/validate/scenario-content", { path: editor.selectedPath, content: editor.content });
        if (!contract.ok) {
          setNotice(`${t.scenarioSchemaSaveBlocked}: ${contract.errors.slice(0, 3).join(" / ")}`);
          return;
        }
      }
      if (kind === "suites") {
        const contract = await apiPost<{ ok: boolean; errors: string[] }>("/api/validate/suite-content", { path: editor.selectedPath, content: editor.content });
        if (!contract.ok) {
          setNotice(`${t.suiteSchemaSaveBlocked}: ${contract.errors.slice(0, 3).join(" / ")}`);
          return;
        }
      }
      await apiPost("/api/files", { path: editor.selectedPath, content: editor.content }, "PUT");
      setEditors((current) => ({
        ...current,
        [kind]: {
          ...current[kind],
          originalContent: current[kind].content,
          isEditing: false,
        },
      }));
      setNotice(`Saved ${editor.selectedPath}`);
      await refreshAll();
    } catch (error: any) {
      setNotice(error.message || String(error));
    }
  }

  function editFile(kind: EditorTab) {
    setEditors((current) => ({ ...current, [kind]: { ...current[kind], isEditing: true } }));
  }

  function toggleEditorList(kind: EditorTab) {
    setEditorListCollapsed((current) => ({ ...current, [kind]: !current[kind] }));
  }

  async function cancelEdit(kind: EditorTab) {
    const originalContent = editors[kind].originalContent;
    setEditors((current) => ({
      ...current,
      [kind]: {
        ...current[kind],
        content: originalContent,
        isEditing: false,
      },
    }));
    if (kind === "scenarios" && originalContent) {
      await inspectScenarioBuilder(originalContent);
    }
    if (kind === "suites" && originalContent) {
      await inspectSuiteBuilder(originalContent);
    }
  }

  async function validatePath(kind: "scenario" | "suite", path: string) {
    try {
      const response = await apiPost(`/api/validate/${kind}`, { path });
      setNotice(response.ok ? `Valid ${kind}: ${path}` : JSON.stringify(response, null, 2));
    } catch (error: any) {
      setNotice(error.message || String(error));
    }
  }

  async function runSuite() {
    if (!selectedSuitePath) {
      setNotice(t.selectSuiteFirst);
      return;
    }
    if (!artifactPath) {
      setNotice(t.suiteArtifactRequired);
      return;
    }
    setIsLaunching(true);
    try {
      const payload = await apiPost<JobSummary>("/api/jobs/run-suite", {
        suitePath: selectedSuitePath,
        configPath: runForm.configPath,
        envFilePath: runForm.envFilePath,
        artifactPath,
        keepVm: runForm.keepVm,
        fullClone: runForm.fullClone,
        maxParallel: Number(runForm.maxParallel),
        timeouts: {
          boot: Number(runForm.boot),
          guest: Number(runForm.guest),
          command: Number(runForm.command),
          pollInterval: Number(runForm.pollInterval),
        },
      });
      setSelectedJob(payload.id);
      setJobLog(`Started suite job ${payload.id}\n${(payload as any).command || ""}\n`);
      rememberArtifactPath(artifactPath);
      loadJobLog(payload.id);
      setNotice(`Started suite job ${payload.id}`);
      await refreshAll();
    } catch (error: any) {
      setIsLaunching(false);
      setNotice(error.message || String(error));
    }
  }

  async function runScenario() {
    if (!selectedScenarioPath) {
      setNotice(t.selectScenarioFirst);
      return;
    }
    setIsLaunching(true);
    try {
      const payload = await apiPost<JobSummary>("/api/jobs/run-scenario", {
        scenarioPath: selectedScenarioPath,
        configPath: runForm.configPath,
        envFilePath: runForm.envFilePath,
        artifactPath: artifactPath || undefined,
        keepVm: runForm.keepVm,
        fullClone: runForm.fullClone,
        timeouts: {
          boot: Number(runForm.boot),
          guest: Number(runForm.guest),
          command: Number(runForm.command),
          pollInterval: Number(runForm.pollInterval),
        },
      });
      setSelectedJob(payload.id);
      setJobLog(`Started scenario job ${payload.id}\n${(payload as any).command || ""}\n`);
      if (artifactPath) rememberArtifactPath(artifactPath);
      loadJobLog(payload.id);
      setNotice(`Started scenario job ${payload.id}`);
      await refreshAll();
    } catch (error: any) {
      setIsLaunching(false);
      setNotice(error.message || String(error));
    }
  }

  function appendJobLog(text: string) {
    setJobLog((value) => (value + text).slice(-200000));
  }

  if (me === undefined) {
    return <LoadingScreen />;
  }

  if (!me) {
    return (
      <LoginScreen
        t={t}
        lang={lang}
        setLang={setLang}
        login={login}
        setLogin={setLogin}
        notice={notice}
        onSubmit={doLogin}
      />
    );
  }

  return (
    <main className="shell">
      <aside className="nav" aria-label={t.primaryNav}>
        <div>
          <p className="eyebrow">oslab</p>
          <h1>Control</h1>
        </div>
        {(["dashboard", "scenarios", "fixtures", "suites", "artifacts", "run", "results"] as Tab[]).map((item) => (
          <button key={item} className={tab === item ? "active" : ""} aria-current={tab === item ? "page" : undefined} title={t[item]} onClick={() => requestTabChange(item)}>
            {t[item]}
            {dirtyEditorTabs.has(item as EditorTab) && <span className="dirtyDotNav" aria-label={t.unsavedIndicator} />}
          </button>
        ))}
      </aside>

      <section className={`workspace workspace-${tab}`}>
        <header className="topbar">
          <div>
            <p className="eyebrow">{t.eyebrow}</p>
            <h2>{tabTitle(tab, t)}</h2>
          </div>
          <div className="topActions">
            <LanguageSwitch lang={lang} setLang={setLang} />
            <button className="secondary" onClick={refreshAll}>{t.refresh}</button>
            <button className="secondary" onClick={logout}>{t.logout}</button>
          </div>
        </header>
        {!!activeJobs.length && (
          <GlobalRunBanner
            jobs={activeJobs}
            t={t}
            onOpenRun={() => requestTabChange("run")}
            onOpenResults={() => requestTabChange("results")}
            onCancel={cancelCurrentJob}
          />
        )}
        {notice && <p className="notice" role="status" aria-live="polite">{notice}</p>}

        {tab === "dashboard" && (
          <DashboardHome
            t={t}
            catalog={catalog}
            jobs={jobs}
            activeJobs={activeJobs}
            runs={runs}
            labStatus={labStatus}
            labStatusLoading={labStatusLoading}
            onRefreshLab={refreshLabStatus}
            onCleanupStale={cleanupStaleVms}
          />
        )}

        {tab === "scenarios" && (
          <>
            <CatalogEditor
              t={t}
              listTitle={t.scenarios}
              listInfo={t.scenarioCatalogTooltip}
              editor={editors.scenarios}
              onQuery={(query) => setEditors((current) => ({ ...current, scenarios: { ...current.scenarios, query } }))}
              items={catalog.scenarios}
              onOpen={(path) => openFile("scenarios", path)}
              onEdit={() => editFile("scenarios")}
              onCancel={() => cancelEdit("scenarios")}
              onSave={() => saveFile("scenarios")}
              onValidate={(path) => validatePath("scenario", path)}
              onContent={(content) => setEditors((current) => ({ ...current, scenarios: { ...current.scenarios, content } }))}
              listCollapsed={editorListCollapsed.scenarios}
              onToggleList={() => toggleEditorList("scenarios")}
              onCreate={() => setScenarioCreateOpen(true)}
              createLabel={t.newScenario}
              syntaxCheck={syntaxChecks.scenarios}
              syntaxChecking={syntaxChecking.scenarios}
              builderLayout="vertical"
              builderCollapsed={!scenarioBuilderExpanded}
              builder={<ScenarioBuilderPanel t={t} model={scenarioBuilder} error={scenarioBuilderError} editable={editors.scenarios.isEditing} onChange={setScenarioBuilder} onApply={applyScenarioBuilder} expanded={scenarioBuilderExpanded} onExpandedChange={setScenarioBuilderExpanded} />}
            />
            <ScenarioCreateDialog
              t={t}
              open={scenarioCreateOpen}
              existingPaths={catalog.scenarios.map((item) => item.path)}
              onClose={() => setScenarioCreateOpen(false)}
              onCreate={createScenarioFromTemplate}
            />
          </>
        )}
        {tab === "fixtures" && (
          <>
            <CatalogEditor
              t={t}
              listTitle={t.fixtures}
              listInfo={t.fixtureCatalogTooltip}
              editor={editors.fixtures}
              onQuery={(query) => setEditors((current) => ({ ...current, fixtures: { ...current.fixtures, query } }))}
              items={catalog.fixtures}
              onOpen={(path) => openFile("fixtures", path)}
              onEdit={() => editFile("fixtures")}
              onCancel={() => cancelEdit("fixtures")}
              onSave={() => saveFile("fixtures")}
              onContent={(content) => setEditors((current) => ({ ...current, fixtures: { ...current.fixtures, content } }))}
              listCollapsed={editorListCollapsed.fixtures}
              onToggleList={() => toggleEditorList("fixtures")}
              onCreate={() => setFixtureCreateOpen(true)}
              createLabel={t.newFixture}
              syntaxCheck={syntaxChecks.fixtures}
              syntaxChecking={syntaxChecking.fixtures}
            />
            <FixtureCreateDialog
              t={t}
              open={fixtureCreateOpen}
              existingPaths={catalog.fixtures.map((item) => item.path)}
              onClose={() => setFixtureCreateOpen(false)}
              onCreate={createFixtureFromTemplate}
            />
          </>
        )}
        {tab === "suites" && (
          <>
            <CatalogEditor
              t={t}
              listTitle={t.suites}
              listInfo={t.suiteCatalogTooltip}
              editor={editors.suites}
              onQuery={(query) => setEditors((current) => ({ ...current, suites: { ...current.suites, query } }))}
              items={catalog.suites}
              onOpen={(path) => openFile("suites", path)}
              onEdit={() => editFile("suites")}
              onCancel={() => cancelEdit("suites")}
              onSave={() => saveFile("suites")}
              onValidate={(path) => validatePath("suite", path)}
              onContent={(content) => setEditors((current) => ({ ...current, suites: { ...current.suites, content } }))}
              listCollapsed={editorListCollapsed.suites}
              onToggleList={() => toggleEditorList("suites")}
              onCreate={() => setSuiteCreateOpen(true)}
              createLabel={t.newSuite}
              syntaxCheck={syntaxChecks.suites}
              syntaxChecking={syntaxChecking.suites}
              builder={<SuiteBuilderPanel t={t} model={suiteBuilder} error={suiteBuilderError} editable={editors.suites.isEditing} scenarios={catalog.scenarios} addScenarioPath={suiteAddScenarioPath} onAddScenarioPath={setSuiteAddScenarioPath} onModelChange={setSuiteBuilder} onAdd={addSuiteRun} onMove={moveSuiteRun} onRemove={removeSuiteRun} onApply={applySuiteBuilder} onRunChange={updateSuiteRun} />}
            />
            <SuiteCreateDialog
              t={t}
              open={suiteCreateOpen}
              existingPaths={catalog.suites.map((item) => item.path)}
              scenarios={catalog.scenarios}
              onClose={() => setSuiteCreateOpen(false)}
              onCreate={createSuiteFromTemplate}
            />
          </>
        )}

        {tab === "artifacts" && (
          <ArtifactStudio
            t={t}
            selectedPath={runForm.artifactPath}
            onUse={useManagedArtifact}
            onArtifactsChanged={refreshArtifactCatalog}
          />
        )}

        {tab === "run" && (
          <>
            <LabStatusPanel status={labStatus} loading={labStatusLoading} t={t} onRefresh={refreshLabStatus} onCleanup={cleanupStaleVms} compact />
            <section className="runGrid">
              <div className="panel">
                <h3>{t.launch}</h3>
                <RunReadinessFlow title={t.runPlan} stages={runReadinessStages} info={t.runPlanTooltip} t={t} />
                <div className="runStepList">
                  <RunStepSection index={1} title={t.runStepTarget} hint={t.runStepTargetHint} tooltipLabel={t.infoTooltipLabel}>
                    <label>{t.selectedSuite}<select value={selectedSuitePath} onChange={(event) => setSelectedSuitePath(event.target.value)}><option value="">{t.noneSuite}</option>{catalog.suites.map((item) => <option key={item.path} value={item.path}>{item.path}</option>)}</select></label>
                    <label>{t.selectedScenario}<select value={selectedScenarioPath} onChange={(event) => setSelectedScenarioPath(event.target.value)}><option value="">{t.noneScenario}</option>{catalog.scenarios.map((item) => <option key={item.path} value={item.path}>{item.path}</option>)}</select></label>
                  </RunStepSection>
                  <RunStepSection index={2} title={t.runStepArtifact} hint={t.runStepArtifactHint} tooltipLabel={t.infoTooltipLabel}>
                    <div className="artifactManagerLauncher">
                      <div>
                        <strong>{t.artifactManagerOpen}</strong>
                        <span>{t.artifactManagerRunHint}</span>
                      </div>
                      <button type="button" className="secondary" onClick={() => setArtifactManagerOpen(true)}>{t.artifactManagerOpen}</button>
                    </div>
                    <label>{t.artifactSource}
                      <select
                        value={selectedArtifactPath}
                        onChange={(event) => {
                          const value = event.target.value;
                          setSelectedArtifactPath(value);
                          if (value !== CUSTOM_ARTIFACT) setRunForm({ ...runForm, artifactPath: value });
                        }}
                      >
                        <option value="">{t.artifactNone}</option>
                        <option value={CUSTOM_ARTIFACT}>{t.artifactCustom}</option>
                        {catalog.artifacts.map((item) => <option key={item.path} value={item.path}>{item.path}</option>)}
                      </select>
                    </label>
                    <div className="artifactUploadBox" data-testid="artifact-upload-box">
                      <div className="recentArtifactsHeader">
                        <strong className="sectionTitleLine">
                          <span>{t.artifactUploadTitle}</span>
                          <InfoTooltip text={t.artifactUploadTooltip} label={t.infoTooltipLabel} />
                        </strong>
                        <span className="recommendedArtifactsHint">{t.artifactUploadHint}</span>
                      </div>
                      <div className="artifactUploadControls">
                        <div className="artifactUploadControlRow">
                          <label className="filePickerButton">
                            <input
                              ref={artifactUploadInputRef}
                              type="file"
                              onChange={(event) => selectArtifactUploadFile(event.target.files?.[0] || null)}
                            />
                            <span>{artifactUploadFile ? artifactUploadFile.name : t.artifactChooseFile}</span>
                          </label>
                          <button type="button" className="secondary" disabled={!artifactUploadFile || artifactUploading || artifactFolderUploading} onClick={uploadSelectedArtifact}>
                            {artifactUploading ? t.artifactUploading : t.artifactUploadAction}
                          </button>
                        </div>
                        <div className="artifactUploadControlRow">
                          <label className="filePickerButton">
                            <input
                              ref={artifactFolderInputRef}
                              type="file"
                              multiple
                              {...({ webkitdirectory: "", directory: "" } as any)}
                              onChange={(event) => selectArtifactUploadFolder(Array.from(event.target.files || []))}
                              data-testid="artifact-folder-input"
                            />
                            <span>{artifactUploadFolderFiles.length ? `${artifactUploadFolderFiles[0].webkitRelativePath?.split("/")[0] || t.artifactFolderSelected} · ${artifactUploadFolderFiles.length}` : t.artifactChooseFolder}</span>
                          </label>
                          <button type="button" className="secondary" disabled={!artifactUploadFolderFiles.length || artifactUploading || artifactFolderUploading} onClick={uploadSelectedArtifactFolder}>
                            {artifactFolderUploading ? t.artifactFolderUploading : t.artifactFolderUploadAction}
                          </button>
                        </div>
                      </div>
                      {artifactUploadStatus && (
                        <div className={`artifactUploadStatus phase-${artifactUploadStatus.phase}`} data-testid="artifact-upload-status" aria-live="polite">
                          <div className="artifactUploadStatusHeader">
                            <div className="artifactUploadStatusTitle">
                              <span>{artifactUploadStatus.kind === "folder" ? t.artifactUploadKindFolder : t.artifactUploadKindFile}</span>
                              <strong>{artifactUploadStatus.name}</strong>
                              <small>
                                {artifactUploadStatus.fileCount.toLocaleString()} {t.files} · {formatBytes(artifactUploadStatus.size)}
                              </small>
                            </div>
                            <span className={`artifactUploadBadge phase-${artifactUploadStatus.phase}`}>
                              {artifactUploadStatus.phase === "uploaded"
                                ? t.artifactUploadStateUploaded
                                : artifactUploadStatus.phase === "uploading"
                                  ? t.artifactUploadStateUploading
                                  : artifactUploadStatus.phase === "failed"
                                    ? t.artifactUploadStateFailed
                                    : t.artifactUploadStateSelected}
                            </span>
                          </div>
                          <div className="artifactUploadProgress" aria-label={t.artifactUploadProgress}>
                            <div className="artifactUploadProgressTrack">
                              <span style={{ width: `${artifactUploadStatus.percent ?? 0}%` }} />
                            </div>
                            <small>
                              {artifactUploadStatus.percent === null || artifactUploadStatus.percent === undefined
                                ? t.artifactUploadProgressUnknown
                                : `${artifactUploadStatus.percent}%`}
                              {artifactUploadStatus.loaded !== undefined && artifactUploadStatus.total
                                ? ` · ${formatBytes(artifactUploadStatus.loaded)} / ${formatBytes(artifactUploadStatus.total)}`
                                : ""}
                            </small>
                          </div>
                          <p className="muted helperText">
                            {artifactUploadStatus.phase === "failed"
                              ? `${t.artifactUploadFailedHint}: ${artifactUploadStatus.message || ""}`
                              : artifactUploadStatus.message}
                          </p>
                          {artifactUploadStatus.path && (
                            <p className="artifactUploadPath">
                              <span>{t.artifactUploadSavedPath}</span>
                              <code>{artifactUploadStatus.path}</code>
                            </p>
                          )}
                        </div>
                      )}
                    </div>
                    {!!artifactRecommendations.length && (
                      <div className="recommendedArtifacts" data-testid="artifact-recommendations">
                        <div className="recentArtifactsHeader">
                          <strong className="sectionTitleLine">
                            <span>{t.recommendedArtifacts}</span>
                            <InfoTooltip text={t.recommendedArtifactsTooltip} label={t.infoTooltipLabel} />
                          </strong>
                          <span className="recommendedArtifactsHint">{t.recommendedArtifactHint}</span>
                        </div>
                        <div className="chipRow">
                          {artifactRecommendations.map((item) => (
                            <button
                              key={item.path}
                              type="button"
                              className={`secondary chipButton recommendationChip${runForm.artifactPath === item.path ? " active" : ""}`}
                              onClick={() => applyArtifactPreset(item.path)}
                              title={item.path}
                            >
                              <span>{item.name}</span>
                              <small>{item.path}</small>
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                    <label>{t.artifactPath}<input disabled={selectedArtifactPath !== CUSTOM_ARTIFACT} value={runForm.artifactPath} onChange={(event) => setRunForm({ ...runForm, artifactPath: event.target.value })} /></label>
                    <p className="muted helperText">{t.artifactOptionalHint}</p>
                    {!!recentArtifacts.length && (
                      <div className="recentArtifacts">
                        <div className="recentArtifactsHeader">
                          <strong className="sectionTitleLine">
                            <span>{t.recentArtifacts}</span>
                            <InfoTooltip text={t.recentArtifactsTooltip} label={t.infoTooltipLabel} />
                          </strong>
                          <button type="button" className="secondary" onClick={clearRecentArtifacts}>{t.clearRecentArtifacts}</button>
                        </div>
                        <div className="chipRow">
                          {recentArtifacts.map((item) => (
                            <button key={item} type="button" className="secondary chipButton" onClick={() => applyArtifactPreset(item)} title={item}>
                              {item}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                    {artifactPath && <ArtifactStatus check={artifactCheck} checking={artifactChecking} t={t} />}
                  </RunStepSection>
                  <ArtifactManagerDialog
                    open={artifactManagerOpen}
                    t={t}
                    selectedPath={runForm.artifactPath}
                    onClose={() => setArtifactManagerOpen(false)}
                    onUse={useManagedArtifact}
                    onArtifactsChanged={refreshArtifactCatalog}
                  />
                  <RunStepSection index={3} title={t.runStepLabConfig} hint={t.runStepLabConfigHint} tooltipLabel={t.infoTooltipLabel}>
                    <label>{t.configPath}<input value={runForm.configPath} onChange={(event) => setRunForm({ ...runForm, configPath: event.target.value })} /></label>
                    <label>{t.envFilePath}<input value={runForm.envFilePath} onChange={(event) => setRunForm({ ...runForm, envFilePath: event.target.value })} /></label>
                    <label>{t.maxParallel}<input type="number" min="1" value={runForm.maxParallel} onChange={(event) => setRunForm({ ...runForm, maxParallel: Number(event.target.value) })} /></label>
                    {suitePolicy && selectedSuitePath && (
                      <p className="muted helperText suitePolicyLine">
                        <span>
                          {t.entries}: {suitePolicy.entries}, {t.enabled}: {Math.max(0, suitePolicy.entries - suitePolicy.disabled)}, {t.allowFailure}: {suitePolicy.allowFailure}
                          {suitePolicy.maxParallel ? `, ${t.maxParallel}: ${suitePolicy.maxParallel}` : ""}
                        </span>
                        <InfoTooltip text={t.suitePolicyTooltip} label={t.infoTooltipLabel} />
                      </p>
                    )}
                    {labRunBlocked && artifactPath && <p className="notice fail">{t.labBlockedRun}</p>}
                  </RunStepSection>
                  <RunStepSection index={4} title={t.runStepOptions} hint={t.runStepOptionsHint} tooltipLabel={t.infoTooltipLabel}>
                    <button className="secondary wideButton" onClick={() => setShowAdvanced((value) => !value)}>{t.advancedOptions}</button>
                    {showAdvanced && (
                      <div className="advancedBox">
                        <p className="muted">{t.advancedWarning}</p>
                        <label className="checkLine"><input type="checkbox" checked={runForm.keepVm} onChange={(event) => setRunForm({ ...runForm, keepVm: event.target.checked })} />{t.keepVm}</label>
                        <label className="checkLine"><input type="checkbox" checked={runForm.fullClone} onChange={(event) => setRunForm({ ...runForm, fullClone: event.target.checked })} />{t.fullClone}</label>
                      </div>
                    )}
                  </RunStepSection>
                  <RunStepSection index={5} title={t.runStepReview} hint={t.runStepReviewHint} tooltipLabel={t.infoTooltipLabel}>
                    <CommandPreview title={t.suiteCommand} command={buildCommandPreview("suite-run", selectedSuitePath, runForm)} />
                    <CommandPreview title={t.scenarioCommand} command={buildCommandPreview("run", selectedScenarioPath, runForm)} />
                    <div className="runActionHints" aria-live="polite">
                      <p className={canRunSuite ? "ready" : "blocked"}>
                        <strong>{t.runSuite}: </strong>
                        <span>{canRunSuite ? t.runReadyToLaunch : suiteRunBlockReason}</span>
                      </p>
                      <p className={canRunScenario ? "ready" : "blocked"}>
                        <strong>{t.runScenario}: </strong>
                        <span>{canRunScenario ? (artifactPath ? t.runReadyToLaunch : t.scenarioSkeletonReady) : scenarioRunBlockReason}</span>
                      </p>
                    </div>
                    <div className="actions">
                      <button disabled={!canRunSuite} title={canRunSuite ? t.runReadyToLaunch : suiteRunBlockReason} onClick={runSuite}>{t.runSuite}</button>
                      <button disabled={!canRunScenario} title={canRunScenario ? t.runReadyToLaunch : scenarioRunBlockReason} className="secondary" onClick={runScenario}>{t.runScenario}</button>
                    </div>
                  </RunStepSection>
                </div>
            </div>
            <div className="panel console">
              <div className="consoleHeader">
                <div>
                  <h3>{t.liveConsole}</h3>
                  <p className="muted">
                    {effectiveJobId
                      ? `${t.selectedJob}: ${effectiveJobId} · ${t.jobStatus}: ${effectiveJobSummary?.status || "connecting"}`
                      : t.noStream}
                  </p>
                </div>
                <div className="actions">
                  {effectiveJobId && <button className="secondary" onClick={() => loadJobLog(effectiveJobId)}>{t.loadLog}</button>}
                  {effectiveJobId && (effectiveJobSummary?.status === "queued" || effectiveJobSummary?.status === "running") && (
                    <button type="button" onClick={cancelCurrentJob}>{t.cancelJob}</button>
                  )}
                </div>
              </div>
              <pre ref={consoleRef} role="log" aria-live="polite">{jobLog || (effectiveJobId ? t.connecting : t.noStream)}</pre>
            </div>
          </section>
        </>
        )}

        {tab === "results" && (
          <ResultsExplorer
            t={t}
            lang={lang}
            runs={filteredRuns}
            query={resultQuery}
            filter={resultFilter}
            kindFilter={resultKindFilter}
            issueFilter={resultIssueFilter}
            evidenceFilter={resultEvidenceFilter}
            selectedRunId={selectedRunId}
            detail={runDetail}
            progressEvents={resultProgressEvents}
            listCollapsed={resultListCollapsed}
            onQuery={setResultQuery}
            onFilter={setResultFilter}
            onKindFilter={setResultKindFilter}
            onIssueFilter={setResultIssueFilter}
            onEvidenceFilter={setResultEvidenceFilter}
            onToggleList={() => setResultListCollapsed((value) => !value)}
            onSelectRun={(runId) => {
              if (runId === selectedRunId) return;
              setRunDetail(null);
              setProgressEvents([]);
              setSelectedRunId(runId);
            }}
          />
        )}
      </section>
    </main>
  );
}

