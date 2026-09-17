"""Minimal local web UI for interactive grading — no framework dependency.

Serves a form where you can paste a question, reference answer, rubric, and student
answer, hit "Grade", and see the GradingResult rendered on the same page.

Usage:
    python scripts/web_ui.py
    python scripts/web_ui.py --port 8080
"""

import argparse
import html
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import ValidationError

from grader.engine import grade
from grader.schema import GradingRequest, RubricItem

PAGE_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>AI Grader</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 800px; margin: 2rem auto; padding: 0 1rem; }}
  label {{ display: block; font-weight: 600; margin-top: 1rem; }}
  textarea, input {{ width: 100%; box-sizing: border-box; font-family: inherit; font-size: 1rem;
                      padding: 0.5rem; margin-top: 0.25rem; }}
  textarea {{ min-height: 4rem; }}
  button {{ margin-top: 1.5rem; padding: 0.6rem 1.5rem; font-size: 1rem; cursor: pointer; }}
  .hint {{ color: #666; font-size: 0.85rem; }}
  .result {{ margin-top: 2rem; padding: 1rem; border: 1px solid #ccc; border-radius: 6px; }}
  .score {{ font-size: 1.5rem; font-weight: 700; }}
  .ambiguous {{ color: #b45309; }}
  .criterion {{ margin: 0.75rem 0; padding: 0.5rem; background: #f7f7f7; border-radius: 4px; }}
  .status-met {{ color: #15803d; }}
  .status-partially_met {{ color: #b45309; }}
  .status-missed {{ color: #b91c1c; }}
  .error {{ color: #b91c1c; background: #fee; padding: 1rem; border-radius: 6px; }}
</style>
</head>
<body>
<h1>AI Grader</h1>
<form method="post">
  <label>Subject <span class="hint">(matches presets/&lt;subject&gt;.json, e.g. math, english, operating_systems)</span></label>
  <input name="subject" value="{subject}">

  <label>Question</label>
  <textarea name="question" required>{question}</textarea>

  <label>Reference answer</label>
  <textarea name="reference_answer" required>{reference_answer}</textarea>

  <label>Rubric <span class="hint">(one criterion per line, format: "points | criterion text")</span></label>
  <textarea name="rubric" required placeholder="2 | States that a process has its own memory space">{rubric}</textarea>

  <label>Student answer</label>
  <textarea name="student_answer" required>{student_answer}</textarea>

  <button type="submit">Grade</button>
</form>
{result}
</body>
</html>
"""


def _parse_rubric(raw: str) -> list[RubricItem]:
    items = []
    for line in raw.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        points_str, _, criterion = line.partition("|")
        items.append(RubricItem(points=float(points_str.strip()), criterion=criterion.strip()))
    return items


def _render_result(req: GradingRequest) -> str:
    try:
        result = grade(req)
    except (ValidationError, ValueError) as exc:
        return f'<div class="error"><strong>Grading failed:</strong> {html.escape(str(exc))}</div>'
    except Exception as exc:
        return f'<div class="error"><strong>Provider error:</strong> {html.escape(str(exc))}</div>'

    criteria_html = "\n".join(
        f'<div class="criterion"><span class="status-{item.status.value}">[{item.status.value}]</span> '
        f"<strong>{html.escape(item.criterion)}</strong> "
        f"— {item.points_awarded}/{item.points_possible} pts<br>"
        f'<span class="hint">{html.escape(item.evidence)}</span></div>'
        for item in result.rubric_results
    )
    ambiguous_html = (
        f'<p class="ambiguous">⚠ Flagged ambiguous: {html.escape(result.ambiguity_reason or "")}</p>'
        if result.is_ambiguous
        else ""
    )
    corrected_html = (
        f"<p><strong>Suggested correction:</strong> {html.escape(result.corrected_answer)}</p>"
        if result.corrected_answer
        else ""
    )
    return f"""<div class="result">
      <div class="score">{result.total_score} / {result.total_possible}</div>
      <p>{html.escape(result.overall_rationale)}</p>
      {ambiguous_html}
      {criteria_html}
      {corrected_html}
    </div>"""


class Handler(BaseHTTPRequestHandler):
    def _send_page(self, fields: dict, result_html: str = "") -> None:
        body = PAGE_TEMPLATE.format(
            subject=html.escape(fields.get("subject", "general")),
            question=html.escape(fields.get("question", "")),
            reference_answer=html.escape(fields.get("reference_answer", "")),
            rubric=html.escape(fields.get("rubric", "")),
            student_answer=html.escape(fields.get("student_answer", "")),
            result=result_html,
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        self._send_page({})

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8")
        parsed = parse_qs(raw)
        fields = {k: v[0] for k, v in parsed.items()}

        try:
            req = GradingRequest(
                subject=fields.get("subject") or "general",
                question=fields.get("question", ""),
                reference_answer=fields.get("reference_answer", ""),
                rubric=_parse_rubric(fields.get("rubric", "")),
                student_answer=fields.get("student_answer", ""),
            )
        except (ValidationError, ValueError) as exc:
            self._send_page(fields, f'<div class="error"><strong>Invalid input:</strong> {html.escape(str(exc))}</div>')
            return

        self._send_page(fields, _render_result(req))

    def log_message(self, format: str, *args) -> None:
        print(f"{self.address_string()} - {format % args}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    server = HTTPServer((args.host, args.port), Handler)
    print(f"Serving on http://{args.host}:{args.port}  (Ctrl+C to stop)", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
