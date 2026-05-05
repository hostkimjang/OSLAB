import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { WorkspaceService } from "../../infrastructure/workspace/workspace.service";
import { validateSuiteSchema } from "./validation.controller";

test("validateSuiteSchema accepts a minimal runnable suite", () => {
  const result = validateSuiteSchema({
    schemaVersion: 1,
    id: "smoke",
    runs: [{ id: "windows-smoke", scenario: "scenarios/windows/smoke.example.yaml" }],
  });

  assert.equal(result.ok, true);
  assert.deepEqual(result.errors, []);
});

test("validateSuiteSchema rejects empty runs, duplicate ids, invalid paths, and bad field shapes", () => {
  const empty = validateSuiteSchema({ schemaVersion: 1, id: "empty", runs: [] });
  assert.equal(empty.ok, false);
  assert.match(empty.errors.join("\n"), /runs must contain at least one run/);

  const invalid = validateSuiteSchema({
    schemaVersion: 1,
    id: "bad",
    maxParallel: 0,
    runs: [
      { id: "same", scenario: "scenarios/windows/smoke.example.yaml", tier: 1 },
      { id: "same", scenario: "../secret.yaml", allowFailure: "yes", enabled: "nope" },
    ],
  });

  assert.equal(invalid.ok, false);
  assert.match(invalid.errors.join("\n"), /maxParallel must be a positive integer/);
  assert.match(invalid.errors.join("\n"), /duplicates another run id/);
  assert.match(invalid.errors.join("\n"), /cannot include \.\. segments/);
  assert.match(invalid.errors.join("\n"), /tier must be a string/);
  assert.match(invalid.errors.join("\n"), /allowFailure must be a boolean/);
  assert.match(invalid.errors.join("\n"), /enabled must be a boolean/);
});

test("WorkspaceService authoring policy allows only expected authoring roots and extensions", async () => {
  const previousRoot = process.env.OSLAB_REPO_ROOT;
  const root = await mkdtemp(path.join(os.tmpdir(), "oslab-api-workspace-"));
  process.env.OSLAB_REPO_ROOT = root;
  try {
    const workspace = new WorkspaceService();
    await workspace.createText("validation/fixtures/windows/demo.ps1", "Write-Output ok");

    const saved = await readFile(path.join(root, "validation", "fixtures", "windows", "demo.ps1"), "utf8");
    assert.equal(saved, "Write-Output ok");
    await workspace.createText("validation/artifacts/windows/web-demo.ps1", "Write-Output artifact");
    const artifact = await workspace.readText("validation/artifacts/windows/web-demo.ps1");
    assert.equal(artifact, "Write-Output artifact");
    await workspace.createText("validation/artifacts/windows/web-metadata.yaml", "schemaVersion: 1\n");
    assert.equal(await workspace.readText("validation/artifacts/windows/web-metadata.yaml"), "schemaVersion: 1\n");
    await workspace.createText("validation/artifacts/windows/web-script.ts", "console.log('ok');\n");
    assert.equal(await workspace.readText("validation/artifacts/windows/web-script.ts"), "console.log('ok');\n");
    await workspace.createText("validation/artifacts/windows/web-script.cs", "Console.WriteLine(\"ok\");\n");
    assert.equal(await workspace.readText("validation/artifacts/windows/web-script.cs"), "Console.WriteLine(\"ok\");\n");
    await workspace.createText("validation/artifacts/windows/Dockerfile", "FROM alpine:3.20\n");
    assert.equal(await workspace.readText("validation/artifacts/windows/Dockerfile"), "FROM alpine:3.20\n");
    await assert.rejects(() => workspace.createText("validation/fixtures/windows/demo.txt", "nope"), /fixture files must end with/);
    await assert.rejects(() => workspace.createText("validation/artifacts/windows/installer.exe", "nope"), /artifactText files must end with/);
    await assert.rejects(() => workspace.writeText(".web-artifacts/uploaded.ps1", "nope"), /outside authoring roots/);
    await assert.rejects(() => workspace.createText("validation/fixtures/windows/con.ps1", "nope"), /reserved device names/);
    await assert.rejects(() => workspace.createText("validation/fixtures/windows/trailing /demo.ps1", "nope"), /dot or space/);
    await assert.rejects(() => workspace.createText("validation/fixtures/windows/bad\u0001name.ps1", "nope"), /control characters/);
    await assert.rejects(() => workspace.createText("validation/fixtures/windows/large.ps1", "x".repeat(1024 * 1024 + 1)), /too large/);
    await assert.rejects(() => workspace.createText("scenarios/windows/demo.local.yaml", "nope"), /Secret files/);
    await assert.rejects(() => workspace.writeText("config/oslab.local.env", "SECRET=1"), /Secret files|outside authoring roots/);
    await assert.rejects(() => workspace.readText("runs/example/run.json"), /outside authoring roots/);
  } finally {
    if (previousRoot === undefined) delete process.env.OSLAB_REPO_ROOT;
    else process.env.OSLAB_REPO_ROOT = previousRoot;
    await rm(root, { recursive: true, force: true });
  }
});
