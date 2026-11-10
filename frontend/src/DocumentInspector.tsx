import { useEffect, useState } from "react";
import type { Source, Evidence } from "./data";
import { Badge, Notice } from "./components";
import { isVerified } from "./schema";
import { getDocumentPage } from "./api";
import type { DocumentPageRow } from "./schema";

export default function DocumentInspector({
  source,
  evidence,
  workspaceId,
}: {
  source?: Source;
  evidence?: Evidence;
  workspaceId?: string;
}) {
  const [pageNumber, setPageNumber] = useState(
    evidence?.page ?? source?.pages?.[0]?.page_number ?? 1,
  );
  const localPage = source?.pages?.find((p) => p.page_number === pageNumber);
  const [remotePage, setRemotePage] = useState<
    (DocumentPageRow & { doc_hash?: string }) | null
  >(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const currentVersion =
    !evidence?.docHash ||
    !source?.fileHash ||
    evidence.docHash === source.fileHash;
  const verified =
    evidence?.origin === "server" && isVerified(evidence.verificationStatus);
  useEffect(() => {
    setRemotePage(null);
    setError("");
    if (
      localPage ||
      !source ||
      source.origin !== "server" ||
      !workspaceId ||
      !currentVersion
    )
      return;
    let alive = true;
    setLoading(true);
    getDocumentPage(source.id, pageNumber, workspaceId)
      .then((result) => {
        if (!alive) return;
        if (
          evidence?.docHash &&
          result.doc_hash &&
          evidence.docHash !== result.doc_hash
        )
          throw new Error(
            "Nguồn đã đổi phiên bản. Đoạn trích cũ vẫn được giữ, không thay bằng văn bản mới.",
          );
        setRemotePage(result);
      })
      .catch((failure) => {
        if (alive)
          setError(
            failure instanceof Error
              ? failure.message
              : "Không tải được văn bản nguồn.",
          );
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [
    source?.id,
    pageNumber,
    workspaceId,
    localPage,
    currentVersion,
    retry,
    evidence?.docHash,
  ]);
  const page = localPage || remotePage;
  return (
    <div className="document-inspector">
      {!currentVersion && (
        <Notice tone="neutral">
          This citation refers to an older version. Its quoted excerpt is kept;
          the current page is not substituted.
        </Notice>
      )}
      <div className="evidence-header">
        <div>
          <strong>
            {source?.name ?? evidence?.file ?? "Unavailable source"}
          </strong>
          <p>{evidence?.context ?? source?.detail}</p>
        </div>
        {evidence && <Badge>{evidence.locator}</Badge>}
      </div>
      {evidence && (
        <>
          <Badge tone={verified ? "document" : "neutral"}>
            {evidence.verificationStatus?.replaceAll("_", " ") ??
              "Unverified sample excerpt"}
          </Badge>
          <h3 className="evidence-title">{evidence.title}</h3>
          <blockquote>
            <mark>{evidence.quote}</mark>
          </blockquote>
          {evidence.matchScore !== undefined && (
            <p className="small">
              Match score: {Math.round(evidence.matchScore * 100)}%
            </p>
          )}
        </>
      )}
      <details className="nb-source-technical">
        <summary>Thông tin tài liệu và xác minh</summary>
        <dl className="document-metadata">
          <dt>Version</dt>
          <dd>{evidence?.docVersion ?? source?.versionId ?? "Unavailable"}</dd>
          <dt>SHA-256</dt>
          <dd>{evidence?.docHash ?? source?.fileHash ?? "Unavailable"}</dd>
          <dt>Size</dt>
          <dd>
            {source?.fileSizeBytes !== undefined
              ? `${source.fileSizeBytes.toLocaleString()} bytes`
              : "Unavailable"}
          </dd>
          <dt>Pages / lines / chunks</dt>
          <dd>
            {source?.totalPages ?? "—"} / {source?.totalLines ?? "—"} /{" "}
            {source?.totalChunks ?? "—"}
          </dd>
          {evidence?.verifiedAt && (
            <>
              <dt>Verified at</dt>
              <dd>{new Date(evidence.verifiedAt).toLocaleString()}</dd>
            </>
          )}
        </dl>
      </details>
      {source &&
      currentVersion &&
      (source.totalPages || source.pages?.length) ? (
        <>
          <label className="document-page-select">
            {source.kind.toLowerCase() === "pptx" ? "Slide" : "Trang văn bản"}
            <select
              aria-label="Document page"
              value={pageNumber}
              onChange={(e) => setPageNumber(Number(e.target.value))}
            >
              {Array.from(
                { length: source.totalPages || source.pages?.length || 1 },
                (_, index) => index + 1,
              ).map((number) => (
                <option key={number} value={number}>
                  {number}
                </option>
              ))}
            </select>
          </label>
          <p className="small muted">
            Văn bản đã trích xuất từ tài liệu.{" "}
            {source.kind.toLowerCase() === "docx" &&
              "Word được lưu thành một trang văn bản, không theo phân trang in."}
          </p>
          {loading && <p role="status">Đang tải văn bản nguồn…</p>}
          {error && (
            <Notice tone="neutral">
              {error}{" "}
              <button
                className="button"
                onClick={() => setRetry((value) => value + 1)}
              >
                Thử lại
              </button>
            </Notice>
          )}
          {page && (
            <ol className="document-lines">
              {page.raw_text.split(/\r?\n/).map((line, index) => (
                <li
                  key={index}
                  data-highlight={
                    pageNumber === evidence?.page &&
                    ((evidence.startLine !== undefined &&
                      index + 1 >= evidence.startLine &&
                      index + 1 <= (evidence.endLine ?? evidence.startLine)) ||
                      (!!evidence.quote &&
                        line.trim().length > 8 &&
                        evidence.quote.includes(line.trim())))
                  }
                >
                  <span>{line || " "}</span>
                </li>
              ))}
            </ol>
          )}
        </>
      ) : (
        <Notice tone="neutral">
          {source?.origin === "sample" || evidence?.origin === "sample"
            ? "This is a sample excerpt. The original document is not loaded or verified."
            : "The original page text is not available in the current API. Only the supplied excerpt and metadata can be shown."}
        </Notice>
      )}
    </div>
  );
}
