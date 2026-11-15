import { chatRequest, draftFromServer } from "./api";
import { validRecipient } from "./workflow-model";
import type { Workspace } from "./data";
import {
  visibleChatMessages,
  type StudioConfig,
  type StudioResult,
} from "./notebook-model";

export async function generateStudio(
  workspace: Workspace,
  config: StudioConfig,
  delivery = false,
): Promise<Pick<StudioResult, "draft" | "content" | "sourceIds">> {
  const selected = workspace.sources.filter(
    (source) =>
      source.selected &&
      source.status === "Processed" &&
      source.origin === "server",
  );
  if (!selected.length && !delivery)
    throw Error("Select at least one ready source before drafting an email.");
  if (!validRecipient(config.recipient))
    throw Error("Enter a valid recipient email address.");

  const thread = workspace.threads[0];
  const history = delivery
    ? visibleChatMessages(workspace, thread)
        .filter(
          (message) => message.state === "answer" && !message.studioResultId,
        )
        .slice(-6)
        .flatMap((message) => [
          { role: "user", content: message.request.slice(0, 1200) },
          {
            role: "assistant",
            content: (
              message.answerText ||
              message.evidenceIds
                .map((id) => workspace.evidence[id]?.finding ?? "")
                .join("\n")
            ).slice(0, 1200),
          },
        ])
    : [];
  const response = await chatRequest(
    delivery
      ? `Draft an email about: ${config.goal.replace(/\s+/g, " ")}\nTone: ${config.tone}. Length: ${config.length}.`
      : `Draft an email about: ${config.goal}. Tone: ${config.tone}. Length: ${config.length}.`,
    selected.map((source) => source.id),
    history,
    config.recipient,
    workspace.id,
    "email",
    delivery,
  );
  if (!response.draft)
    throw Error(
      response.message ||
        "Could not create the draft. Check the recipient and selected sources.",
    );

  const draft = draftFromServer(
    response.draft,
    workspace.threads[0].id,
    workspace,
  );
  const citations = response.draft.citations.join(" ");
  return {
    draft,
    content: draft.body,
    sourceIds: selected
      .filter(
        (source) =>
          citations.includes(source.id) || citations.includes(source.name),
      )
      .map((source) => source.id),
  };
}
