import { useEffect, useRef, useState } from "react";
import { Monitor, Smartphone } from "lucide-react";
import { Modal } from "./components";

export function DeviceControl({
  onPhone,
  onDesktop,
  phone,
}: {
  onPhone: () => void;
  onDesktop: () => void;
  phone: boolean;
}) {
  return (
    <div className="toolbar-tool device-tool">
      <span className="tool-label">Preview</span>
      <div className="device-control" role="group" aria-label="Layout preview">
        <button
          aria-label="Desktop preview"
          aria-pressed={!phone}
          className={!phone ? "selected" : ""}
          title="Current desktop layout"
          onClick={onDesktop}
        >
          <Monitor size={15} />
          <span>Desktop</span>
        </button>
        <button
          aria-label="Phone preview"
          aria-haspopup="dialog"
          aria-pressed={phone}
          className={phone ? "selected" : ""}
          onClick={onPhone}
        >
          <Smartphone size={15} />
          <span>Phone</span>
        </button>
      </div>
    </div>
  );
}

export default function DevicePreview({
  hash,
  onClose,
}: {
  hash: string;
  onClose: () => void;
}) {
  const frame = useRef<HTMLIFrameElement>(null);
  const [url] = useState(
    () => `${location.pathname}?preview=phone${hash || "#home"}`,
  );
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      if (
        event.origin !== location.origin ||
        event.source !== frame.current?.contentWindow
      )
        return;
      if (
        event.data?.type === "workspaceai:preview-route" &&
        /^#(?:home$|workspace\/)/.test(event.data.hash)
      ) {
        if (location.hash !== event.data.hash) location.hash = event.data.hash;
      }
      if (event.data?.type === "workspaceai:preview-close") closeRef.current();
    };
    const media = matchMedia("(max-width: 640px)");
    const onResize = () => {
      if (media.matches) closeRef.current();
    };
    addEventListener("message", onMessage);
    media.addEventListener("change", onResize);
    return () => {
      removeEventListener("message", onMessage);
      media.removeEventListener("change", onResize);
    };
  }, []);
  useEffect(() => {
    frame.current?.contentWindow?.postMessage(
      { type: "workspaceai:preview-location", hash },
      location.origin,
    );
  }, [hash]);
  return (
    <Modal
      title="Phone preview"
      onClose={onClose}
      className="phone-preview-modal"
    >
      <p className="phone-preview-caption">
        <Smartphone size={14} />
        Live layout <span>390 px wide</span>
      </p>
      <div className="phone-preview-frame">
        <iframe ref={frame} title="WorkspaceAI phone preview" src={url} />
      </div>
      <p className="phone-preview-note">
        The same workspace, adapted for touch.
      </p>
    </Modal>
  );
}
