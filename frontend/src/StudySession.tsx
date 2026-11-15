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
  MessageSquare,
  RotateCcw,
  Shuffle,
  ThumbsDown,
  ThumbsUp,
  X,
} from "lucide-react";
import { studyRequest } from "./api";
import type { Source } from "./data";
import {
  quizTopics,
  scoreQuiz,
  shuffled,
  type QuizProgress,
  type QuestionType,
  type StudyCitation,
  type StudyItem,
  type StudySet,
} from "./study-model";

type SessionProps = {
  set: StudySet;
  workspaceId: string;
  sources: Source[];
  expanded: boolean;
  onExpand: () => void;
  onBack: () => void;
  onUpdate: (change: (current: StudySet) => StudySet) => void;
  onSource: (citation: StudyCitation) => void;
  onReview: (items: StudyItem[]) => void;
  onExplain: (prompt: string, sourceIds: string[]) => void;
};

function explanationPrompt(
  question: string,
  chosen: string,
  correct: string,
  draft = false,
  isCorrect = chosen === correct,
) {
  const judgment = !chosen
    ? "Tôi chưa trả lời câu hỏi này."
    : draft
      ? `Tôi đã trả lời: “${chosen}”.`
      : isCorrect
        ? `Tôi đã chọn: “${chosen}”. Đáp án này đúng.`
        : `Tôi đã chọn: “${chosen}”. Đáp án này chưa đúng.`;
  return `Tôi đang làm một bài kiểm tra về tài liệu này và nhận được câu hỏi: “${question}”\n\n${judgment}\n\n${draft ? "Đáp án gợi ý" : "Đáp án đúng"} là: “${correct}”.\n\nHãy dựa vào tài liệu để giải thích vì sao đáp án này phù hợp${chosen && !isCorrect ? " và đáp án của tôi khác ở điểm nào" : ""}.`;
}

function ExplainButton({ onClick }: { onClick: () => void }) {
  return (
    <button type="button" className="button" onClick={onClick}>
      <MessageSquare size={16} /> Explain in chat
    </button>
  );
}

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
            {set.draft ? " · AI draft" : ""}
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
      {set.engine === "f2" ? (
        <ServerPractice {...props} />
      ) : flashcard ? (
        <Flashcards {...props} />
      ) : (
        <Quiz {...props} />
      )}
    </>
  );
}

type ServerRef = {
  doc_id: string;
  doc_hash: string;
  page_number: number;
  start_line: number;
  end_line: number;
  evidence_quote: string;
};
type ServerQuiz = {
  questions: {
    question_id: string;
    question: string;
    kind?: QuestionType;
    options: { option_id: string; text: string }[];
  }[];
};
type ServerResult = {
  correct_count: number;
  total_count: number;
  score_percent: number;
  items: {
    question_id: string;
    selected_option_id: string | null;
    correct_option_id: string | null;
    correct_option_ids?: string[];
    selected_option_ids?: string[];
    expected_text?: string | null;
    is_correct: boolean;
    submitted_text?: string | null;
    explanation: string;
    source_refs: ServerRef[];
  }[];
};
type ServerCard = {
  card_id: string;
  front: string;
  actual_count: number;
  current_index: number;
} & (
  { side: "front" } | { side: "back"; back: string; source_refs: ServerRef[] }
);

function ServerPractice({
  set,
  workspaceId,
  sources,
  onUpdate,
  onSource,
  onExplain,
}: SessionProps) {
  const isQuiz = set.config.kind === "quiz";
  const path = `/${set.config.kind}/${set.sessionId}`;
  const [quiz, setQuiz] = useState<ServerQuiz>();
  const [result, setResult] = useState<ServerResult | null>(null);
  const [checks, setChecks] = useState<
    Record<string, ServerResult["items"][number]>
  >({});
  const [card, setCard] = useState<ServerCard>();
  const cardFace = useRef<HTMLSpanElement>(null);
  const [animateCardFace, setAnimateCardFace] = useState(false);
  const [answers, setAnswers] = useState<Record<string, string | string[]>>({});
  const [position, setPosition] = useState(0);
  const [showScore, setShowScore] = useState(false);
  const submittedAnswers =
    quiz?.questions.flatMap<
      { question_id: string } & (
        { option_id: string } | { option_ids: string[] } | { text: string }
      )
    >(({ question_id, kind }) => {
      const answer = answers[question_id];
      if (Array.isArray(answer))
        return answer.length ? [{ question_id, option_ids: answer }] : [];
      if (!answer?.trim()) return [];
      return [
        kind === "blank" || kind === "short"
          ? { question_id, text: answer.trim() }
          : { question_id, option_id: answer },
      ];
    }) ?? [];
  const allAnswered = !!quiz && submittedAnswers.length === quiz.questions.length;
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  const pending = useRef(false);

  useEffect(() => {
    let active = true;
    setBusy(true);
    setError("");
    const load = async () => {
      try {
        if (isQuiz) {
          const data = await studyRequest<{
            view: ServerQuiz;
            result: ServerResult | null;
          }>(workspaceId, path);
          if (active) {
            setQuiz(data.view);
            setResult(data.result);
          }
        } else {
          const data = await studyRequest<ServerCard>(workspaceId, path);
          if (active) {
            setAnimateCardFace(false);
            setCard(data);
          }
        }
      } catch (err) {
        if (active)
          setError(
            err instanceof Error
              ? err.message
              : "Could not open the study set.",
          );
      } finally {
        if (active) setBusy(false);
      }
    };
    void load();
    return () => {
      active = false;
    };
  }, [isQuiz, path, reload, workspaceId]);

  const update = async (request: () => Promise<void>) => {
    if (pending.current) return;
    pending.current = true;
    setBusy(true);
    setError("");
    try {
      await request();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not update the study set.",
      );
    } finally {
      pending.current = false;
      setBusy(false);
    }
  };

  const citations = (refs: ServerRef[]) =>
    refs.map((ref, index) => {
      const citation = {
        docId: ref.doc_id,
        docHash: ref.doc_hash,
        file:
          sources.find((source) => source.id === ref.doc_id)?.name ??
          ref.doc_id,
        page: ref.page_number,
        startLine: ref.start_line,
        endLine: ref.end_line,
        quote: ref.evidence_quote,
      };
      return (
        <SourceChip
          key={index}
          citation={citation}
          open={() => onSource(citation)}
        />
      );
    });
  const cardAction = (action: "flip" | "previous" | "next") => {
    if (!card) return;
    void update(async () => {
      const next = await studyRequest<ServerCard>(workspaceId, path, {
        action,
        card_id: card.card_id,
      });
      const face = cardFace.current;
      const animate = action === "flip" && next.side !== card.side &&
        !matchMedia("(prefers-reduced-motion: reduce)").matches;
      if (animate && face) {
        const direction = next.side === "back" ? 1 : -1;
        const exit = face.animate(
          [{ transform: "rotateY(0deg)" }, { transform: `rotateY(${direction * 90}deg)` }],
          { duration: 140, easing: "ease-in", fill: "forwards" },
        );
        await exit.finished;
      }
      setAnimateCardFace(Boolean(animate));
      setCard(next);
    });
  };
  const mastered = Object.values(set.mastered ?? {}).filter(Boolean).length;
  const mark = (value: boolean) => {
    if (!card || busy) return;
    onUpdate((current) => ({
      ...current,
      mastered: { ...current.mastered, [card.card_id]: value },
    }));
    if (card.current_index + 1 < card.actual_count) cardAction("next");
  };
  const cardKeys = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (!card || busy || event.altKey || event.ctrlKey || event.metaKey) return;
    if (event.key === "ArrowLeft" && card.current_index > 0) {
      event.preventDefault();
      cardAction("previous");
    } else if (
      event.key === "ArrowRight" &&
      card.current_index + 1 < card.actual_count
    ) {
      event.preventDefault();
      cardAction("next");
    }
  };

  return (
    <div className="study-scroll">
      <div
        onKeyDown={isQuiz ? undefined : cardKeys}
        className={`study-content ${isQuiz ? "study-quiz-layout" : "study-flash-layout"}`}
        aria-busy={busy}
      >
        {set.draft && (
          <p className="study-explanation">
            Sources were checked. Review the AI’s proposed answers against the
            citations.
          </p>
        )}
        {error && (
          <div className="study-explanation">
            <p role="alert">{error}</p>
            <button
              className="button"
              onClick={() => setReload((value) => value + 1)}
            >
              Reload study set
            </button>
          </div>
        )}
        {busy && !quiz && !card && <p role="status">Loading study set…</p>}
        {quiz && (
          <div className="study-server-quiz">
            <div className="study-metadata" role="status">
              <strong>
                {result
                  ? `${result.correct_count}/${result.total_count} ${set.draft ? "match the AI answer key" : "correct"}`
                  : `Question ${position + 1} / ${quiz.questions.length}`}
              </strong>
              <span>{result ? `${result.score_percent}%` : `${submittedAnswers.length} answered`}</span>
            </div>
            <StudyProgress
              value={position + 1}
              max={quiz.questions.length}
              label="Question position"
            />
            {!showScore &&
              quiz.questions.slice(position, position + 1).map((question) => {
                const feedback =
                  result?.items.find(
                    (item) => item.question_id === question.question_id,
                  ) ?? checks[question.question_id];
                const written =
                  question.kind === "blank" || question.kind === "short";
                const multiple = question.kind === "multiple";
                const answer = answers[question.question_id];
                const selectedIds = feedback
                  ? feedback.selected_option_ids?.length
                    ? feedback.selected_option_ids
                    : [feedback.selected_option_id]
                  : Array.isArray(answer)
                    ? answer
                    : [answer];
                const correctIds = feedback?.correct_option_ids?.length
                  ? feedback.correct_option_ids
                  : [feedback?.correct_option_id];
                return (
                  <div key={question.question_id}>
                    <fieldset
                      className="study-question"
                      disabled={busy || !!feedback || !!result}
                    >
                      <legend>{question.question}</legend>
                      {written ? (
                        <input
                          className="study-written-answer"
                          type="text"
                          maxLength={500}
                          aria-label={
                            question.kind === "blank"
                              ? "Fill in the blank"
                              : "Short answer"
                          }
                          placeholder={
                            question.kind === "blank"
                              ? "Complete the blank"
                              : "Write a short answer"
                          }
                          value={
                            feedback
                              ? (feedback.submitted_text ?? "")
                              : typeof answer === "string"
                                ? answer
                                : ""
                          }
                          onChange={(event) => {
                            const text = event.target.value;
                            setAnswers((current) => ({
                              ...current,
                              [question.question_id]: text,
                            }));
                          }}
                        />
                      ) : (
                        question.options.map((option, index) => (
                          <label
                            key={option.option_id}
                            data-result={
                              feedback && correctIds.includes(option.option_id)
                                ? "correct"
                                : feedback &&
                                    selectedIds.includes(option.option_id)
                                  ? "wrong"
                                  : undefined
                            }
                            data-graded={!!feedback}
                          >
                            <input
                              type={multiple ? "checkbox" : "radio"}
                              name={question.question_id}
                              checked={selectedIds.includes(option.option_id)}
                              onChange={() =>
                                setAnswers((current) => ({
                                  ...current,
                                  [question.question_id]: multiple
                                    ? selectedIds.includes(option.option_id)
                                      ? selectedIds.filter(
                                          (id): id is string =>
                                            typeof id === "string" &&
                                            id !== option.option_id,
                                        )
                                      : [
                                          ...selectedIds.filter(
                                            (id): id is string =>
                                              typeof id === "string",
                                          ),
                                          option.option_id,
                                        ]
                                    : option.option_id,
                                }))
                              }
                            />
                            <span>
                              <small className="study-option-letter">
                                {String.fromCharCode(65 + index)}.
                              </small>{" "}
                              {option.text}
                              {feedback &&
                                (correctIds.includes(option.option_id) ||
                                  selectedIds.includes(option.option_id)) && (
                                  <small className="study-option-feedback">
                                    {correctIds.includes(option.option_id)
                                      ? set.draft
                                        ? "Suggested answer"
                                        : "Correct answer"
                                      : "Your answer · Incorrect"}
                                    {correctIds.includes(option.option_id) && (
                                      <span>{feedback.explanation}</span>
                                    )}
                                  </small>
                                )}
                            </span>
                            {feedback &&
                              correctIds.includes(option.option_id) && (
                                <Check
                                  size={18}
                                  aria-label={
                                    set.draft
                                      ? "AI-proposed answer"
                                      : "Correct answer"
                                  }
                                />
                              )}
                          </label>
                        ))
                      )}
                      {feedback && written && (
                        <div className="study-explanation">
                          <strong>
                            {feedback.is_correct
                              ? "Matches the answer key"
                              : "Does not match the answer key"}
                          </strong>
                          {written && (
                            <p>Suggested answer: {feedback.expected_text}</p>
                          )}
                          <p>{feedback.explanation}</p>
                        </div>
                      )}
                    </fieldset>
                    {!feedback && !result && (
                      <button
                        type="button"
                        className="button study-primary study-check-answer"
                        disabled={
                          busy ||
                          !submittedAnswers.some(
                            (item) => item.question_id === question.question_id,
                          )
                        }
                        onClick={() => {
                          const answer = submittedAnswers.find(
                            (item) => item.question_id === question.question_id,
                          );
                          if (!answer) return;
                          void update(async () => {
                            const checked = await studyRequest<
                              ServerResult["items"][number]
                            >(workspaceId, `${path}/check`, {
                              answers: [answer],
                            });
                            setChecks((current) => ({
                              ...current,
                              [question.question_id]: checked,
                            }));
                          });
                        }}
                      >
                        Check answer
                      </button>
                    )}
                    {feedback && (
                      <>
                        {!written && (
                          <p
                            className="study-quiz-verdict"
                            role="status"
                            data-correct={feedback.is_correct}
                          >
                            {feedback.is_correct
                              ? set.draft
                                ? "Matches the AI answer key"
                                : "Correct"
                              : set.draft
                                ? "Does not match the AI answer key"
                                : "Incorrect"}
                          </p>
                        )}
                        {citations(feedback.source_refs)}
                        <div className="study-actions study-explain-actions">
                          <ExplainButton
                            onClick={() => {
                              const answerText = (
                                ids: (string | null | undefined)[],
                              ) =>
                                question.options
                                  .filter((option) =>
                                    ids.includes(option.option_id),
                                  )
                                  .map((option) => option.text)
                                  .join("; ");
                              onExplain(
                                explanationPrompt(
                                  question.question,
                                  written
                                    ? (feedback.submitted_text ?? "")
                                    : answerText(selectedIds),
                                  written
                                    ? (feedback.expected_text ?? "")
                                    : answerText(correctIds),
                                  set.draft,
                                  feedback.is_correct,
                                ),
                                feedback.source_refs.length
                                  ? feedback.source_refs.map((ref) => ref.doc_id)
                                  : set.config.sourceIds,
                              );
                            }}
                          />
                        </div>
                      </>
                    )}
                  </div>
                );
              })}
            <div className="study-actions study-server-navigation">
              {showScore ? (
                <button
                  type="button"
                  className="button"
                  onClick={() => {
                    setShowScore(false);
                    setPosition(0);
                  }}
                >
                  Review answers
                </button>
              ) : (
                <>
                  <button
                    type="button"
                    className="button"
                    disabled={position === 0 || busy}
                    onClick={() => setPosition(position - 1)}
                  >
                    Previous
                  </button>
                  <span>
                    {position + 1} / {quiz.questions.length}
                  </span>
                  {position + 1 < quiz.questions.length ? (
                    <button
                      type="button"
                      className="button study-primary"
                      disabled={busy}
                      onClick={() => setPosition(position + 1)}
                    >
                      Next question <ArrowRight size={16} />
                    </button>
                  ) : result ? (
                    <button
                      type="button"
                      className="button study-primary"
                      onClick={() => setShowScore(true)}
                    >
                      View score
                    </button>
                  ) : (
                    <>
                    {!allAnswered && <span className="study-shortcuts" role="status">
                      Answer every question before submitting.
                    </span>}
                    <button
                      className="button study-primary"
                      type="button"
                      disabled={busy || !allAnswered}
                      onClick={() => {
                        if (!allAnswered) return;
                        void update(async () => {
                          const graded = await studyRequest<ServerResult>(
                            workspaceId, path, { answers: submittedAnswers },
                          );
                          setResult(graded);
                          setPosition(0);
                          if (!set.draft)
                            onUpdate((current) => ({
                              ...current,
                              lastScore: {
                                correct: graded.correct_count,
                                total: graded.total_count,
                                completedAt: new Date().toISOString(),
                              },
                            }));
                        });
                      }}
                    >
                      Submit quiz
                    </button>
                    </>
                  )}
                </>
              )}
            </div>
          </div>
        )}
        {card && (
          <>
            <div className="study-metadata">
              <strong>
                Card {card.current_index + 1} / {card.actual_count}
              </strong>
              <span>
                {mastered}/{card.actual_count} mastered
              </span>
            </div>
            <StudyProgress
              value={mastered}
              max={card.actual_count}
              label="Cards mastered"
            />
            <div className="study-card-layout">
              <button
                className="button"
                aria-label="Previous card"
                onClick={() => cardAction("previous")}
                disabled={busy || card.current_index === 0}
              >
                <ArrowLeft size={18} />
              </button>
              <button
                className="study-server-card"
                onClick={() => cardAction("flip")}
                disabled={busy}
              >
                <span
                  key={`${card.card_id}:${card.side}`}
                  ref={cardFace}
                  className="study-server-card-face"
                  data-entering={animateCardFace}
                  data-side={card.side}
                >
                  <strong>
                    {card.side === "front" ? card.front : card.back}
                  </strong>
                  <span className="study-flip-hint">
                    <RotateCcw size={15} />{" "}
                    {card.side === "front"
                      ? "Flip to see answer"
                      : "Back to question"}
                  </span>
                </span>
              </button>
              <button
                className="button"
                aria-label="Next card"
                onClick={() => cardAction("next")}
                disabled={busy || card.current_index + 1 === card.actual_count}
              >
                <ArrowRight size={18} />
              </button>
            </div>
            {card.side === "back" && citations(card.source_refs)}
            <div className="study-actions study-card-nav">
              <button
                type="button"
                className="button study-primary"
                disabled={busy}
                aria-pressed={set.mastered?.[card.card_id] === true}
                onClick={() => mark(true)}
              >
                <ThumbsUp size={18} /> Mastered
              </button>
              <button
                type="button"
                className="button"
                disabled={busy}
                aria-pressed={set.mastered?.[card.card_id] === false}
                onClick={() => mark(false)}
              >
                <ThumbsDown size={18} /> Needs review
              </button>
            </div>
            <p className="study-shortcuts">
              Select the card to flip it. With a card control focused, use{" "}
              <kbd>Space</kbd> to activate it or <kbd>←</kbd> <kbd>→</kbd> to
              change cards.
            </p>
          </>
        )}
      </div>
    </div>
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
      <div className="study-content study-flash-layout">
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
        <div className="study-card-layout">
          <button
            className="button"
            aria-label="Previous card"
            onClick={() => move(-1)}
            disabled={!item || index === 0}
          >
            <ArrowLeft size={18} />
          </button>
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
          <button
            className="button"
            aria-label="Next card"
            onClick={() => move(1)}
            disabled={!item || index === visible.length - 1}
          >
            <ArrowRight size={18} />
          </button>
        </div>
        {item && (
          <>
            <SourceChip
              citation={item.citation}
              open={() => onSource(item.citation)}
            />
            <div className="study-actions study-card-nav">
              <button
                className="button study-primary"
                onClick={() => mark(true)}
              >
                <ThumbsUp size={18} /> Mastered
              </button>
              <button className="button" onClick={() => mark(false)}>
                <ThumbsDown size={18} /> Needs review
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

function Quiz({ set, onUpdate, onSource, onReview, onExplain }: SessionProps) {
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
                  <ExplainButton
                    onClick={() =>
                      onExplain(
                        explanationPrompt(
                          question.question,
                          question.options?.[progress.answers[question.id]] ??
                            "",
                          question.options?.[question.correctIndex ?? -1] ??
                            question.answer,
                        ),
                        [question.citation.docId],
                      )
                    }
                  />
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
      <div className="study-content study-quiz-layout">
        <div className="study-metadata">
          <strong>
            Question {position + 1} / {items.length}
          </strong>
          <span>{answered} answered</span>
        </div>
        <StudyProgress
          value={position + 1}
          max={items.length}
          label="Question position"
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
              <span>
                <small className="study-option-letter">
                  {String.fromCharCode(65 + index)}.
                </small>{" "}
                {option}
                {chosen !== undefined &&
                  (chosen === index || index === item.correctIndex) && (
                    <small className="study-option-feedback">
                      {index === item.correctIndex
                        ? "Correct answer"
                        : "Your answer · Incorrect"}
                      {index === item.correctIndex && (
                        <span>{item.answer}</span>
                      )}
                    </small>
                  )}
              </span>
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
            <>
              <ExplainButton
                onClick={() =>
                  onExplain(
                    explanationPrompt(
                      item.question,
                      item.options?.[chosen] ?? "",
                      item.options?.[item.correctIndex ?? -1] ?? item.answer,
                    ),
                    [item.citation.docId],
                  )
                }
              />
              <button className="button study-primary" onClick={next}>
                {position + 1 === items.length
                  ? "View results"
                  : "Next question"}{" "}
                <ArrowRight size={16} />
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
