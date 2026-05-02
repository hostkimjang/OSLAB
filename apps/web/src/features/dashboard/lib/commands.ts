import { defaultRequest, type DashboardRequest } from "../model";

export function buildCommandPreview(kind: "run" | "suite-run", definitionPath: string, request: DashboardRequest = defaultRequest): string {
  const args = ["uv", "run", "oslab", kind];
  if (kind === "run") args.push("--scenario", definitionPath || "<scenario>");
  else args.push("--suite", definitionPath || "<suite>");
  args.push("--config", request.configPath || "<config>");
  args.push("--env-file", request.envFilePath || "<env-file>");
  if (request.artifactPath.trim()) {
    args.push("--artifact-path", request.artifactPath.trim());
  } else if (kind === "suite-run") {
    args.push("--artifact-path", "<artifact-path>");
  }
  if (request.keepVm) args.push("--keep-vm");
  if (request.fullClone) args.push("--full-clone");
  args.push("--boot-timeout-seconds", String(request.boot));
  args.push("--guest-timeout-seconds", String(request.guest));
  args.push("--command-timeout-seconds", String(request.command));
  args.push("--poll-interval-seconds", String(request.pollInterval));
  if (kind === "suite-run") args.push("--max-parallel", String(request.maxParallel));
  return args.map((part) => (/\s/.test(part) ? `"${part}"` : part)).join(" ");
}
