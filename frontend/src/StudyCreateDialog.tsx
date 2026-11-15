import { useMemo, useState, type ReactNode } from "react";
import { Check, ChevronDown } from "lucide-react";
import { DialogCancel, Modal } from "./components";
import type { Source } from "./data";
import type { QuestionType, StudyConfig } from "./study-model";
import type { RuntimeStatus } from "./api";
import flashcardIcon from "./flashcard-icon.svg";
import quizIcon from "./quiz-icon.svg";

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
  runtime: RuntimeStatus | null;
  runtimeError: boolean;
  onChange: (value: StudyConfig) => void;
  onClose: () => void;
  onCreate: () => void;
  onSave: () => void;
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
  runtime,
  runtimeError,
  onChange,
  onCreate,
  onSave,
}: StudyCreateProps) {
  const isQuiz = config.kind === "quiz";
  const engine = runtime?.engine_mode;
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
  const maxCount = isQuiz ? 50 : 30;
  const questionTypes = config.questionTypes ?? ["single"];
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const selectedIds = useMemo(
    () => new Set(config.sourceIds),
    [config.sourceIds],
  );
  const selected = useMemo(
    () => sources.filter((source) => selectedIds.has(source.id)),
    [sources, selectedIds],
  );
  const invalid = working || !selected.length || !Number.isInteger(config.count)
    || config.count < 1 || config.count > maxCount
    || (isQuiz && (!questionTypes.length || new Set(questionTypes).size > config.count));
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
                {isQuiz ? "Questions" : "Cards"} (1–{maxCount})
                <input
                  type="number"
                  min={1}
                  max={maxCount}
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
              {(["easy", "medium", "hard"] as const).map((difficulty) => (
                <Choice key={difficulty} selected={config.difficulty === difficulty}
                  onClick={() => onChange({ ...config, difficulty })}>
                  {{ easy: "Easy", medium: "Medium", hard: "Hard" }[difficulty]}
                </Choice>
              ))}
            </div>
          </fieldset>
          {isQuiz && (
            <fieldset className="study-create-types">
              <legend>Question types</legend>
              <div className="study-type-options">
                {([
                  ["single", "Single choice"],
                  ["multiple", "Multiple answers"],
                  ["blank", "Fill in the blank"],
                  ["short", "Short answer"],
                ] as const).map(([type, name]) => (
                  <label key={type}>
                    <input type="checkbox" checked={questionTypes.includes(type)}
                      onChange={(event) => onChange({ ...config, questionTypes: event.target.checked
                        ? [...questionTypes, type] as QuestionType[]
                        : questionTypes.filter((value) => value !== type) as QuestionType[],
                      })}
                    />
                    {name}
                  </label>
                ))}
              </div>
            </fieldset>
          )}
          <label className="study-language">
            Language
            <select value={config.language ?? "auto"}
              onChange={(event) => onChange({ ...config, language: event.target.value as StudyConfig["language"] })}>
              <option value="auto">Match the sources</option>
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
              {!sources.length && <p>Add documents to the workspace library to create a study set.</p>}
              {sourcesOpen &&
                sources.length > 0 && (
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
                )}
            </details>
          </fieldset>
        </div>
        <label className="study-focus">
          Topic or instructions
          <textarea rows={3} maxLength={500} value={config.focus}
            onChange={(event) => onChange({ ...config, focus: event.target.value })}
            placeholder={isQuiz ? "Example: Focus on when each protocol is used." : "Example: Keep the front short and explain key differences on the back."}
          />
        </label>
      </div>
      <p className="study-model-status" role="status">
        {runtimeError
          ? "Could not check the AI model. Reopen this dialog to try again."
          : engine === "gemini"
            ? `${runtime?.model ?? "Gemini"} will receive excerpts from the selected sources.`
            : engine === "ollama"
              ? `Generates locally with ${runtime?.model ?? "Ollama"}.`
              : engine === "offline"
                ? "Select Gemini or Ollama in Chat to generate a study set."
                : "Checking the AI model…"}
      </p>
      <div className="study-create-footer">
        <DialogCancel />
        <button className="button" type="button" onClick={onSave} disabled={invalid}>Save for later</button>
        <button
          type="submit"
          className="button study-primary"
          disabled={
            !engine || engine === "offline" || invalid
          }
        >
          {working ? "Creating another set…" : "Create"}
        </button>
      </div>
    </form>
  );
}
