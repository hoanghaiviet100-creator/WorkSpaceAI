import { chatRequest, draftFromServer } from "./api";
import { validRecipient } from "./workflow-model";
import type { Workspace } from "./data";
import type { StudioConfig, StudioResult } from "./notebook-model";

export async function generateStudio(
  workspace: Workspace,
  config: StudioConfig,
): Promise<Pick<StudioResult, "draft" | "content" | "sourceIds">> {
  const selected = workspace.sources.filter(
    (source) =>
      source.selected &&
      source.status === "Processed" &&
      source.origin === "server",
  );
  if (!selected.length)
    throw Error("Select at least one ready source before drafting an email.");
  if (!validRecipient(config.recipient))
    throw Error("Enter a valid recipient email address.");

  const response = await chatRequest(
    `Draft an email about: ${config.goal}. Tone: ${config.tone}. Length: ${config.length}.`,
    selected.map((source) => source.id),
    [],
    config.recipient,
    undefined,
    workspace.id,
    "email",
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
