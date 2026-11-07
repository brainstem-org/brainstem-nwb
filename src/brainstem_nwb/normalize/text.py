"""Plain text from BrainSTEM rich text, and readable names for schema keys and enum codes."""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser

_BLOCK_TAGS = {"p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "table", "blockquote"}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "li":
            self.parts.append("\n- ")
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _BLOCK_TAGS and tag != "li":
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def html_to_text(value: str | None) -> str:
    """Convert CKEditor HTML (session, project and subject descriptions) to plain text."""
    if not value:
        return ""
    if "<" not in value:
        return _collapse(html.unescape(value))
    parser = _TextExtractor()
    parser.feed(value)
    parser.close()
    return _collapse("".join(parser.parts))


def _collapse(text: str) -> str:
    lines = [re.sub(r"[ \t ]+", " ", line).strip() for line in text.replace("\r", "").split("\n")]
    out: list[str] = []
    for line in lines:
        if line or (out and out[-1]):
            out.append(line)
    return "\n".join(out).strip()


def one_line(text: str) -> str:
    """Collapse text to a single line, for narratives and table cells."""
    return re.sub(r"\s+", " ", text).strip()


def humanize_key(key: str) -> str:
    """``postInfusionDwell`` -> ``post infusion dwell``; ``nChannels`` -> ``n channels``."""
    words = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", key.replace("_", " "))
    return words.lower().strip()


def humanize_code(code: str) -> str:
    """``bolus_injection`` -> ``bolus injection``; ``SiliconProbeImplant`` -> ``silicon probe implant``."""
    if "_" in code or code.islower():
        return code.replace("_", " ")
    return humanize_key(code)
