import { useEffect, useMemo, useState, type RefObject } from "react";
import {
  ArrowUpRight,
  BookOpen,
  MoreHorizontal,
  PanelRightClose,
  Pencil,
  RotateCcw,
  Settings2,
  Trash2,
} from "lucide-react";
import { DialogCancel, Modal } from "./components";
import type { Workspace } from "./data";
import StudySession from "./StudySession";
import StudyCreateDialog from "./StudyCreateDialog";
import { createStudyItems } from "./study-generator";
import {
  reviewCards,
  studyConfig,
  studySources,
  type StudyCitation,
  type StudyConfig,
  type StudyItem,
  type StudyKind,
  type StudySet,
} from "./study-model";
import { sampleStudy } from "./study-sample";
import flashcardIcon from "./flashcard-icon.svg";
import quizIcon from "./quiz-icon.svg";

const tools = {
  flashcard: {
    label: "Flashcard",
    description: "Review key concepts on cards.",
    icon: flashcardIcon,
  },
  quiz: {
    label: "Quiz",
    description: "Test your understanding.",
    icon: quizIcon,
  },
} as const;
const toolEntries = Object.entries(tools) as [
  StudyKind,
  (typeof tools)[StudyKind],
][];
const dateFormat = new Intl.DateTimeFormat("en-US", {
  dateStyle: "short",
  timeStyle: "short",
});

export default function Studio({
  workspace,
  update,
  onClose,
  selected,
  onSelect,
  expanded,
  onExpand,
  launch,
  clearLaunch,
  onSource,
  motionRef,
}: {
  workspace: Workspace;
  update: (change: (current: Workspace) => Workspace) => void;
  onClose: () => void;
  selected?: StudySet;
  onSelect: (id: string | null) => void;
  expanded: boolean;
  onExpand: () => void;
  launch: StudyConfig | null;
  clearLaunch: () => void;
  onSource: (citation: StudyCitation) => void;
  motionRef: RefObject<HTMLDivElement | null>;
}) {
  const [config, setConfig] = useState<StudyConfig | null>(null);
  const [dialog, setDialog] = useState<{
    type: "rename" | "delete";
    set: StudySet;
  } | null>(null);
  const [title, setTitle] = useState("");
  const [menu, setMenu] = useState<string | null>(null);
  const sets = workspace.studySets ?? [];
  const available = useMemo(() => studySources(workspace), [workspace]);
  const working = sets.some((set) => set.status === "generating");
  useEffect(() => {
    if (launch) setConfig(launch);
  }, [launch]);
  const changeSet = (id: string, change: (set: StudySet) => StudySet) =>
    update((current) => ({
      ...current,
      studySets: current.studySets?.map((set) =>
        set.id === id ? change(set) : set,
      ),
    }));
  const addSet = (set: StudySet) =>
    update((current) => ({
      ...current,
      studySets: [set, ...(current.studySets ?? [])],
    }));
  const closeConfig = () => {
    setConfig(null);
    clearLaunch();
  };
  const generate = async (settings: StudyConfig, retry?: StudySet) => {
    if (working || !settings.sourceIds.length) return;
    const sources = settings.sourceIds.map((id) =>
      available.find((source) => source.id === id),
    );
    if (sources.some((source) => !source)) {
      setConfig({
        ...settings,
        sourceIds: sources.flatMap((source) => source?.id ?? []),
      });
      return;
    }
    const base =
      settings.focus.trim() ||
      (sources.length === 1
        ? sources[0]?.name.replace(/\.[^.]+$/, "")
        : "Selected documents");
    const set: StudySet = {
      id: retry?.id ?? crypto.randomUUID(),
      title: retry?.title ?? `${tools[settings.kind].label} · ${base}`,
      createdAt: retry?.createdAt ?? new Date().toISOString(),
      status: "generating",
      config: settings,
      items: [],
    };
    if (retry) changeSet(set.id, () => set);
    else addSet(set);
    closeConfig();
    try {
      const items = await createStudyItems(workspace, settings);
      changeSet(set.id, (current) => ({
        ...current,
        items,
        status: "ready",
        engine: "extractive",
      }));
    } catch (error) {
      changeSet(set.id, (current) => ({
        ...current,
        status: "error",
        error:
          error instanceof Error
            ? error.message
            : "Could not create the study set.",
      }));
    }
  };
  const openSample = (kind: StudyKind) => {
    const sample = sampleStudy(kind);
    if (!sets.some((set) => set.id === sample.id)) addSet(sample);
    onSelect(sample.id);
  };
  const createReview = (set: StudySet, items: StudyItem[]) => {
    const deck = {
      id: crypto.randomUUID(),
      title: `Review · ${set.title}`,
      createdAt: new Date().toISOString(),
      status: "ready",
      engine: "review",
      config: {
        ...set.config,
        kind: "flashcard",
        count: items.length,
        sourceIds: [...new Set(items.map((item) => item.citation.docId))],
      },
      items: reviewCards(items),
    } satisfies StudySet;
    addSet(deck);
    onSelect(deck.id);
  };

  return (
    <>
      <div className="nb-panel-content nb-rail-surface" ref={motionRef}>
        {selected ? (
          <StudySession
            key={selected.id}
            set={selected}
            expanded={expanded}
            onExpand={onExpand}
            onBack={() => onSelect(null)}
            onUpdate={(change) => changeSet(selected.id, change)}
            onSource={onSource}
            onReview={(items) => createReview(selected, items)}
          />
        ) : (
          <>
            <header className="nb-panel-header study-studio-header">
              <h2>Studio</h2>
              <button
                className="icon-button"
                aria-label="Collapse Studio"
                onClick={onClose}
              >
                <PanelRightClose size={18} />
              </button>
            </header>
            <div className="study-scroll study-studio-body">
              <div className="study-tools" aria-label="Study tools">
                {toolEntries.map(([kind, tool]) => (
                  <div className="study-tool" data-kind={kind} key={kind}>
                    <button
                      className="study-tool-main"
                      onClick={() => setConfig(studyConfig(workspace, kind))}
                    >
                      <img
                        className="study-tool-icon"
                        src={tool.icon}
                        width={44}
                        height={44}
                        alt=""
                      />
                      <strong>{tool.label}</strong>
                      <span>{tool.description}</span>
                    </button>
                    <button
                      className="icon-button study-tool-settings"
                      aria-label={`Customize ${tool.label}`}
                      title={`Customize ${tool.label}`}
                      onClick={() => setConfig(studyConfig(workspace, kind))}
                    >
                      <Settings2 size={16} />
                    </button>
                  </div>
                ))}
              </div>
              <section className="study-history" aria-label="Study set history">
                <div className="study-history-title">
                  <h3>Study history</h3>
                  <span>
                    {sets.length} {sets.length === 1 ? "set" : "sets"}
                  </span>
                </div>
                {sets.length ? (
                  <ul className="study-history-list">
                    {sets.map((set) => {
                      const tool = tools[set.config.kind];
                      const progress =
                        set.config.kind === "flashcard"
                          ? `${set.items.filter((item) => set.mastered?.[item.id]).length}/${set.items.length} mastered`
                          : set.lastScore
                            ? `${set.lastScore.correct}/${set.lastScore.total} correct`
                            : set.quiz
                              ? `${Object.keys(set.quiz.answers).length}/${set.quiz.order.length} answered`
                              : "Not started";
                      const sourceCount =
                        set.status === "ready"
                          ? new Set(
                              set.items.map((item) => item.citation.docId),
                            ).size
                          : set.config.sourceIds.length;
                      return (
                        <li key={set.id}>
                          <div className="study-history-row">
                            <img
                              className="study-history-icon"
                              src={tool.icon}
                              width={24}
                              height={24}
                              alt=""
                            />
                            {set.status === "ready" ? (
                              <button
                                className="study-open"
                                onClick={() => onSelect(set.id)}
                              >
                                <strong title={set.title}>{set.title}</strong>
                                <span>
                                  {dateFormat.format(new Date(set.createdAt))} ·{" "}
                                  {sourceCount}{" "}
                                  {sourceCount === 1 ? "source" : "sources"}
                                </span>
                                <span>
                                  {progress}
                                  {set.engine === "sample"
                                    ? " · Sample set"
                                    : ""}
                                  {set.engine === "extractive" &&
                                  set.items.length < set.config.count
                                    ? ` · Created ${set.items.length}/${set.config.count}`
                                    : ""}
                                </span>
                              </button>
                            ) : (
                              <div className="study-history-status">
                                <strong>{set.title}</strong>
                                {set.status === "generating" ? (
                                  <span
                                    className="study-skeleton"
                                    role="status"
                                  >
                                    Creating study set…
                                    <i />
                                  </span>
                                ) : (
                                  <>
                                    <span className="study-error" role="status">
                                      {set.error}
                                    </span>
                                    <button
                                      className="study-text-button"
                                      disabled={working}
                                      onClick={() =>
                                        void generate(set.config, set)
                                      }
                                    >
                                      <RotateCcw size={14} /> Retry
                                    </button>
                                  </>
                                )}
                              </div>
                            )}
                            {set.status !== "generating" && (
                              <button
                                className="icon-button study-more"
                                aria-expanded={menu === set.id}
                                aria-label={`Options for ${set.title}`}
                                onClick={() =>
                                  setMenu(menu === set.id ? null : set.id)
                                }
                              >
                                <MoreHorizontal size={19} />
                              </button>
                            )}
                          </div>
                          {menu === set.id && (
                            <div className="study-row-actions">
                              <button
                                className="study-text-button"
                                onClick={() => {
                                  setTitle(set.title);
                                  setDialog({ type: "rename", set });
                                  setMenu(null);
                                }}
                              >
                                <Pencil size={14} /> Rename
                              </button>
                              {set.engine !== "review" &&
                                set.engine !== "sample" && (
                                  <button
                                    className="study-text-button"
                                    disabled={working}
                                    onClick={() => {
                                      setConfig({
                                        ...set.config,
                                        sourceIds: set.config.sourceIds.filter(
                                          (id) =>
                                            available.some(
                                              (source) => source.id === id,
                                            ),
                                        ),
                                      });
                                      setMenu(null);
                                    }}
                                  >
                                    <RotateCcw size={14} /> Regenerate
                                  </button>
                                )}
                              {(set.engine === "sample" ||
                                set.engine === "review") && (
                                <button
                                  className="study-text-button"
                                  onClick={() => {
                                    changeSet(set.id, (current) => ({
                                      ...current,
                                      mastered: undefined,
                                      quiz: undefined,
                                      lastScore: undefined,
                                    }));
                                    setMenu(null);
                                    onSelect(set.id);
                                  }}
                                >
                                  <RotateCcw size={14} /> Regenerate
                                </button>
                              )}
                              <button
                                className="study-text-button study-error"
                                onClick={() => {
                                  setDialog({ type: "delete", set });
                                  setMenu(null);
                                }}
                              >
                                <Trash2 size={14} /> Delete
                              </button>
                            </div>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                ) : (
                  <div className="study-empty">
                    <BookOpen size={24} strokeWidth={1.5} />
                    <h3>No study sets yet</h3>
                    <p>
                      Flashcards and quizzes you create from documents will
                      appear here.
                    </p>
                  </div>
                )}
                {toolEntries.some(
                  ([kind]) => !sets.some((set) => set.id === `sample-${kind}`),
                ) && (
                  <div className="study-samples">
                    <span>Try a sample</span>
                    {toolEntries
                      .filter(
                        ([kind]) =>
                          !sets.some((set) => set.id === `sample-${kind}`),
                      )
                      .map(([kind, tool]) => (
                        <button
                          key={kind}
                          className="study-text-button"
                          onClick={() => openSample(kind)}
                        >
                          {tool.label} ·{" "}
                          {kind === "quiz" ? "5 questions" : "8 cards"}{" "}
                          <ArrowUpRight size={14} />
                        </button>
                      ))}
                  </div>
                )}
              </section>
            </div>
          </>
        )}
      </div>
      {config && (
        <StudyCreateDialog
          config={config}
          sources={available}
          working={working}
          onChange={setConfig}
          onClose={closeConfig}
          onCreate={() => void generate(config)}
        />
      )}
      {dialog && (
        <Modal
          title={
            dialog.type === "rename" ? "Rename study set" : "Delete study set?"
          }
          onClose={() => setDialog(null)}
          className="study-modal"
        >
          <form
            className="study-config"
            onSubmit={(event) => {
              event.preventDefault();
              if (dialog.type === "rename" && !title.trim()) return;
              if (dialog.type === "rename")
                changeSet(dialog.set.id, (set) => ({
                  ...set,
                  title: title.trim(),
                }));
              else
                update((current) => ({
                  ...current,
                  studySets: current.studySets?.filter(
                    (set) => set.id !== dialog.set.id,
                  ),
                }));
              setDialog(null);
            }}
          >
            {dialog.type === "rename" ? (
              <label>
                Study set name
                <input
                  autoFocus
                  required
                  maxLength={120}
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                />
              </label>
            ) : (
              <p>
                “{dialog.set.title}” and its progress will be removed from study
                history.
              </p>
            )}
            <div className="modal-actions">
              <DialogCancel />
              <button
                type="submit"
                className="button study-primary"
                disabled={dialog.type === "rename" && !title.trim()}
              >
                {dialog.type === "rename" ? "Save name" : "Delete study set"}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </>
  );
}
