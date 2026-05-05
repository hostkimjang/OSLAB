import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { WorkspaceService } from "../../infrastructure/workspace/workspace.service";
import { ArtifactLanguageService } from "./artifact-language.service";
import { ArtifactController } from "./artifact.controller";

test("ArtifactController manages repo and uploaded artifacts with safe text authoring", async () => {
  const previousRoot = process.env.OSLAB_REPO_ROOT;
  const root = await mkdtemp(path.join(os.tmpdir(), "oslab-artifacts-"));
  process.env.OSLAB_REPO_ROOT = root;
  try {
    await mkdir(path.join(root, "validation", "artifacts", "demo-folder"), { recursive: true });
    await writeFile(path.join(root, "validation", "artifacts", "demo.ps1"), "Write-Output ok", "utf8");
    await writeFile(path.join(root, "validation", "artifacts", "demo-folder", "note.txt"), "folder file", "utf8");
    await mkdir(path.join(root, ".web-artifacts", "uploaded"), { recursive: true });
    await writeFile(path.join(root, ".web-artifacts", "uploaded", "tool.exe"), Buffer.from([1, 2, 3]));

    const workspace = new WorkspaceService();
    const controller = new ArtifactController({ artifactUpload: { create: async () => ({}), findMany: async () => [] } } as any, workspace, new ArtifactLanguageService());

    const managed = await controller.manage();
    const repoText = managed.find((item) => item.path === "validation/artifacts/demo.ps1");
    const uploadedDir = managed.find((item) => item.path === ".web-artifacts/uploaded");
    assert.equal(repoText?.editable, true);
    assert.equal(repoText?.archivable, true);
    assert.equal(repoText?.deletable, false);
    assert.equal(repoText?.archiveOnly, true);
    assert.equal(repoText?.artifactType, "text");
    assert.equal(repoText?.hash?.length, 64);
    assert.equal(uploadedDir?.source, "uploaded");
    assert.equal(uploadedDir?.artifactType, "directory");
    assert.equal(uploadedDir?.fileCount, 1);
    assert.equal(uploadedDir?.deletable, true);

    const tree = await controller.tree("validation/artifacts/demo-folder");
    assert.equal(tree.path, "validation/artifacts/demo-folder");
    assert.equal(tree.truncated, false);
    assert.ok(tree.items.some((item) => item.path === "validation/artifacts/demo-folder/note.txt"));

    const content = await controller.content("validation/artifacts/demo.ps1");
    assert.equal(content.content, "Write-Output ok");
    await controller.saveContent({ path: "validation/artifacts/demo.ps1", content: "Write-Output saved" });
    assert.equal(await readFile(path.join(root, "validation", "artifacts", "demo.ps1"), "utf8"), "Write-Output saved");

    const created = await controller.template({ kind: "json", path: "validation/artifacts/new-result.json" });
    assert.equal(created.path, "validation/artifacts/new-result.json");
    await assert.rejects(() => controller.template({ kind: "json", path: "validation/artifacts/new-result.json" }), /already exists/);
    const yamlArtifact = await controller.template({ kind: "yaml", path: "validation/artifacts/new-metadata.yaml" });
    assert.equal(yamlArtifact.path, "validation/artifacts/new-metadata.yaml");
    assert.match(yamlArtifact.content, /schemaVersion: 1/);
    const tsArtifact = await controller.template({ kind: "typescript", path: "validation/artifacts/new-script.ts" });
    assert.match(tsArtifact.content, /type CommandResult/);
    const csharpArtifact = await controller.template({ kind: "csharp", path: "validation/artifacts/new-script.cs" });
    assert.match(csharpArtifact.content, /JsonSerializer/);
    const project = await controller.projectTemplate({ kind: "script-project", path: "validation/artifacts/web-project", shell: "powershell", name: "QA project" });
    assert.equal(project.path, "validation/artifacts/web-project");
    assert.ok(project.files.includes("validation/artifacts/web-project/run-artifact.ps1"));
    assert.match(await readFile(path.join(root, "validation", "artifacts", "web-project", "run-artifact.ps1"), "utf8"), /QA project/);
    const inventory = await controller.projectTemplate({ kind: "inventory-agent", path: "validation/artifacts/inventory-starter" });
    assert.ok(inventory.files.includes("validation/artifacts/inventory-starter/run-inventory.ps1"));
    await assert.rejects(() => controller.projectTemplate({ kind: "script-project", path: "validation/artifacts/web-project" }), /already exists/);
    await assert.rejects(() => controller.projectTemplate({ kind: "script-project", path: "validation/fixtures/nope" }), /validation\/artifacts/);
    const assist = await controller.assistCheck({ path: "validation/artifacts/demo.ps1", content: "Remove-Item C:\\Temp -Recurse\nWrite-Output '{{BadToken}}'" });
    assert.equal(assist.ok, true);
    assert.equal(assist.language, "powershell");
    assert.ok(assist.toolStatus);
    assert.ok(assist.firstRunTips?.length);
    assert.ok(assist.suggestedSnippets?.some((snippet) => snippet.id === "powershell-result"));
    assert.ok(assist.issues.some((issue) => issue.code === "dangerous.pattern"));
    assert.ok(assist.issues.some((issue) => issue.code === "placeholder.unknown"));
    const badPython = await controller.assistCheck({ path: "validation/artifacts/demo.py", content: "import subprocess\nsubprocess.run('echo hi', shell=True)\n" });
    assert.ok(badPython.issues.some((issue) => issue.code === "python.subprocess-shell"));
    const badJson = await controller.assistCheck({ path: "validation/artifacts/new-result.json", content: "{ nope" });
    assert.equal(badJson.ok, false);
    assert.ok(badJson.issues.some((issue) => issue.code === "json.parse"));
    const pythonCompletion = await controller.assistComplete({
      path: "validation/artifacts/demo.py",
      language: "python",
      content: "pri",
      line: 1,
      column: 4,
    });
    assert.equal(pythonCompletion.ok, true);
    assert.equal(pythonCompletion.language, "python");
    assert.ok(pythonCompletion.items.some((item) => item.label === "print"));
    const pythonRangeCompletion = await controller.assistComplete({
      path: "validation/artifacts/demo.py",
      language: "python",
      content: "for i in ra",
      line: 1,
      column: 11,
    });
    assert.ok(pythonRangeCompletion.items.some((item) => item.label === "range"));
    assert.ok(pythonRangeCompletion.items.some((item) => item.label === "for i in range"));
    const shellCompletion = await controller.assistComplete({
      path: "validation/artifacts/demo.sh",
      language: "shell",
      content: "gre",
      line: 1,
      column: 4,
    });
    assert.ok(shellCompletion.items.some((item) => item.label === "grep"));
    assert.ok(["lsp", "setupNeeded", "internal"].includes(pythonCompletion.mode));
    const jsonCompletion = await controller.assistComplete({
      path: "validation/artifacts/result.json",
      content: "{\n  \"sche",
      line: 2,
      column: 8,
    });
    assert.ok(jsonCompletion.items.some((item) => item.label === "schemaVersion"));
    const yamlCompletion = await controller.assistComplete({
      path: "validation/artifacts/result.yaml",
      content: "sche",
      line: 1,
      column: 5,
    });
    assert.ok(yamlCompletion.items.some((item) => item.label === "schemaVersion"));
    const scenarioYamlCompletion = await controller.assistComplete({
      path: "scenarios/windows/demo-authoring.yaml",
      language: "yaml",
      content: "sche",
      line: 1,
      column: 5,
    });
    assert.ok(scenarioYamlCompletion.items.some((item) => item.label === "schemaVersion"));
    const suiteYamlCompletion = await controller.assistComplete({
      path: "validation/suites/demo-authoring.yaml",
      language: "yaml",
      content: "runs:\n  - scen",
      line: 2,
      column: 9,
    });
    assert.ok(suiteYamlCompletion.items.some((item) => item.label === "scenario"));
    const tsCompletion = await controller.assistComplete({
      path: "validation/artifacts/result.ts",
      content: "con",
      line: 1,
      column: 4,
    });
    assert.ok(tsCompletion.items.some((item) => item.label === "console.log"));
    const csharpCompletion = await controller.assistComplete({
      path: "validation/artifacts/result.cs",
      content: "Con",
      line: 1,
      column: 4,
    });
    assert.equal(csharpCompletion.language, "csharp");
    assert.ok(csharpCompletion.items.some((item) => item.label === "Console.WriteLine"));
    const diagnostics = await controller.assistDiagnostics({ path: "validation/artifacts/result.json", content: "{ nope" });
    assert.equal(diagnostics.ok, false);
    assert.ok(diagnostics.issues.some((issue) => issue.code === "json.parse"));
    const yamlDiagnostics = await controller.assistDiagnostics({ path: "validation/artifacts/result.yaml", content: "key: [nope" });
    assert.equal(yamlDiagnostics.ok, false);
    assert.ok(yamlDiagnostics.issues.some((issue) => issue.code === "yaml.parse"));
    await assert.rejects(() => controller.assistComplete({ path: "config/oslab.local.env", content: "x", line: 1, column: 1 }), /Secret files|outside authoring roots|Only validation\/artifacts/);
    await assert.rejects(() => controller.saveContent({ path: ".web-artifacts/uploaded/tool.exe", content: "nope" }), /outside authoring roots|Only validation\/artifacts/);
    await assert.rejects(() => controller.content("validation/artifacts/installer.exe"), /artifactText files must end with|Only validation\/artifacts/);
    await assert.rejects(() => controller.content(".web-artifacts/uploaded/tool.exe"), /outside authoring roots|Only validation\/artifacts/);
    const languageTools = await controller.languageTools();
    assert.ok(languageTools.some((tool) => tool.language === "python"));
    assert.ok(languageTools.some((tool) => tool.language === "yaml" && tool.mode === "lsp"));
    assert.ok(languageTools.some((tool) => tool.language === "typescript" && tool.mode === "lsp"));
    assert.ok(languageTools.some((tool) => tool.language === "csharp" && ["lsp", "setupNeeded"].includes(tool.mode || "")));
    const pythonInstall = await controller.installLanguageTool({ language: "python" });
    assert.equal(pythonInstall.ok, false);
    assert.equal(pythonInstall.language, "python");
    assert.match(pythonInstall.message, /Python|Install/i);
    await assert.rejects(() => controller.installLanguageTool({ language: "ruby" as any }), /Unsupported artifact language/);
    await assert.rejects(() => controller.template({ kind: "powershell", path: "validation/artifacts/con.ps1" }), /reserved device names/);
    await assert.rejects(() => controller.projectTemplate({ kind: "script-project", path: "validation/artifacts/con" }), /reserved device names/);
    await assert.rejects(() => controller.tree("../validation/artifacts/demo-folder"), /cannot include|outside/);
    await assert.rejects(() => controller.tree("config/oslab.local.env"), /Secret files|outside/);
    await assert.rejects(() => controller.delete({ path: "validation/artifacts/demo.ps1", dryRun: true }), /archived before deletion/);

    const repoArchivePreview = await controller.archive({ path: "validation/artifacts/demo-folder", dryRun: true });
    assert.equal(repoArchivePreview.ok, false);
    assert.equal(repoArchivePreview.dryRun, true);
    assert.equal(repoArchivePreview.archiveOnly, true);
    assert.match(repoArchivePreview.archivePath || "", /^\.artifact-archive\//);
    const repoArchive = await controller.archive({ path: "validation/artifacts/demo-folder", dryRun: false, confirmToken: repoArchivePreview.confirmToken });
    assert.equal(repoArchive.ok, true);
    assert.ok(repoArchive.completedPath?.startsWith(".artifact-archive/"));
    await assert.rejects(() => readFile(path.join(root, "validation", "artifacts", "demo-folder", "note.txt"), "utf8"), /ENOENT/);
    const archivedTree = await controller.tree(repoArchive.completedPath || "");
    assert.ok(archivedTree.items.some((item) => item.name === "note.txt"));
    const archiveDeletePreview = await controller.delete({ path: repoArchive.completedPath || "", dryRun: true });
    const archiveDelete = await controller.delete({ path: repoArchive.completedPath || "", dryRun: false, confirmToken: archiveDeletePreview.confirmToken });
    assert.equal(archiveDelete.ok, true);
    assert.ok(!(await controller.manage()).some((item) => item.path.startsWith(".artifact-archive/")));

    const uploadedDeletePreview = await controller.delete({ path: ".web-artifacts/uploaded", dryRun: true });
    assert.equal(uploadedDeletePreview.source, "uploaded");
    assert.equal(uploadedDeletePreview.fileCount, 1);
    await assert.rejects(() => controller.delete({ path: ".web-artifacts/uploaded", dryRun: false, confirmToken: "bad-token" }), /Invalid artifact confirmation/);
    const uploadedDelete = await controller.delete({ path: ".web-artifacts/uploaded", dryRun: false, confirmToken: uploadedDeletePreview.confirmToken });
    assert.equal(uploadedDelete.ok, true);
    await assert.rejects(() => readFile(path.join(root, ".web-artifacts", "uploaded", "tool.exe")), /ENOENT/);
  } finally {
    if (previousRoot === undefined) delete process.env.OSLAB_REPO_ROOT;
    else process.env.OSLAB_REPO_ROOT = previousRoot;
    await rm(root, { recursive: true, force: true });
  }
});
