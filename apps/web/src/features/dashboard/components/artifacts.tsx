import dynamic from "next/dynamic";
import { useEffect, useMemo, useRef, useState } from "react";
import type {
  ArtifactAssistCheckResult,
  ArtifactAssistCompletionResponse,
  ArtifactAssistIssue,
  ArtifactLanguageKind,
  ArtifactLanguageToolInstallResponse,
  ArtifactLanguageToolStatus,
  ArtifactManageAction,
  ArtifactManageActionResponse,
  ArtifactProjectTemplateKind,
  ArtifactStudioMode,
  ArtifactTemplateKind,
  ArtifactTreeResponse,
  ManagedArtifactItem,
  SyntaxValidationResult,
} from "@oslab/shared";
import { apiGet, apiPost, formatBytes } from "../lib";
import type { DashboardText } from "../model";
import { InfoTooltip } from "./common";

const MonacoEditor = dynamic(() => import("@monaco-editor/react").then((module) => module.Editor), {
  ssr: false,
  loading: () => <div className="artifactMonacoLoading">Loading editor...</div>,
});

type ArtifactSourceFilter = "all" | "repo" | "uploaded" | "archive";
type ArtifactTypeFilter = "all" | "text" | "binary" | "directory";
type ArtifactCreateMode = "file" | "project" | "inventory";
type AssistTab = "help" | "complete" | "check" | "contract" | "ai";

const TEMPLATE_KINDS: ArtifactTemplateKind[] = ["powershell", "shell", "python", "c", "csharp", "json", "yaml", "javascript", "typescript", "html", "css", "markdown", "dockerfile", "txt", "cmd", "bat"];
const PROJECT_SHELLS = ["powershell", "shell", "python", "cmd", "bat"] as const;
const TEMPLATE_EXTENSIONS: Record<ArtifactTemplateKind, string> = {
  powershell: ".ps1",
  shell: ".sh",
  python: ".py",
  c: ".c",
  csharp: ".cs",
  json: ".json",
  yaml: ".yaml",
  javascript: ".js",
  typescript: ".ts",
  html: ".html",
  css: ".css",
  markdown: ".md",
  dockerfile: ".dockerfile",
  txt: ".txt",
  cmd: ".cmd",
  bat: ".bat",
};

export function ArtifactManagerDialog({
  open,
  t,
  selectedPath,
  onClose,
  onUse,
  onArtifactsChanged,
}: {
  open: boolean;
  t: DashboardText;
  selectedPath: string;
  onClose: () => void;
  onUse: (path: string) => void;
  onArtifactsChanged: () => Promise<void> | void;
}) {
  const dialogRef = useRef<HTMLElement | null>(null);
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    const previousActiveElement = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    document.body.style.overflow = "hidden";
    closeButtonRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
      if (event.key !== "Tab") return;
      const focusable = Array.from(dialogRef.current?.querySelectorAll<HTMLElement>("button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])") ?? []).filter(
        (element) => !element.hasAttribute("disabled"),
      );
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (!first || !last) return;
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
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="previewOverlay"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section ref={dialogRef} className="previewDialog artifactManagerDialog artifactStudioDialog" role="dialog" aria-modal="true" aria-labelledby="artifact-manager-title">
        <header className="previewDialogHeader">
          <div>
            <p className="eyebrow">{t.runStepArtifact}</p>
            <h3 id="artifact-manager-title">{copy(t, "artifactStudioTitle", "Artifact Studio")}</h3>
            <p className="muted previewPath">{copy(t, "artifactStudioSubtitle", t.artifactManagerSubtitle)}</p>
          </div>
          <div className="previewDialogActions">
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
        <ArtifactStudio
          t={t}
          selectedPath={selectedPath}
          onUse={onUse}
          onArtifactsChanged={onArtifactsChanged}
          embedded
        />
      </section>
    </div>
  );
}

export function ArtifactStudio({
  t,
  selectedPath,
  onUse,
  onUseForScenario,
  onArtifactsChanged,
  embedded = false,
}: {
  t: DashboardText;
  selectedPath: string;
  onUse: (path: string) => void;
  onUseForScenario?: (path: string) => void;
  onArtifactsChanged: () => Promise<void> | void;
  embedded?: boolean;
}) {
  const [items, setItems] = useState<ManagedArtifactItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState("");
  const [sourceFilter, setSourceFilter] = useState<ArtifactSourceFilter>("all");
  const [typeFilter, setTypeFilter] = useState<ArtifactTypeFilter>("all");
  const [studioMode, setStudioMode] = useState<ArtifactStudioMode>("browse");
  const [selected, setSelected] = useState<ManagedArtifactItem | null>(null);
  const [content, setContent] = useState("");
  const [originalContent, setOriginalContent] = useState("");
  const [contentLoading, setContentLoading] = useState(false);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [syntax, setSyntax] = useState<SyntaxValidationResult | null>(null);
  const [assist, setAssist] = useState<ArtifactAssistCheckResult | null>(null);
  const [languageTools, setLanguageTools] = useState<ArtifactLanguageToolStatus[]>([]);
  const [assistTab, setAssistTab] = useState<AssistTab>("help");
  const [diffOpen, setDiffOpen] = useState(false);
  const [tree, setTree] = useState<ArtifactTreeResponse | null>(null);
  const [treeLoading, setTreeLoading] = useState(false);
  const [artifactAction, setArtifactAction] = useState<ArtifactManageAction | null>(null);
  const [actionPreview, setActionPreview] = useState<ArtifactManageActionResponse | null>(null);
  const [actionWorking, setActionWorking] = useState(false);
  const [createMode, setCreateMode] = useState<ArtifactCreateMode>("file");
  const [templateKind, setTemplateKind] = useState<ArtifactTemplateKind>("powershell");
  const [templatePath, setTemplatePath] = useState(() => defaultArtifactPath("powershell"));
  const [projectKind, setProjectKind] = useState<ArtifactProjectTemplateKind>("script-project");
  const [projectShell, setProjectShell] = useState<typeof PROJECT_SHELLS[number]>("powershell");
  const [projectPath, setProjectPath] = useState(() => defaultProjectPath("script-project"));
  const [projectName, setProjectName] = useState("Web artifact project");
  const [notice, setNotice] = useState("");
  const contentRef = useRef("");
  const editorRef = useRef<any>(null);
  const monacoRef = useRef<any>(null);

  const dirty = content !== originalContent;
  const diff = useMemo(() => buildDiffPreview(originalContent, content), [content, originalContent]);
  const filteredItems = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return items.filter((item) => {
      if (sourceFilter !== "all" && item.source !== sourceFilter) return false;
      if (typeFilter !== "all" && item.artifactType !== typeFilter) return false;
      if (!needle) return true;
      return `${item.name} ${item.path}`.toLowerCase().includes(needle);
    });
  }, [items, query, sourceFilter, typeFilter]);
  const createLanguage = createMode === "file" ? monacoLanguageForTemplate(templateKind) : monacoLanguageForProjectShell(projectShell);
  const editorLanguage = selected ? monacoLanguageForPath(selected.path) : createLanguage;
  const activeLanguage = studioMode === "create" ? createLanguage : editorLanguage;
  const currentToolStatus = languageTools.find((tool) => tool.language === activeLanguage) || assist?.toolStatus || null;

  useEffect(() => {
    void refreshItems();
    void refreshLanguageTools();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    setTemplatePath(defaultArtifactPath(templateKind));
  }, [templateKind]);

  useEffect(() => {
    setProjectPath(defaultProjectPath(projectKind));
  }, [projectKind]);

  useEffect(() => {
    if (!selected?.editable || studioMode === "create") return;
    const timer = window.setTimeout(() => {
      void runAssistCheck();
    }, 350);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [content, selected?.path, studioMode]);

  useEffect(() => {
    if (!monacoRef.current || !editorRef.current) return;
    const model = editorRef.current.getModel?.();
    if (!model) return;
    configureMonaco(monacoRef.current, editorLanguage);
    monacoRef.current.editor.setModelLanguage(model, editorLanguage);
  }, [editorLanguage]);

  useEffect(() => {
    if (!monacoRef.current || !editorRef.current) return;
    applyAssistMarkers(monacoRef.current, editorRef.current, assist);
  }, [assist, selected?.path]);

  async function refreshLanguageTools(forceLanguage?: ArtifactLanguageKind) {
    try {
      if (forceLanguage) {
        const response = await apiPost<ArtifactLanguageToolInstallResponse>("/api/artifacts/language-tools/install", { language: forceLanguage });
        setLanguageTools((current) => current.filter((item) => item.language !== response.language).concat(response.status));
        setNotice(response.message);
        return;
      }
      const response = await apiGet<ArtifactLanguageToolStatus[]>("/api/artifacts/language-tools");
      setLanguageTools(response);
    } catch (error: any) {
      setNotice(error.message || String(error));
    }
  }

  async function refreshItems(preferredPath = selected?.path || selectedPath, options: { autoSelect?: boolean } = {}) {
    const autoSelect = options.autoSelect ?? studioMode !== "create";
    setLoading(true);
    try {
      const response = await apiGet<ManagedArtifactItem[]>("/api/artifacts/manage");
      setItems(response);
      const nextSelected = autoSelect ? response.find((item) => item.path === preferredPath) || response[0] || null : null;
      setSelected(nextSelected);
      if (nextSelected?.previewable) await loadContent(nextSelected, false);
      else {
        resetContent();
        if (nextSelected?.kind === "directory") await loadTree(nextSelected.path);
        else setTree(null);
      }
    } catch (error: any) {
      setNotice(error.message || String(error));
    } finally {
      setLoading(false);
    }
  }

  async function selectItem(item: ManagedArtifactItem) {
    if (!canLeaveDirty()) return;
    setStudioMode("browse");
    setSelected(item);
    setNotice("");
    setEditing(false);
    setDiffOpen(false);
    if (item.previewable) await loadContent(item, false);
    else {
      resetContent();
      if (item.kind === "directory") await loadTree(item.path);
      else setTree(null);
    }
  }

  function canLeaveDirty() {
    if (!dirty) return true;
    return window.confirm(copy(t, "artifactStudioUnsavedConfirm", "You have unsaved artifact edits. Leave without saving?"));
  }

  function startCreateFlow() {
    if (!canLeaveDirty()) return;
    setStudioMode("create");
    setSelected(null);
    setTree(null);
    resetContent();
    setSyntax(null);
    setAssist(null);
    setDiffOpen(false);
    setNotice("");
  }

  async function loadContent(item: ManagedArtifactItem, editAfterLoad: boolean) {
    setContentLoading(true);
    setSyntax(null);
    setAssist(null);
    try {
      const response = await apiGet<{ path: string; content: string }>(`/api/artifacts/content?path=${encodeURIComponent(item.path)}`);
      contentRef.current = response.content;
      setContent(response.content);
      setOriginalContent(response.content);
      setEditing(editAfterLoad);
      setStudioMode(editAfterLoad ? "edit" : "browse");
    } catch (error: any) {
      setNotice(error.message || String(error));
      resetContent();
    } finally {
      setContentLoading(false);
    }
  }

  function resetContent() {
    contentRef.current = "";
    setContent("");
    setOriginalContent("");
    setEditing(false);
    setSyntax(null);
    setAssist(null);
  }

  async function loadTree(pathValue: string) {
    setTreeLoading(true);
    try {
      const response = await apiGet<ArtifactTreeResponse>(`/api/artifacts/tree?path=${encodeURIComponent(pathValue)}`);
      setTree(response);
    } catch (error: any) {
      setNotice(error.message || String(error));
      setTree(null);
    } finally {
      setTreeLoading(false);
    }
  }

  async function validateContent() {
    if (!selected) return null;
    const currentContent = getCurrentEditorContent();
    syncContentState(currentContent);
    try {
      const result = await apiPost<SyntaxValidationResult>("/api/validate/content", { path: selected.path, content: currentContent });
      setSyntax(result);
      await runAssistCheck();
      return result;
    } catch (error: any) {
      const result = { ok: false, kind: "unsupported", checkedAt: new Date().toISOString(), issues: [{ message: error.message || String(error) }], message: error.message || String(error) } satisfies SyntaxValidationResult;
      setSyntax(result);
      return result;
    }
  }

  async function runAssistCheck() {
    if (!selected) return null;
    const currentContent = getCurrentEditorContent();
    try {
      const result = await apiPost<ArtifactAssistCheckResult>("/api/artifacts/assist/check", { path: selected.path, content: currentContent });
      setAssist(result);
      return result;
    } catch (error: any) {
      setAssist({
        ok: false,
        checkedAt: new Date().toISOString(),
        language: editorLanguage,
        issues: [{ severity: "error", code: "assist.failed", message: error.message || String(error) }],
        snippets: [],
      });
      return null;
    }
  }

  async function saveContent() {
    const currentContent = getCurrentEditorContent();
    if (!selected || currentContent === originalContent) return;
    syncContentState(currentContent);
    setSaving(true);
    try {
      const result = await validateContent();
      if (result?.ok === false) return;
      await apiPost("/api/artifacts/content", { path: selected.path, content: currentContent }, "PUT");
      setOriginalContent(currentContent);
      setEditing(false);
      setStudioMode("browse");
      setDiffOpen(false);
      setNotice(`${t.artifactManagerSaveNotice}: ${selected.path}`);
      await refreshItems(selected.path);
      await onArtifactsChanged();
    } catch (error: any) {
      setNotice(error.message || String(error));
    } finally {
      setSaving(false);
    }
  }

  async function createTemplate() {
    setSaving(true);
    try {
      const response = await apiPost<{ path: string; content: string }>("/api/artifacts/template", { kind: templateKind, path: templatePath });
      setNotice(`${t.artifactManagerCreateNotice}: ${response.path}`);
      onUse(response.path);
      setStudioMode("browse");
      await refreshItems(response.path, { autoSelect: true });
      await onArtifactsChanged();
    } catch (error: any) {
      setNotice(error.message || String(error));
    } finally {
      setSaving(false);
    }
  }

  async function createProjectTemplate() {
    setSaving(true);
    try {
      const response = await apiPost<{ path: string; files: string[] }>("/api/artifacts/project-template", {
        kind: projectKind,
        path: projectPath,
        shell: projectShell,
        name: projectName,
      });
      setNotice(`${copy(t, "artifactStudioProjectCreated", "Artifact project created")}: ${response.path}`);
      onUse(response.path);
      setStudioMode("browse");
      await refreshItems(response.path, { autoSelect: true });
      await onArtifactsChanged();
    } catch (error: any) {
      setNotice(error.message || String(error));
    } finally {
      setSaving(false);
    }
  }

  function insertSnippet(value: string) {
    setEditing(true);
    setStudioMode("edit");
    const applySnippet = () => {
      const editor = editorRef.current;
      if (!editor) {
        setContent((current) => {
          const prefix = current && !current.endsWith("\n") ? `${current}\n` : current;
          return `${prefix}${value}`;
        });
        return;
      }
      editor.updateOptions?.({ readOnly: false });
      const selection = editor.getSelection?.();
      const model = editor.getModel?.();
      if (!selection || !model) return;
      const prefix = model.getValue() && !model.getValue().endsWith("\n") && selection.isEmpty() && selection.getStartPosition().lineNumber === model.getLineCount()
        ? "\n"
        : "";
      editor.executeEdits("oslab-artifact-snippet", [{ range: selection, text: `${prefix}${value}`, forceMoveMarkers: true }]);
      editor.focus();
      syncContentState(editor.getValue());
    };
    window.setTimeout(applySnippet, 0);
  }

  function getCurrentEditorContent() {
    return editorRef.current?.getValue?.() ?? contentRef.current;
  }

  function syncContentState(nextContent: string) {
    contentRef.current = nextContent;
    setContent(nextContent);
  }

  function cancelEdit() {
    contentRef.current = originalContent;
    editorRef.current?.setValue?.(originalContent);
    setContent(originalContent);
    setEditing(false);
    setStudioMode("browse");
    setSyntax(null);
    setAssist(null);
  }

  function useForRun(pathValue: string) {
    onUse(pathValue);
    setNotice(`${t.artifactManagerUseRun}: ${pathValue}`);
  }

  function useForScenario(pathValue: string) {
    (onUseForScenario || onUse)(pathValue);
    setNotice(`${t.artifactManagerUseScenario}: ${pathValue}`);
  }

  async function openArtifactAction(action: ArtifactManageAction) {
    if (!selected) return;
    setActionWorking(true);
    try {
      const endpoint = action === "archive" ? "/api/artifacts/archive" : "/api/artifacts/delete";
      const preview = await apiPost<ArtifactManageActionResponse>(endpoint, { path: selected.path, dryRun: true });
      setArtifactAction(action);
      setActionPreview(preview);
    } catch (error: any) {
      setNotice(error.message || String(error));
    } finally {
      setActionWorking(false);
    }
  }

  async function confirmArtifactAction() {
    if (!selected || !artifactAction || !actionPreview) return;
    setActionWorking(true);
    try {
      const endpoint = artifactAction === "archive" ? "/api/artifacts/archive" : "/api/artifacts/delete";
      const result = await apiPost<ArtifactManageActionResponse>(endpoint, {
        path: selected.path,
        dryRun: false,
        confirmToken: actionPreview.confirmToken,
      });
      setNotice(`${actionLabel(artifactAction, t)}: ${result.completedPath || selected.path}`);
      setArtifactAction(null);
      setActionPreview(null);
      setTree(null);
      if (selected.path === selectedPath) onUse("");
      await refreshItems(result.completedPath || undefined);
      await onArtifactsChanged();
    } catch (error: any) {
      setNotice(error.message || String(error));
    } finally {
      setActionWorking(false);
    }
  }

  const parentRunPath = selected ? parentArtifactPath(selected.path) : null;

  return (
    <div className={`artifactStudio ${embedded ? "embedded" : "page"} mode-${studioMode}`}>
      {!embedded && (
        <section className="panel artifactStudioHero">
          <div>
            <p className="eyebrow">{t.runStepArtifact}</p>
            <h2>{copy(t, "artifactStudioTitle", "Artifact Studio")}</h2>
            <p className="muted">{copy(t, "artifactStudioSubtitle", "Create, inspect, and connect test files, scripts, folders, and inventory starters.")}</p>
          </div>
          <button type="button" className="secondary" onClick={() => refreshItems()} disabled={loading}>{t.artifactManagerRefresh}</button>
        </section>
      )}

      <div className="artifactManagerBody artifactStudioBody">
        <aside className="artifactManagerSidebar artifactStudioSidebar">
          <div className="artifactManagerToolbar">
            <div className="artifactManagerToolbarTitle">
              <strong>{copy(t, "artifactStudioArtifactsLabel", "Artifacts")}</strong>
              <button type="button" data-testid="artifact-studio-new" onClick={startCreateFlow}>{copy(t, "artifactStudioNewArtifact", "New artifact")}</button>
            </div>
            <label>
              <span>{t.artifactManagerSearch}</span>
              <input value={query} onChange={(event) => setQuery(event.target.value)} />
            </label>
            <div className="artifactManagerFilters">
              <select value={sourceFilter} onChange={(event) => setSourceFilter(event.target.value as ArtifactSourceFilter)} aria-label={t.artifactManagerSource}>
                <option value="all">{t.artifactManagerSourceAll}</option>
                <option value="repo">{t.artifactManagerSourceRepo}</option>
                <option value="uploaded">{t.artifactManagerSourceUploaded}</option>
                <option value="archive">{copy(t, "artifactManagerSourceArchive", "Archived")}</option>
              </select>
              <select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value as ArtifactTypeFilter)} aria-label={t.artifactManagerType}>
                <option value="all">{t.artifactManagerTypeAll}</option>
                <option value="text">{t.artifactManagerTypeText}</option>
                <option value="binary">{t.artifactManagerTypeBinary}</option>
                <option value="directory">{t.artifactManagerTypeDirectory}</option>
              </select>
            </div>
          </div>
          <div className="artifactManagerList" aria-busy={loading}>
            {filteredItems.map((item) => (
              <button key={item.path} type="button" className={studioMode !== "create" && selected?.path === item.path ? "selected" : ""} onClick={() => selectItem(item)} title={item.path}>
                <span>
                  <strong>{item.name}</strong>
                  <small>{item.path}</small>
                </span>
                <em>{sourceLabel(item, t)} · {typeLabel(item, t)}</em>
              </button>
            ))}
            {!filteredItems.length && <p className="muted helperText">{loading ? t.previewLoading : t.artifactManagerNoResults}</p>}
          </div>
        </aside>

        <main className="artifactManagerMain artifactStudioMain">
          {studioMode === "create" ? (
            <ArtifactCreateWorkspace
              t={t}
              createMode={createMode}
              setCreateMode={setCreateMode}
              templateKind={templateKind}
              setTemplateKind={setTemplateKind}
              templatePath={templatePath}
              setTemplatePath={setTemplatePath}
              projectKind={projectKind}
              setProjectKind={setProjectKind}
              projectShell={projectShell}
              setProjectShell={setProjectShell}
              projectName={projectName}
              setProjectName={setProjectName}
              projectPath={projectPath}
              setProjectPath={setProjectPath}
              toolStatus={currentToolStatus}
              saving={saving}
              onCreateTemplate={createTemplate}
              onCreateProject={createProjectTemplate}
              onCancel={() => {
                setStudioMode("browse");
                void refreshItems(selectedPath || undefined, { autoSelect: true });
              }}
              onInstallTool={() => refreshLanguageTools(createLanguage)}
            />
          ) : selected ? (
            <section className="artifactManagerDetail artifactStudioDetail">
              <div className="artifactManagerDetailHeader">
                <div>
                  <h4>{selected.name}</h4>
                  <p className="muted">{selected.path}</p>
                </div>
                <div className="artifactManagerActions">
                  {selected.source !== "archive" && <button type="button" onClick={() => useForRun(selected.path)}>{t.artifactManagerUseRun}</button>}
                  {selected.source !== "archive" && parentRunPath && parentRunPath !== selected.path && (
                    <button type="button" className="secondary" onClick={() => useForRun(parentRunPath)}>
                      {copy(t, "artifactManagerUseParentRun", "Use parent folder in Run Launcher")}
                    </button>
                  )}
                  {selected.source !== "archive" && <button type="button" className="secondary" onClick={() => useForScenario(selected.path)}>{t.artifactManagerUseScenario}</button>}
                  {selected.editable && !editing && <button type="button" className="secondary" onClick={() => (content ? (setEditing(true), setStudioMode("edit")) : loadContent(selected, true))}>{t.edit}</button>}
                </div>
              </div>
              <dl className="artifactManagerMeta">
                <div><dt>{t.artifactManagerSource}</dt><dd>{sourceLabel(selected, t)}</dd></div>
                <div><dt>{t.artifactManagerType}</dt><dd>{typeLabel(selected, t)}</dd></div>
                <div><dt>{t.artifactManagerSize}</dt><dd>{selected.size === null ? "-" : formatBytes(selected.size)}</dd></div>
                <div><dt>{t.artifactManagerFileCount}</dt><dd>{selected.fileCount ?? "-"}</dd></div>
                <div><dt>{t.artifactManagerModifiedAt}</dt><dd>{selected.modifiedAt ? new Date(selected.modifiedAt).toLocaleString() : "-"}</dd></div>
                <div><dt>{copy(t, "artifactManagerTotalBytes", "Total bytes")}</dt><dd>{selected.totalBytes === null || selected.totalBytes === undefined ? "-" : formatBytes(selected.totalBytes)}</dd></div>
                <div><dt>{copy(t, "artifactManagerActionPolicy", "Policy")}</dt><dd>{selected.editable ? t.artifactManagerEditable : copy(t, "artifactManagerRunOnly", "Run-only")}</dd></div>
                <div className="span2"><dt>{t.artifactManagerHash}</dt><dd>{selected.hash || "-"}</dd></div>
              </dl>
              {selected.previewable ? (
                <div className="artifactStudioEditorGrid">
                  <div className="artifactManagerEditor artifactStudioEditor">
                    <div className="artifactManagerEditorHeader">
                      <strong>{editing ? t.edit : t.artifactManagerPreview}</strong>
                      <span className={`artifactManagerReadState ${selected.editable ? "editable" : ""}`}>{selected.editable ? t.artifactManagerEditable : t.artifactManagerReadOnly}</span>
                    </div>
                    {contentLoading ? <p className="muted helperText">{t.previewLoading}</p> : (
                      <div className="artifactMonacoShell">
                        <MonacoEditor
                          key={selected.path}
                          path={selected.path}
                          height="100%"
                          language={editorLanguage}
                          theme="vs-dark"
                          defaultValue={content}
                          options={{
                            readOnly: !editing,
                            minimap: { enabled: false },
                            fontSize: 13,
                            lineNumbers: "on",
                            scrollBeyondLastLine: false,
                            automaticLayout: true,
                            wordWrap: "on",
                            quickSuggestions: { other: true, comments: false, strings: false },
                            quickSuggestionsDelay: 220,
                            suggestOnTriggerCharacters: true,
                            acceptSuggestionOnCommitCharacter: false,
                            // Monaco renders suggest/hover widgets outside the editor so edge popups are not clipped.
                            fixedOverflowWidgets: true,
                          }}
                          onMount={(editor: any, monaco: any) => {
                            editorRef.current = editor;
                            monacoRef.current = monaco;
                            if (editor.getValue?.() !== contentRef.current) {
                              editor.setValue?.(contentRef.current);
                            }
                            configureMonaco(monaco, editorLanguage);
                            applyAssistMarkers(monaco, editor, assist);
                          }}
                          onChange={(value) => syncContentState(value ?? "")}
                        />
                      </div>
                    )}
                    {syntax && (
                      <p className={`artifactManagerSyntax ${syntax.ok ? "ok" : "bad"}`}>
                        {syntax.ok ? t.artifactManagerSyntaxReady : t.artifactManagerSyntaxIssue}: {syntax.message}
                      </p>
                    )}
                    {editing && (
                      <div className="artifactManagerEditorActions">
                        <span>{t.changedLines}: {diff.changed} · {t.addedLines}: {diff.added} · {t.removedLines}: {diff.removed}</span>
                        <button type="button" className="secondary" onClick={validateContent}>{t.validate}</button>
                        <button type="button" className="secondary" disabled={!dirty} onClick={() => setDiffOpen(true)}>{t.artifactManagerSavePreview}</button>
                        <button type="button" disabled={!dirty || saving || syntax?.ok === false} onClick={() => setDiffOpen(true)}>{t.save}</button>
                        <button type="button" className="secondary" onClick={cancelEdit}>{t.cancel}</button>
                      </div>
                    )}
                  </div>
                  <ScriptAssistPanel
                    t={t}
                    activeTab={assistTab}
                    onTab={setAssistTab}
                    assist={assist}
                    language={editorLanguage}
                    toolStatus={assist?.toolStatus || currentToolStatus}
                    onInsert={insertSnippet}
                    onInstallTool={() => refreshLanguageTools(editorLanguage)}
                  />
                </div>
              ) : (
                <ReadOnlyArtifactDetail
                  t={t}
                  item={selected}
                  tree={tree}
                  loading={treeLoading}
                  onUse={useForRun}
                  onUseScenario={useForScenario}
                />
              )}
              <ArtifactDangerZone
                t={t}
                item={selected}
                working={actionWorking}
                onArchive={() => openArtifactAction("archive")}
                onDelete={() => openArtifactAction("delete")}
              />
            </section>
          ) : (
            <p className="muted helperText">{t.artifactManagerSelectedHint}</p>
          )}
          {notice && <p className="notice" aria-live="polite">{notice}</p>}
        </main>
      </div>

      {diffOpen && selected && (
        <ArtifactDiffDialog
          t={t}
          path={selected.path}
          before={originalContent}
          after={content}
          saving={saving}
          onClose={() => setDiffOpen(false)}
          onSave={saveContent}
        />
      )}
      {artifactAction && actionPreview && (
        <ArtifactActionDialog
          t={t}
          action={artifactAction}
          preview={actionPreview}
          working={actionWorking}
          onClose={() => {
            if (actionWorking) return;
            setArtifactAction(null);
            setActionPreview(null);
          }}
          onConfirm={confirmArtifactAction}
        />
      )}
    </div>
  );
}

function ReadOnlyArtifactDetail({
  t,
  item,
  tree,
  loading,
  onUse,
  onUseScenario,
}: {
  t: DashboardText;
  item: ManagedArtifactItem;
  tree: ArtifactTreeResponse | null;
  loading: boolean;
  onUse: (path: string) => void;
  onUseScenario: (path: string) => void;
}) {
  return (
    <div className="artifactReadOnlyPanel">
      <div className="artifactReadOnlySummary">
        <strong>{copy(t, "artifactManagerRunOnly", "Run-only artifact")}</strong>
        <p>{t.artifactManagerBinaryReadOnly}</p>
      </div>
      {item.kind === "directory" ? (
        <div className="artifactTreePanel">
          <div className="artifactTreeHeader">
            <strong>{copy(t, "artifactManagerTreeTitle", "Folder contents")}</strong>
            <span>{loading ? t.previewLoading : tree ? `${tree.totalItems}${tree.truncated ? "+" : ""} ${t.artifactManagerFileCount}` : "-"}</span>
          </div>
          <div className="artifactTreeList" aria-busy={loading}>
            {tree?.items.map((entry) => (
              <div key={entry.path} className="artifactTreeRow" style={{ paddingLeft: `${Math.min(entry.depth, 8) * 12 + 10}px` }} title={entry.path}>
                <span className={`artifactTreeIcon ${entry.kind}`}>{entry.kind === "directory" ? "DIR" : "FILE"}</span>
                <span>
                  <strong>{entry.name}</strong>
                  <small>{entry.path}</small>
                </span>
                <em>{entry.kind === "file" && entry.size !== null ? formatBytes(entry.size) : typeLabel({ ...item, artifactType: entry.artifactType }, t)}</em>
              </div>
            ))}
            {tree?.truncated && <p className="muted helperText">{copy(t, "artifactManagerTreeTruncated", "Large folder preview is truncated. The full folder is still usable for execution.")}</p>}
            {!loading && tree && !tree.items.length && <p className="muted helperText">{copy(t, "artifactManagerTreeEmpty", "This folder is empty.")}</p>}
          </div>
        </div>
      ) : (
        <div className="artifactBinaryPanel">
          <strong>{copy(t, "artifactManagerBinaryTitle", "Binary file")}</strong>
          <p className="muted">{copy(t, "artifactManagerBinaryHint", "This file can be copied into the VM as an artifact. It is not editable in the dashboard.")}</p>
        </div>
      )}
      {item.source !== "archive" ? (
        <div className="artifactReadOnlyActions">
          <button type="button" onClick={() => onUse(item.path)}>{t.artifactManagerUseRun}</button>
          <button type="button" className="secondary" onClick={() => onUseScenario(item.path)}>{t.artifactManagerUseScenario}</button>
        </div>
      ) : (
        <p className="muted helperText">{copy(t, "artifactManagerArchiveReadOnlyHint", "Archived artifacts are kept for audit or later cleanup and are not offered as run inputs.")}</p>
      )}
    </div>
  );
}

function ArtifactDangerZone({
  t,
  item,
  working,
  onArchive,
  onDelete,
}: {
  t: DashboardText;
  item: ManagedArtifactItem;
  working: boolean;
  onArchive: () => void;
  onDelete: () => void;
}) {
  return (
    <div className="artifactDangerZone">
      <div>
        <strong>{copy(t, "artifactManagerDangerTitle", "Archive/Delete")}</strong>
        <p className="muted">
          {item.source === "repo"
            ? copy(t, "artifactManagerArchiveOnlyHint", "Repo artifacts are archived first. Direct delete is disabled for safety.")
            : copy(t, "artifactManagerDeleteHint", "Uploaded or archived artifacts can be deleted after confirmation.")}
        </p>
      </div>
      <div className="artifactDangerActions">
        {item.archivable && <button type="button" className="secondary" disabled={working} onClick={onArchive}>{copy(t, "artifactManagerArchive", "Archive")}</button>}
        {item.deletable && <button type="button" className="danger" disabled={working} onClick={onDelete}>{copy(t, "artifactManagerDelete", "Delete")}</button>}
      </div>
    </div>
  );
}

function ArtifactActionDialog({
  t,
  action,
  preview,
  working,
  onClose,
  onConfirm,
}: {
  t: DashboardText;
  action: ArtifactManageAction;
  preview: ArtifactManageActionResponse;
  working: boolean;
  onClose: () => void;
  onConfirm: () => void;
}) {
  return (
    <div className="previewOverlay nestedOverlay" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="previewDialog artifactActionDialog" role="dialog" aria-modal="true" aria-labelledby="artifact-action-title">
        <header className="previewDialogHeader">
          <div>
            <p className="eyebrow">{copy(t, "artifactManagerDangerTitle", "Archive/Delete")}</p>
            <h3 id="artifact-action-title">{actionLabel(action, t)}</h3>
            <p className="muted previewPath">{preview.path}</p>
          </div>
          <button type="button" className="previewCloseButton" onClick={onClose} aria-label={t.closePreview} title={t.closePreview}><span aria-hidden="true">×</span></button>
        </header>
        <div className="previewBody artifactActionBody">
          <p className={action === "delete" ? "notice bad" : "notice"}>{preview.message}</p>
          <dl className="artifactManagerMeta">
            <div><dt>{t.artifactManagerSource}</dt><dd>{sourceText(preview.source, t)}</dd></div>
            <div><dt>{t.artifactManagerType}</dt><dd>{preview.artifactType}</dd></div>
            <div><dt>{t.artifactManagerFileCount}</dt><dd>{preview.fileCount}</dd></div>
            <div><dt>{copy(t, "artifactManagerTotalBytes", "Total bytes")}</dt><dd>{formatBytes(preview.totalBytes)}</dd></div>
            {preview.archivePath && <div className="span2"><dt>{copy(t, "artifactManagerArchivePath", "Archive path")}</dt><dd>{preview.archivePath}</dd></div>}
          </dl>
          <div className="artifactManagerEditorActions">
            <button type="button" className={action === "delete" ? "danger" : ""} disabled={working} onClick={onConfirm}>{working ? t.previewLoading : actionLabel(action, t)}</button>
            <button type="button" className="secondary" disabled={working} onClick={onClose}>{t.cancel}</button>
          </div>
        </div>
      </section>
    </div>
  );
}

function ArtifactCreateWorkspace({
  t,
  createMode,
  setCreateMode,
  templateKind,
  setTemplateKind,
  templatePath,
  setTemplatePath,
  projectKind,
  setProjectKind,
  projectShell,
  setProjectShell,
  projectName,
  setProjectName,
  projectPath,
  setProjectPath,
  toolStatus,
  saving,
  onCreateTemplate,
  onCreateProject,
  onCancel,
  onInstallTool,
}: {
  t: DashboardText;
  createMode: ArtifactCreateMode;
  setCreateMode: (mode: ArtifactCreateMode) => void;
  templateKind: ArtifactTemplateKind;
  setTemplateKind: (kind: ArtifactTemplateKind) => void;
  templatePath: string;
  setTemplatePath: (path: string) => void;
  projectKind: ArtifactProjectTemplateKind;
  setProjectKind: (kind: ArtifactProjectTemplateKind) => void;
  projectShell: typeof PROJECT_SHELLS[number];
  setProjectShell: (shell: typeof PROJECT_SHELLS[number]) => void;
  projectName: string;
  setProjectName: (name: string) => void;
  projectPath: string;
  setProjectPath: (path: string) => void;
  toolStatus: ArtifactLanguageToolStatus | null;
  saving: boolean;
  onCreateTemplate: () => void;
  onCreateProject: () => void;
  onCancel: () => void;
  onInstallTool: () => void;
}) {
  return (
    <section className="artifactCreateWorkspace" data-testid="artifact-create-workspace">
      <header className="artifactCreateHero">
        <div>
          <p className="eyebrow">{copy(t, "artifactStudioCreateEyebrow", "New artifact")}</p>
          <h3>{copy(t, "artifactStudioCreateQuestion", "Create a new artifact?")}</h3>
          <p className="muted">{copy(t, "artifactStudioCreateGuide", "An artifact is a test file, script, binary, or folder copied into the VM. Text artifacts can be made here and then selected in Run Launcher or Scenario Builder.")}</p>
        </div>
        <button type="button" className="secondary" onClick={onCancel}>{t.cancel}</button>
      </header>

      <div className="artifactCreateModeBar">
        <button type="button" className={createMode === "file" ? "active" : ""} onClick={() => setCreateMode("file")}>
          <strong>{copy(t, "artifactStudioSingleFile", "Single file")}</strong>
          <span>{copy(t, "artifactStudioSingleFileHint", "One script or text file")}</span>
        </button>
        <button type="button" className={createMode === "project" ? "active" : ""} onClick={() => { setCreateMode("project"); setProjectKind("script-project"); }}>
          <strong>{copy(t, "artifactStudioProject", "Project")}</strong>
          <span>{copy(t, "artifactStudioProjectHint", "Folder with entrypoint and expected output")}</span>
        </button>
        <button type="button" className={createMode === "inventory" ? "active" : ""} onClick={() => { setCreateMode("inventory"); setProjectKind("inventory-agent"); }}>
          <strong>{copy(t, "artifactStudioInventory", "Inventory")}</strong>
          <span>{copy(t, "artifactStudioInventoryHint", "Inventory wrapper starter")}</span>
        </button>
      </div>

      <div className="artifactCreateGrid">
        <div className="artifactCreateForm">
          <strong className="sectionTitleLine">
            <span>{copy(t, "artifactStudioCreateTitle", "Create artifact")}</span>
            <InfoTooltip text={copy(t, "artifactStudioCreateHint", "Create safe text files or folder projects under validation/artifacts. Uploaded binary artifacts stay read-only.")} label={t.infoTooltipLabel} />
          </strong>
          {createMode === "file" ? (
            <div className="artifactManagerCreateGrid createWorkspaceFormGrid">
              <label>
                <span>{t.artifactManagerTemplateKind}</span>
                <select value={templateKind} onChange={(event) => setTemplateKind(event.target.value as ArtifactTemplateKind)}>
                  {TEMPLATE_KINDS.map((kind) => <option key={kind} value={kind}>{kind}{TEMPLATE_EXTENSIONS[kind]}</option>)}
                </select>
              </label>
              <label>
                <span>{t.artifactManagerCreatePath}</span>
                <input value={templatePath} onChange={(event) => setTemplatePath(event.target.value)} />
              </label>
              <button type="button" data-testid="artifact-create-submit" onClick={onCreateTemplate} disabled={saving || !templatePath.trim()}>{t.artifactManagerCreate}</button>
            </div>
          ) : (
            <div className="artifactManagerCreateGrid projectCreateGrid createWorkspaceFormGrid">
              <label>
                <span>{copy(t, "artifactStudioProjectKind", "Project template")}</span>
                <select value={projectKind} onChange={(event) => setProjectKind(event.target.value as ArtifactProjectTemplateKind)} disabled={createMode === "inventory"}>
                  <option value="script-project">{copy(t, "artifactStudioScriptProject", "Script project")}</option>
                  <option value="inventory-agent">{copy(t, "artifactStudioInventoryAgent", "Inventory agent")}</option>
                  <option value="install-profile">{copy(t, "artifactStudioInstallProfile", "Install profile")}</option>
                </select>
              </label>
              <label>
                <span>{copy(t, "artifactStudioShell", "Shell")}</span>
                <select value={projectShell} onChange={(event) => setProjectShell(event.target.value as typeof PROJECT_SHELLS[number])}>
                  {PROJECT_SHELLS.map((shell) => <option key={shell} value={shell}>{shell}</option>)}
                </select>
              </label>
              <label>
                <span>{copy(t, "artifactStudioProjectName", "Name")}</span>
                <input value={projectName} onChange={(event) => setProjectName(event.target.value)} />
              </label>
              <label>
                <span>{t.artifactManagerCreatePath}</span>
                <input value={projectPath} onChange={(event) => setProjectPath(event.target.value)} />
              </label>
              <button type="button" data-testid="artifact-create-project-submit" onClick={onCreateProject} disabled={saving || !projectPath.trim()}>{copy(t, "artifactStudioCreateProject", "Create project")}</button>
            </div>
          )}
        </div>

        <ArtifactFirstRunGuide t={t} language={createMode === "file" ? monacoLanguageForTemplate(templateKind) : monacoLanguageForProjectShell(projectShell)} toolStatus={toolStatus} onInstallTool={onInstallTool} />
      </div>
    </section>
  );
}

function ArtifactFirstRunGuide({
  t,
  language,
  toolStatus,
  onInstallTool,
}: {
  t: DashboardText;
  language: ArtifactLanguageKind;
  toolStatus: ArtifactLanguageToolStatus | null;
  onInstallTool: () => void;
}) {
  return (
    <aside className="artifactFirstRunGuide">
      <div>
        <h4>{copy(t, "artifactStudioFirstRunTitle", "First-time guide")}</h4>
        <p className="muted">{copy(t, "artifactStudioFirstRunBody", "Choose a template, keep paths under validation/artifacts, then write a stable output file that Results can inspect.")}</p>
      </div>
      <ol>
        <li>{copy(t, "artifactStudioFirstRunStep1", "Create a text file or project folder.")}</li>
        <li>{copy(t, "artifactStudioFirstRunStep2", "Use OSLAB placeholders instead of local machine paths.")}</li>
        <li>{copy(t, "artifactStudioFirstRunStep3", "Select the artifact in Run Launcher and run a smoke scenario.")}</li>
      </ol>
      <LanguageToolCard t={t} language={language} toolStatus={toolStatus} onInstallTool={onInstallTool} />
    </aside>
  );
}

function LanguageToolCard({
  t,
  language,
  toolStatus,
  onInstallTool,
}: {
  t: DashboardText;
  language: ArtifactLanguageKind;
  toolStatus: ArtifactLanguageToolStatus | null;
  onInstallTool: () => void;
}) {
  return (
    <div className={`languageToolCard ${toolStatus?.state || "missing"}`}>
      <div>
        <strong>{copy(t, "artifactLanguageToolTitle", "Language tools")}</strong>
        <span>{toolStatus?.label || language} · {toolStatus ? languageToolStateLabel(toolStatus.state, t) : copy(t, "artifactLanguageToolChecking", "checking")}</span>
      </div>
      <p className="muted">{toolStatus?.nextAction || copy(t, "artifactLanguageToolFallback", "Built-in static checks are available even when external tools are missing.")}</p>
      {toolStatus?.tools?.length ? (
        <div className="languageToolList">
          {toolStatus.tools.map((tool) => (
            <span key={tool.id} className={tool.state}>
              <strong>{tool.label}</strong>
              <small>{tool.version || tool.hint || tool.state}</small>
            </span>
          ))}
        </div>
      ) : null}
      {toolStatus?.installable && (
        <button type="button" className="secondary" onClick={onInstallTool}>
          {copy(t, "artifactLanguageToolInstall", "Install/enable guide")}
        </button>
      )}
    </div>
  );
}

function CompletionGuideRow({
  item,
  onInsert,
}: {
  item: ReturnType<typeof completionGuideForLanguage>[number];
  onInsert: (value: string) => void;
}) {
  return (
    <div className="completionGuideItem">
      <div>
        <strong>{item.label}</strong>
        <small>{item.trigger}</small>
      </div>
      <span>{item.detail}</span>
      <code>{item.example}</code>
      <button type="button" className="secondary" onClick={() => onInsert(item.insertText)}>삽입</button>
    </div>
  );
}

function ScriptAssistPanel({
  t,
  activeTab,
  onTab,
  assist,
  language,
  toolStatus,
  onInsert,
  onInstallTool,
}: {
  t: DashboardText;
  activeTab: AssistTab;
  onTab: (tab: AssistTab) => void;
  assist: ArtifactAssistCheckResult | null;
  language: ArtifactLanguageKind;
  toolStatus: ArtifactLanguageToolStatus | null;
  onInsert: (value: string) => void;
  onInstallTool: () => void;
}) {
  const snippets = assist?.suggestedSnippets || assist?.snippets || localSnippets(language);
  const issues = assist?.issues || [];
  const tips = assist?.firstRunTips || firstRunTipsForLanguage(language);
  const completionGuides = completionGuideForLanguage(language);
  return (
    <aside className="scriptAssistPanel">
      <div className="scriptAssistTabs">
        {([
          ["help", copy(t, "artifactAssistHelp", "Help")],
          ["complete", copy(t, "artifactAssistComplete", "Complete")],
          ["check", copy(t, "artifactAssistCheck", "Check")],
          ["contract", copy(t, "artifactAssistContract", "Output")],
          ["ai", copy(t, "artifactAssistAi", "AI help")],
        ] as Array<[AssistTab, string]>).map(([tab, label]) => (
          <button key={tab} type="button" className={activeTab === tab ? "active" : ""} onClick={() => onTab(tab)}>{label}</button>
        ))}
      </div>
      {activeTab === "help" && (
        <div className="scriptAssistContent">
          <h4>{copy(t, "artifactAssistHelpTitle", "Script building help")}</h4>
          <p className="muted">{copy(t, "artifactAssistHelpBody", "Use snippets for repeatable output contracts and OSLAB placeholders. The script is never executed by this checker.")}</p>
          <LanguageToolCard t={t} language={language} toolStatus={toolStatus} onInstallTool={onInstallTool} />
          <section className="scriptAssistSection">
            <h5>처음 만들기</h5>
            <ol className="compactGuideSteps">
              <li>Artifact는 VM에 복사해서 실행하거나 결과 파일을 검사하는 테스트 파일/폴더입니다.</li>
              <li>Run Launcher에서 artifact path를 선택하면 VM 안 지정 경로로 전달됩니다.</li>
              <li>Output contract는 Results가 성공/실패와 stdout/stderr를 안정적으로 읽기 위한 JSON 약속입니다.</li>
              <li>저장 후 Run Launcher의 테스트 파일 단계에서 선택하고 smoke 시나리오로 실행합니다.</li>
            </ol>
          </section>
          <section className="scriptAssistSection">
            <h5>이 언어의 최소 구조</h5>
            <pre>{minimumStructureForLanguage(language)}</pre>
          </section>
          <section className="scriptAssistSection">
            <h5>자동완성 안내</h5>
            <p className="muted">{autocompleteIntroForLanguage(language)}</p>
            <div className="completionGuideList compact">
              {completionGuides.slice(0, 5).map((item) => (
                <CompletionGuideRow key={`help-${item.id}`} item={item} onInsert={onInsert} />
              ))}
            </div>
          </section>
          <div className="artifactAssistTipList">
            <strong>{copy(t, "artifactStudioFirstRunTitle", "First-time guide")}</strong>
            {tips.map((tip, index) => <span key={`${tip}-${index}`}>{tip}</span>)}
          </div>
          <strong className="scriptAssistSubhead">자주 쓰는 스니펫</strong>
          <div className="snippetList">
            {snippets.map((snippet) => (
              <button key={snippet.id} type="button" className="secondary snippetButton" onClick={() => onInsert(snippet.insertText)}>
                <strong>{snippet.label}</strong>
                <span>{snippet.detail}</span>
              </button>
            ))}
          </div>
        </div>
      )}
      {activeTab === "complete" && (
        <div className="scriptAssistContent">
          <h4>{copy(t, "artifactAssistCompleteTitle", "Autocomplete")}</h4>
          <p className="muted">{copy(t, "artifactAssistCompleteBody", "The editor asks the dashboard API for language-specific suggestions. Press Ctrl+Space if the list is hidden.")}</p>
          <LanguageToolCard t={t} language={language} toolStatus={toolStatus} onInstallTool={onInstallTool} />
          <div className="completionGuideList">
            {completionGuides.map((item) => <CompletionGuideRow key={item.id} item={item} onInsert={onInsert} />)}
          </div>
        </div>
      )}
      {activeTab === "check" && (
        <div className="scriptAssistContent">
          <h4>{copy(t, "artifactAssistCheckTitle", "Static checks")}</h4>
          {!issues.length ? <p className="notice pass">{copy(t, "artifactAssistNoIssues", "No script-assist issues found.")}</p> : (
            <div className="assistIssueList">
              {issues.map((issue, index) => <AssistIssue key={`${issue.code}-${index}`} issue={issue} />)}
            </div>
          )}
        </div>
      )}
      {activeTab === "contract" && (
        <div className="scriptAssistContent">
          <h4>{copy(t, "artifactAssistContractTitle", "Output contract")}</h4>
          <p className="muted">{copy(t, "artifactAssistContractBody", "Prefer a commandResult JSON with exitCode/stdout/stderr or canonical inventory JSON written to {{OutputPath}}.")}</p>
          <pre>{`{
  "schemaVersion": 1,
  "kind": "commandResult",
  "exitCode": 0,
  "stdout": "ok\\n",
  "stderr": ""
}`}</pre>
        </div>
      )}
      {activeTab === "ai" && (
        <div className="scriptAssistContent">
          <h4>{copy(t, "artifactAssistAiTitle", "AI help extension point")}</h4>
          <p className="muted">{copy(t, "artifactAssistAiBody", "AI generation is intentionally not connected yet. This panel is reserved for a future opt-in assistant with explicit security policy.")}</p>
        </div>
      )}
    </aside>
  );
}

function AssistIssue({ issue }: { issue: ArtifactAssistIssue }) {
  return (
    <div className={`assistIssue ${issue.severity}`}>
      <strong>{issue.severity.toUpperCase()} · {issue.code}</strong>
      <span>{issue.message}</span>
      {issue.line && <small>L{issue.line}{issue.column ? `:${issue.column}` : ""}</small>}
    </div>
  );
}

function ArtifactDiffDialog({ t, path, before, after, saving, onClose, onSave }: { t: DashboardText; path: string; before: string; after: string; saving: boolean; onClose: () => void; onSave: () => void }) {
  const diff = buildDiffPreview(before, after, Number.POSITIVE_INFINITY);
  return (
    <div className="previewOverlay nestedOverlay" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="previewDialog diffDialog artifactDiffDialog" role="dialog" aria-modal="true" aria-labelledby="artifact-diff-title">
        <header className="previewDialogHeader">
          <div>
            <p className="eyebrow">{t.diffPreview}</p>
            <h3 id="artifact-diff-title">{t.diffPreviewPanel}</h3>
            <p className="muted previewPath">{path}</p>
          </div>
          <div className="previewDialogActions">
            <span className="diffDialogStats">{t.changedLines}: {diff.changed} · {t.addedLines}: {diff.added} · {t.removedLines}: {diff.removed}</span>
            <button type="button" disabled={saving} onClick={onSave}>{t.save}</button>
            <button type="button" className="previewCloseButton" onClick={onClose} aria-label={t.closePreview} title={t.closePreview}><span aria-hidden="true">×</span></button>
          </div>
        </header>
        <div className="previewBody diffDialogBody">
          <div className="diffRows">
            <div className="diffRow diffColumnHeader" aria-hidden="true"><span /><span>{t.diffBefore}</span><span>{t.diffAfter}</span></div>
            {diff.rows.map((row) => (
              <div key={row.index} className="diffRow">
                <span className="diffLine">L{row.index}</span>
                <code className="before">{row.before ?? ""}</code>
                <code className="after">{row.after ?? ""}</code>
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}

function buildDiffPreview(before: string, after: string, limit = 8) {
  const beforeLines = before.split(/\r?\n/);
  const afterLines = after.split(/\r?\n/);
  const rows: Array<{ index: number; before?: string; after?: string }> = [];
  let added = 0;
  let removed = 0;
  let changed = 0;
  const max = Math.max(beforeLines.length, afterLines.length);
  for (let index = 0; index < max; index += 1) {
    if (beforeLines[index] === afterLines[index]) continue;
    if (beforeLines[index] === undefined) added += 1;
    else if (afterLines[index] === undefined) removed += 1;
    else changed += 1;
    if (rows.length < limit) rows.push({ index: index + 1, before: beforeLines[index], after: afterLines[index] });
  }
  return { added, removed, changed, rows };
}

function defaultArtifactPath(kind: ArtifactTemplateKind) {
  const stamp = new Date().toISOString().replace(/[-:TZ.]/g, "").slice(0, 14);
  return `validation/artifacts/web-${kind}-${stamp}${TEMPLATE_EXTENSIONS[kind]}`;
}

function defaultProjectPath(kind: ArtifactProjectTemplateKind) {
  const stamp = new Date().toISOString().replace(/[-:TZ.]/g, "").slice(0, 14);
  const prefix = kind === "script-project" ? "web-script" : kind === "install-profile" ? "install-profile" : "inventory-agent";
  return `validation/artifacts/${prefix}-${stamp}`;
}

function sourceLabel(item: ManagedArtifactItem, t: DashboardText) {
  return sourceText(item.source, t);
}

function sourceText(source: ManagedArtifactItem["source"], t: DashboardText) {
  if (source === "repo") return t.artifactManagerSourceRepo;
  if (source === "archive") return copy(t, "artifactManagerSourceArchive", "Archived");
  return t.artifactManagerSourceUploaded;
}

function typeLabel(item: ManagedArtifactItem, t: DashboardText) {
  if (item.artifactType === "text") return t.artifactManagerTypeText;
  if (item.artifactType === "binary") return t.artifactManagerTypeBinary;
  if (item.artifactType === "directory") return t.artifactManagerTypeDirectory;
  return t.artifactManagerTypeOther;
}

function monacoLanguageForPath(pathValue: string): ArtifactLanguageKind {
  const lower = pathValue.toLowerCase();
  if (lower.endsWith(".ps1")) return "powershell";
  if (lower.endsWith(".sh")) return "shell";
  if (lower.endsWith(".py")) return "python";
  if (lower.endsWith(".json")) return "json";
  if (lower.endsWith(".yaml") || lower.endsWith(".yml")) return "yaml";
  if (lower.endsWith(".js") || lower.endsWith(".mjs") || lower.endsWith(".cjs")) return "javascript";
  if (lower.endsWith(".ts")) return "typescript";
  if (lower.endsWith(".html") || lower.endsWith(".htm")) return "html";
  if (lower.endsWith(".css")) return "css";
  if (lower.endsWith(".md") || lower.endsWith(".markdown")) return "markdown";
  if (lower.endsWith(".dockerfile") || lower.endsWith("/dockerfile")) return "dockerfile";
  if (lower.endsWith(".c")) return "c";
  if (lower.endsWith(".cs")) return "csharp";
  if (lower.endsWith(".cmd") || lower.endsWith(".bat")) return "bat";
  return "plaintext";
}

function monacoLanguageForTemplate(kind: ArtifactTemplateKind): ArtifactLanguageKind {
  if (kind === "powershell") return "powershell";
  if (kind === "shell") return "shell";
  if (kind === "python") return "python";
  if (kind === "json") return "json";
  if (kind === "yaml") return "yaml";
  if (kind === "javascript") return "javascript";
  if (kind === "typescript") return "typescript";
  if (kind === "html") return "html";
  if (kind === "css") return "css";
  if (kind === "markdown") return "markdown";
  if (kind === "dockerfile") return "dockerfile";
  if (kind === "c") return "c";
  if (kind === "csharp") return "csharp";
  if (kind === "cmd" || kind === "bat") return "bat";
  return "plaintext";
}

function monacoLanguageForProjectShell(shell: typeof PROJECT_SHELLS[number]): ArtifactLanguageKind {
  if (shell === "powershell") return "powershell";
  if (shell === "shell") return "shell";
  if (shell === "python") return "python";
  return "bat";
}

function configureMonaco(monaco: any, language: ArtifactLanguageKind) {
  const providerLanguage = language || "plaintext";
  const configuredKey = `__oslabArtifactMonacoConfigured_${providerLanguage}`;
  if ((window as any)[configuredKey]) return;
  (window as any)[configuredKey] = true;
  monaco.languages.registerCompletionItemProvider(providerLanguage, {
    triggerCharacters: ["{", "$", ".", "%", "-", "#", "@", ":", "/", "\\", "\"", "'", "<", ">", "[", "(", "=", "p", "P", "W", "w", "r", "R", "f", "F", "j", "J", "s", "S", "m", "M", "e", "E", "i", "I", "o", "O", "c", "C", "t", "T", "g", "G"],
    provideCompletionItems: async (model: any, position: any) => {
      const word = model.getWordUntilPosition(position);
      const range = {
        startLineNumber: position.lineNumber,
        endLineNumber: position.lineNumber,
        startColumn: word.startColumn,
        endColumn: word.endColumn,
      };
      const localFallbackItems = [
        ...completionGuideForLanguage(providerLanguage).map((item) => ({
          label: item.label,
          detail: item.detail,
          insertText: item.insertText,
          kind: "snippet",
          source: "snippet",
        })),
        ...localSnippets(providerLanguage).map((snippet) => ({
          label: snippet.label,
          detail: snippet.detail,
          insertText: snippet.insertText,
          kind: "snippet",
          source: "snippet",
        })),
      ];
      const fallbackSuggestions = rankMonacoFallbackItems(localFallbackItems, word.word).map((snippet) => ({
        label: snippet.label,
        kind: monacoCompletionKind(monaco, snippet.kind, snippet.source),
        insertText: snippet.insertText,
        insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
        detail: snippet.detail,
        documentation: snippet.detail,
        range,
      }));
      try {
        // Ask the dashboard LSP bridge first; the API returns internal fallback completions if a server is unavailable.
        const response = await apiPost<ArtifactAssistCompletionResponse>("/api/artifacts/assist/complete", {
          path: artifactPathFromModel(model),
          language: providerLanguage,
          content: model.getValue(),
          line: position.lineNumber,
          column: position.column,
        });
        const apiSuggestions = response.items.map((item) => ({
            label: item.label,
            kind: monacoCompletionKind(monaco, item.kind, item.source),
            insertText: item.insertText,
            insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
            detail: `${item.source.toUpperCase()} · ${item.detail}`,
            documentation: item.documentation || item.detail,
            range,
          }));
        return { suggestions: mergeCompletionSuggestions(apiSuggestions, fallbackSuggestions) };
      } catch {
        // Keep the editor useful when the API/LSP bridge is unavailable.
        return { suggestions: fallbackSuggestions };
      }
    },
  });
}

function mergeCompletionSuggestions(primary: any[], fallback: any[]) {
  const seen = new Set<string>();
  return [...primary, ...fallback].filter((item) => {
    const key = String(item.label).toLowerCase();
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  }).slice(0, 250);
}

function artifactPathFromModel(model: any) {
  const rawPath = String(model?.uri?.path || "validation/artifacts/draft.txt").replaceAll("\\", "/");
  const normalized = rawPath.replace(/^\/+/, "");
  return normalized.startsWith("validation/artifacts/") ? normalized : "validation/artifacts/draft.txt";
}

function monacoCompletionKind(monaco: any, kind: string | undefined, source: string | undefined) {
  if (source === "snippet" || kind === "snippet") return monaco.languages.CompletionItemKind.Snippet;
  if (kind === "function") return monaco.languages.CompletionItemKind.Function;
  if (kind === "keyword") return monaco.languages.CompletionItemKind.Keyword;
  if (kind === "variable") return monaco.languages.CompletionItemKind.Variable;
  if (kind === "module") return monaco.languages.CompletionItemKind.Module;
  if (kind === "property") return monaco.languages.CompletionItemKind.Property;
  if (kind === "file") return monaco.languages.CompletionItemKind.File;
  return monaco.languages.CompletionItemKind.Text;
}

function rankMonacoFallbackItems<T extends { label: string }>(items: T[], prefix: string) {
  const needle = prefix.trim().toLowerCase();
  return items
    .map((item) => {
      const label = item.label.toLowerCase();
      let score = 3;
      if (!needle) score = 2;
      else if (label === needle) score = 0;
      else if (label.startsWith(needle)) score = 1;
      else if (label.includes(needle)) score = 2;
      else score = 4;
      return { item, score };
    })
    .filter((entry) => entry.score < 4 || needle.length < 2)
    .sort((a, b) => a.score - b.score || a.item.label.localeCompare(b.item.label))
    .map((entry) => entry.item)
    .slice(0, 40);
}

function completionGuideForLanguage(language: ArtifactLanguageKind) {
  if (language === "python") {
    return [
      { id: "python-print", label: "print", trigger: "pri, p, Ctrl+Space", detail: "Python 표준 출력 함수입니다.", example: "print(\"artifact executed\")", insertText: "print(${1:\"artifact executed\"})" },
      { id: "python-range", label: "range", trigger: "for i in ra, r", detail: "반복문에서 정수 구간을 만듭니다.", example: "for i in range(3):", insertText: "range(${1:3})" },
      { id: "python-for-range", label: "for i in range", trigger: "for, range", detail: "Python 반복문 골격입니다.", example: "for i in range(3):\\n    print(i)", insertText: "for ${1:i} in range(${2:3}):\n    ${3:print($1)}" },
      { id: "python-json", label: "json.dumps", trigger: "json. 또는 dumps", detail: "결과 dict를 JSON 문자열로 바꿉니다.", example: "json.dumps(result, indent=2)", insertText: "json.dumps(${1:result}, indent=2)" },
      { id: "python-path", label: "Path", trigger: "Path 또는 pathlib", detail: "OutputPath 같은 파일 경로를 다룹니다.", example: "Path(r\"{{OutputPath}}\")", insertText: "Path(r\"{{OutputPath}}\")" },
      { id: "python-open", label: "open", trigger: "o, open", detail: "UTF-8 파일을 열 때 사용합니다.", example: "open(path, \"r\", encoding=\"utf-8\")", insertText: "open(${1:path}, ${2:\"r\"}, encoding=\"utf-8\")" },
      { id: "python-subprocess", label: "subprocess.run", trigger: "sub, run", detail: "외부 명령을 실행하고 exit code를 확인합니다.", example: "subprocess.run([\"cmd\"], check=True)", insertText: "subprocess.run(${1:[\"cmd\"]}, check=True, capture_output=True, text=True)" },
      { id: "python-main", label: "if __name__ == \"__main__\"", trigger: "main, if", detail: "직접 실행될 때만 main을 호출합니다.", example: "if __name__ == \"__main__\":\\n    main()", insertText: "if __name__ == \"__main__\":\n    ${1:main()}" },
    ];
  }
  if (language === "powershell") {
    return [
      { id: "ps-write-output", label: "Write-Output", trigger: "W, Write, Ctrl+Space", detail: "PowerShell 표준 출력입니다.", example: "Write-Output \"artifact executed\"", insertText: "Write-Output ${1:\"artifact executed\"}" },
      { id: "ps-get-content", label: "Get-Content", trigger: "G, Get", detail: "파일 내용을 읽습니다.", example: "Get-Content -LiteralPath $OutputPath -Raw", insertText: "Get-Content -LiteralPath ${1:$OutputPath} -Raw" },
      { id: "ps-set-content", label: "Set-Content", trigger: "S, Set", detail: "UTF-8 파일을 저장합니다.", example: "Set-Content -Encoding UTF8 -LiteralPath $OutputPath -Value $json", insertText: "Set-Content -Encoding UTF8 -LiteralPath ${1:$OutputPath} -Value ${2:$json}" },
      { id: "ps-test-path", label: "Test-Path", trigger: "T, Test", detail: "파일/폴더 존재 여부를 확인합니다.", example: "Test-Path -LiteralPath $path", insertText: "Test-Path -LiteralPath ${1:$path}" },
      { id: "ps-json", label: "ConvertTo-Json", trigger: "Convert 또는 Json", detail: "PowerShell 객체를 결과 JSON으로 만듭니다.", example: "$result | ConvertTo-Json -Depth 8", insertText: "${1:$result} | ConvertTo-Json -Depth 8" },
      { id: "ps-output", label: "OutputPath param", trigger: "$, param", detail: "OSLAB 출력 파일 경로 파라미터입니다.", example: "param([string]$OutputPath = \"C:\\\\Oslab\\\\command-result.json\")", insertText: "param(\n  [string]$OutputPath = \"C:\\\\Oslab\\\\command-result.json\"\n)" },
      { id: "ps-cim", label: "Get-CimInstance", trigger: "Cim, Win32", detail: "Windows OS/서비스/프로세스 정보를 조회합니다.", example: "Get-CimInstance -ClassName Win32_OperatingSystem", insertText: "Get-CimInstance -ClassName ${1:Win32_OperatingSystem}" },
    ];
  }
  if (language === "shell") {
    return [
      { id: "sh-strict", label: "set -eu", trigger: "s, set, Ctrl+Space", detail: "shell script를 안전하게 실패 처리합니다.", example: "set -eu", insertText: "set -eu" },
      { id: "sh-printf", label: "printf", trigger: "pri 또는 printf", detail: "portable shell 출력입니다.", example: "printf '%s\\n' \"artifact executed\"", insertText: "printf '%s\\n' ${1:\"artifact executed\"}" },
      { id: "sh-test", label: "test -f", trigger: "test", detail: "파일 존재 여부를 확인합니다.", example: "test -f \"{{OutputPath}}\"", insertText: "test -f ${1:\"{{OutputPath}}\"}" },
      { id: "sh-grep", label: "grep", trigger: "g, grep", detail: "텍스트에서 패턴을 찾습니다.", example: "grep -n \"pattern\" file", insertText: "grep -n ${1:\"pattern\"} ${2:file}" },
      { id: "sh-find", label: "find", trigger: "f, find", detail: "파일/폴더를 검색합니다.", example: "find . -maxdepth 2 -type f", insertText: "find ${1:.} -maxdepth ${2:2} -type ${3:f}" },
      { id: "sh-cat", label: "cat", trigger: "c, cat", detail: "파일 내용을 출력합니다.", example: "cat \"{{OutputPath}}\"", insertText: "cat ${1:\"{{OutputPath}}\"}" },
    ];
  }
  if (language === "json") {
    return [
      { id: "json-schema", label: "schemaVersion", trigger: "{, sche", detail: "OSLAB 결과 JSON schema version입니다.", example: "\"schemaVersion\": 1", insertText: "\"schemaVersion\": 1" },
      { id: "json-kind", label: "kind", trigger: "{, kind", detail: "commandResult 같은 결과 종류입니다.", example: "\"kind\": \"commandResult\"", insertText: "\"kind\": \"commandResult\"" },
      { id: "json-exit-code", label: "exitCode", trigger: "exit", detail: "명령 성공/실패 code입니다.", example: "\"exitCode\": 0", insertText: "\"exitCode\": 0" },
      { id: "json-stdout", label: "stdout", trigger: "std, out", detail: "검증 로그로 남길 표준 출력입니다.", example: "\"stdout\": \"ok\\n\"", insertText: "\"stdout\": \"ok\\n\"" },
      { id: "json-metadata", label: "metadata", trigger: "meta", detail: "파일/서비스/패키지 상태를 assertions가 읽게 할 수 있습니다.", example: "\"metadata\": { \"files\": [] }", insertText: "\"metadata\": {\n  ${1:\"files\": []}\n}" },
      { id: "json-result", label: "commandResult object", trigger: "{, command", detail: "Results가 읽는 기본 출력 계약입니다.", example: "{ \"schemaVersion\": 1, \"kind\": \"commandResult\" }", insertText: "{\n  \"schemaVersion\": 1,\n  \"kind\": \"commandResult\",\n  \"exitCode\": 0,\n  \"stdout\": \"ok\\n\",\n  \"stderr\": \"\"\n}" },
    ];
  }
  if (language === "yaml") {
    return [
      { id: "yaml-schema", label: "schemaVersion", trigger: "sche, :", detail: "OSLAB YAML schema version입니다.", example: "schemaVersion: 1", insertText: "schemaVersion: 1" },
      { id: "yaml-kind", label: "kind", trigger: "kind", detail: "artifact/result 종류를 표시합니다.", example: "kind: commandResult", insertText: "kind: ${1:commandResult}" },
      { id: "yaml-command-result", label: "commandResult YAML", trigger: "command, result", detail: "Results가 읽는 출력 계약 YAML입니다.", example: "schemaVersion: 1\\nkind: commandResult", insertText: "schemaVersion: 1\nkind: commandResult\nexitCode: 0\nstdout: \"ok\\n\"\nstderr: \"\"\n" },
      { id: "yaml-artifact-path", label: "artifact path", trigger: "artifact", detail: "artifact 경로를 YAML에 기록합니다.", example: "artifact:\\n  path: validation/artifacts/demo", insertText: "artifact:\n  path: validation/artifacts/${1:demo}" },
    ];
  }
  if (language === "javascript" || language === "typescript") {
    return [
      { id: "js-console", label: "console.log", trigger: "con, log", detail: "Node/브라우저 표준 출력입니다.", example: "console.log(\"artifact executed\")", insertText: "console.log(${1:\"artifact executed\"});" },
      { id: "js-json", label: "JSON.stringify", trigger: "JSON, str", detail: "객체를 JSON 문자열로 바꿉니다.", example: "JSON.stringify(result, null, 2)", insertText: "JSON.stringify(${1:result}, null, 2)" },
      { id: "js-command-result", label: "commandResult object", trigger: "result, command", detail: "Results가 읽는 출력 계약 객체입니다.", example: "const result = { schemaVersion: 1, kind: \"commandResult\" }", insertText: "const result = {\n  schemaVersion: 1,\n  kind: \"commandResult\",\n  exitCode: 0,\n  stdout: \"ok\\n\",\n  stderr: \"\",\n};" },
      { id: "js-fs", label: "fs.writeFileSync", trigger: "fs, write", detail: "OutputPath에 UTF-8 결과 파일을 씁니다.", example: "fs.writeFileSync(path, text, \"utf8\")", insertText: "fs.writeFileSync(${1:\"{{OutputPath}}\"}, ${2:text}, \"utf8\");" },
    ];
  }
  if (language === "html") {
    return [
      { id: "html-doc", label: "<!doctype html>", trigger: "<, html", detail: "HTML 문서 골격입니다.", example: "<!doctype html>", insertText: "<!doctype html>\n<html lang=\"en\">\n  <head>\n    <meta charset=\"utf-8\" />\n    <title>${1:OSLAB Artifact}</title>\n  </head>\n  <body>\n    ${2:artifact executed}\n  </body>\n</html>" },
      { id: "html-script", label: "<script>", trigger: "<, script", detail: "스크립트 블록입니다.", example: "<script>...</script>", insertText: "<script>\n  ${1:console.log(\"artifact executed\")}\n</script>" },
      { id: "html-link", label: "link stylesheet", trigger: "link, css", detail: "CSS 파일을 연결합니다.", example: "<link rel=\"stylesheet\" href=\"style.css\" />", insertText: "<link rel=\"stylesheet\" href=\"${1:style.css}\" />" },
    ];
  }
  if (language === "css") {
    return [
      { id: "css-root", label: ":root", trigger: ":, root", detail: "CSS custom property root입니다.", example: ":root { --accent: #2563eb; }", insertText: ":root {\n  ${1:--accent}: ${2:#2563eb};\n}" },
      { id: "css-body", label: "body", trigger: "body", detail: "기본 body 스타일입니다.", example: "body { font-family: system-ui; }", insertText: "body {\n  font-family: system-ui, sans-serif;\n  margin: 0;\n}" },
      { id: "css-media", label: "@media", trigger: "@, media", detail: "반응형 media query입니다.", example: "@media (max-width: 768px)", insertText: "@media (max-width: ${1:768px}) {\n  ${2:.target} {\n    ${3:display: block;}\n  }\n}" },
    ];
  }
  if (language === "markdown") {
    return [
      { id: "md-heading", label: "# Heading", trigger: "#", detail: "Markdown heading입니다.", example: "# Artifact Notes", insertText: "# ${1:Artifact Notes}" },
      { id: "md-check", label: "- [ ] checklist", trigger: "-, [", detail: "검증 체크리스트입니다.", example: "- [ ] Verify output", insertText: "- [ ] ${1:Verify artifact output}" },
      { id: "md-code", label: "code fence", trigger: "```", detail: "코드 블록입니다.", example: "```text", insertText: "```text\n${1:artifact executed}\n```" },
    ];
  }
  if (language === "dockerfile") {
    return [
      { id: "docker-from", label: "FROM", trigger: "F, FROM", detail: "Base image 선언입니다.", example: "FROM alpine:3.20", insertText: "FROM ${1:alpine:3.20}" },
      { id: "docker-workdir", label: "WORKDIR", trigger: "W, work", detail: "작업 디렉터리 설정입니다.", example: "WORKDIR /artifact", insertText: "WORKDIR ${1:/artifact}" },
      { id: "docker-run", label: "RUN", trigger: "R, run", detail: "build 단계 명령입니다.", example: "RUN apk add --no-cache bash", insertText: "RUN ${1:apk add --no-cache bash}" },
      { id: "docker-cmd", label: "CMD", trigger: "C, cmd", detail: "기본 실행 명령입니다.", example: "CMD [\"sh\", \"-c\", \"echo ok\"]", insertText: "CMD [\"${1:sh}\", \"${2:-c}\", \"${3:printf '%s\\\\n' artifact executed}\"]" },
    ];
  }
  if (language === "c") {
    return [
      { id: "c-printf", label: "printf", trigger: "p, pri, printf", detail: "C formatted stdout입니다.", example: "printf(\"%s\\n\", \"artifact executed\");", insertText: "printf(\"%s\\n\", ${1:\"artifact executed\"});" },
      { id: "c-puts", label: "puts", trigger: "p, puts", detail: "간단한 줄 출력입니다.", example: "puts(\"artifact executed\");", insertText: "puts(${1:\"artifact executed\"});" },
      { id: "c-fopen", label: "fopen", trigger: "f, fopen", detail: "파일을 열어 결과를 저장합니다.", example: "fopen(\"{{OutputPath}}\", \"w\")", insertText: "fopen(${1:\"{{OutputPath}}\"}, ${2:\"w\"})" },
      { id: "c-main", label: "int main(void)", trigger: "m, main", detail: "C 프로그램 진입점입니다.", example: "int main(void) { return 0; }", insertText: "int main(void) {\n  puts(\"artifact executed\");\n  return 0;\n}" },
      { id: "c-stdio", label: "#include <stdio.h>", trigger: "#, stdio", detail: "printf/puts에 필요한 헤더입니다.", example: "#include <stdio.h>", insertText: "#include <stdio.h>" },
      { id: "c-return", label: "return 0", trigger: "r, return", detail: "성공 exit code입니다.", example: "return 0;", insertText: "return 0;" },
    ];
  }
  if (language === "csharp") {
    return [
      { id: "cs-console", label: "Console.WriteLine", trigger: "C, Console, Write", detail: "C# 표준 출력입니다.", example: "Console.WriteLine(\"artifact executed\");", insertText: "Console.WriteLine(${1:\"artifact executed\"});" },
      { id: "cs-json", label: "JsonSerializer.Serialize", trigger: "Json, serialize", detail: "객체를 commandResult JSON으로 직렬화합니다.", example: "JsonSerializer.Serialize(result)", insertText: "JsonSerializer.Serialize(${1:result})" },
      { id: "cs-using-system", label: "using System", trigger: "using, System", detail: "Console과 기본 타입 namespace입니다.", example: "using System;", insertText: "using System;" },
      { id: "cs-using-json", label: "using System.Text.Json", trigger: "using, Json", detail: "System.Text.Json namespace입니다.", example: "using System.Text.Json;", insertText: "using System.Text.Json;" },
      { id: "cs-command-result", label: "commandResult object", trigger: "result, command", detail: "Results가 읽는 출력 계약 객체입니다.", example: "var result = new { schemaVersion = 1, kind = \"commandResult\" }", insertText: "var result = new {\n  schemaVersion = 1,\n  kind = \"commandResult\",\n  exitCode = 0,\n  stdout = \"ok\\n\",\n  stderr = \"\"\n};\nConsole.WriteLine(JsonSerializer.Serialize(result));" },
    ];
  }
  if (language === "bat") {
    return [
      { id: "bat-echo-off", label: "@echo off", trigger: "@, echo", detail: "Batch 로그 noise를 줄입니다.", example: "@echo off", insertText: "@echo off" },
      { id: "bat-echo", label: "echo", trigger: "e, echo", detail: "Batch 표준 출력입니다.", example: "echo artifact executed", insertText: "echo ${1:artifact executed}" },
      { id: "bat-if-exist", label: "if exist", trigger: "i, if", detail: "파일/폴더 존재 여부를 확인합니다.", example: "if exist file.txt echo ok", insertText: "if exist ${1:\"{{OutputPath}}\"} (\n  ${2:echo exists}\n)" },
      { id: "bat-errorlevel", label: "if errorlevel", trigger: "error", detail: "명령 실패 시 종료합니다.", example: "if errorlevel 1 exit /b %ERRORLEVEL%", insertText: "if errorlevel 1 exit /b %ERRORLEVEL%" },
      { id: "bat-dir", label: "%~dp0", trigger: "%", detail: "현재 batch 파일 폴더입니다.", example: "%~dp0", insertText: "%~dp0" },
      { id: "bat-for", label: "for %%F in", trigger: "f, for", detail: "파일 목록을 반복합니다.", example: "for %%F in (*.*) do echo %%F", insertText: "for %%F in (${1:*.*}) do (\n  echo %%F\n)" },
    ];
  }
  return [
    { id: "text-artifact-dir", label: "{{ArtifactDir}}", trigger: "{{", detail: "VM 안 artifact 폴더 placeholder입니다.", example: "{{ArtifactDir}}", insertText: "{{ArtifactDir}}" },
    { id: "text-output", label: "{{OutputPath}}", trigger: "{{", detail: "결과 JSON 파일 경로 placeholder입니다.", example: "{{OutputPath}}", insertText: "{{OutputPath}}" },
  ];
}

function minimumStructureForLanguage(language: ArtifactLanguageKind) {
  if (language === "python") return "import json\nfrom pathlib import Path\n\nresult = {\"schemaVersion\": 1, \"kind\": \"commandResult\", \"exitCode\": 0, \"stdout\": \"ok\\n\", \"stderr\": \"\"}\nPath(r\"{{OutputPath}}\").write_text(json.dumps(result, indent=2), encoding=\"utf-8\")\nprint(result[\"stdout\"], end=\"\")";
  if (language === "powershell") return "param(\n  [string]$OutputPath = \"C:\\Oslab\\command-result.json\"\n)\n$result = @{ schemaVersion = 1; kind = \"commandResult\"; exitCode = 0; stdout = \"ok`n\"; stderr = \"\" }\n$result | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 -LiteralPath $OutputPath";
  if (language === "shell") return "#!/usr/bin/env sh\nset -eu\nprintf '%s\\n' \"artifact executed\"\n# write JSON to {{OutputPath}} when assertions need structured output";
  if (language === "json") return "{\n  \"schemaVersion\": 1,\n  \"kind\": \"commandResult\",\n  \"exitCode\": 0,\n  \"stdout\": \"ok\\n\",\n  \"stderr\": \"\"\n}";
  if (language === "yaml") return "schemaVersion: 1\nkind: commandResult\nexitCode: 0\nstdout: \"ok\\n\"\nstderr: \"\"";
  if (language === "javascript") return "const result = { schemaVersion: 1, kind: \"commandResult\", exitCode: 0, stdout: \"ok\\n\", stderr: \"\" };\nconsole.log(JSON.stringify(result, null, 2));";
  if (language === "typescript") return "type CommandResult = { schemaVersion: number; kind: \"commandResult\"; exitCode: number; stdout: string; stderr: string };\nconst result: CommandResult = { schemaVersion: 1, kind: \"commandResult\", exitCode: 0, stdout: \"ok\\n\", stderr: \"\" };\nconsole.log(JSON.stringify(result, null, 2));";
  if (language === "html") return "<!doctype html>\n<html lang=\"en\">\n  <body>artifact executed</body>\n</html>";
  if (language === "css") return "body {\n  font-family: system-ui, sans-serif;\n}";
  if (language === "markdown") return "# Artifact Notes\n\n- Purpose:\n- Expected output:\n";
  if (language === "dockerfile") return "FROM alpine:3.20\nWORKDIR /artifact\nCMD [\"sh\", \"-c\", \"printf '%s\\\\n' artifact executed\"]";
  if (language === "c") return "#include <stdio.h>\n\nint main(void) {\n  puts(\"artifact executed\");\n  return 0;\n}";
  if (language === "csharp") return "using System;\nusing System.Text.Json;\n\nvar result = new { schemaVersion = 1, kind = \"commandResult\", exitCode = 0, stdout = \"ok\\n\", stderr = \"\" };\nConsole.WriteLine(JsonSerializer.Serialize(result));";
  if (language === "bat") return "@echo off\necho artifact executed\nrem write JSON to {{OutputPath}} when assertions need structured output";
  return "Artifact purpose: describe what this file or folder proves.\nUse {{ArtifactDir}} and {{OutputPath}} when the scenario command needs runtime paths.";
}

function autocompleteIntroForLanguage(language: ArtifactLanguageKind) {
  if (language === "python") return "`pri`를 입력하면 print, `for i in ra` 또는 `ra`에서는 range가 우선 추천됩니다. `json.`은 json.dumps, `Path`는 pathlib 경로 helper를 보여줍니다.";
  if (language === "powershell") return "`W`나 `Write`는 Write-Output, `$`와 `param`은 OutputPath 파라미터, `Convert`는 ConvertTo-Json을 우선 보여줍니다.";
  if (language === "shell") return "`pri`는 printf, `set`은 set -eu, `test`는 test -f 후보를 보여줍니다.";
  if (language === "json") return "`{` 또는 `sche`는 schemaVersion, `kind`는 commandResult kind, `command`는 전체 output contract를 보여줍니다.";
  if (language === "yaml") return "`schema`, `kind`, `artifact` 입력 시 YAML LSP와 OSLAB YAML snippets가 함께 표시됩니다.";
  if (language === "javascript" || language === "typescript") return "`console`, `JSON`, `result`, `fs` 입력 시 JS/TS LSP와 output contract snippets가 함께 표시됩니다.";
  if (language === "html") return "`<`, `html`, `script`, `link` 입력 시 HTML LSP와 문서 snippets가 표시됩니다.";
  if (language === "css") return "`:`, `body`, `@media` 입력 시 CSS LSP와 layout snippets가 표시됩니다.";
  if (language === "markdown") return "`#`, `- [ ]`, code fence snippets와 Markdown LSP 후보가 표시됩니다.";
  if (language === "dockerfile") return "`FROM`, `RUN`, `CMD`, `WORKDIR` 입력 시 Dockerfile LSP와 starter snippets가 표시됩니다.";
  if (language === "c") return "`p`나 `pri`는 printf, `main`은 int main(void), `#`은 include 후보를 보여줍니다.";
  if (language === "csharp") return "`Console`, `Json`, `using`, `result` 입력 시 C# LSP 또는 내부 C# snippets가 표시됩니다.";
  if (language === "bat") return "`e` 또는 `echo`는 echo, `%`는 %~dp0, `error`는 errorlevel 분기를 보여줍니다.";
  return "`{{` 또는 Ctrl+Space로 ArtifactDir, OutputPath 같은 OSLAB placeholder를 확인할 수 있습니다.";
}

function applyAssistMarkers(monaco: any, editor: any, assist: ArtifactAssistCheckResult | null) {
  const model = editor.getModel?.();
  if (!model) return;
  const markers = (assist?.issues || [])
    .filter((issue) => issue.line)
    .map((issue) => {
      const line = Math.max(1, issue.line || 1);
      const column = Math.max(1, issue.column || 1);
      const lineMaxColumn = model.getLineMaxColumn?.(line) || column + 1;
      const severity = issue.severity === "error"
        ? monaco.MarkerSeverity.Error
        : issue.severity === "warning"
          ? monaco.MarkerSeverity.Warning
          : monaco.MarkerSeverity.Info;
      return {
        severity,
        message: issue.message,
        source: "OSLAB Script Assist",
        startLineNumber: line,
        startColumn: column,
        endLineNumber: line,
        endColumn: Math.max(column + 1, lineMaxColumn),
      };
    });
  monaco.editor.setModelMarkers(model, "oslab-artifact-assist", markers);
}

function localSnippets(language: ArtifactLanguageKind) {
  const common = [
    {
      id: "placeholder-artifact-dir",
      label: "{{ArtifactDir}}",
      detail: "Artifact directory placeholder.",
      language,
      insertText: "{{ArtifactDir}}",
    },
    {
      id: "placeholder-output-path",
      label: "{{OutputPath}}",
      detail: "Output JSON path placeholder.",
      language,
      insertText: "{{OutputPath}}",
    },
    {
      id: "placeholder-scenario-id",
      label: "{{ScenarioId}}",
      detail: "Current scenario id placeholder.",
      language,
      insertText: "{{ScenarioId}}",
    },
    {
      id: "placeholder-run-id",
      label: "{{RunId}}",
      detail: "Current run id placeholder.",
      language,
      insertText: "{{RunId}}",
    },
  ];
  if (language === "powershell") {
    return [
      {
        id: "powershell-oslab-demo",
        label: "PowerShell OSLAB demo runner",
        detail: "Runnable demo-powershell-system script with OutputPath.",
        language,
        insertText: "param(\n  [string]$OutputPath = \"C:\\Oslab\\command-result.json\"\n)\n$lines = @(\n  \"oslab powershell system demo\",\n  \"artifactDir=$PSScriptRoot\",\n  \"generatedBy=Artifact Studio\"\n)\n$result = @{\n  schemaVersion = 1\n  kind = \"commandResult\"\n  command = \"artifact studio powershell demo\"\n  exitCode = 0\n  stdout = (($lines -join [Environment]::NewLine) + [Environment]::NewLine)\n  stderr = \"\"\n}\n$result | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 -LiteralPath $OutputPath\nGet-Content -LiteralPath $OutputPath -Raw\n",
      },
      {
        id: "powershell-result",
        label: "PowerShell result writer",
        detail: "Write commandResult JSON to a script OutputPath parameter.",
        language,
        insertText: "param(\n  [string]$OutputPath = \"C:\\Oslab\\command-result.json\"\n)\n$result = @{ schemaVersion = 1; kind = \"commandResult\"; exitCode = 0; stdout = \"ok`n\"; stderr = \"\" }\n$result | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 -LiteralPath $OutputPath\nGet-Content -LiteralPath $OutputPath -Raw\n",
      },
      ...common,
    ];
  }
  if (language === "shell") {
    return [
      {
        id: "shell-strict",
        label: "Shell strict starter",
        detail: "Safe shell starter with strict error handling.",
        language,
        insertText: "#!/usr/bin/env sh\nset -eu\nprintf '%s\\n' \"artifact executed\"\n",
      },
      ...common,
    ];
  }
  if (language === "python") {
    return [
      {
        id: "python-command-result",
        label: "Python commandResult writer",
        detail: "Write a commandResult JSON object.",
        language,
        insertText: "import json\nfrom pathlib import Path\n\noutput_path = Path(r\"{{OutputPath}}\")\nresult = {\n    \"schemaVersion\": 1,\n    \"kind\": \"commandResult\",\n    \"exitCode\": 0,\n    \"stdout\": \"artifact executed\\n\",\n    \"stderr\": \"\",\n}\noutput_path.write_text(json.dumps(result, indent=2), encoding=\"utf-8\")\nprint(output_path.read_text(encoding=\"utf-8\"))\n",
      },
      ...common,
    ];
  }
  if (language === "bat") {
    return [
      {
        id: "bat-starter",
        label: "Batch starter",
        detail: "Batch/CMD starter with quoted output path.",
        language,
        insertText: "@echo off\necho artifact executed\n",
      },
      ...common,
    ];
  }
  if (language === "c") {
    return [
      {
        id: "c-starter",
        label: "C starter",
        detail: "Minimal C program that exits successfully.",
        language,
        insertText: "#include <stdio.h>\n\nint main(void) {\n  puts(\"artifact executed\");\n  return 0;\n}\n",
      },
      ...common,
    ];
  }
  if (language === "csharp") {
    return [
      {
        id: "csharp-command-result",
        label: "C# commandResult writer",
        detail: "Serialize a commandResult object to stdout.",
        language,
        insertText: "using System;\nusing System.Text.Json;\n\nvar result = new {\n  schemaVersion = 1,\n  kind = \"commandResult\",\n  exitCode = 0,\n  stdout = \"artifact executed\\n\",\n  stderr = \"\"\n};\n\nConsole.WriteLine(JsonSerializer.Serialize(result));\n",
      },
      ...common,
    ];
  }
  if (language === "json") {
    return [
      {
        id: "json-command-result",
        label: "commandResult JSON",
        detail: "Stable result object for assertions.",
        language,
        insertText: "{\n  \"schemaVersion\": 1,\n  \"kind\": \"commandResult\",\n  \"exitCode\": 0,\n  \"stdout\": \"ok\\n\",\n  \"stderr\": \"\"\n}\n",
      },
      ...common,
    ];
  }
  if (language === "yaml") {
    return [
      {
        id: "yaml-command-result",
        label: "commandResult YAML",
        detail: "Stable result object in YAML form.",
        language,
        insertText: "schemaVersion: 1\nkind: commandResult\nexitCode: 0\nstdout: \"ok\\n\"\nstderr: \"\"\n",
      },
      ...common,
    ];
  }
  if (language === "javascript" || language === "typescript") {
    return [
      {
        id: "js-command-result",
        label: "JS/TS commandResult",
        detail: "Create a result object and print JSON.",
        language,
        insertText: "const result = {\n  schemaVersion: 1,\n  kind: \"commandResult\",\n  exitCode: 0,\n  stdout: \"artifact executed\\n\",\n  stderr: \"\",\n};\nconsole.log(JSON.stringify(result, null, 2));\n",
      },
      ...common,
    ];
  }
  if (language === "html") {
    return [
      {
        id: "html-document",
        label: "HTML document",
        detail: "Minimal HTML document.",
        language,
        insertText: "<!doctype html>\n<html lang=\"en\">\n  <head>\n    <meta charset=\"utf-8\" />\n    <title>OSLAB Artifact</title>\n  </head>\n  <body>\n    artifact executed\n  </body>\n</html>\n",
      },
      ...common,
    ];
  }
  if (language === "css") {
    return [
      {
        id: "css-base",
        label: "CSS base",
        detail: "Small CSS starter.",
        language,
        insertText: ":root {\n  color-scheme: light dark;\n}\n\nbody {\n  font-family: system-ui, sans-serif;\n}\n",
      },
      ...common,
    ];
  }
  if (language === "markdown") {
    return [
      {
        id: "markdown-notes",
        label: "Artifact notes",
        detail: "Markdown notes scaffold.",
        language,
        insertText: "# Artifact Notes\n\n- Purpose:\n- Expected output:\n- Run Launcher path:\n",
      },
      ...common,
    ];
  }
  if (language === "dockerfile") {
    return [
      {
        id: "dockerfile-starter",
        label: "Dockerfile starter",
        detail: "Minimal Dockerfile starter.",
        language,
        insertText: "FROM alpine:3.20\nWORKDIR /artifact\nCMD [\"sh\", \"-c\", \"printf '%s\\\\n' artifact executed\"]\n",
      },
      ...common,
    ];
  }
  return common;
}

function firstRunTipsForLanguage(language: ArtifactLanguageKind) {
  const common = [
    "Artifact is copied into the VM before the command runs.",
    "Use {{ArtifactDir}} and {{OutputPath}} instead of local user paths.",
    "Write a predictable output file so Results can inspect it later.",
  ];
  if (language === "powershell") return ["Start with param([string]$OutputPath = ...).", "ConvertTo-Json + Set-Content is the safest result writer.", ...common];
  if (language === "python") return ["Use the json module for result files.", "Avoid packages that are not installed in the VM unless your artifact includes setup.", ...common];
  if (language === "shell") return ["Use set -eu to fail early.", "Quote paths because VM paths can include spaces.", ...common];
  if (language === "yaml") return ["Keep indentation stable; YAML completion is provided by the repo-managed YAML language server.", "Use YAML for metadata or scenario-adjacent artifact descriptors.", ...common];
  if (language === "javascript" || language === "typescript") return ["Use JSON.stringify for machine-readable stdout.", "If writing files, prefer explicit UTF-8 writes and avoid shell-based child_process.exec.", ...common];
  if (language === "html") return ["Use this for small report/fixture assets; generated run reports still live under runs/.", ...common];
  if (language === "css") return ["Keep CSS assets paired with an HTML or project artifact folder.", ...common];
  if (language === "markdown") return ["Use Markdown for artifact operator notes and expected behavior.", ...common];
  if (language === "dockerfile") return ["Pin base images and document network downloads.", "Prefer vendored assets or checksum-verified downloads.", ...common];
  if (language === "bat") return ["Use @echo off for readable logs.", "Quote output paths and check ERRORLEVEL when needed.", ...common];
  if (language === "c") return ["Compile separately or include a build step before executing.", ...common];
  if (language === "csharp") return ["Use System.Text.Json for commandResult JSON.", "Prepare the VM with dotnet SDK/runtime or include an explicit publish/build step.", ...common];
  return common;
}

function languageToolStateLabel(state: ArtifactLanguageToolStatus["state"], t: DashboardText) {
  if (state === "available") return copy(t, "artifactLanguageToolAvailable", "available");
  if (state === "partial") return copy(t, "artifactLanguageToolPartial", "partial");
  if (state === "missing") return copy(t, "artifactLanguageToolMissing", "missing");
  if (state === "error") return copy(t, "artifactLanguageToolError", "error");
  return copy(t, "artifactLanguageToolUnsupported", "unsupported");
}

function copy(t: DashboardText, key: string, fallback: string) {
  return (t as Record<string, string>)[key] || fallback;
}

function actionLabel(action: ArtifactManageAction, t: DashboardText) {
  return action === "archive" ? copy(t, "artifactManagerArchive", "Archive") : copy(t, "artifactManagerDelete", "Delete");
}

function parentArtifactPath(pathValue: string) {
  const normalized = pathValue.replaceAll("\\", "/");
  if (!normalized.startsWith("validation/artifacts/")) return null;
  const parts = normalized.split("/").filter(Boolean);
  if (parts.length <= 3) return null;
  return parts.slice(0, -1).join("/");
}
