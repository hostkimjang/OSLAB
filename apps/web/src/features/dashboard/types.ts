export type Tab = "dashboard" | "scenarios" | "fixtures" | "suites" | "artifacts" | "run" | "results";
export type EditorTab = "scenarios" | "fixtures" | "suites";
export type Lang = "en" | "ko";
export type ResultFilter = "all" | "failed" | "passed" | "running" | "stale";
export type ResultKindFilter = "all" | "run" | "suite";
export type ResultIssueFilter =
  | "all"
  | "provider_failure"
  | "preflight_failure"
  | "assertion_failure"
  | "run_failure"
  | "suite_entry_failure"
  | "required_failed"
  | "allowed_failed"
  | "cancelled"
  | "contract_gaps";
export type ResultEvidenceFilter = "all" | "clean" | "contract_gaps";
export type EditorState = { selectedPath: string; content: string; originalContent: string; query: string; isEditing: boolean };
export type ProgressEvent = { timestamp?: string; phase?: string; status?: string; message?: string; details?: Record<string, unknown> };
export type RunDetail = Record<string, any>;

export type ScenarioCommandModel = {
  shell: string;
  template: string;
};

export type ScenarioFixtureModel = {
  id: string;
  type: string;
  source: string;
  expectedOutput: string;
};

export type ScenarioProductStepModel = {
  id: string;
  shell: string;
  template: string;
  captureStdoutJson: boolean;
  expectStdoutJsonJson: string;
  secretTokensJson: string;
};

export type ScenarioAssertionModel = {
  id: string;
  type: string;
  bodyJson: string;
};

export type ScenarioBuilderModel = {
  schemaVersion: number;
  id: string;
  name: string;
  osFamily: string;
  osVersion: string;
  template: string;
  templateVmId: number | null;
  vmIdStart: number | null;
  vmIdEnd: number | null;
  guestMode: string;
  windowsOrder: string[];
  linuxOrder: string[];
  artifactType: string;
  artifactPathParam: string;
  artifactDestination: string;
  artifactTransfer: string;
  artifactCommand: ScenarioCommandModel;
  outputActualPath: string;
  outputActualAdapter: string;
  reportFormats: string[];
  cleanupDestroyVm: boolean;
  cleanupKeepVmOnFailure: boolean;
  fixtures: ScenarioFixtureModel[];
  productSteps: ScenarioProductStepModel[];
  assertions: ScenarioAssertionModel[];
  fixtureCount: number;
  assertionCount: number;
};

export type SuiteBuilderRun = {
  id: string;
  scenario: string;
  tier: string;
  allowFailure: boolean;
  enabled: boolean;
};

export type SuiteBuilderModel = {
  schemaVersion: number;
  id: string;
  name: string;
  maxParallel: number | null;
  runs: SuiteBuilderRun[];
};
