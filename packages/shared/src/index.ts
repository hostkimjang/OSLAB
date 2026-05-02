export type RunKind = "scenario" | "suite";

export type JobStatus = "queued" | "running" | "passed" | "failed" | "cancelled";

export interface JobTimeouts {
  boot?: number;
  guest?: number;
  command?: number;
  pollInterval?: number;
}

export interface RunScenarioRequest {
  scenarioPath: string;
  configPath?: string;
  envFilePath?: string;
  artifactPath?: string;
  uploadedArtifactId?: string | null;
  runId?: string;
  keepVm?: boolean;
  fullClone?: boolean;
  timeouts?: JobTimeouts;
}

export interface RunSuiteRequest {
  suitePath: string;
  configPath?: string;
  envFilePath?: string;
  artifactPath?: string;
  uploadedArtifactId?: string | null;
  runId?: string;
  keepVm?: boolean;
  fullClone?: boolean;
  maxParallel?: number;
  timeouts?: JobTimeouts;
}

export interface ValidationSuiteEntry {
  id: string;
  scenario: string;
  tier?: string;
  allowFailure?: boolean;
  enabled?: boolean;
}

export interface ValidationSuiteFile {
  schemaVersion: 1;
  id: string;
  name?: string;
  maxParallel?: number;
  runs: ValidationSuiteEntry[];
}

export interface CatalogItem {
  path: string;
  name: string;
  kind: "scenario" | "suite" | "fixture" | "artifact";
}

export interface ArtifactUploadSummary {
  id: string;
  filename: string;
  path: string;
  size: number;
  fileCount?: number;
  createdAt: string;
}

export type ManagedArtifactSource = "repo" | "uploaded" | "archive";
export type ManagedArtifactKind = "file" | "directory" | "other";
export type ManagedArtifactType = "text" | "binary" | "directory" | "other";
export type ArtifactManageAction = "archive" | "delete";
export type ArtifactTemplateKind = "powershell" | "shell" | "python" | "c" | "json" | "txt" | "cmd" | "bat";
export type ArtifactProjectTemplateKind = "script-project" | "inventory-agent" | "install-profile";
export type ArtifactStudioMode = "browse" | "create" | "edit";
export type ArtifactLanguageKind = "powershell" | "shell" | "python" | "json" | "bat" | "c" | "plaintext";
export type ArtifactLanguageToolState = "available" | "partial" | "missing" | "unsupported" | "error";
export type ArtifactLanguageToolMode = "lsp" | "internal" | "setupNeeded" | "unavailable";
export type ArtifactAssistCompletionSource = "lsp" | "internal" | "snippet";

export interface ArtifactLanguageToolDetail {
  id: string;
  label: string;
  state: Exclude<ArtifactLanguageToolState, "partial">;
  command?: string;
  version?: string;
  hint?: string;
}

export interface ArtifactLanguageToolStatus {
  language: ArtifactLanguageKind;
  label: string;
  state: ArtifactLanguageToolState;
  mode?: ArtifactLanguageToolMode;
  serverManaged?: boolean;
  installable: boolean;
  installHint: string;
  nextAction: string;
  tools: ArtifactLanguageToolDetail[];
}

export interface ArtifactLanguageToolInstallResponse {
  ok: boolean;
  language: ArtifactLanguageKind;
  message: string;
  status: ArtifactLanguageToolStatus;
}

export interface ArtifactProjectTemplateRequest {
  kind: ArtifactProjectTemplateKind;
  path: string;
  shell?: "powershell" | "shell" | "python" | "cmd" | "bat";
  name?: string;
}

export interface ArtifactProjectTemplateResponse {
  path: string;
  files: string[];
}

export type ArtifactAssistSeverity = "info" | "warning" | "error";

export interface ArtifactAssistIssue {
  severity: ArtifactAssistSeverity;
  code: string;
  message: string;
  line?: number | null;
  column?: number | null;
}

export interface ArtifactAssistSnippet {
  id: string;
  label: string;
  detail: string;
  language: string;
  insertText: string;
}

export interface ArtifactAssistCompletionItem {
  id: string;
  label: string;
  detail: string;
  documentation?: string;
  language: ArtifactLanguageKind;
  insertText: string;
  source: ArtifactAssistCompletionSource;
  kind?: "function" | "keyword" | "variable" | "module" | "snippet" | "property" | "file" | "text";
}

export interface ArtifactAssistCompletionRequest {
  path: string;
  language?: ArtifactLanguageKind;
  content: string;
  line: number;
  column: number;
}

export interface ArtifactAssistCompletionResponse {
  ok: boolean;
  language: ArtifactLanguageKind;
  mode: ArtifactLanguageToolMode;
  checkedAt: string;
  items: ArtifactAssistCompletionItem[];
  toolStatus?: ArtifactLanguageToolStatus;
  fallbackReason?: string | null;
}

export interface ArtifactAssistDiagnosticsRequest {
  path: string;
  language?: ArtifactLanguageKind;
  content: string;
}

export interface ArtifactAssistDiagnosticsResponse {
  ok: boolean;
  language: ArtifactLanguageKind;
  mode: ArtifactLanguageToolMode;
  checkedAt: string;
  issues: ArtifactAssistIssue[];
  toolStatus?: ArtifactLanguageToolStatus;
  fallbackReason?: string | null;
}

export interface ArtifactAssistCheckResult {
  ok: boolean;
  checkedAt: string;
  language: ArtifactLanguageKind;
  toolStatus?: ArtifactLanguageToolStatus;
  issues: ArtifactAssistIssue[];
  snippets: ArtifactAssistSnippet[];
  suggestedSnippets?: ArtifactAssistSnippet[];
  firstRunTips?: string[];
}

export interface ManagedArtifactItem {
  path: string;
  name: string;
  source: ManagedArtifactSource;
  kind: ManagedArtifactKind;
  artifactType: ManagedArtifactType;
  editable: boolean;
  previewable: boolean;
  size: number | null;
  totalBytes?: number | null;
  fileCount?: number | null;
  modifiedAt: string | null;
  hash?: string | null;
  archivable?: boolean;
  deletable?: boolean;
  archiveOnly?: boolean;
  truncated?: boolean;
}

export interface ArtifactTreeItem {
  path: string;
  name: string;
  kind: ManagedArtifactKind;
  artifactType: ManagedArtifactType;
  size: number | null;
  modifiedAt: string | null;
  depth: number;
}

export interface ArtifactTreeResponse {
  path: string;
  items: ArtifactTreeItem[];
  totalItems: number;
  truncated: boolean;
}

export interface ArtifactManagePreview {
  action: ArtifactManageAction;
  path: string;
  source: ManagedArtifactSource;
  kind: ManagedArtifactKind;
  artifactType: ManagedArtifactType;
  fileCount: number;
  totalBytes: number;
  archivePath?: string | null;
  archiveOnly: boolean;
  confirmationRequired: boolean;
  confirmToken: string;
  message: string;
}

export interface ArtifactManageActionResponse extends ArtifactManagePreview {
  ok: boolean;
  dryRun: boolean;
  completedPath?: string | null;
}

export type SyntaxValidationKind = "yaml" | "powershell" | "unsupported";

export interface SyntaxValidationIssue {
  message: string;
  line?: number | null;
  column?: number | null;
  endLine?: number | null;
  endColumn?: number | null;
}

export interface SyntaxValidationResult {
  ok: boolean;
  kind: SyntaxValidationKind;
  checkedAt: string;
  issues: SyntaxValidationIssue[];
  message: string;
  skipped?: boolean;
}

export interface JobSummary {
  id: string;
  kind: RunKind;
  status: JobStatus;
  title: string;
  createdAt: string;
  startedAt?: string | null;
  completedAt?: string | null;
  runId?: string | null;
  exitCode?: number | null;
}

export interface RunSummary {
  id: string;
  kind: "run" | "suite";
  status?: string;
  scenarioId?: string | null;
  scenarioPath?: string | null;
  suiteId?: string | null;
  failureClass?: string | null;
  failureClasses?: string[];
  entries?: number | null;
  failedEntries?: number | null;
  requiredFailed?: number | null;
  allowedFailed?: number | null;
  evidenceSummary?: {
    total: number;
    present: number;
    missingRequired: number;
    contractGaps: number;
  };
  artifactStatus?: string;
  jobId?: string | null;
  jobStatus?: string | null;
  startedAt?: string | null;
  completedAt?: string | null;
  statusMeta?: {
    source: "artifact" | "job" | "stale-timeout";
    reason: string;
    artifactStatus: string;
    effectiveStatus: string;
    jobId?: string | null;
    jobStatus?: string | null;
  };
  path: string;
  updatedAt: string;
}

export type RunEvidenceStatus = "present" | "missing" | "notApplicable" | "contractGap";

export type RunEvidenceGroup = "core" | "timeline" | "outputs" | "reports" | "cleanup";

export type RunFileGroup = RunEvidenceGroup | "other";

export interface RunEvidenceItem {
  key: string;
  label: string;
  group: RunEvidenceGroup;
  relativePath?: string;
  required: boolean;
  status: RunEvidenceStatus;
  size?: number | null;
  modifiedAt?: string | null;
  reason?: string;
  description: string;
  previewable?: boolean;
}

export interface RunEvidenceChecklist {
  total: number;
  present: number;
  missingRequired: number;
  contractGaps: number;
  items: RunEvidenceItem[];
}

export interface RunFileItem {
  label: string;
  group: RunFileGroup;
  relativePath: string;
  status: RunEvidenceStatus;
  required: boolean;
  size?: number | null;
  modifiedAt?: string | null;
  previewable: boolean;
  discovered: boolean;
  reason?: string;
  description?: string;
}

export type LabStatusLevel = "ready" | "degraded" | "blocked";

export interface LabStatusCheck {
  ok: boolean;
  message: string;
  details?: Record<string, unknown>;
}

export interface LabVmSummary {
  vmid: number;
  name?: string;
  node?: string;
  status?: string;
}

export interface LabStatus {
  status: LabStatusLevel;
  checkedAt: string;
  scenarioPath: string;
  configPath: string;
  envFilePath: string;
  checks: {
    configFile: LabStatusCheck;
    envFile: LabStatusCheck;
    token: LabStatusCheck;
    connectivity: LabStatusCheck;
    node: LabStatusCheck;
    template: LabStatusCheck;
    vmidRange: LabStatusCheck;
  };
  provider: {
    type: "proxmox";
    apiUrl?: string;
    node?: string;
    verifyTls?: boolean;
    version?: string;
    release?: string;
    elapsedMs?: number;
  };
  template?: {
    vmId?: number;
    expectedName?: string;
    name?: string;
    node?: string;
    status?: string;
    isTemplate?: boolean;
  };
  vmidRange?: {
    start?: number;
    end?: number;
    total?: number;
    usedInRange: number[];
    reservedLocks: number[];
    freeCount?: number;
    recommendedVmId?: number | null;
    requiredCapacity?: number;
    capacityOk?: boolean;
  };
  vms: {
    running: LabVmSummary[];
    stale: LabVmSummary[];
    oslab: LabVmSummary[];
  };
  issues: string[];
  warnings: string[];
}

export interface LabCleanupTarget {
  vmid: number;
  name?: string;
  node?: string;
  status?: string;
  stale: boolean;
  running: boolean;
}

export interface LabCleanupRequest {
  scenarioPath?: string;
  configPath?: string;
  envFilePath?: string;
  dryRun?: boolean;
  confirmToken?: string;
  includeRunning?: boolean;
}

export interface LabCleanupResponse {
  ok: boolean;
  dryRun: boolean;
  confirmationRequired: boolean;
  confirmToken?: string;
  targets: LabCleanupTarget[];
  wouldDestroy: number[];
  requested: number[];
  failed: string[];
  message: string;
}

export interface ArtifactPathCheck {
  ok: boolean;
  exists: boolean;
  path?: string;
  kind?: "directory" | "file" | "other";
  size?: number | null;
  modifiedAt?: string;
  message: string;
}
