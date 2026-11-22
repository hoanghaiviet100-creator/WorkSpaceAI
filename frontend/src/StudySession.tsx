import {
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
} from "react";
import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Check,
  Layers,
  Maximize2,
  Minimize2,
  RotateCcw,
  Shuffle,
  X,
} from "lucide-react";
import {
  quizTopics,
  scoreQuiz,
  shuffled,
  type QuizProgress,
  type StudyCitation,
  type StudyItem,
  type StudySet,
} from "./study-model";

type SessionProps = {
  set: StudySet;
  expanded: boolean;
  onExpand: () => void;
  onBack: () => void;
  onUpdate: (change: (current: StudySet) => StudySet) => void;
  onSource: (citation: StudyCitation) => void;
  onReview: (items: StudyItem[]) => void;
};

export function StudyProgress({
  value,
  max,
  label,
}: {
  value: number;
  max: number;
  label: string;
}) {
  const total = Math.max(1, max);
  return (
    <div
      className="study-progress"
      role="progressbar"
      aria-valuenow={value}
      aria-valuemin={0}
      aria-valuemax={total}
      aria-label={label}
    >
      <span
        className="study-progress-fill"
        style={{ "--study-progress": value / total } as CSSProperties}
      />
    </div>
  );
}

function FlashcardFace({
  item,
  back,
  hidden,
  descriptionId,
}: {
  item: StudyItem;
  back: boolean;
  hidden?: boolean;
  descriptionId?: string;
}) {
  return (
    <span className="study-flip-face" data-back={back} aria-hidden={hidden}>
      <span className="study-face-label">{back ? "Answer" : item.topic}</span>
      <strong id={descriptionId}>{back ? item.answer : item.question}</strong>
      <span className="study-flip-hint">
        <RotateCcw size={15} />{" "}
        {back ? "Back to question" : "Flip to see answer"}
      </span>
    </span>
  );
}

function QuizScore({ percent }: { percent: number }) {
  const score = useRef<HTMLSpanElement>(null);
  useLayoutEffect(() => {
    const label = score.current;
    const preference = matchMedia("(prefers-reduced-motion: reduce)");
    if (!label || preference.matches || percent === 0) return;
    const start = performance.now();
    let frame: number;
    const count = (now: number) => {
      const progress = preference.matches
        ? 1
        : Math.min((now - start) / 260, 1);
      label.textContent = `${Math.round(percent * (1 - (1 - progress) ** 2))}%`;
      if (progress < 1) frame = requestAnimationFrame(count);
    };
    count(start);
    return () => cancelAnimationFrame(frame);
  }, [percent]);
  return (
    <strong>
      <span className="sr-only">{percent}%</span>
      <span aria-hidden="true" ref={score}>
        {percent}%
      </span>
    </strong>
  );
}

function SourceChip({
  citation,
  open,
}: {
  citation: StudyCitation;
  open: () => void;
}) {
  return (
    <button
      className="study-citation"
      onClick={open}
      title={`${citation.file} · Page ${citation.page}`}
    >
      <BookOpen size={15} />
      <span>{citation.file}</span>
      <span>· p. {citation.page}</span>
    </button>
  );
}

export default function StudySession(props: SessionProps) {
  const { set, expanded, onExpand, onBack } = props;
  const flashcard = set.config.kind === "flashcard";
  const title = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    title.current?.focus({ preventScroll: true });
  }, []);
  return (
    <>
      <header className="nb-panel-header study-session-header">
        <button
          className="icon-button"
          aria-label="Back to Studio history"
          onClick={onBack}
        >
          <ArrowLeft size={19} />
        </button>
        <div>
          <h2 tabIndex={-1} ref={title}>
            {set.title}
          </h2>
          <span>
            {flashcard ? "Flashcard" : "Quiz"}
            {set.engine === "sample" ? " · Sample set" : ""}
          </span>
        </div>
        <button
          className="icon-button"
          aria-label={
            expanded ? "Exit expanded study mode" : "Expand study mode"
          }
          onClick={onExpand}
        >
          {expanded ? <Minimize2 size={18} /> : <Maximize2 size={18} />}
        </button>
      </header>
      {flashcard ? <Flashcards {...props} /> : <Quiz {...props} />}
    </>
  );
}

function Flashcards({ set, onUpdate, onSource }: SessionProps) {
  const scroll = useRef<HTMLDivElement>(null);
  const [order, setOrder] = useState(() => set.items.map((item) => item.id));
  const [cardId, setCardId] = useState(order[0]);
  const [flipped, setFlipped] = useState(false);
  const [unmastered, setUnmastered] = useState(false);
  const [flight, setFlight] = useState<{
    item: StudyItem;
    back: boolean;
    remembered: boolean;
  } | null>(null);
  useEffect(() => {
    if (!flight) return;
    const preference = matchMedia("(prefers-reduced-motion: reduce)");
    const reduce = () => {
      if (preference.matches) setFlight(null);
    };
    reduce();
    preference.addEventListener("change", reduce);
    return () => preference.removeEventListener("change", reduce);
  }, [flight]);
  const cardTextId = useId();
  const mastered = set.mastered ?? {};
  const remembered = set.items.filter((item) => mastered[item.id]).length;
  const visible = unmastered ? order.filter((id) => !mastered[id]) : order;
  const index = Math.max(0, visible.indexOf(cardId));
  const item = set.items.find((candidate) => candidate.id === visible[index]);
  const select = (id: string) => {
    setCardId(id);
    setFlipped(false);
  };
  const move = (delta: number) => {
    const next = visible[index + delta];
    if (next) select(next);
  };
  const mark = (value: boolean) => {
    if (!item) return;
    if (!matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setFlight({ item, back: flipped, remembered: value });
    }
    onUpdate((current) => ({
      ...current,
      mastered: { ...current.mastered, [item.id]: value },
    }));
    const next =
      visible[index + 1] ??
      (unmastered && value ? visible[index - 1] : undefined);
    if (next) select(next);
    else setFlipped(false);
  };
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (
        !item ||
        !scroll.current?.getClientRects().length ||
        event.defaultPrevented ||
        event.altKey ||
        event.ctrlKey ||
        event.metaKey ||
        document.querySelector('[role="dialog"]') ||
        (event.target instanceof HTMLElement &&
          event.target.closest(
            "button, a, input, select, textarea, [contenteditable]",
          ))
      )
        return;
      if (event.code === "Space") {
        event.preventDefault();
        setFlipped((value) => !value);
      } else if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
        event.preventDefault();
        move(event.key === "ArrowLeft" ? -1 : 1);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });
  return (
    <div className="study-scroll" ref={scroll}>
      <div className="study-content">
        <div className="study-metadata">
          <span>
            {item ? `Card ${index + 1} / ${visible.length}` : "Review complete"}
          </span>
          <strong>
            {remembered}/{set.items.length} mastered
          </strong>
        </div>
        <StudyProgress
          value={remembered}
          max={set.items.length}
          label="Cards mastered"
        />
        <div className="study-actions study-card-options">
          <button
            className="button"
            onClick={() => {
              const next = shuffled(order);
              setOrder(next);
              const first = next.find((id) => !unmastered || !mastered[id]);
              if (first) select(first);
            }}
          >
            <Shuffle size={16} /> Shuffle
          </button>
          <label>
            <input
              type="checkbox"
              checked={unmastered}
              onChange={(event) => {
                setUnmastered(event.target.checked);
                setFlipped(false);
              }}
            />{" "}
            Only unmastered cards
          </label>
        </div>
        <div className="study-card-stage" data-departing={!!flight}>
          {item ? (
            <button
              key={item.id}
              className="study-flip"
              data-flipped={flipped}
              onClick={() => setFlipped(!flipped)}
              aria-label={
                flipped ? "Show question" : "Flip card to reveal answer"
              }
              aria-describedby={cardTextId}
            >
              <span className="study-flip-inner">
                <FlashcardFace
                  item={item}
                  back={false}
                  hidden={flipped}
                  descriptionId={flipped ? undefined : cardTextId}
                />
                <FlashcardFace
                  item={item}
                  back
                  hidden={!flipped}
                  descriptionId={flipped ? cardTextId : undefined}
                />
              </span>
            </button>
          ) : (
            <div className="study-empty">
              <Check size={24} />
              <h3>You mastered all cards</h3>
              <button className="button" onClick={() => setUnmastered(false)}>
                Show all cards
              </button>
            </div>
          )}
          {flight && (
            <div
              key={flight.item.id}
              className="study-card-flight"
              data-remembered={flight.remembered}
              aria-hidden="true"
              onAnimationEnd={() => setFlight(null)}
            >
              <FlashcardFace item={flight.item} back={flight.back} />
            </div>
          )}
        </div>
        {item && (
          <>
            <SourceChip
              citation={item.citation}
              open={() => onSource(item.citation)}
            />
            <div className="study-actions study-card-nav">
              <button
                className="button"
                aria-label="Previous card"
                onClick={() => move(-1)}
                disabled={index === 0}
              >
                <ArrowLeft size={18} />
              </button>
              <button className="button" onClick={() => mark(false)}>
                Needs review
              </button>
              <button
                className="button study-primary"
                onClick={() => mark(true)}
              >
                <Check size={16} /> Mastered
              </button>
              <button
                className="button"
                aria-label="Next card"
                onClick={() => move(1)}
                disabled={index === visible.length - 1}
              >
                <ArrowRight size={18} />
              </button>
            </div>
            <p className="study-shortcuts">
              <kbd>Space</kbd> flip card <span>·</span> <kbd>←</kbd>{" "}
              <kbd>→</kbd> change cards
            </p>
          </>
        )}
      </div>
    </div>
  );
}

function Quiz({ set, onUpdate, onSource, onReview }: SessionProps) {
  const initial: QuizProgress = {
    order: set.items.map((item) => item.id),
    answers: {},
    complete: false,
  };
  const progress = set.quiz ?? initial;
  const items = progress.order.flatMap(
    (id) => set.items.find((item) => item.id === id) ?? [],
  );
  const [position, setPosition] = useState(() => {
    const next = items.findIndex(
      (item) => progress.answers[item.id] === undefined,
    );
    return next === -1 ? items.length - 1 : next;
  });
  const [choice, setChoice] = useState<number | null>(null);
  const item = items[position];
  const chosen = item ? progress.answers[item.id] : undefined;
  const wrong = items.filter(
    (question) => progress.answers[question.id] !== question.correctIndex,
  );
  const score = scoreQuiz(items, progress.answers);
  const restart = (order: string[]) => {
    onUpdate((current) => ({
      ...current,
      quiz: { order, answers: {}, complete: false },
    }));
    setPosition(0);
    setChoice(null);
  };

  if (progress.complete) {
    const topics = quizTopics(items, progress.answers);
    return (
      <div className="study-scroll">
        <div className="study-content study-results">
          <div className="study-score">
            <span>
              {items.length < set.items.length
                ? "Retry results"
                : "Quiz results"}
            </span>
            <QuizScore
              percent={Math.round(
                (score.correct / Math.max(1, score.total)) * 100,
              )}
            />
            <div>
              <span>
                <Check size={16} /> {score.correct} correct
              </span>
              <span>
                <X size={16} /> {score.total - score.correct} incorrect
              </span>
            </div>
          </div>
          <section
            className="study-topic-results"
            aria-label="Results by topic"
          >
            <h3>Understanding by topic</h3>
            {topics.map((topic) => (
              <div key={topic.topic}>
                <div className="study-metadata">
                  <strong>{topic.topic}</strong>
                  <span>
                    {topic.correct}/{topic.total} correct
                  </span>
                </div>
                <StudyProgress
                  value={topic.correct}
                  max={topic.total}
                  label={topic.topic}
                />
                <span className="study-topic-note">
                  {topic.correct === topic.total
                    ? "Mastered in this attempt"
                    : "Needs more review"}
                </span>
              </div>
            ))}
          </section>
          <div className="study-actions">
            {wrong.length > 0 && (
              <button
                className="button"
                onClick={() => restart(wrong.map((question) => question.id))}
              >
                <RotateCcw size={16} /> Retry missed questions
              </button>
            )}
            <button
              className="button study-primary"
              onClick={() => onReview(wrong.length ? wrong : items)}
            >
              <Layers size={16} /> Review with flashcards
            </button>
          </div>
          <button
            className="study-text-button"
            onClick={() => restart(initial.order)}
          >
            Retake quiz
          </button>
          {wrong.length > 0 && (
            <details className="study-wrong">
              <summary>
                Review {wrong.length} missed{" "}
                {wrong.length === 1 ? "question" : "questions"}
              </summary>
              {wrong.map((question) => (
                <article key={question.id}>
                  <strong>{question.question}</strong>
                  <p>
                    Your answer:{" "}
                    {question.options?.[progress.answers[question.id]]}
                  </p>
                  <p>
                    Answer: {question.options?.[question.correctIndex ?? -1]}
                  </p>
                  <p>{question.answer}</p>
                  <SourceChip
                    citation={question.citation}
                    open={() => onSource(question.citation)}
                  />
                </article>
              ))}
            </details>
          )}
        </div>
      </div>
    );
  }
  if (!item) return null;
  const answered = Object.keys(progress.answers).length;
  const next = () => {
    if (position + 1 < items.length) {
      setPosition(position + 1);
      setChoice(null);
    } else {
      onUpdate((current) => ({
        ...current,
        quiz: { ...progress, complete: true },
        lastScore: { ...score, completedAt: new Date().toISOString() },
      }));
    }
  };
  return (
    <div className="study-scroll">
      <div className="study-content">
        <div className="study-metadata">
          <strong>
            Question {position + 1} / {items.length}
          </strong>
          <span>{answered} answered</span>
        </div>
        <StudyProgress
          value={answered}
          max={items.length}
          label="Quiz progress"
        />
        <fieldset className="study-question" key={item.id}>
          <legend>{item.question}</legend>
          {item.options?.map((option, index) => (
            <label
              key={index}
              data-shake={
                choice !== null &&
                chosen === choice &&
                chosen === index &&
                index !== item.correctIndex
              }
              data-result={
                chosen === undefined
                  ? undefined
                  : index === item.correctIndex
                    ? "correct"
                    : chosen === index
                      ? "wrong"
                      : undefined
              }
            >
              <input
                type="radio"
                name="study-answer"
                checked={(chosen ?? choice) === index}
                disabled={chosen !== undefined}
                onChange={() => setChoice(index)}
              />
              <span>{option}</span>
              {chosen !== undefined && index === item.correctIndex && (
                <Check size={18} aria-label="Correct answer" />
              )}
              {chosen === index && index !== item.correctIndex && (
                <X size={18} aria-label="Incorrect answer" />
              )}
            </label>
          ))}
        </fieldset>
        {chosen !== undefined && (
          <div className="study-explanation" role="status">
            <strong>
              {chosen === item.correctIndex ? "Correct" : "Incorrect"}
            </strong>
            <p>{item.answer}</p>
            <SourceChip
              citation={item.citation}
              open={() => onSource(item.citation)}
            />
          </div>
        )}
        <div className="study-actions study-quiz-next">
          {chosen === undefined ? (
            <button
              className="button study-primary"
              disabled={choice === null}
              onClick={() => {
                if (choice === null) return;
                onUpdate((current) => ({
                  ...current,
                  quiz: {
                    ...progress,
                    answers: { ...progress.answers, [item.id]: choice },
                  },
                }));
              }}
            >
              Check answer
            </button>
          ) : (
            <button className="button study-primary" onClick={next}>
              {position + 1 === items.length ? "View results" : "Next question"}{" "}
              <ArrowRight size={16} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
