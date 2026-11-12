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
  studyExcerpt = false,
}: {
  source?: Source;
  evidence?: Evidence;
  workspaceId?: string;
  studyExcerpt?: boolean;
}) {
  const [pageNumber, setPageNumber] = useState(
    evidence?.page ?? source?.pages?.[0]?.page_number ?? 1,
  );
  const localPage = source?.pages?.find((p) => p.page_number === pageNumber);
  const [remotePage, setRemotePage] = useState<
    (DocumentPageRow & { doc_hash?: string }) | null
  >(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const currentVersion =
    !evidence?.docHash ||
    !source?.fileHash ||
    evidence.docHash === source.fileHash;
  const needsRemotePage =
    !localPage &&
    source?.origin === "server" &&
    !!workspaceId &&
    currentVersion;
  const verified =
    evidence?.origin === "server" && isVerified(evidence.verificationStatus);
  useEffect(() => {
    setRemotePage(null);
    setError("");
    if (!needsRemotePage || !source || !workspaceId) return;
    let alive = true;
    getDocumentPage(source.id, pageNumber, workspaceId)
      .then((result) => {
        if (!alive) return;
        if (
          evidence?.docHash &&
          result.doc_hash &&
          evidence.docHash !== result.doc_hash
        )
          throw new Error(
            "The source version changed. The original excerpt is still available.",
          );
        setRemotePage(result);
      })
      .catch((failure) => {
        if (alive)
          setError(
            failure instanceof Error
              ? failure.message
              : "Could not load the source text.",
          );
      });
    return () => {
      alive = false;
    };
  }, [
    source?.id,
    pageNumber,
    workspaceId,
    needsRemotePage,
    retry,
    evidence?.docHash,
  ]);
  const page =
    localPage || (remotePage?.page_number === pageNumber ? remotePage : null);
  const loading = needsRemotePage && !page && !error;
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
            {studyExcerpt
              ? "Study set excerpt"
              : (evidence.verificationStatus?.replaceAll("_", " ") ??
                "Unverified sample excerpt")}
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
        <summary>Document details and verification</summary>
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
            {source.kind.toLowerCase() === "pptx" ? "Slide" : "Document page"}
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
            Text extracted from the document.{" "}
            {source.kind.toLowerCase() === "docx" &&
              "Word documents are stored as one text page, regardless of print pagination."}
          </p>
          {loading && (
            <p role="status" className="window-loading">
              Loading source text…
            </p>
          )}
          {error && (
            <Notice tone="neutral">
              {error}{" "}
              <button
                className="button"
                onClick={() => setRetry((value) => value + 1)}
              >
                Retry
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
