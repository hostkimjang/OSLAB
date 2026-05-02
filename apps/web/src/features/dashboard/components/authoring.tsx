import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { CatalogItem, SyntaxValidationResult } from "@oslab/shared";
import type { DashboardText, EditorState, ScenarioAssertionModel, ScenarioBuilderModel, ScenarioFixtureModel, ScenarioProductStepModel, SuiteBuilderModel, SuiteBuilderRun } from "../model";
import { InfoTooltip } from "./common";

type DiffRow = { index: number; before?: string; after?: string };

function buildDiffPreview(before: string, after: string, limit = 8) {
  const beforeLines = before.split(/\r?\n/);
  const afterLines = after.split(/\r?\n/);
  const rows: DiffRow[] = [];
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

function DiffRows({ rows, t }: { rows: DiffRow[]; t: DashboardText }) {
  return (
    <div className="diffRows">
      <div className="diffRow diffColumnHeader" aria-hidden="true">
        <span />
        <span>{t.diffBefore}</span>
        <span>{t.diffAfter}</span>
      </div>
      {rows.map((row) => (
        <div key={row.index} className="diffRow">
          <span className="diffLine">L{row.index}</span>
          <code className="before">{row.before ?? ""}</code>
          <code className="after">{row.after ?? ""}</code>
        </div>
      ))}
    </div>
  );
}

export function CatalogEditor(props: {
  t: DashboardText;
  listTitle: string;
  listInfo?: string;
  editor: EditorState;
  onQuery: (query: string) => void;
  items: CatalogItem[];
  onOpen: (path: string) => void;
  onEdit: () => void;
  onCancel: () => void;
  onSave: () => void;
  onValidate?: (path: string) => void;
  onContent: (content: string) => void;
  listCollapsed: boolean;
  onToggleList: () => void;
  onCreate?: () => void;
  createLabel?: string;
  syntaxCheck?: SyntaxValidationResult | null;
  syntaxChecking?: boolean;
  builder?: ReactNode;
  builderLayout?: "stacked" | "vertical";
  builderCollapsed?: boolean;
}) {
  const [isDiffDialogOpen, setDiffDialogOpen] = useState(false);
  const closeDiffDialog = useCallback(() => setDiffDialogOpen(false), []);
  const filtered = props.items.filter((item) => item.path.toLowerCase().includes(props.editor.query.toLowerCase()));
  const dirty = props.editor.content !== props.editor.originalContent;
  const diff = dirty ? buildDiffPreview(props.editor.originalContent, props.editor.content) : null;
  const canSave = dirty && !props.syntaxChecking && props.syntaxCheck?.ok !== false;
  const showSyntaxError = Boolean(props.editor.selectedPath && props.editor.isEditing && dirty && props.syntaxCheck?.ok === false);
  const showSyntaxToast = Boolean(
    props.editor.selectedPath &&
    props.editor.isEditing &&
    dirty &&
    (props.syntaxChecking || (props.syntaxCheck && props.syntaxCheck.ok !== false)),
  );
  useEffect(() => {
    if (!dirty) setDiffDialogOpen(false);
  }, [dirty]);
  const editorTextareaRef = useRef<HTMLTextAreaElement | null>(null);
  const lineNumberGutterRef = useRef<HTMLDivElement | null>(null);
  const editorLineNumbers = useMemo(() => {
    const lineCount = Math.max(1, props.editor.content.split(/\r\n|\r|\n/).length);
    return Array.from({ length: lineCount }, (_, index) => index + 1);
  }, [props.editor.content]);
  const syncEditorScroll = useCallback(() => {
    if (lineNumberGutterRef.current && editorTextareaRef.current) {
      lineNumberGutterRef.current.scrollTop = editorTextareaRef.current.scrollTop;
    }
  }, []);
  const editorSurface = (
    <div className="editorTextSurface">
      {showSyntaxToast && <SyntaxStatusToast result={props.syntaxCheck} checking={Boolean(props.syntaxChecking)} t={props.t} />}
      {showSyntaxError && <SyntaxCheckPanel result={props.syntaxCheck} checking={false} t={props.t} />}
      {diff && (
        <div className="diffPreview diffPreviewCompact" aria-live="polite">
          <div className="diffHeader">
            <strong className="sectionTitleLine">
              <span>{props.t.diffPreview}</span>
              <InfoTooltip text={props.t.diffPreviewTooltip} label={props.t.infoTooltipLabel} />
            </strong>
            <div className="diffSummaryActions">
              <span>
                {props.t.changedLines}: {diff.changed} · {props.t.addedLines}: {diff.added} · {props.t.removedLines}: {diff.removed}
              </span>
              <button type="button" className="secondary" onClick={() => setDiffDialogOpen(true)}>
                {props.t.openDiffPreview}
              </button>
            </div>
          </div>
        </div>
      )}
      {diff && isDiffDialogOpen && (
        <DiffPreviewDialog
          before={props.editor.originalContent}
          after={props.editor.content}
          path={props.editor.selectedPath}
          t={props.t}
          canSave={canSave}
          onSave={props.onSave}
          onClose={closeDiffDialog}
        />
      )}
      <div className="codeEditorShell">
        <div className="lineNumberGutter" ref={lineNumberGutterRef} aria-hidden="true">
          {editorLineNumbers.map((line) => <span key={line}>{line}</span>)}
        </div>
        <textarea
          ref={editorTextareaRef}
          className={!props.editor.isEditing ? "readOnlyEditor" : ""}
          value={props.editor.content}
          onChange={(event) => props.onContent(event.target.value)}
          onScroll={syncEditorScroll}
          readOnly={!props.editor.isEditing}
          aria-readonly={!props.editor.isEditing}
          spellCheck={false}
          wrap="off"
        />
      </div>
    </div>
  );
  return (
    <section className={`editorGrid ${props.builderLayout === "vertical" ? "editorGridVertical" : ""} ${props.listCollapsed ? "editorGridCollapsed" : ""}`}>
      <div className={`panel listPanel ${props.listCollapsed ? "collapsed" : ""}`}>
        {props.listCollapsed ? (
          <div className="catalogListRail">
            <button
              type="button"
              className="iconButton"
              aria-label={props.t.catalogListExpand}
              aria-expanded={false}
              title={props.t.catalogListExpand}
              onClick={props.onToggleList}
            >
              <span className="catalogToggleGlyph catalogToggleExpand" aria-hidden="true" />
            </button>
            <span className="catalogListRailCount" title={props.t.catalogListCollapsed}>
              {filtered.length}
            </span>
          </div>
        ) : (
          <>
            <div className="listPanelHeader">
              <div className="listPanelTitle">
                <div>
                  <strong className="sectionTitleLine">
                    <span>{props.listTitle}</span>
                    {props.listInfo && <InfoTooltip text={props.listInfo} label={`${props.listTitle} ${props.t.infoTooltipLabel}`} />}
                  </strong>
                  <span>{filtered.length}/{props.items.length}</span>
                </div>
                <div className="listPanelActions">
                  {props.onCreate && (
                    <button type="button" className="secondary createCatalogButton" onClick={props.onCreate}>
                      {props.createLabel || props.t.newFile}
                    </button>
                  )}
                  <button
                    type="button"
                    className="iconButton"
                    aria-label={props.t.catalogListCollapse}
                    aria-expanded={true}
                    title={props.t.catalogListCollapse}
                    onClick={props.onToggleList}
                  >
                    <span className="catalogToggleGlyph catalogToggleCollapse" aria-hidden="true" />
                  </button>
                </div>
              </div>
              <input placeholder={props.t.searchFiles} value={props.editor.query} onChange={(event) => props.onQuery(event.target.value)} />
            </div>
            <div className="listPanelBody">
              {filtered.map((item) => (
                <button key={item.path} className={props.editor.selectedPath === item.path ? "selected" : ""} onClick={() => props.onOpen(item.path)}>
                  <span className="listTitle">{item.name}</span>
                  <small>{item.path}</small>
                </button>
              ))}
            </div>
          </>
        )}
      </div>
      <div className={`panel editorPanel ${props.builderLayout === "vertical" ? "verticalEditorPanel" : ""}`}>
        <div className="editorHeader">
          <div className="editorTitle">
            <code>{props.editor.selectedPath || props.t.selectFile}</code>
            {props.editor.selectedPath && (
              <span className={`editorMode ${props.editor.isEditing ? "editing" : ""}`}>
                {props.editor.isEditing ? (dirty ? props.t.unsavedChanges : props.t.edit) : props.t.readOnly}
              </span>
            )}
          </div>
          <div className="actions">
            {props.onValidate && props.editor.selectedPath && !props.editor.isEditing && <button className="secondary" onClick={() => props.onValidate!(props.editor.selectedPath)}>{props.t.validate}</button>}
            {props.editor.selectedPath && !props.editor.isEditing && <button onClick={props.onEdit}>{props.t.edit}</button>}
            {props.editor.selectedPath && props.editor.isEditing && <button className="secondary" onClick={props.onCancel}>{props.t.cancel}</button>}
            {props.editor.selectedPath && props.editor.isEditing && (
              <button disabled={!canSave} onClick={() => (diff ? setDiffDialogOpen(true) : props.onSave())}>
                {props.t.save}
              </button>
            )}
          </div>
        </div>
        {props.builder && props.builderLayout === "vertical" ? (
          <div className={`editorWorkspace editorWorkspaceVertical ${props.builderCollapsed ? "editorWorkspaceBuilderCollapsed" : ""}`}>
            <aside className={`editorBuilderSide ${props.builderCollapsed ? "builderSideCollapsed" : ""}`} aria-label={props.t.scenarioBuilder}>{props.builder}</aside>
            <div className="editorYamlSide">{editorSurface}</div>
          </div>
        ) : (
          <>
            {props.builder}
            {editorSurface}
          </>
        )}
      </div>
    </section>
  );
}

export type ScenarioCreateDraft = {
  kind: "windows-basic" | "linux-basic" | "inventory-basic";
  id: string;
  name: string;
  path: string;
};

export type FixtureCreateDraft = {
  kind: "windows-powershell" | "linux-shell";
  id: string;
  path: string;
};

export type SuiteCreateDraft = {
  kind: "smoke-suite" | "matrix-suite";
  id: string;
  name: string;
  path: string;
  scenarioPath: string;
  scenarioPaths: string[];
  tier: string;
  allowFailure: boolean;
  enabled: boolean;
  maxParallel: number;
};

const SCENARIO_CREATE_DEFAULTS: Record<ScenarioCreateDraft["kind"], ScenarioCreateDraft> = {
  "windows-basic": {
    kind: "windows-basic",
    id: "new.windows.smoke",
    name: "New Windows smoke",
    path: "scenarios/windows/new-windows-smoke.example.yaml",
  },
  "linux-basic": {
    kind: "linux-basic",
    id: "new.linux.smoke",
    name: "New Linux smoke",
    path: "scenarios/linux/new-linux-smoke.example.yaml",
  },
  "inventory-basic": {
    kind: "inventory-basic",
    id: "inventory.agent.smoke.windows",
    name: "Inventory agent smoke",
    path: "scenarios/windows/inventory-agent-smoke.example.yaml",
  },
};

export function ScenarioCreateDialog({
  t,
  open,
  existingPaths,
  onClose,
  onCreate,
}: {
  t: DashboardText;
  open: boolean;
  existingPaths: string[];
  onClose: () => void;
  onCreate: (draft: ScenarioCreateDraft) => Promise<void> | void;
}) {
  const existingPathKey = useMemo(() => existingPaths.map(normalizeScenarioCreatePath).sort().join("\n"), [existingPaths]);
  const existingPathSet = useMemo(() => new Set(existingPathKey ? existingPathKey.split("\n") : []), [existingPathKey]);
  const [draft, setDraft] = useState<ScenarioCreateDraft>(() => withUniqueScenarioPath(SCENARIO_CREATE_DEFAULTS["windows-basic"], existingPathSet));
  const [pathTouched, setPathTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (!open) return;
    setDraft(withUniqueScenarioPath(SCENARIO_CREATE_DEFAULTS["windows-basic"], existingPathSet));
    setPathTouched(false);
    closeButtonRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open]);

  if (!open) return null;

  const updateKind = (kind: ScenarioCreateDraft["kind"]) => {
    setDraft(withUniqueScenarioPath(SCENARIO_CREATE_DEFAULTS[kind], existingPathSet));
    setPathTouched(false);
  };
  const normalizedPath = normalizeScenarioCreatePath(draft.path);
  const pathIssue = getScenarioCreatePathIssue(normalizedPath, existingPathSet, t);
  const canCreate = Boolean(draft.id.trim()) && !pathIssue && !busy;
  const templateSummary = getScenarioCreateTemplateSummary(draft.kind, t);

  const submit = async () => {
    if (!canCreate) return;
    setBusy(true);
    try {
      await onCreate({ ...draft, path: normalizedPath });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="previewOverlay"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section className="previewDialog scenarioCreateDialog" role="dialog" aria-modal="true" aria-labelledby="scenario-create-title" data-testid="scenario-create-dialog">
        <header className="previewDialogHeader">
          <div>
            <p className="eyebrow">{t.newScenario}</p>
            <h3 id="scenario-create-title">{t.scenarioCreateTitle}</h3>
            <p className="muted previewPath">{t.scenarioCreateHint}</p>
          </div>
          <button ref={closeButtonRef} type="button" className="previewCloseButton" onClick={onClose} aria-label={t.closePreview} title={t.closePreview}>
            <span aria-hidden="true">×</span>
          </button>
        </header>
        <div className="previewBody scenarioCreateBody">
          <ol className="scenarioCreateSteps" aria-label={t.scenarioCreateFlow}>
            <li><b>1</b><span>{t.scenarioCreateStepTemplate}</span></li>
            <li><b>2</b><span>{t.scenarioCreateStepIdentity}</span></li>
            <li><b>3</b><span>{t.scenarioCreateStepBuilder}</span></li>
          </ol>
          <label>
            <BuilderLabel label={t.scenarioCreateTemplate} info={t.scenarioCreateTemplateTooltip} t={t} />
            <select data-testid="scenario-create-kind-select" value={draft.kind} onChange={(event) => updateKind(event.target.value as ScenarioCreateDraft["kind"])}>
              <option value="windows-basic">{t.scenarioCreateWindowsBasic}</option>
              <option value="linux-basic">{t.scenarioCreateLinuxBasic}</option>
              <option value="inventory-basic">{t.scenarioCreateInventoryBasic}</option>
            </select>
            <span className="scenarioCreateTemplateSummary">{templateSummary}</span>
          </label>
          <div className="builderGrid">
            <label>
              <BuilderLabel label="id" info={t.scenarioFieldIdTooltip} t={t} />
              <input
                data-testid="scenario-create-id-input"
                value={draft.id}
                onChange={(event) => {
                  const id = event.target.value;
                  setDraft((current) => {
                    if (pathTouched) return { ...current, id };
                    return withUniqueScenarioPath({ ...current, id, path: scenarioPathFromId(current.kind, id) }, existingPathSet, { updateId: false });
                  });
                }}
              />
            </label>
            <label>
              <BuilderLabel label="name" info={t.scenarioFieldNameTooltip} t={t} />
              <input data-testid="scenario-create-name-input" value={draft.name} onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))} />
            </label>
          </div>
          <label>
            <BuilderLabel label={t.scenarioCreatePath} info={t.scenarioCreatePathTooltip} t={t} />
            <input
              data-testid="scenario-create-path-input"
              value={draft.path}
              onChange={(event) => {
                setPathTouched(true);
                setDraft((current) => ({ ...current, path: event.target.value }));
              }}
            />
            <span className={`scenarioCreatePathStatus ${pathIssue ? "invalid" : "valid"}`}>
              {pathIssue || t.scenarioCreatePathAvailable}
            </span>
          </label>
          <div className="scenarioCreateActions">
            <button type="button" className="secondary" onClick={onClose}>
              {t.cancel}
            </button>
            <button type="button" data-testid="scenario-create-submit" disabled={!canCreate} onClick={submit}>
              {busy ? t.creatingScenario : t.createScenario}
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}

const FIXTURE_CREATE_DEFAULTS: Record<FixtureCreateDraft["kind"], FixtureCreateDraft> = {
  "windows-powershell": {
    kind: "windows-powershell",
    id: "new-fixture",
    path: "validation/fixtures/windows/new-fixture.ps1",
  },
  "linux-shell": {
    kind: "linux-shell",
    id: "new-fixture",
    path: "validation/fixtures/linux/new-fixture.sh",
  },
};

export function FixtureCreateDialog({
  t,
  open,
  existingPaths,
  onClose,
  onCreate,
}: {
  t: DashboardText;
  open: boolean;
  existingPaths: string[];
  onClose: () => void;
  onCreate: (draft: FixtureCreateDraft) => Promise<void> | void;
}) {
  const existingPathKey = useMemo(() => existingPaths.map(normalizeAuthoringCreatePath).sort().join("\n"), [existingPaths]);
  const existingPathSet = useMemo(() => new Set(existingPathKey ? existingPathKey.split("\n") : []), [existingPathKey]);
  const [draft, setDraft] = useState<FixtureCreateDraft>(() => withUniqueFixturePath(FIXTURE_CREATE_DEFAULTS["windows-powershell"], existingPathSet));
  const [pathTouched, setPathTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (!open) return;
    setDraft(withUniqueFixturePath(FIXTURE_CREATE_DEFAULTS["windows-powershell"], existingPathSet));
    setPathTouched(false);
    closeButtonRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open]);

  if (!open) return null;

  const updateKind = (kind: FixtureCreateDraft["kind"]) => {
    setDraft(withUniqueFixturePath(FIXTURE_CREATE_DEFAULTS[kind], existingPathSet));
    setPathTouched(false);
  };
  const normalizedPath = normalizeAuthoringCreatePath(draft.path);
  const pathIssue = getFixtureCreatePathIssue(normalizedPath, existingPathSet, t);
  const canCreate = Boolean(draft.id.trim()) && !pathIssue && !busy;
  const templateSummary = draft.kind === "linux-shell" ? t.fixtureCreateLinuxSummary : t.fixtureCreateWindowsSummary;

  const submit = async () => {
    if (!canCreate) return;
    setBusy(true);
    try {
      await onCreate({ ...draft, path: normalizedPath });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="previewOverlay" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose();
    }}>
      <section className="previewDialog scenarioCreateDialog" role="dialog" aria-modal="true" aria-labelledby="fixture-create-title" data-testid="fixture-create-dialog">
        <header className="previewDialogHeader">
          <div>
            <p className="eyebrow">{t.newFixture}</p>
            <h3 id="fixture-create-title">{t.fixtureCreateTitle}</h3>
            <p className="muted previewPath">{t.fixtureCreateHint}</p>
          </div>
          <button ref={closeButtonRef} type="button" className="previewCloseButton" onClick={onClose} aria-label={t.closePreview} title={t.closePreview}>
            <span aria-hidden="true">x</span>
          </button>
        </header>
        <div className="previewBody scenarioCreateBody">
          <ol className="scenarioCreateSteps" aria-label={t.fixtureCreateFlow}>
            <li><b>1</b><span>{t.fixtureCreateStepTemplate}</span></li>
            <li><b>2</b><span>{t.fixtureCreateStepIdentity}</span></li>
            <li><b>3</b><span>{t.fixtureCreateStepScript}</span></li>
          </ol>
          <label>
            <BuilderLabel label={t.scenarioCreateTemplate} info={t.fixtureCreateTemplateTooltip} t={t} />
            <select data-testid="fixture-create-kind-select" value={draft.kind} onChange={(event) => updateKind(event.target.value as FixtureCreateDraft["kind"])}>
              <option value="windows-powershell">{t.fixtureCreateWindowsPowerShell}</option>
              <option value="linux-shell">{t.fixtureCreateLinuxShell}</option>
            </select>
            <span className="scenarioCreateTemplateSummary">{templateSummary}</span>
          </label>
          <label>
            <BuilderLabel label="id" info={t.fixtureCreateIdTooltip} t={t} />
            <input
              data-testid="fixture-create-id-input"
              value={draft.id}
              onChange={(event) => {
                const id = event.target.value;
                setDraft((current) => {
                  if (pathTouched) return { ...current, id };
                  return withUniqueFixturePath({ ...current, id, path: fixturePathFromId(current.kind, id) }, existingPathSet);
                });
              }}
            />
          </label>
          <label>
            <BuilderLabel label={t.scenarioCreatePath} info={t.fixtureCreatePathTooltip} t={t} />
            <input
              data-testid="fixture-create-path-input"
              value={draft.path}
              onChange={(event) => {
                setPathTouched(true);
                setDraft((current) => ({ ...current, path: event.target.value }));
              }}
            />
            <span className={`scenarioCreatePathStatus ${pathIssue ? "invalid" : "valid"}`}>
              {pathIssue || t.scenarioCreatePathAvailable}
            </span>
          </label>
          <div className="scenarioCreateActions">
            <button type="button" className="secondary" onClick={onClose}>{t.cancel}</button>
            <button type="button" data-testid="fixture-create-submit" disabled={!canCreate} onClick={submit}>{busy ? t.creatingFixture : t.createFixture}</button>
          </div>
        </div>
      </section>
    </div>
  );
}

const SUITE_CREATE_DEFAULTS: Record<SuiteCreateDraft["kind"], SuiteCreateDraft> = {
  "smoke-suite": {
    kind: "smoke-suite",
    id: "new.smoke",
    name: "New smoke suite",
    path: "validation/suites/new-smoke.example.yaml",
    scenarioPath: "",
    scenarioPaths: [],
    tier: "ci",
    allowFailure: false,
    enabled: true,
    maxParallel: 1,
  },
  "matrix-suite": {
    kind: "matrix-suite",
    id: "new.matrix",
    name: "New matrix suite",
    path: "validation/suites/new-matrix.example.yaml",
    scenarioPath: "",
    scenarioPaths: [],
    tier: "exploratory",
    allowFailure: true,
    enabled: true,
    maxParallel: 2,
  },
};

export function SuiteCreateDialog({
  t,
  open,
  existingPaths,
  scenarios,
  onClose,
  onCreate,
}: {
  t: DashboardText;
  open: boolean;
  existingPaths: string[];
  scenarios: CatalogItem[];
  onClose: () => void;
  onCreate: (draft: SuiteCreateDraft) => Promise<void> | void;
}) {
  const existingPathKey = useMemo(() => existingPaths.map(normalizeAuthoringCreatePath).sort().join("\n"), [existingPaths]);
  const existingPathSet = useMemo(() => new Set(existingPathKey ? existingPathKey.split("\n") : []), [existingPathKey]);
  const defaultScenarioPath = scenarios[0]?.path || "";
  const [draft, setDraft] = useState<SuiteCreateDraft>(() => withUniqueSuitePath(defaultSuiteCreateDraft("smoke-suite", defaultScenarioPath), existingPathSet));
  const [scenarioQuery, setScenarioQuery] = useState("");
  const [pathTouched, setPathTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (!open) return;
    setDraft(withUniqueSuitePath(defaultSuiteCreateDraft("smoke-suite", defaultScenarioPath), existingPathSet));
    setScenarioQuery("");
    setPathTouched(false);
    closeButtonRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open]);

  if (!open) return null;

  const updateKind = (kind: SuiteCreateDraft["kind"]) => {
    const selectedPaths = draft.scenarioPaths.length ? draft.scenarioPaths : [draft.scenarioPath].filter(Boolean);
    setDraft(withUniqueSuitePath({ ...defaultSuiteCreateDraft(kind, defaultScenarioPath), scenarioPath: selectedPaths[0] || "", scenarioPaths: selectedPaths }, existingPathSet));
    setPathTouched(false);
  };
  const normalizedPath = normalizeAuthoringCreatePath(draft.path);
  const pathIssue = getSuiteCreatePathIssue(normalizedPath, existingPathSet, t);
  const selectedScenarioPaths = draft.scenarioPaths.length ? draft.scenarioPaths : [draft.scenarioPath].filter(Boolean);
  const canCreate = Boolean(draft.id.trim() && draft.name.trim() && selectedScenarioPaths.length) && !pathIssue && !busy;
  const templateSummary = draft.kind === "matrix-suite" ? t.suiteCreateMatrixSummary : t.suiteCreateSmokeSummary;
  const filteredScenarios = scenarios.filter((item) => {
    const query = scenarioQuery.trim().toLowerCase();
    return !query || item.path.toLowerCase().includes(query) || item.name.toLowerCase().includes(query);
  });

  const submit = async () => {
    if (!canCreate) return;
    setBusy(true);
    try {
      await onCreate({ ...draft, path: normalizedPath, scenarioPath: selectedScenarioPaths[0] || "", scenarioPaths: selectedScenarioPaths, maxParallel: Math.max(1, Number(draft.maxParallel) || 1) });
    } finally {
      setBusy(false);
    }
  };

  const toggleScenario = (scenarioPath: string, checked: boolean) => {
    setDraft((current) => {
      const nextPaths = checked
        ? Array.from(new Set([...current.scenarioPaths, scenarioPath]))
        : current.scenarioPaths.filter((path) => path !== scenarioPath);
      return { ...current, scenarioPath: nextPaths[0] || "", scenarioPaths: nextPaths };
    });
  };

  return (
    <div className="previewOverlay" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose();
    }}>
      <section className="previewDialog scenarioCreateDialog" role="dialog" aria-modal="true" aria-labelledby="suite-create-title" data-testid="suite-create-dialog">
        <header className="previewDialogHeader">
          <div>
            <p className="eyebrow">{t.newSuite}</p>
            <h3 id="suite-create-title">{t.suiteCreateTitle}</h3>
            <p className="muted previewPath">{t.suiteCreateHint}</p>
          </div>
          <button ref={closeButtonRef} type="button" className="previewCloseButton" onClick={onClose} aria-label={t.closePreview} title={t.closePreview}>
            <span aria-hidden="true">x</span>
          </button>
        </header>
        <div className="previewBody scenarioCreateBody">
          <ol className="scenarioCreateSteps" aria-label={t.suiteCreateFlow}>
            <li><b>1</b><span>{t.suiteCreateStepTemplate}</span></li>
            <li><b>2</b><span>{t.suiteCreateStepScenario}</span></li>
            <li><b>3</b><span>{t.suiteCreateStepBuilder}</span></li>
          </ol>
          <label>
            <BuilderLabel label={t.scenarioCreateTemplate} info={t.suiteCreateTemplateTooltip} t={t} />
            <select data-testid="suite-create-kind-select" value={draft.kind} onChange={(event) => updateKind(event.target.value as SuiteCreateDraft["kind"])}>
              <option value="smoke-suite">{t.suiteCreateSmoke}</option>
              <option value="matrix-suite">{t.suiteCreateMatrix}</option>
            </select>
            <span className="scenarioCreateTemplateSummary">{templateSummary}</span>
          </label>
          <div className="builderGrid">
            <label>
              <BuilderLabel label="id" info={t.suiteCreateIdTooltip} t={t} />
              <input
                data-testid="suite-create-id-input"
                value={draft.id}
                onChange={(event) => {
                  const id = event.target.value;
                  setDraft((current) => {
                    if (pathTouched) return { ...current, id };
                    return withUniqueSuitePath({ ...current, id, path: suitePathFromId(id) }, existingPathSet);
                  });
                }}
              />
            </label>
            <label>
              <BuilderLabel label="name" info={t.suiteCreateNameTooltip} t={t} />
              <input data-testid="suite-create-name-input" value={draft.name} onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))} />
            </label>
          </div>
          <div className="suiteCreateScenarioPicker">
            <BuilderLabel label={t.selectedScenarios} info={t.suiteCreateScenarioTooltip} t={t} />
            <input
              data-testid="suite-create-scenario-search"
              value={scenarioQuery}
              onChange={(event) => setScenarioQuery(event.target.value)}
              placeholder={t.suiteCreateScenarioSearch}
              aria-label={t.suiteCreateScenarioSearch}
            />
            <div className="suiteCreateScenarioList" role="group" aria-label={t.selectedScenarios}>
              {filteredScenarios.length ? filteredScenarios.map((item) => (
                <label key={item.path} className="suiteCreateScenarioOption" data-testid="suite-create-scenario-option" data-scenario-path={item.path}>
                  <input
                    data-testid="suite-create-scenario-checkbox"
                    type="checkbox"
                    checked={selectedScenarioPaths.includes(item.path)}
                    onChange={(event) => toggleScenario(item.path, event.target.checked)}
                  />
                  <span>
                    <strong>{item.name}</strong>
                    <small>{item.path}</small>
                  </span>
                </label>
              )) : <p className="muted helperText">{t.suiteCreateNoScenarios}</p>}
            </div>
            <span className="scenarioCreateTemplateSummary">{selectedScenarioPaths.length} {t.entries}</span>
          </div>
          <div className="builderGrid suiteCreatePolicyGrid">
            <label>
              <BuilderLabel label={t.tier} info={t.suiteCreateTierTooltip} t={t} />
              <input data-testid="suite-create-tier-input" value={draft.tier} onChange={(event) => setDraft((current) => ({ ...current, tier: event.target.value }))} />
            </label>
            <label>
              <BuilderLabel label={t.maxParallel} info={t.suiteCreateMaxParallelTooltip} t={t} />
              <input data-testid="suite-create-max-parallel-input" type="number" min="1" value={draft.maxParallel} onChange={(event) => setDraft((current) => ({ ...current, maxParallel: Math.max(1, Number(event.target.value) || 1) }))} />
            </label>
            <label className="checkLine suiteCreateCheck">
              <input data-testid="suite-create-allow-failure-checkbox" type="checkbox" checked={draft.allowFailure} onChange={(event) => setDraft((current) => ({ ...current, allowFailure: event.target.checked }))} />
              {t.allowFailure}
            </label>
            <label className="checkLine suiteCreateCheck">
              <input data-testid="suite-create-enabled-checkbox" type="checkbox" checked={draft.enabled} onChange={(event) => setDraft((current) => ({ ...current, enabled: event.target.checked }))} />
              {t.enabled}
            </label>
          </div>
          <label>
            <BuilderLabel label={t.scenarioCreatePath} info={t.suiteCreatePathTooltip} t={t} />
            <input
              data-testid="suite-create-path-input"
              value={draft.path}
              onChange={(event) => {
                setPathTouched(true);
                setDraft((current) => ({ ...current, path: event.target.value }));
              }}
            />
            <span className={`scenarioCreatePathStatus ${pathIssue ? "invalid" : "valid"}`}>
              {pathIssue || t.scenarioCreatePathAvailable}
            </span>
          </label>
          <div className="scenarioCreateActions">
            <button type="button" className="secondary" onClick={onClose}>{t.cancel}</button>
            <button type="button" data-testid="suite-create-submit" disabled={!canCreate} onClick={submit}>{busy ? t.creatingSuite : t.createSuite}</button>
          </div>
        </div>
      </section>
    </div>
  );
}

function normalizeScenarioCreatePath(path: string) {
  return normalizeAuthoringCreatePath(path);
}

function normalizeAuthoringCreatePath(path: string) {
  return String(path || "").trim().replaceAll("\\", "/").replace(/^\/+/, "");
}

function getScenarioCreatePathIssue(path: string, existingPathSet: Set<string>, t: DashboardText) {
  if (!path) return t.scenarioCreatePathRequired;
  if (!path.startsWith("scenarios/") || !/\.ya?ml$/i.test(path)) return t.scenarioCreatePathInvalid;
  if (path.split("/").includes("..")) return t.scenarioCreatePathInvalid;
  if (existingPathSet.has(normalizeScenarioCreatePath(path))) return t.scenarioCreatePathExists;
  return "";
}

function getScenarioCreateTemplateSummary(kind: ScenarioCreateDraft["kind"], t: DashboardText) {
  if (kind === "linux-basic") return t.scenarioCreateLinuxSummary;
  if (kind === "inventory-basic") return t.scenarioCreateInventorySummary;
  return t.scenarioCreateWindowsSummary;
}

function scenarioPathFromId(kind: ScenarioCreateDraft["kind"], id: string) {
  const slug = String(id || "")
    .trim()
    .replace(/[^a-z0-9]+/gi, "-")
    .replace(/^-+|-+$/g, "")
    .toLowerCase() || "new-scenario";
  if (kind === "linux-basic") return `scenarios/linux/${slug}.example.yaml`;
  if (kind === "inventory-basic") return `scenarios/windows/${slug}.example.yaml`;
  return `scenarios/windows/${slug}.example.yaml`;
}

function withUniqueScenarioPath(draft: ScenarioCreateDraft, existingPathSet: Set<string>, options: { updateId?: boolean } = {}) {
  let path = normalizeAuthoringCreatePath(draft.path);
  let id = draft.id;
  if (!existingPathSet.has(path)) return { ...draft, id, path };

  const match = path.match(/^(.*?)(\.example)?(\.ya?ml)$/i);
  const base = (match?.[1] || path.replace(/\.ya?ml$/i, "")).replace(/(?:-\d+)?$/, "");
  const exampleSuffix = match?.[2] || "";
  const extension = match?.[3] || (path.toLowerCase().endsWith(".yml") ? ".yml" : ".yaml");
  for (let index = 2; index < 1000; index += 1) {
    const candidatePath = `${base}-${index}${exampleSuffix}${extension}`;
    if (!existingPathSet.has(candidatePath)) {
      if (options.updateId !== false) id = `${draft.id}.${index}`;
      path = candidatePath;
      break;
    }
  }
  return { ...draft, id, path };
}

function getFixtureCreatePathIssue(path: string, existingPathSet: Set<string>, t: DashboardText) {
  if (!path) return t.scenarioCreatePathRequired;
  const validExtension = path.endsWith(".ps1") || path.endsWith(".sh");
  if (!path.startsWith("validation/fixtures/") || !validExtension) return t.fixtureCreatePathInvalid;
  if (path.split("/").includes("..")) return t.fixtureCreatePathInvalid;
  if (existingPathSet.has(normalizeAuthoringCreatePath(path))) return t.scenarioCreatePathExists;
  return "";
}

function fixturePathFromId(kind: FixtureCreateDraft["kind"], id: string) {
  const slug = createSlug(id, "new-fixture");
  if (kind === "linux-shell") return `validation/fixtures/linux/${slug}.sh`;
  return `validation/fixtures/windows/${slug}.ps1`;
}

function withUniqueFixturePath(draft: FixtureCreateDraft, existingPathSet: Set<string>) {
  let path = normalizeAuthoringCreatePath(draft.path);
  if (!existingPathSet.has(path)) return { ...draft, path };
  const match = path.match(/^(.*?)(\.(?:ps1|sh))$/i);
  const base = (match?.[1] || path.replace(/\.(ps1|sh)$/i, "")).replace(/(?:-\d+)?$/, "");
  const extension = match?.[2] || (draft.kind === "linux-shell" ? ".sh" : ".ps1");
  for (let index = 2; index < 1000; index += 1) {
    const candidatePath = `${base}-${index}${extension}`;
    if (!existingPathSet.has(candidatePath)) {
      path = candidatePath;
      break;
    }
  }
  return { ...draft, path };
}

function getSuiteCreatePathIssue(path: string, existingPathSet: Set<string>, t: DashboardText) {
  if (!path) return t.scenarioCreatePathRequired;
  if (!path.startsWith("validation/suites/") || !/\.ya?ml$/i.test(path)) return t.suiteCreatePathInvalid;
  if (path.split("/").includes("..")) return t.suiteCreatePathInvalid;
  if (existingPathSet.has(normalizeAuthoringCreatePath(path))) return t.scenarioCreatePathExists;
  return "";
}

function defaultSuiteCreateDraft(kind: SuiteCreateDraft["kind"], _defaultScenarioPath: string): SuiteCreateDraft {
  const base = SUITE_CREATE_DEFAULTS[kind];
  return { ...base, scenarioPath: "", scenarioPaths: [] };
}

function suitePathFromId(id: string) {
  return `validation/suites/${createSlug(id, "new-suite")}.example.yaml`;
}

function withUniqueSuitePath(draft: SuiteCreateDraft, existingPathSet: Set<string>) {
  let path = normalizeAuthoringCreatePath(draft.path);
  if (!existingPathSet.has(path)) return { ...draft, path };
  const match = path.match(/^(.*?)(\.example)?(\.ya?ml)$/i);
  const base = (match?.[1] || path.replace(/\.ya?ml$/i, "")).replace(/(?:-\d+)?$/, "");
  const exampleSuffix = match?.[2] || "";
  const extension = match?.[3] || ".yaml";
  for (let index = 2; index < 1000; index += 1) {
    const candidatePath = `${base}-${index}${exampleSuffix}${extension}`;
    if (!existingPathSet.has(candidatePath)) {
      path = candidatePath;
      break;
    }
  }
  return { ...draft, path };
}

function createSlug(value: string, fallback: string) {
  return String(value || "")
    .trim()
    .replace(/[^a-z0-9]+/gi, "-")
    .replace(/^-+|-+$/g, "")
    .toLowerCase() || fallback;
}

function DiffPreviewDialog({
  before,
  after,
  path,
  t,
  canSave,
  onSave,
  onClose,
}: {
  before: string;
  after: string;
  path: string;
  t: DashboardText;
  canSave: boolean;
  onSave: () => void;
  onClose: () => void;
}) {
  const dialogRef = useRef<HTMLElement | null>(null);
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);
  const diff = buildDiffPreview(before, after, Number.POSITIVE_INFINITY);

  useEffect(() => {
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
  }, [onClose]);

  return (
    <div
      className="previewOverlay"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section ref={dialogRef} className="previewDialog diffDialog" role="dialog" aria-modal="true" aria-labelledby="authoring-diff-preview-title">
        <header className="previewDialogHeader">
          <div>
            <p className="eyebrow">{t.diffPreview}</p>
            <h3 id="authoring-diff-preview-title">{t.diffPreviewPanel}</h3>
            <p className="muted previewPath">{path}</p>
          </div>
          <div className="previewDialogActions">
            <span className="diffDialogStats">
              {t.changedLines}: {diff.changed} · {t.addedLines}: {diff.added} · {t.removedLines}: {diff.removed}
            </span>
            <button type="button" disabled={!canSave} onClick={onSave}>
              {t.save}
            </button>
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
        <div className="previewBody diffDialogBody">
          <DiffRows rows={diff.rows} t={t} />
        </div>
      </section>
    </div>
  );
}

function SyntaxStatusToast({ result, checking, t }: { result?: SyntaxValidationResult | null; checking: boolean; t: DashboardText }) {
  if (!checking && !result) return null;
  const statusClass = checking ? "checking" : result?.skipped ? "skipped" : result?.ok ? "ok" : "checking";
  const title = checking ? t.syntaxChecking : result?.skipped ? t.syntaxSkipped : result?.ok ? t.syntaxValid : t.syntaxChecking;
  const message = checking ? t.syntaxCheckingHint : result?.message || t.syntaxCheckingHint;
  const key = `${statusClass}-${message}`;
  return (
    <div key={key} className={`syntaxToast ${statusClass}`} role="status" aria-live="polite" aria-atomic="true">
      <strong>{title}</strong>
      <span>{message}</span>
      {result && <small>{result.kind}</small>}
    </div>
  );
}

function SyntaxCheckPanel({ result, checking, t }: { result?: SyntaxValidationResult | null; checking: boolean; t: DashboardText }) {
  const statusClass = checking ? "checking" : result?.skipped ? "skipped" : result?.ok ? "ok" : result ? "bad" : "checking";
  const title = checking
    ? t.syntaxChecking
    : result?.skipped
      ? t.syntaxSkipped
      : result?.ok
        ? t.syntaxValid
        : result
          ? t.syntaxInvalid
          : t.syntaxChecking;
  return (
    <div className={`syntaxPreview ${statusClass}`} aria-live="polite">
      <div className="syntaxHeader">
        <strong className="sectionTitleLine">
          <span>{title}</span>
          <InfoTooltip text={t.syntaxTooltip} label={t.infoTooltipLabel} />
        </strong>
        {result && <span>{result.kind}</span>}
      </div>
      <p>{checking ? t.syntaxCheckingHint : result?.message || t.syntaxCheckingHint}</p>
      {!!result?.issues.length && (
        <div className="syntaxRows">
          {result.issues.slice(0, 4).map((issue, index) => (
            <div key={`${issue.message}-${index}`} className="syntaxRow">
              <span>{formatIssueLocation(issue)}</span>
              <code>{issue.message}</code>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function formatIssueLocation(issue: SyntaxValidationResult["issues"][number]) {
  if (!issue.line) return "-";
  return issue.column ? `L${issue.line}:${issue.column}` : `L${issue.line}`;
}

const OS_FAMILY_OPTIONS = ["windows", "linux"];
const GUEST_MODE_OPTIONS = ["auto", "qemuAgent", "winrm", "ssh"];
const GUEST_CHANNEL_OPTIONS = ["qemuAgent", "winrm", "ssh"];
const REPORT_FORMAT_OPTIONS = ["junit", "json", "html"];
const ARTIFACT_TYPE_OPTIONS = ["folder", "installer"];
const ARTIFACT_TRANSFER_OPTIONS = ["archive", "files"];
const FIXTURE_TYPE_OPTIONS = ["powershell", "shell"];
const SHELL_OPTIONS = ["powershell", "cmd", "sh", "bash"];

function BuilderLabel({ label, info, t }: { label: string; info?: string; t: DashboardText }) {
  return (
    <span className="builderLabelLine">
      <span>{label}</span>
      {info && <InfoTooltip text={info} label={`${label} ${t.infoTooltipLabel}`} />}
    </span>
  );
}

function toggleListValue(values: string[], value: string) {
  return values.includes(value) ? values.filter((item) => item !== value) : [...values, value];
}

function ChipToggleGroup({ values, options, disabled, onChange }: { values: string[]; options: string[]; disabled?: boolean; onChange: (next: string[]) => void }) {
  return (
    <div className="builderChipGroup">
      {options.map((option) => (
        <button key={option} type="button" className={`chipButton ${values.includes(option) ? "active" : ""}`} aria-pressed={values.includes(option)} disabled={disabled} onClick={() => onChange(toggleListValue(values, option))}>
          {option}
        </button>
      ))}
    </div>
  );
}

function compactValue(value?: string | null, fallback = "-") {
  const trimmed = value?.trim();
  return trimmed || fallback;
}

type ScenarioBuilderStage = "target" | "fixtures" | "artifact" | "run" | "assertions" | "cleanup";

export function ScenarioBuilderPanel({
  t,
  model,
  error,
  editable,
  onChange,
  onApply,
  expanded: controlledExpanded,
  onExpandedChange,
}: {
  t: DashboardText;
  model: ScenarioBuilderModel | null;
  error: string;
  editable: boolean;
  onChange: (next: ScenarioBuilderModel | null) => void;
  onApply: () => void;
  expanded?: boolean;
  onExpandedChange?: (next: boolean) => void;
}) {
  const [internalExpanded, setInternalExpanded] = useState(editable);
  const expanded = controlledExpanded ?? internalExpanded;
  const isExpandedControlled = controlledExpanded !== undefined;
  const setExpanded = useCallback((next: boolean) => {
    if (!isExpandedControlled) setInternalExpanded(next);
    onExpandedChange?.(next);
  }, [isExpandedControlled, onExpandedChange]);
  const [selectedStage, setSelectedStage] = useState<ScenarioBuilderStage>("target");
  useEffect(() => {
    if (editable) setExpanded(true);
  }, [editable, setExpanded]);
  const fixtureCount = model?.fixtures?.length ?? model?.fixtureCount ?? 0;
  const productStepCount = model?.productSteps?.length ?? 0;
  const assertionCount = model?.assertions?.length ?? model?.assertionCount ?? 0;
  const cleanupTone = model?.cleanupKeepVmOnFailure ? "warning" : model?.cleanupDestroyVm ? "good" : "warning";
  const cleanupLabel = model?.cleanupKeepVmOnFailure ? t.cleanupKeepVmOnFailure : model?.cleanupDestroyVm ? t.cleanupDestroyVm : t.cleanupVmNotDeleted;
  const stageItems: Array<{ id: ScenarioBuilderStage; index: string; label: string; detail: string; status: string }> = model ? [
    { id: "target", index: "1", label: t.scenarioBuilderTarget, detail: t.scenarioStageTargetHint, status: compactValue(model.osFamily) },
    { id: "fixtures", index: "2", label: t.scenarioBuilderFixtures, detail: t.scenarioStageFixturesHint, status: String(fixtureCount) },
    { id: "artifact", index: "3", label: t.scenarioBuilderArtifact, detail: t.scenarioStageArtifactHint, status: compactValue(model.artifactType) },
    { id: "run", index: "4", label: t.scenarioBuilderRun, detail: t.scenarioStageRunHint, status: productStepCount ? `${productStepCount}` : t.artifactCommandShort },
    { id: "assertions", index: "5", label: t.scenarioBuilderAssertions, detail: t.scenarioStageAssertionsHint, status: String(assertionCount) },
    { id: "cleanup", index: "6", label: t.scenarioBuilderCleanup, detail: t.scenarioStageCleanupHint, status: cleanupLabel },
  ] : [];
  const selectedStageItem = stageItems.find((item) => item.id === selectedStage) || stageItems[0];
  const renderSelectedStage = () => {
    if (!model || !selectedStageItem) return null;
    switch (selectedStage) {
      case "target":
        return (
          <section className="builderSection builderStagePanel">
            <div className="builderStagePanelHeader"><span className="builderStageTitle"><b>1</b>{t.scenarioBuilderTarget}</span><span>{compactValue(model.osFamily)} · VMID {model.vmIdStart ?? "-"}-{model.vmIdEnd ?? "-"}</span></div>
            <div className="builderGrid">
              <label><BuilderLabel label="id" info={t.scenarioFieldIdTooltip} t={t} /><input value={model.id} disabled={!editable} onChange={(event) => onChange({ ...model, id: event.target.value })} /></label>
              <label><BuilderLabel label="name" info={t.scenarioFieldNameTooltip} t={t} /><input value={model.name} disabled={!editable} onChange={(event) => onChange({ ...model, name: event.target.value })} /></label>
              <label><BuilderLabel label="OS family" info={t.scenarioFieldOsFamilyTooltip} t={t} /><select value={model.osFamily} disabled={!editable} onChange={(event) => onChange({ ...model, osFamily: event.target.value })}>{OS_FAMILY_OPTIONS.map((option) => <option key={option} value={option}>{option}</option>)}</select></label>
              <label><BuilderLabel label="OS version" info={t.scenarioFieldOsVersionTooltip} t={t} /><input value={model.osVersion} disabled={!editable} onChange={(event) => onChange({ ...model, osVersion: event.target.value })} /></label>
              <label className="span2"><BuilderLabel label="template" info={t.scenarioFieldTemplateTooltip} t={t} /><input value={model.template} disabled={!editable} onChange={(event) => onChange({ ...model, template: event.target.value })} /></label>
              <label><BuilderLabel label="templateVmId" info={t.scenarioFieldTemplateVmidTooltip} t={t} /><input type="number" value={model.templateVmId ?? ""} disabled={!editable} onChange={(event) => onChange({ ...model, templateVmId: event.target.value ? Number(event.target.value) : null })} /></label>
              <label><BuilderLabel label="vmId start" info={t.scenarioFieldVmidRangeTooltip} t={t} /><input type="number" value={model.vmIdStart ?? ""} disabled={!editable} onChange={(event) => onChange({ ...model, vmIdStart: event.target.value ? Number(event.target.value) : null })} /></label>
              <label><BuilderLabel label="vmId end" info={t.scenarioFieldVmidRangeTooltip} t={t} /><input type="number" value={model.vmIdEnd ?? ""} disabled={!editable} onChange={(event) => onChange({ ...model, vmIdEnd: event.target.value ? Number(event.target.value) : null })} /></label>
              <label><BuilderLabel label="guest mode" info={t.scenarioFieldGuestModeTooltip} t={t} /><select value={model.guestMode} disabled={!editable} onChange={(event) => onChange({ ...model, guestMode: event.target.value })}>{GUEST_MODE_OPTIONS.map((option) => <option key={option} value={option}>{option}</option>)}</select></label>
              <label className="span2"><BuilderLabel label={t.guestOrder} info={t.scenarioFieldGuestOrderTooltip} t={t} /><ChipToggleGroup values={model.osFamily === "linux" ? model.linuxOrder : model.windowsOrder} options={GUEST_CHANNEL_OPTIONS} disabled={!editable} onChange={(next) => onChange(model.osFamily === "linux" ? { ...model, linuxOrder: next } : { ...model, windowsOrder: next })} /></label>
            </div>
          </section>
        );
      case "fixtures":
        return <ScenarioFixturesEditor t={t} editable={editable} model={model} onChange={onChange} open stageNumber="2" />;
      case "artifact":
        return (
          <section className="builderSection builderStagePanel">
            <div className="builderStagePanelHeader"><span className="builderStageTitle"><b>3</b>{t.scenarioBuilderArtifact}</span><span>{compactValue(model.artifactType)} · {compactValue(model.artifactTransfer)}</span></div>
            <div className="builderGrid">
              <label><BuilderLabel label="artifact type" info={t.scenarioFieldArtifactTypeTooltip} t={t} /><select value={model.artifactType} disabled={!editable} onChange={(event) => onChange({ ...model, artifactType: event.target.value })}>{ARTIFACT_TYPE_OPTIONS.map((option) => <option key={option} value={option}>{option}</option>)}</select></label>
              <label><BuilderLabel label="artifact transfer" info={t.scenarioFieldArtifactTransferTooltip} t={t} /><select value={model.artifactTransfer} disabled={!editable} onChange={(event) => onChange({ ...model, artifactTransfer: event.target.value })}>{ARTIFACT_TRANSFER_OPTIONS.map((option) => <option key={option} value={option}>{option}</option>)}</select></label>
              <label><BuilderLabel label="artifact pathParam" info={t.scenarioFieldArtifactPathParamTooltip} t={t} /><input value={model.artifactPathParam} disabled={!editable} onChange={(event) => onChange({ ...model, artifactPathParam: event.target.value })} /></label>
              <label className="span2"><BuilderLabel label="artifact destination" info={t.scenarioFieldArtifactDestinationTooltip} t={t} /><input value={model.artifactDestination} disabled={!editable} onChange={(event) => onChange({ ...model, artifactDestination: event.target.value })} /></label>
              <label><BuilderLabel label="output path" info={t.scenarioFieldOutputPathTooltip} t={t} /><input value={model.outputActualPath} disabled={!editable} onChange={(event) => onChange({ ...model, outputActualPath: event.target.value })} /></label>
              <label><BuilderLabel label="output adapter" info={t.scenarioFieldOutputAdapterTooltip} t={t} /><input value={model.outputActualAdapter} disabled={!editable} onChange={(event) => onChange({ ...model, outputActualAdapter: event.target.value })} /></label>
              <label className="span2"><BuilderLabel label={t.reportFormats} info={t.scenarioFieldReportsTooltip} t={t} /><ChipToggleGroup values={model.reportFormats} options={REPORT_FORMAT_OPTIONS} disabled={!editable} onChange={(reportFormats) => onChange({ ...model, reportFormats })} /></label>
            </div>
          </section>
        );
      case "run":
        return (
          <div className="builderStepStack">
            <section className="builderSection builderStagePanel">
              <div className="builderStagePanelHeader"><span className="builderStageTitle"><b>4A</b>{t.scenarioBuilderArtifactCommand}</span><span>{compactValue(model.artifactCommand.shell)}</span></div>
              <div className="builderGrid">
                <label><BuilderLabel label="shell" info={t.scenarioFieldShellTooltip} t={t} /><select value={model.artifactCommand.shell} disabled={!editable} onChange={(event) => onChange({ ...model, artifactCommand: { ...model.artifactCommand, shell: event.target.value } })}>{SHELL_OPTIONS.map((option) => <option key={option} value={option}>{option}</option>)}</select></label>
                <label className="span2"><BuilderLabel label="template" info={t.scenarioFieldCommandTemplateTooltip} t={t} /><textarea value={model.artifactCommand.template} disabled={!editable} onChange={(event) => onChange({ ...model, artifactCommand: { ...model.artifactCommand, template: event.target.value } })} /></label>
              </div>
            </section>
            <ScenarioProductStepsEditor t={t} editable={editable} model={model} onChange={onChange} open stageNumber="4B" />
          </div>
        );
      case "assertions":
        return <ScenarioAssertionsEditor t={t} editable={editable} model={model} onChange={onChange} open stageNumber="5" />;
      case "cleanup":
        return (
          <section className="builderSection builderStagePanel">
            <div className="builderStagePanelHeader"><span className="builderStageTitle"><b>6</b>{t.scenarioBuilderCleanup}</span><span>{cleanupLabel}</span></div>
            <div className="builderToggleGrid">
              <label className="checkLine"><input type="checkbox" checked={model.cleanupDestroyVm} disabled={!editable} onChange={(event) => onChange({ ...model, cleanupDestroyVm: event.target.checked })} />{t.cleanupDestroyVm}<InfoTooltip text={t.scenarioFieldCleanupDestroyTooltip} label={t.infoTooltipLabel} /></label>
              <label className="checkLine"><input type="checkbox" checked={model.cleanupKeepVmOnFailure} disabled={!editable} onChange={(event) => onChange({ ...model, cleanupKeepVmOnFailure: event.target.checked })} />{t.cleanupKeepVmOnFailure}<InfoTooltip text={t.scenarioFieldCleanupKeepTooltip} label={t.infoTooltipLabel} /></label>
            </div>
          </section>
        );
      default:
        return null;
    }
  };
  return (
    <div className={`builderPanel scenarioBuilderPanel ${expanded ? "expanded" : "collapsed"}`}>
      <div className="builderHeader">
        <strong className="sectionTitleLine">
          <span>{t.scenarioBuilder}</span>
          <InfoTooltip text={t.scenarioBuilderTooltip} label={t.infoTooltipLabel} />
        </strong>
        <div className="builderHeaderActions">
          {!editable && <span className="muted">{t.builderReadOnly}</span>}
          <button
            type="button"
            className="secondary builderToggle"
            aria-label={expanded ? t.builderCollapse : t.builderExpand}
            aria-expanded={expanded}
            title={expanded ? t.builderCollapse : t.builderExpand}
            onClick={() => setExpanded(!expanded)}
          >
            <span className={`builderToggleGlyph ${expanded ? "builderToggleCollapseGlyph" : "builderToggleExpandGlyph"}`} aria-hidden="true" />
            <span className="builderToggleText">{expanded ? t.builderCollapse : t.builderExpand}</span>
          </button>
        </div>
      </div>
      {error && <p className="muted">{t.builderUnavailable}</p>}
      {!error && model && (
        <>
          <div className="builderSummary" aria-label={t.scenarioBuilder}>
            <span><b>ID</b>{compactValue(model.id)}</span>
            <span><b>OS</b>{compactValue(model.osFamily)} {compactValue(model.osVersion, "")}</span>
            <span><b>Template</b>{compactValue(model.template)}</span>
            <span><b>VMID</b>{model.vmIdStart ?? "-"}-{model.vmIdEnd ?? "-"}</span>
            <span><b>Artifact</b>{compactValue(model.artifactType)}/{compactValue(model.artifactTransfer)}</span>
            <span><b>Guest</b>{compactValue(model.guestMode)}</span>
            <span><b>{t.workflowRun}</b>{productStepCount || t.artifactCommandShort}</span>
            <span><b>{t.assertionCount}</b>{assertionCount}</span>
            <span className={`builderSummaryTone ${cleanupTone}`}><b>{t.scenarioBuilderCleanup}</b>{cleanupLabel}</span>
          </div>
          {expanded && (
            <>
              <div className="scenarioBuilderVerticalLayout">
                <div className="builderStepperRail" aria-label={t.scenarioBuilderWorkflow}>
                  {stageItems.map((stage) => (
                    <button
                      key={stage.id}
                      type="button"
                      className={selectedStage === stage.id ? "active" : ""}
                      aria-current={selectedStage === stage.id ? "step" : undefined}
                      onClick={() => setSelectedStage(stage.id)}
                    >
                      <b>{stage.index}</b>
                      <span>{stage.label}<small>{stage.detail}</small></span>
                      <em>{stage.status}</em>
                    </button>
                  ))}
                </div>
                <div className="builderStepDetail">
                  {selectedStageItem && (
                    <div className="builderStepContext">
                      <strong>{selectedStageItem.label}</strong>
                      <span>{selectedStageItem.detail}</span>
                    </div>
                  )}
                  {renderSelectedStage()}
                </div>
              </div>
              <div className="actions builderApplyActions">
                <button type="button" className="secondary builderApplyButton" disabled={!editable} onClick={onApply}>{t.applyBuilder}</button>
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}

function ScenarioFixturesEditor({ t, editable, model, onChange, open = false, stageNumber = "2" }: { t: DashboardText; editable: boolean; model: ScenarioBuilderModel; onChange: (next: ScenarioBuilderModel | null) => void; open?: boolean; stageNumber?: string }) {
  const fixtures = model.fixtures || [];
  const updateFixture = (index: number, patch: Partial<ScenarioFixtureModel>) => {
    onChange({ ...model, fixtures: fixtures.map((fixture, fixtureIndex) => (fixtureIndex === index ? { ...fixture, ...patch } : fixture)) });
  };
  const addFixture = () => {
    onChange({ ...model, fixtures: [...fixtures, { id: "prepare", type: "powershell", source: "validation/fixtures/windows/new-fixture.ps1", expectedOutput: "" }] });
  };
  const removeFixture = (index: number) => {
    onChange({ ...model, fixtures: fixtures.filter((_, fixtureIndex) => fixtureIndex !== index) });
  };
  return (
    <details className="builderSection" open={open}>
      <summary><span className="builderStageTitle"><b>{stageNumber}</b>{t.scenarioBuilderFixtures}</span><span>{fixtures.length}</span></summary>
      <div className="builderList">
        {fixtures.length === 0 && <p className="builderEmptyState">{t.scenarioBuilderFixturesEmpty}</p>}
        {fixtures.map((fixture, index) => (
          <div key={`${fixture.id}-${index}`} className="builderListRow fixtureRow">
            <label><BuilderLabel label="id" info={t.scenarioFieldFixtureIdTooltip} t={t} /><input value={fixture.id} disabled={!editable} onChange={(event) => updateFixture(index, { id: event.target.value })} /></label>
            <label><BuilderLabel label="type" info={t.scenarioFieldFixtureTypeTooltip} t={t} /><select value={fixture.type} disabled={!editable} onChange={(event) => updateFixture(index, { type: event.target.value })}>{FIXTURE_TYPE_OPTIONS.map((option) => <option key={option} value={option}>{option}</option>)}</select></label>
            <label className="span2"><BuilderLabel label="source" info={t.scenarioFieldFixtureSourceTooltip} t={t} /><input value={fixture.source} disabled={!editable} onChange={(event) => updateFixture(index, { source: event.target.value })} /></label>
            <label className="span2"><BuilderLabel label="expectedOutput" info={t.scenarioFieldFixtureExpectedTooltip} t={t} /><input value={fixture.expectedOutput} disabled={!editable} onChange={(event) => updateFixture(index, { expectedOutput: event.target.value })} /></label>
            <button type="button" className="secondary iconBuilderButton dangerBuilderButton" disabled={!editable} onClick={() => removeFixture(index)} aria-label={t.remove} title={t.remove}>×</button>
          </div>
        ))}
        <button type="button" className="secondary builderAddButton" disabled={!editable} onClick={addFixture}>{t.scenarioBuilderAddFixture}</button>
      </div>
    </details>
  );
}

function ScenarioProductStepsEditor({ t, editable, model, onChange, open = false, stageNumber = "4B" }: { t: DashboardText; editable: boolean; model: ScenarioBuilderModel; onChange: (next: ScenarioBuilderModel | null) => void; open?: boolean; stageNumber?: string }) {
  const steps = model.productSteps || [];
  const updateStep = (index: number, patch: Partial<ScenarioProductStepModel>) => {
    onChange({ ...model, productSteps: steps.map((step, stepIndex) => (stepIndex === index ? { ...step, ...patch } : step)) });
  };
  const addStep = () => {
    onChange({ ...model, productSteps: [...steps, { id: "run-product", shell: "powershell", template: "", captureStdoutJson: false, expectStdoutJsonJson: "{}", secretTokensJson: "{}" }] });
  };
  const removeStep = (index: number) => {
    onChange({ ...model, productSteps: steps.filter((_, stepIndex) => stepIndex !== index) });
  };
  return (
    <details className="builderSection" open={open}>
      <summary><span className="builderStageTitle"><b>{stageNumber}</b>{t.scenarioBuilderProductSteps}</span><span>{steps.length}</span></summary>
      <div className="builderList">
        {steps.length === 0 && <p className="builderEmptyState">{t.scenarioBuilderProductStepsEmpty}</p>}
        {steps.map((step, index) => (
          <div key={`${step.id}-${index}`} className="builderListRow productStepRow">
            <label><BuilderLabel label="id" info={t.scenarioFieldProductStepIdTooltip} t={t} /><input value={step.id} disabled={!editable} onChange={(event) => updateStep(index, { id: event.target.value })} /></label>
            <label><BuilderLabel label="shell" info={t.scenarioFieldShellTooltip} t={t} /><select value={step.shell} disabled={!editable} onChange={(event) => updateStep(index, { shell: event.target.value })}>{SHELL_OPTIONS.map((option) => <option key={option} value={option}>{option}</option>)}</select></label>
            <label className="span2"><BuilderLabel label="command" info={t.scenarioFieldProductStepCommandTooltip} t={t} /><textarea rows={2} value={step.template} disabled={!editable} onChange={(event) => updateStep(index, { template: event.target.value })} /></label>
            <label className="checkLine builderCheck"><input type="checkbox" checked={step.captureStdoutJson} disabled={!editable} onChange={(event) => updateStep(index, { captureStdoutJson: event.target.checked })} />{t.captureStdoutJson}</label>
            <label><BuilderLabel label="expectStdoutJson" info={t.scenarioFieldJsonObjectTooltip} t={t} /><textarea rows={3} value={step.expectStdoutJsonJson} disabled={!editable} onChange={(event) => updateStep(index, { expectStdoutJsonJson: event.target.value })} /></label>
            <label><BuilderLabel label="secretTokens" info={t.scenarioFieldSecretTokensTooltip} t={t} /><textarea rows={3} value={step.secretTokensJson} disabled={!editable} onChange={(event) => updateStep(index, { secretTokensJson: event.target.value })} /></label>
            <button type="button" className="secondary iconBuilderButton dangerBuilderButton" disabled={!editable} onClick={() => removeStep(index)} aria-label={t.remove} title={t.remove}>×</button>
          </div>
        ))}
        <button type="button" className="secondary builderAddButton" disabled={!editable} onClick={addStep}>{t.scenarioBuilderAddProductStep}</button>
      </div>
    </details>
  );
}

function ScenarioAssertionsEditor({ t, editable, model, onChange, open = true, stageNumber = "5" }: { t: DashboardText; editable: boolean; model: ScenarioBuilderModel; onChange: (next: ScenarioBuilderModel | null) => void; open?: boolean; stageNumber?: string }) {
  const assertions = model.assertions || [];
  const updateAssertion = (index: number, patch: Partial<ScenarioAssertionModel>) => {
    onChange({ ...model, assertions: assertions.map((assertion, assertionIndex) => (assertionIndex === index ? { ...assertion, ...patch } : assertion)) });
  };
  const addAssertion = () => {
    onChange({ ...model, assertions: [...assertions, { id: "exit-zero", type: "command.exitCode", bodyJson: "{\n  \"exitCode\": 0\n}" }] });
  };
  const removeAssertion = (index: number) => {
    onChange({ ...model, assertions: assertions.filter((_, assertionIndex) => assertionIndex !== index) });
  };
  return (
    <details className="builderSection" open={open}>
      <summary><span className="builderStageTitle"><b>{stageNumber}</b>{t.scenarioBuilderAssertions}</span><span>{assertions.length}</span></summary>
      <div className="builderList">
        {assertions.length === 0 && <p className="builderEmptyState">{t.scenarioBuilderAssertionsEmpty}</p>}
        {assertions.map((assertion, index) => (
          <div key={`${assertion.id}-${index}`} className="builderListRow assertionRow">
            <label><BuilderLabel label="id" info={t.scenarioFieldAssertionIdTooltip} t={t} /><input value={assertion.id} disabled={!editable} onChange={(event) => updateAssertion(index, { id: event.target.value })} /></label>
            <label><BuilderLabel label="type" info={t.scenarioFieldAssertionTypeTooltip} t={t} /><input value={assertion.type} disabled={!editable} onChange={(event) => updateAssertion(index, { type: event.target.value })} /></label>
            <label className="span2"><BuilderLabel label="body JSON" info={t.scenarioFieldAssertionBodyTooltip} t={t} /><textarea rows={4} value={assertion.bodyJson} disabled={!editable} onChange={(event) => updateAssertion(index, { bodyJson: event.target.value })} /></label>
            <button type="button" className="secondary iconBuilderButton dangerBuilderButton" disabled={!editable} onClick={() => removeAssertion(index)} aria-label={t.remove} title={t.remove}>×</button>
          </div>
        ))}
        <button type="button" className="secondary builderAddButton" disabled={!editable} onClick={addAssertion}>{t.scenarioBuilderAddAssertion}</button>
      </div>
    </details>
  );
}

export function SuiteBuilderPanel({
  t,
  model,
  error,
  editable,
  scenarios,
  addScenarioPath,
  onAddScenarioPath,
  onModelChange,
  onAdd,
  onMove,
  onRemove,
  onApply,
  onRunChange,
}: {
  t: DashboardText;
  model: SuiteBuilderModel | null;
  error: string;
  editable: boolean;
  scenarios: CatalogItem[];
  addScenarioPath: string;
  onAddScenarioPath: (path: string) => void;
  onModelChange: (next: SuiteBuilderModel | null) => void;
  onAdd: () => void;
  onMove: (index: number, direction: -1 | 1) => void;
  onRemove: (index: number) => void;
  onApply: () => void;
  onRunChange: (index: number, patch: Partial<SuiteBuilderRun>) => void;
}) {
  const [expanded, setExpanded] = useState(editable);
  useEffect(() => {
    if (editable) setExpanded(true);
  }, [editable]);
  const allowFailureCount = model?.runs.filter((entry) => entry.allowFailure).length ?? 0;
  const enabledCount = model?.runs.filter((entry) => entry.enabled !== false).length ?? 0;
  return (
    <div className={`builderPanel ${expanded ? "expanded" : "collapsed"}`}>
      <div className="builderHeader">
        <strong className="sectionTitleLine">
          <span>{t.suiteBuilder}</span>
          <InfoTooltip text={t.suiteBuilderTooltip} label={t.infoTooltipLabel} />
        </strong>
        <div className="builderHeaderActions">
          {!editable && <span className="muted">{t.builderReadOnly}</span>}
          <button type="button" className="secondary builderToggle" onClick={() => setExpanded((value) => !value)}>
            {expanded ? t.builderCollapse : t.builderExpand}
          </button>
        </div>
      </div>
      {error && <p className="muted">{t.builderUnavailable}</p>}
      {!error && model && (
        <>
          <div className="builderSummary" aria-label={t.suiteBuilder}>
            <span><b>id</b>{model.id || "-"}</span>
            <span><b>name</b>{model.name || "-"}</span>
            <span><b>{t.entries}</b>{model.runs.length}</span>
            <span><b>{t.enabled}</b>{enabledCount}</span>
            <span><b>{t.allowFailure}</b>{allowFailureCount}</span>
            <span><b>{t.maxParallel}</b>{model.maxParallel || 1}</span>
          </div>
          {expanded && (
            <>
              <div className="builderGrid">
                <label>id<input value={model.id} disabled={!editable} onChange={(event) => onModelChange({ ...model, id: event.target.value })} /></label>
                <label>name<input value={model.name} disabled={!editable} onChange={(event) => onModelChange({ ...model, name: event.target.value })} /></label>
                <label>{t.maxParallel}<input type="number" min="1" value={model.maxParallel || 1} disabled={!editable} onChange={(event) => onModelChange({ ...model, maxParallel: Math.max(1, Number(event.target.value) || 1) })} /></label>
              </div>
              <div className="builderAddRow">
                <label className="suiteAddSelect">
                  <span>{t.addSuiteEntry}</span>
                  <select value={addScenarioPath} disabled={!editable} onChange={(event) => onAddScenarioPath(event.target.value)}>
                    {scenarios.map((item) => <option key={item.path} value={item.path}>{item.path}</option>)}
                  </select>
                </label>
                <button type="button" disabled={!editable || !addScenarioPath} onClick={onAdd}>{t.addSuiteEntry}</button>
              </div>
              <div className="suiteRunList">
                <div className="suiteRunHeader" aria-hidden="true">
                  <span>#</span>
                  <span>id</span>
                  <span>{t.selectedScenario}</span>
                  <span>{t.tier}</span>
                  <span>{t.enabled}</span>
                  <span>{t.allowFailure}</span>
                  <span />
                </div>
                {model.runs.map((entry, index) => (
                  <div key={`${entry.id}-${entry.scenario}-${index}`} className="suiteRunRow">
                    <div className="suiteRunIndex" aria-hidden="true">{index + 1}</div>
                    <label className="suiteRunField"><span className="srOnly">id</span><input value={entry.id} disabled={!editable} onChange={(event) => onRunChange(index, { id: event.target.value })} /></label>
                    <label className="suiteScenarioSelect suiteRunField"><span className="srOnly">{t.selectedScenario}</span>
                      <select value={entry.scenario} disabled={!editable} onChange={(event) => onRunChange(index, { scenario: event.target.value })}>
                        {scenarios.map((item) => <option key={item.path} value={item.path}>{item.path}</option>)}
                      </select>
                    </label>
                    <label className="suiteRunField"><span className="srOnly">{t.tier}</span><input value={entry.tier} disabled={!editable} onChange={(event) => onRunChange(index, { tier: event.target.value })} /></label>
                    <label className="checkLine suiteRunCheck"><input type="checkbox" checked={entry.enabled !== false} disabled={!editable} onChange={(event) => onRunChange(index, { enabled: event.target.checked })} />{t.enabled}</label>
                    <label className="checkLine suiteRunCheck"><input type="checkbox" checked={entry.allowFailure} disabled={!editable} onChange={(event) => onRunChange(index, { allowFailure: event.target.checked })} />{t.allowFailure}</label>
                    <div className="suiteRunActions">
                      <button type="button" className="secondary iconBuilderButton" disabled={!editable || index === 0} onClick={() => onMove(index, -1)} aria-label={t.moveUp} title={t.moveUp}>↑</button>
                      <button type="button" className="secondary iconBuilderButton" disabled={!editable || index === model.runs.length - 1} onClick={() => onMove(index, 1)} aria-label={t.moveDown} title={t.moveDown}>↓</button>
                      <button type="button" className="secondary iconBuilderButton dangerBuilderButton" disabled={!editable} onClick={() => onRemove(index)} aria-label={t.remove} title={t.remove}>×</button>
                    </div>
                  </div>
                ))}
              </div>
              <div className="actions builderApplyActions">
                <button type="button" className="secondary builderApplyButton" disabled={!editable} onClick={onApply}>{t.applyBuilder}</button>
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}
