export const CUSTOM_ARTIFACT = "__custom__";
export const RECENT_ARTIFACTS_KEY = "oslab.recentArtifacts";

export const defaultRequest = {
  configPath: "config/oslab.local.yaml",
  envFilePath: "config/oslab.local.env",
  artifactPath: "",
  maxParallel: 1,
  boot: 300,
  guest: 300,
  command: 420,
  pollInterval: 5,
  keepVm: false,
  fullClone: false,
};

export type DashboardRequest = typeof defaultRequest;
