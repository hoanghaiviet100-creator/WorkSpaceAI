import { useMemo, useState, type ReactNode } from "react";
import { Check, ChevronDown, Plus } from "lucide-react";
import { DialogCancel, Modal } from "./components";
import type { Source } from "./data";
import type { StudyConfig } from "./study-model";
import flashcardIcon from "./flashcard-icon.svg";
import quizIcon from "./quiz-icon.svg";

const levels = [
  ["easy", "Easy"],
  ["medium", "Medium"],
  ["hard", "Hard"],
] as const;

function Choice({
  selected,
  onClick,
  children,
}: {
  selected: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button type="button" aria-pressed={selected} onClick={onClick}>
      <Check size={15} className="study-segment-check" aria-hidden="true" />
      {children}
    </button>
  );
}

type StudyCreateProps = {
  config: StudyConfig;
  sources: Source[];
  working: boolean;
  onChange: (value: StudyConfig) => void;
  onClose: () => void;
  onCreate: () => void;
};

export default function StudyCreateDialog(props: StudyCreateProps) {
  const isQuiz = props.config.kind === "quiz";
  return (
    <Modal
      title={isQuiz ? "Create quiz" : "Create flashcards"}
      titleIcon={
        <img
          src={isQuiz ? quizIcon : flashcardIcon}
          width={24}
          height={24}
          alt=""
        />
      }
      onClose={props.onClose}
      className="study-create-modal"
      deferContent
    >
      <StudyCreateForm {...props} />
    </Modal>
  );
}

function StudyCreateForm({
  config,
  sources,
  working,
  onChange,
  onCreate,
}: StudyCreateProps) {
  const isQuiz = config.kind === "quiz";
  const standard = isQuiz ? 5 : 8;
  const fewer = isQuiz ? 3 : 4;
  const [quantity, setQuantity] = useState(
    config.count === standard
      ? "standard"
      : config.count === fewer
        ? "fewer"
        : "custom",
  );
  const label = isQuiz ? "Quiz" : "Flashcard";
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const selectedIds = useMemo(
    () => new Set(config.sourceIds),
    [config.sourceIds],
  );
  const selected = useMemo(
    () => sources.filter((source) => selectedIds.has(source.id)),
    [sources, selectedIds],
  );
  const topics = useMemo(
    () =>
      [
        ...new Set(
          selected.map((source) =>
            source.name
              .replace(/\.[^.]+$/, "")
              .replace(/[_-]+/g, " ")
              .trim(),
          ),
        ),
      ]
        .filter((name) => name.length >= 3 && name.length <= 48)
        .slice(0, 3),
    [selected],
  );
  const useQuantity = (choice: string, count: number) => {
    setQuantity(choice);
    onChange({ ...config, count });
  };
  return (
    <form
      className="study-config"
      onSubmit={(event) => {
        event.preventDefault();
        onCreate();
      }}
    >
      <div className="study-create-body">
        <div className="study-create-grid">
          <fieldset>
            <legend>
              {isQuiz ? "Number of questions" : "Number of cards"}
            </legend>
            <div className="study-segments">
              <Choice
                selected={quantity === "fewer"}
                onClick={() => useQuantity("fewer", fewer)}
              >
                Fewer
              </Choice>
              <Choice
                selected={quantity === "standard"}
                onClick={() => useQuantity("standard", standard)}
              >
                Standard
              </Choice>
              <Choice
                selected={quantity === "custom"}
                onClick={() => setQuantity("custom")}
              >
                Custom
              </Choice>
            </div>
            {quantity === "custom" && (
              <label className="study-custom-count">
                {isQuiz ? "Questions (3–12)" : "Cards (3–12)"}
                <input
                  type="number"
                  min={3}
                  max={12}
                  required
                  value={config.count || ""}
                  onChange={(event) =>
                    onChange({ ...config, count: Number(event.target.value) })
                  }
                />
              </label>
            )}
          </fieldset>
          <fieldset>
            <legend>Difficulty</legend>
            <div className="study-segments">
              {levels.map(([id, name]) => (
                <Choice
                  key={id}
                  selected={config.difficulty === id}
                  onClick={() => onChange({ ...config, difficulty: id })}
                >
                  {name}
                </Choice>
              ))}
            </div>
          </fieldset>
          <label className="study-language">
            Prompt language
            <select
              value={config.language ?? "auto"}
              onChange={(event) =>
                onChange({
                  ...config,
                  language: event.target.value as StudyConfig["language"],
                })
              }
            >
              <option value="auto">Match the documents</option>
              <option value="vi">Vietnamese</option>
              <option value="en">English</option>
            </select>
          </label>
          <fieldset className="study-create-sources">
            <legend>Sources</legend>
            <details
              onToggle={(event) => setSourcesOpen(event.currentTarget.open)}
            >
              <summary>
                {selected.length} {selected.length === 1 ? "source" : "sources"}{" "}
                <ChevronDown size={16} />
              </summary>
              {sourcesOpen &&
                (sources.length ? (
                  <div className="study-source-list">
                    {sources.map((source) => (
                      <label key={source.id}>
                        <input
                          type="checkbox"
                          checked={selectedIds.has(source.id)}
                          onChange={(event) =>
                            onChange({
                              ...config,
                              sourceIds: event.target.checked
                                ? [...config.sourceIds, source.id]
                                : config.sourceIds.filter(
                                    (id) => id !== source.id,
                                  ),
                            })
                          }
                        />
                        <span>{source.name}</span>
                      </label>
                    ))}
                  </div>
                ) : (
                  <p>Add documents in Sources to create a study set.</p>
                ))}
            </details>
          </fieldset>
        </div>
        <label className="study-focus">
          What should this cover?{" "}
          <textarea
            value={config.focus}
            maxLength={160}
            rows={4}
            onChange={(event) =>
              onChange({ ...config, focus: event.target.value })
            }
            placeholder={
              isQuiz
                ? "Example: Test my understanding of algorithm complexity."
                : "Example: Review binary search definitions and examples."
            }
          />
        </label>
        {!!topics.length && (
          <div
            className="study-topic-chips"
            aria-label="Suggestions from source names"
          >
            {topics.map((topic) => {
              const active = config.focus
                .split(",")
                .some((value) => value.trim() === topic);
              return (
                <button
                  type="button"
                  key={topic}
                  aria-pressed={active}
                  onClick={() => {
                    const values = config.focus
                      .split(",")
                      .map((value) => value.trim())
                      .filter(Boolean);
                    onChange({
                      ...config,
                      focus: (active
                        ? values.filter((value) => value !== topic)
                        : [...values, topic]
                      )
                        .join(", ")
                        .slice(0, 160),
                    });
                  }}
                >
                  {active ? <Check size={14} /> : <Plus size={14} />}
                  {topic}
                </button>
              );
            })}
          </div>
        )}
      </div>
      <div className="study-create-footer">
        <DialogCancel />
        <button
          type="submit"
          className="button study-primary"
          disabled={
            working || !selected.length || config.count < 3 || config.count > 12
          }
        >
          {working ? "Creating another set…" : "Create"}
        </button>
      </div>
    </form>
  );
}
