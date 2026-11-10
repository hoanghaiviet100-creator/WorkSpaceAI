import { chatRequest, draftFromServer } from "./api";
import { isVerified } from "./schema";
import { resolveCitedSource, validRecipient } from "./workflow-model";
import type { Evidence, Workspace, Suggestion } from "./data";
import type { StudioConfig, StudioResult } from "./notebook-model";

/** Studio generation reuses the existing guarded document/email API. It never sends email. */
export async function generateStudio(
  workspace: Workspace,
  config: StudioConfig,
  resultId: string,
) {
  const selected = workspace.sources.filter(
    (source) =>
      source.selected &&
      source.status === "Processed" &&
      source.origin === "server",
  );
  if (!selected.length)
    throw Error("Chọn ít nhất một nguồn đã sẵn sàng trước khi tạo kết quả.");
  if (config.kind === "email" && !validRecipient(config.recipient))
    throw Error("Nhập một địa chỉ email người nhận hợp lệ.");
  const query =
    config.kind === "plan"
      ? `Find source-supported requirements and next actions for this study goal: ${config.goal}`
      : `Draft an email about: ${config.goal}. Tone: ${config.tone}. Length: ${config.length}.`;
  const response = await chatRequest(
    query,
    selected.map((source) => source.id),
    [],
    config.kind === "email" ? config.recipient : undefined,
    new Date().toLocaleDateString("en-CA"),
    workspace.id,
    config.kind,
  );
  const evidence: Record<string, Evidence> = {};
  if (config.kind === "email") {
    if (!response.draft)
      throw Error(
        response.message ||
          "Chưa tạo được bản nháp. Kiểm tra người nhận và nguồn đã chọn.",
      );
    const draft = draftFromServer(
      response.draft,
      workspace.threads[0].id,
      workspace,
    );
    const citations = response.draft.citations.join(" ");
    const sourceIds = selected
      .filter(
        (source) =>
          citations.includes(source.id) || citations.includes(source.name),
      )
      .map((source) => source.id);
    return {
      evidence,
      patch: {
        draft,
        content: draft.body,
        sourceIds,
        evidenceIds: [],
      } as Partial<StudioResult>,
    };
  }
  const maximum =
    config.detail === "concise" ? 3 : config.detail === "detailed" ? 8 : 5;
  const suggestions: Suggestion[] = [];
  for (const claim of response.validated_claims ?? []) {
    const source = resolveCitedSource(claim.cited_doc_id, selected);
    if (
      !source ||
      !isVerified(claim.verification_status) ||
      (claim.doc_hash && source.fileHash && claim.doc_hash !== source.fileHash)
    )
      continue;
    const id = `${resultId}-e${suggestions.length + 1}`;
    evidence[id] = {
      id: source.id,
      file: source.name,
      title: "Nội dung có trong nguồn",
      finding: claim.claim_text,
      quote: claim.evidence_quote,
      context: "Trích dẫn đã kiểm tra",
      locator: `${source.kind.toLowerCase() === "pptx" ? "Slide" : "Trang"} ${claim.cited_page}`,
      page: claim.cited_page,
      startLine: claim.cited_start_line ?? undefined,
      endLine: claim.cited_end_line ?? undefined,
      verificationStatus: claim.verification_status,
      matchScore: claim.match_score ?? undefined,
      docHash: claim.doc_hash ?? undefined,
      docVersion: claim.doc_version ?? undefined,
      origin: "server",
    };
    suggestions.push({
      id: `${resultId}-task${suggestions.length + 1}`,
      title: `Rà soát: ${claim.claim_text.slice(0, 110)}`,
      description: claim.claim_text,
      owner: "",
      due: "",
      status: "TODO",
      selected: true,
      source: id,
      threadId: workspace.threads[0].id,
      completionPct: 0,
    });
    if (suggestions.length >= maximum) break;
  }
  if (!suggestions.length)
    throw Error(
      response.message ||
        "Nguồn đã chọn chưa đủ bằng chứng cho mục tiêu này. Hãy bổ sung nguồn hoặc chỉnh mục tiêu.",
    );
  const sourceIds = [
    ...new Set(Object.values(evidence).map((entry) => entry.id)),
  ];
  const content =
    `# ${config.title || "Kế hoạch học tập"}\n\nMục tiêu: ${config.goal}\nThời gian dự kiến: ${config.timeframe}\n\n` +
    suggestions
      .map(
        (suggestion, index) =>
          `${index + 1}. ${suggestion.title}\n   ${suggestion.description}`,
      )
      .join("\n\n") +
    "\n\nCác bước trên là đề xuất dựa trên nguồn. Xác nhận trong bảng công việc để tạo task; người phụ trách và hạn chính thức vẫn để trống.";
  return {
    evidence,
    patch: {
      content,
      suggestions,
      sourceIds,
      evidenceIds: Object.keys(evidence),
    } as Partial<StudioResult>,
  };
}
