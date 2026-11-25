"""Bounded, credential-redacted diagnostics for unexpected controller replies."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urlsplit, urlunsplit
from xml.etree import ElementTree as ET


class _BodyPreview(HTMLParser):
    """Keep markup and visible text, never form attributes or script contents."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "textarea"):
            self.hidden.append(tag)
        if not self.hidden:
            self.parts.append(f"<{tag}>")

    def handle_startendtag(self, tag, attrs):
        if not self.hidden:
            self.parts.append(f"<{tag}/>")

    def handle_endtag(self, tag):
        if self.hidden:
            if tag == self.hidden[-1]:
                self.hidden.pop()
        else:
            self.parts.append(f"</{tag}>")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def safe_url(url: str) -> str:
    """Omit URL credentials, query values and fragments from diagnostics."""
    try:
        parts = urlsplit(str(url))
        host = parts.hostname or ""
        port = parts.port
    except ValueError:
        return "[invalid URL omitted]"
    if ":" in host:
        host = f"[{host}]"
    if port:
        host += f":{port}"
    return urlunsplit((parts.scheme, host, parts.path, "", ""))


def redact(text: str, secrets: list[str]) -> str:
    """Remove known credentials and common session/password assignments."""
    for secret in sorted({s for s in secrets if s}, key=len, reverse=True):
        text = text.replace(secret, "[redacted]")
    text = re.sub(
        r"(?i)\b(password|passwd|passhash|authorization|cookie|softplc|token|session(?:id)?)\b"
        r"\s*[:=]\s*[^\s<>;,]+",
        r"\1=[redacted]", text,
    )
    return text


def diagnose_status_body(
    raw: bytes, status: int, secrets: list[str], encoding_hint: str | None = None,
) -> dict:
    """Accept only a PAGE containing real INPUT values, with no LOGIN element."""
    valid = False
    kind = "empty" if not raw.strip() else "unexpected"
    if raw.strip():
        try:
            root = ET.fromstring(raw)
        except (ET.ParseError, ValueError, LookupError):
            kind = "html" if re.search(rb"<\s*(?:!doctype\s+html|html)\b", raw, re.I) else "invalid-xml"
        else:
            if root.tag.upper() == "HTML":
                kind = "html"
            elif any(str(el.tag).upper() == "LOGIN" for el in root.iter()):
                kind = "login"
            else:
                kind = "xml"
                valid = status == 200 and root.tag == "PAGE" and any(
                    "P" in el.attrib and "VALUE" in el.attrib
                    for el in root.iter("INPUT")
                )
    match = re.search(rb'<\?xml[^>]+encoding=["\']([^"\']+)', raw[:200], re.I)
    encoding = match.group(1).decode("ascii", errors="replace") if match else encoding_hint or "utf-8"
    try:
        text = raw.decode(encoding, errors="replace")
    except LookupError:
        text = raw.decode("utf-8", errors="replace")
    if valid:
        preview = "[valid data XML; values omitted]"
    else:
        parser = _BodyPreview()
        # Only inspect a bounded prefix, but redact before truncating so a
        # credential crossing the output boundary cannot leak partially.
        parser.feed(redact(text, secrets)[:16384])
        preview = redact(" ".join("".join(parser.parts).split()), secrets)[:800]
    return {"valid": valid, "kind": kind, "bytes": len(raw), "preview": preview}
