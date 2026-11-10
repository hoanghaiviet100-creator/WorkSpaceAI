import { useEffect, useState } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  CalendarDays,
  ChevronDown,
  FileText,
  MessageSquare,
  Paperclip,
  CheckCheck,
} from "lucide-react";
import type { Workspace, View } from "./data";
import {
  activityLabel,
  conversationSources,
  dashboardData,
  workspaceColor,
} from "./home-model";

type Dashboard = ReturnType<typeof dashboardData>;
type Open = (workspaceId: string, threadId?: string, view?: View) => void;

export function HomeMetrics({ data }: { data: Dashboard }) {
  return (
    <section className="home-metrics" aria-label="Workspace overview">
      {[
        {
          label: "Open tasks",
          value: data.open,
          note: "To-do, in progress & review",
        },
        {
          label: "In progress",
          value: data.inProgress,
          note: "Currently being worked on",
        },
        {
          label: "Completed",
          value: data.done,
          note: "Tasks marked as done",
        },
        {
          label: "Documents",
          value: data.documents,
          note: "Across the selected scope",
        },
      ].map((metric) => (
        <div className="home-metric" key={metric.label}>
          <span>{metric.label}</span>
          <strong>{metric.value.toLocaleString("en-US")}</strong>
          <small>{metric.note}</small>
        </div>
      ))}
    </section>
  );
}

export function HomeAssistant({
  data,
  target,
  workspaces,
  choose,
  start,
  open,
  create,
}: {
  data: Dashboard;
  target?: Workspace;
  workspaces: Workspace[];
  choose: (id: string) => void;
  start: (id: string, prompt?: string) => void;
  open: Open;
  create: () => void;
}) {
  const [phone, setPhone] = useState(
    () => matchMedia("(max-width: 640px)").matches,
  );
  useEffect(() => {
    const media = matchMedia("(max-width: 640px)");
    const change = () => setPhone(media.matches);
    media.addEventListener("change", change);
    return () => media.removeEventListener("change", change);
  }, []);
  const [prompt, setPrompt] = useState("");
  const resume = data.resume;
  const message = resume?.thread.messages.at(-1);
  const trail = resume
    ? conversationSources(resume.workspace, resume.thread)
    : null;
  const text =
    message?.answerText ||
    (resume && message?.state === "answer"
      ? message.evidenceIds
          .map((id) => resume.workspace.evidence[id]?.finding)
          .filter(Boolean)
          .slice(0, 2)
          .join("\n\n")
      : "");
  const preview =
    message?.state === "error"
      ? message.errorText || "This question could not be completed."
      : message?.state === "abstention"
        ? "There wasn't enough evidence in the selected sources. Open the conversation to review its sources."
        : text ||
          "Open this conversation to review the saved response and its sources.";
  const composer = (
    <div className="home-compose-region">
      <div className="home-question-starters" aria-label="Question starters">
        {["Summarize my documents", "What should I work on next?"].map(
          (question) => (
            <button key={question} onClick={() => setPrompt(question)}>
              {question}
              <ArrowUpRight size={13} />
            </button>
          ),
        )}
      </div>
      <form
        className="home-question-composer"
        onSubmit={(event) => {
          event.preventDefault();
          if (target && prompt.trim()) start(target.id, prompt.trim());
        }}
      >
        <label className="sr-only" htmlFor="home-question-input">
          Ask about your documents
        </label>
        <textarea
          id="home-question-input"
          rows={2}
          maxLength={4000}
          placeholder={
            target
              ? "What would you like to explore in your documents?"
              : "Create a workspace to ask your first question"
          }
          value={prompt}
          disabled={!target}
          onChange={(event) => setPrompt(event.target.value)}
        />
        <div className="home-composer-footer">
          <label className="home-composer-workspace">
            <Paperclip size={15} />
            <span className="sr-only">Workspace for your question</span>
            <select
              aria-label="Workspace for your question"
              value={target?.id ?? ""}
              disabled={!workspaces.length}
              onChange={(event) => choose(event.target.value)}
            >
              {!workspaces.length && <option value="">No workspace yet</option>}
              {workspaces.map((workspace) => (
                <option value={workspace.id} key={workspace.id}>
                  {workspace.name}
                </option>
              ))}
            </select>
            <ChevronDown size={13} />
          </label>
          <button
            type="submit"
            className="home-question-submit"
            disabled={!target || !prompt.trim()}
            aria-label="Continue in chat"
            title="Continue in chat"
          >
            <ArrowRight size={18} />
          </button>
        </div>
      </form>
      <p className="home-composer-note">
        Your question opens in chat, ready for you to review and send.
      </p>
    </div>
  );
  return (
    <section
      className="home-assistant home-panel"
      aria-labelledby="assistant-title"
    >
      <header className="home-panel-heading">
        <div className="home-assistant-title">
          <BookOpen size={19} />
          <h2 id="assistant-title">Research assistant</h2>
        </div>
        <span className="home-local-label">Your documents, in context</span>
      </header>
      <div className="home-assistant-body">
        {phone && composer}
        {resume && message ? (
          <>
            <div className="home-resume-label">
              <span>Pick up where you left off</span>
              <time dateTime={resume.thread.updated}>
                {activityLabel(resume.thread.updated)}
              </time>
            </div>
            <div className="home-question">
              <span>Your last question</span>
              <p>{message.request}</p>
            </div>
            <div className="home-saved-response">
              <div className="home-answer-mark">
                <BookOpen size={18} />
              </div>
              <div className="home-answer-content">
                <div className="home-answer-heading">
                  <strong>WorkspaceAI</strong>
                  <span>
                    {message.origin === "sample"
                      ? "Sample conversation"
                      : "Saved response"}
                  </span>
                </div>
                <p className="home-answer-excerpt">
                  {preview
                    .split(/(\*\*[^*\n]+\*\*)/g)
                    .map((part, index) =>
                      part.startsWith("**") && part.endsWith("**") ? (
                        <strong key={index}>{part.slice(2, -2)}</strong>
                      ) : (
                        part
                      ),
                    )}
                </p>
                {!!trail?.sources.length && (
                  <div className="home-answer-sources">
                    {trail.sources.slice(0, 2).map((source) => (
                      <span key={source.id} title={source.name}>
                        <FileText size={13} />
                        {source.name}
                      </span>
                    ))}
                    {trail.sources.length > 2 && (
                      <span>+{trail.sources.length - 2} files</span>
                    )}
                  </div>
                )}
                <button
                  className="home-text-action"
                  onClick={() =>
                    open(resume.workspace.id, resume.thread.id, "chat")
                  }
                >
                  Continue this conversation
                  <ArrowRight size={15} />
                </button>
              </div>
            </div>
          </>
        ) : (
          <div className="home-first-question">
            <BookOpen size={28} />
            <h3>Start with your documents.</h3>
            <p>
              Add your course notes, project brief or reading material. Then ask
              a question with the sources beside the answer.
            </p>
            <button
              className="home-text-action"
              onClick={() =>
                target ? open(target.id, undefined, "chat") : create()
              }
            >
              {target
                ? "Open workspace & add sources"
                : "Create your first workspace"}
              <ArrowRight size={15} />
            </button>
          </div>
        )}
        {!phone && composer}
      </div>
    </section>
  );
}

export function HomeInsights({
  data,
  open,
  onHistory,
  onWorkspaces,
  onTasks,
}: {
  data: Dashboard;
  open: Open;
  onHistory: () => void;
  onWorkspaces: () => void;
  onTasks: () => void;
}) {
  return (
    <aside
      className="home-insights"
      aria-label="Workspace activity and deadlines"
    >
      <section
        className="home-panel home-deadlines"
        aria-labelledby="deadlines-title"
      >
        <header className="home-panel-heading">
          <h2 id="deadlines-title">
            <CalendarDays size={16} />
            Task deadlines
          </h2>
          <button aria-label="View tasks" onClick={onTasks}>
            <ArrowUpRight size={15} />
          </button>
        </header>
        <p className="home-panel-caption">
          {data.overdue
            ? `${data.overdue} ${data.overdue === 1 ? "task needs" : "tasks need"} a deadline review`
            : "Next dates in your task list"}
        </p>
        <div className="home-deadline-list">
          {data.deadlines.slice(0, 3).map(({ workspace, task, overdue }) => {
            const date = new Date(`${task.due}T12:00:00Z`);
            return (
              <button
                className="home-deadline-row"
                key={`${workspace.id}:${task.id}`}
                onClick={() => open(workspace.id, undefined, "tasks")}
              >
                <time dateTime={task.due}>
                  <span>
                    {date.toLocaleDateString("en-US", {
                      month: "short",
                      timeZone: "Asia/Bangkok",
                    })}
                  </span>
                  <strong>{date.getUTCDate()}</strong>
                </time>
                <span>
                  <strong>{task.title}</strong>
                  <small>
                    {overdue
                      ? "Overdue"
                      : task.due === data.today
                        ? "Due today"
                        : workspace.name}
                  </small>
                </span>
              </button>
            );
          })}
        </div>
        {!data.deadlines.length && (
          <p className="home-small-empty">
            No dated tasks yet. Add a deadline in your task board.
          </p>
        )}
      </section>
      <section
        className="home-panel home-progress"
        aria-labelledby="progress-title"
      >
        <header className="home-panel-heading">
          <h2 id="progress-title">
            <CheckCheck size={16} />
            Workspace progress
          </h2>
          <button onClick={onWorkspaces} aria-label="Choose a workspace">
            <ArrowUpRight size={15} />
          </button>
        </header>
        <p className="home-panel-caption">
          Completed tasks · local task boards
        </p>
        {data.progress
          .slice(0, 3)
          .map(({ workspace, complete, total, percent }) => (
            <button
              className="home-progress-row workspace-identity"
              data-workspace-color={workspaceColor(workspace)}
              key={workspace.id}
              onClick={() => open(workspace.id, undefined, "tasks")}
            >
              <span>
                <strong>{workspace.name}</strong>
                <small>{percent === null ? "—" : `${percent}%`}</small>
              </span>
              <span className="home-progress-track" aria-hidden="true">
                <span style={{ width: `${percent ?? 0}%` }} />
              </span>
              <span className="home-progress-detail">
                {total
                  ? `${complete} of ${total} tasks completed`
                  : "No tasks yet"}
              </span>
            </button>
          ))}
        {!data.progress.length && (
          <p className="home-small-empty">
            Create a workspace to organize your work.
          </p>
        )}
      </section>
      <section
        className="home-panel home-activity"
        aria-labelledby="activity-title"
      >
        <header className="home-panel-heading">
          <h2 id="activity-title">
            <MessageSquare size={16} />
            Recent conversations
          </h2>
          <button onClick={onHistory} aria-label="View all conversations">
            <ArrowUpRight size={15} />
          </button>
        </header>
        {data.recent.slice(0, 2).map(({ workspace, thread }) => (
          <button
            className="home-activity-row"
            key={`${workspace.id}:${thread.id}`}
            title={thread.title}
            onClick={() => open(workspace.id, thread.id, "chat")}
          >
            <span
              className="workspace-identity"
              data-workspace-color={workspaceColor(workspace)}
            >
              <span className="workspace-dot" />
            </span>
            <span>
              <strong>{thread.title}</strong>
              <small>
                {activityLabel(thread.updated)} · {workspace.name}
              </small>
            </span>
          </button>
        ))}
        {!data.recent.length && (
          <p className="home-small-empty">
            Your conversations will appear here.
          </p>
        )}
      </section>
    </aside>
  );
}
