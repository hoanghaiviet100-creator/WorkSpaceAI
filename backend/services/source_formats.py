"""Optional source adapters. I/O stays in services; R2 algorithms remain pure stdlib."""
import io
import ipaddress
import posixpath
import re
import socket
import zipfile
from html.parser import HTMLParser
from urllib.parse import unquote, urljoin, urlsplit
from xml.etree import ElementTree as ET
import httpx

MAX_SOURCE_BYTES = 25 * 1024 * 1024
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def _office_archive(content: bytes) -> zipfile.ZipFile:
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
        if len(archive.infolist()) > 10000 or sum(item.file_size for item in archive.infolist()) > 64 * 1024 * 1024:
            archive.close()
            raise ValueError("Nội dung giải nén vượt giới hạn 64 MB.")
        return archive
    except zipfile.BadZipFile:
        raise ValueError("Tệp Office không hợp lệ hoặc đã bị hỏng.") from None


def parse_office_pages(filename: str, content: bytes):
    """DOCX uses one extracted-text page; PPTX follows sldIdLst, not ZIP filename order."""
    try:
        with _office_archive(content) as archive:
            if filename.lower().endswith(".docx"):
                root = ET.fromstring(archive.read("word/document.xml"))
                paragraphs = []
                for paragraph in root.iter(W + "p"):
                    parts = []
                    for node in paragraph.iter():
                        if node.tag == W + "t":
                            parts.append(node.text or "")
                        elif node.tag == W + "tab":
                            parts.append("\t")
                        elif node.tag == W + "br":
                            parts.append("\n")
                    paragraphs.append("".join(parts))
                pages = [(1, "\n".join(paragraphs))]
            else:
                presentation = ET.fromstring(archive.read("ppt/presentation.xml"))
                relationships = ET.fromstring(archive.read("ppt/_rels/presentation.xml.rels"))
                targets = {node.attrib.get("Id"): node.attrib.get("Target", "") for node in relationships}
                pages = []
                for number, slide in enumerate(presentation.iter(P + "sldId"), 1):
                    target = targets.get(slide.attrib.get(R + "id"), "")
                    path = posixpath.normpath(posixpath.join("ppt", target)) if not target.startswith("/") else target.lstrip("/")
                    if not path.startswith("ppt/slides/"):
                        raise ValueError("Liên kết slide không hợp lệ.")
                    root = ET.fromstring(archive.read(path))
                    text = "\n".join("".join(node.text or "" for node in paragraph.iter(A + "t")) for paragraph in root.iter(A + "p"))
                    pages.append((number, text))
            if not any(text.strip() for _, text in pages):
                raise ValueError("Tệp không có lớp văn bản để đọc. Hãy dùng bản có văn bản hoặc OCR trước.")
            return pages
    except (KeyError, ET.ParseError, RuntimeError, zipfile.BadZipFile):
        raise ValueError("Không thể đọc cấu trúc Word/PowerPoint. Hãy dùng tệp DOCX hoặc PPTX hợp lệ.") from None


class _PageText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "template"}:
            self.hidden += 1
        if not self.hidden and tag in {"p", "div", "h1", "h2", "h3", "li", "br", "tr", "section", "article"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "template"}:
            self.hidden = max(0, self.hidden - 1)
        if not self.hidden and tag in {"p", "div", "h1", "h2", "h3", "li", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def validate_public_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Dùng liên kết HTTP/HTTPS công khai, không kèm thông tin đăng nhập.")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(entry[4][0]).is_global for entry in addresses):
            raise ValueError("Không thể nhập địa chỉ nội bộ hoặc địa chỉ không công khai.")
    except (socket.gaierror, ValueError) as error:
        if isinstance(error, ValueError):
            raise
        raise ValueError("Không tìm thấy máy chủ của liên kết.") from None
    return parsed.geturl()


def fetch_public_source(url: str, title: str = ""):
    """Explicit user import only. Never runs on render or sends workspace files/API keys."""
    current = url
    try:
        for _ in range(4):
            current = validate_public_url(current)
            with httpx.stream("GET", current, timeout=15, follow_redirects=False, trust_env=False,
                              headers={"User-Agent": "WorkspaceAI/1.0", "Accept": "text/html,text/plain,application/pdf,*/*;q=0.5"}) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    current = urljoin(current, response.headers.get("location", ""))
                    continue
                if response.status_code != 200:
                    raise ValueError(f"Trang nguồn trả về mã {response.status_code}. Hãy thử tệp hoặc dán văn bản.")
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_SOURCE_BYTES:
                        raise ValueError("Nguồn vượt giới hạn 25 MB.")
                content_type = response.headers.get("content-type", "").lower()
                filename = unquote(urlsplit(current).path.rsplit("/", 1)[-1])
                if "text/html" in content_type or "application/xhtml" in content_type:
                    parser = _PageText()
                    parser.feed(bytes(body).decode(response.encoding or "utf-8", errors="replace"))
                    text = "\n".join(re.sub(r"[ \t]+", " ", line).strip() for line in "".join(parser.parts).splitlines())
                    text = re.sub(r"\n{3,}", "\n\n", text).strip()
                    if not text:
                        raise ValueError("Trang không có văn bản đọc được. Bạn có thể dán nội dung từ trang.")
                    name = re.sub(r'[\\/:*?"<>|]', "-", title.strip() or urlsplit(current).hostname or "Web source")[:120] + ".txt"
                    return name, f"Nguồn: {current}\n\n{text}".encode("utf-8"), current
                if not filename.lower().endswith((".pdf", ".txt", ".md", ".csv", ".docx", ".pptx")):
                    if "application/pdf" in content_type:
                        filename = (title.strip() or "Web source") + ".pdf"
                    elif "text/plain" in content_type:
                        filename = (title.strip() or "Web source") + ".txt"
                    else:
                        raise ValueError("Định dạng liên kết chưa được hỗ trợ. Hãy tải tệp hoặc dán văn bản.")
                return filename, bytes(body), current
        raise ValueError("Liên kết chuyển hướng quá nhiều lần.")
    except httpx.HTTPError:
        raise ValueError("Không tải được liên kết. Kiểm tra Internet hoặc dán nội dung văn bản để dùng Offline.") from None
