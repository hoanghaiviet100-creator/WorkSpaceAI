import { apiFor, getDocumentPage } from "./api";
import type { Workspace } from "./data";
import {
  explicitDate,
  id,
  initialColumns,
  newCard,
  localDay,
  workspaceBoard,
  type KanbanProposal,
} from "./kanban-model";

/** Deterministic Offline suggestions. No LLM/API key: source text and chat remain on this device. */
export async function suggestKanban(
  workspace: Workspace,
  demo = false,
  progress: (text: string) => void = () => {},
): Promise<KanbanProposal> {
  const board = workspaceBoard(workspace),
    columns = board?.columns || initialColumns();
  const proposal: KanbanProposal = {
    id: id(),
    boardId: board?.id,
    name: `Kế hoạch · ${workspace.name}`,
    mode: board ? "append" : "initial",
    columns: columns.map((col) => ({ ...col, selected: true })),
    cards: [],
    engine: demo ? "demo" : "offline",
    contextNote: "",
    sourceIds: [],
  };
  const existing = new Set(
    board?.cards.map((card) => card.title.trim().toLocaleLowerCase()) || [],
  );
  const add = (
    title: string,
    description: string,
    sourceIds: string[],
    taskId?: string,
    due = "",
    status = "TODO",
    manual = false,
  ) => {
    const clean = title
      .replace(/^\s*(?:[-*•]\s+|\d+[.)]\s+)/, "")
      .trim()
      .slice(0, 160);
    if (
      !clean ||
      existing.has(clean.toLocaleLowerCase()) ||
      proposal.cards.some(
        (card) => card.title.toLocaleLowerCase() === clean.toLocaleLowerCase(),
      ) ||
      proposal.cards.length >= 12
    )
      return;
    const column = columns.find((col) => col.status === status) || columns[0];
    proposal.cards.push({
      ...newCard(column.id, clean, manual ? "manual" : "ai"),
      description,
      sourceIds,
      taskId: taskId || `kanban-${id()}`,
      dueDate: due || explicitDate(description),
      selected: true,
    });
  };
  if (demo) {
    const titles = [
      "Đọc đề bài và ghi lại yêu cầu",
      "Lập dàn ý báo cáo",
      "Đối chiếu các mốc nộp bài",
      "Chuẩn bị câu hỏi cho giảng viên",
      "Hoàn thiện bản nháp báo cáo",
      "Rà soát trích dẫn tài liệu",
      "Tổng hợp tài liệu đầu vào",
      "Thống nhất phân công nhóm",
    ];
    titles.forEach((title, index) => {
      add(
        title,
        "Dữ liệu mẫu minh họa thao tác Kanban. Không phải kết luận từ tài liệu của bạn.",
        [],
        undefined,
        "",
        index < 4 ? "TODO" : index < 6 ? "IN_PROGRESS" : "DONE",
        index === 1 || index === 7,
      );
      const card = proposal.cards.at(-1)!;
      card.priority = index === 2 ? "high" : index === 4 ? "medium" : "none";
      card.labels = [
        {
          name: index === 2 ? "Cần xác minh" : "Báo cáo",
          tone: index === 2 ? "rose" : "teal",
        },
      ];
      if (index === 3) card.kind = "event";
      if (index === 0 || index === 2 || index === 4) {
        const sampleDate = new Date();
        sampleDate.setDate(
          sampleDate.getDate() + (index === 2 ? -1 : index === 0 ? 2 : 5),
        );
        card.dueDate = localDay(sampleDate);
      }
      if (index === 4)
        card.checklist = [
          { id: id(), text: "Hoàn thiện nội dung", done: true },
          { id: id(), text: "Kiểm tra nguồn trích", done: false },
        ];
    });
    proposal.contextNote =
      "Bảng mẫu gồm 8 thẻ để thử thao tác. Nội dung và ngày trong bản mẫu chỉ minh họa, không lấy từ tài liệu thật của bạn.";
    return proposal;
  }
  progress("Đang đọc công việc và hội thoại của workspace…");
  for (const task of workspace.tasks.filter(
    (task) =>
      !task.archived && !board?.cards.some((card) => card.taskId === task.id),
  )) {
    add(
      task.title,
      task.description,
      [],
      task.id,
      explicitDate(task.due),
      task.status,
      true,
    );
  }
  const selected = workspace.sources.filter(
    (source) =>
      source.selected &&
      source.status === "Processed" &&
      source.origin !== "sample",
  );
  const inputs: { text: string; sourceIds: string[] }[] = [];
  for (const source of selected.slice(0, 8)) {
    progress(
      `Đang đọc nguồn ${inputs.length + 1}/${Math.min(selected.length, 8)}: ${source.name}`,
    );
    let text = source.pages?.map((page) => page.raw_text).join("\n") || "";
    if (!text && source.origin === "server" && apiFor(workspace.id)) {
      const page = await getDocumentPage(source.id, 1, workspace.id);
      text = page.raw_text;
    }
    if (text.trim()) {
      inputs.push({ text, sourceIds: [source.id] });
      proposal.sourceIds.push(source.id);
    }
  }
  for (const message of workspace.threads[0]?.messages.slice(-20) || []) {
    if (
      message.origin === "sample" ||
      message.kanbanEvent ||
      message.studioResultId
    )
      continue;
    if (message.request.trim())
      inputs.push({ text: message.request, sourceIds: [] });
    if (message.answerText?.trim())
      inputs.push({
        text: message.answerText,
        sourceIds: message.sourceIds.filter((sourceId) =>
          selected.some((source) => source.id === sourceId),
        ),
      });
  }
  progress("Đang chọn các gợi ý để bạn xem lại…");
  for (const input of inputs) {
    for (const line of input.text.split(/\n+|(?<=[.!?])\s+/).slice(0, 250)) {
      if (
        line.trim().length < 16 ||
        !/(cần |nộp|hoàn thành|chuẩn bị|rà soát|kiểm tra|báo cáo|yêu cầu|lên kế hoạch|must |submit|review|prepare|complete|deadline|requirement|report|meeting|due\b)/iu.test(
          line,
        )
      )
        continue;
      add(line, line.trim().slice(0, 2000), input.sourceIds);
    }
  }
  if (!proposal.cards.length)
    throw Error(
      board
        ? "Chưa tìm thấy công việc mới. Bổ sung nguồn hoặc trao đổi thêm trong hội thoại rồi thử lại; bạn vẫn có thể thêm thẻ thủ công."
        : "Chưa đủ nội dung để gợi ý. Chọn nguồn đã xử lý, trao đổi mục tiêu trong Chat hoặc mở bản mẫu để thử giao diện.",
    );
  proposal.contextNote = `Offline đọc trang đầu của tối đa 8 nguồn đã chọn, nội dung công việc hiện có và 20 trao đổi gần nhất. Gợi ý theo quy tắc, chưa có mô hình AI sinh nội dung. Hạn chót chỉ lấy ngày có đủ ngày, tháng và năm được ghi rõ; hãy kiểm tra lại trước khi xác nhận.`;
  return proposal;
}
