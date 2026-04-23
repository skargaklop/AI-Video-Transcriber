import re


TIMECODE_LINE_RE = re.compile(
    r"(?m)^\s*(?:\*\*)?\[?\d{1,2}:\d{2}(?::\d{2})?\s*(?:-|\u2013|\u2014)\s*"
    r"\d{1,2}:\d{2}(?::\d{2})?\]?(?:\*\*)?\s*$"
)
PRESERVED_BLOCK_RE = re.compile(
    r"^(?:#{1,6}\s+|---+$|\*\*[^*]+:\*\*|source:\s*)",
    re.IGNORECASE,
)


def strip_transcript_timecodes(transcript: str) -> str:
    if not transcript:
        return ""

    without_timecodes = TIMECODE_LINE_RE.sub("", transcript.replace("\r\n", "\n"))
    without_timecodes = re.sub(r"\n{3,}", "\n\n", without_timecodes)
    return without_timecodes.strip()


def format_transcript_without_timecodes(transcript: str, max_paragraph_chars: int = 900) -> str:
    """Remove timecode blocks and merge subtitle cues into readable paragraphs."""
    stripped = strip_transcript_timecodes(transcript)
    if not stripped:
        return ""

    blocks: list[str] = []
    paragraph_lines: list[str] = []

    def flush_paragraph() -> None:
        if paragraph_lines:
            blocks.append(" ".join(paragraph_lines).strip())
            paragraph_lines.clear()

    for raw_line in stripped.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if PRESERVED_BLOCK_RE.match(line):
            flush_paragraph()
            blocks.append(line)
            continue

        paragraph_lines.append(line)
        paragraph = " ".join(paragraph_lines)
        ends_sentence = bool(re.search(r'[.!?\u2026\u3002\uff01\uff1f]"?$', line))
        if (len(paragraph) >= max_paragraph_chars and ends_sentence) or len(paragraph) >= max_paragraph_chars * 1.35:
            flush_paragraph()

    flush_paragraph()
    return "\n\n".join(blocks).strip()
