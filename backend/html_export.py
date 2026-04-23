import html
import re


def _inline_markdown(text: str) -> str:
    escaped = html.escape(text, quote=True)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"`(.+?)`", r"<code>\1</code>", escaped)
    return escaped


def markdown_to_html(markdown_text: str) -> str:
    html_lines: list[str] = []
    in_ul = False
    in_ol = False

    def close_lists() -> None:
        nonlocal in_ul, in_ol
        if in_ul:
            html_lines.append("</ul>")
            in_ul = False
        if in_ol:
            html_lines.append("</ol>")
            in_ol = False

    for raw_line in markdown_text.splitlines():
        line = raw_line.strip()
        if not line:
            close_lists()
            continue

        if line.startswith("### "):
            close_lists()
            html_lines.append(f"<h3>{_inline_markdown(line[4:])}</h3>")
        elif line.startswith("## "):
            close_lists()
            html_lines.append(f"<h2>{_inline_markdown(line[3:])}</h2>")
        elif line.startswith("# "):
            close_lists()
            html_lines.append(f"<h1>{_inline_markdown(line[2:])}</h1>")
        elif line.startswith("- "):
            if in_ol:
                html_lines.append("</ol>")
                in_ol = False
            if not in_ul:
                html_lines.append("<ul>")
                in_ul = True
            html_lines.append(f"<li>{_inline_markdown(line[2:])}</li>")
        elif re.match(r"^\d+\.\s+", line):
            if in_ul:
                html_lines.append("</ul>")
                in_ul = False
            if not in_ol:
                html_lines.append("<ol>")
                in_ol = True
            item = re.sub(r"^\d+\.\s+", "", line)
            html_lines.append(f"<li>{_inline_markdown(item)}</li>")
        elif line == "---":
            close_lists()
            html_lines.append("<hr>")
        else:
            close_lists()
            html_lines.append(f"<p>{_inline_markdown(line)}</p>")

    close_lists()
    return "\n".join(html_lines)


def render_summary_html(title: str, summary_markdown: str, source_url: str = "") -> str:
    safe_title = html.escape(title or "Video Summary", quote=True)
    body = markdown_to_html(summary_markdown or "")
    source = ""
    if source_url:
        safe_url = html.escape(source_url, quote=True)
        source = f'<p class="source">Source: <a href="{safe_url}">{safe_url}</a></p>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{safe_title}</title>
  <style>
    body {{
      margin: 0;
      background: #f6f3ef;
      color: #221b16;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
      line-height: 1.65;
    }}
    main {{
      max-width: 860px;
      margin: 0 auto;
      padding: 48px 24px 72px;
    }}
    h1, h2, h3 {{ line-height: 1.25; color: #17110d; }}
    h1 {{ font-size: 2rem; margin: 0 0 22px; }}
    h2 {{ font-size: 1.35rem; margin-top: 30px; }}
    h3 {{ font-size: 1.05rem; margin-top: 22px; }}
    p, li {{ font-size: 1rem; }}
    code {{
      background: #e8dfd5;
      border-radius: 4px;
      padding: 1px 5px;
    }}
    a {{ color: #8f521f; }}
    hr {{ border: none; border-top: 1px solid #d4c7bb; margin: 24px 0; }}
    .source {{
      margin-top: 36px;
      padding-top: 18px;
      border-top: 1px solid #d4c7bb;
      color: #6d625a;
      word-break: break-word;
    }}
  </style>
</head>
<body>
  <main>
{body}
{source}
  </main>
</body>
</html>
"""
