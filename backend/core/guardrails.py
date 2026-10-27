import re
from typing import Optional, Tuple

INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"system\s+override",
    r"disregard\s+safeguards",
    r"send\s+all\s+workspace\s+files\s+to",
]

EMAIL_REGEX = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def detect_prompt_injection(text: str) -> Tuple[bool, Optional[str]]:
    """R7 Safeguard: Scans user input or untrusted document chunks for injection patterns."""
    normalized = text.lower()
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, normalized):
            return True, f"Matched restricted security pattern: {pattern}"
    return False, None


def wrap_untrusted_chunk(doc_name: str, page: int, raw_text: str) -> str:
    """R7 Data-Instruction Separation: Encapsulates document text in passive XML tags."""
    sanitized = raw_text.replace("</untrusted_document_data>", "")
    return (
        f'<untrusted_document_data source="{doc_name}" page="{page}">\n'
        f"{sanitized}\n"
        f"</untrusted_document_data>"
    )


def validate_email_address(email: Optional[str]) -> bool:
    """Validates RFC-5322 compatible email address format."""
    if not email:
        return False
    return bool(EMAIL_REGEX.match(email.strip()))
