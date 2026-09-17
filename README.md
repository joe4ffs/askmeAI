# AI Grader

An AI-powered grading assistant: upload a student's script and get it graded with cited,
auditable feedback — plus a tutor chat and spaced-repetition study tools built from the mistakes
it finds.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate      # Windows
pip install -r requirements.txt
```

No API key is required — the app runs out of the box with a deterministic `fake` provider. For
real grading, get a free key at https://aistudio.google.com/apikey (no card needed) and set it:

```bash
setx GEMINI_API_KEY "..."
```

Other providers (Anthropic, OpenAI, local Ollama) are also supported — see `grader/providers/`.

## Usage

```bash
python scripts/web_ui.py
```

Open http://127.0.0.1:8000. Three modes:

- **Tutor Chat** — ask any academic question; conversations persist and the tutor remembers your
  weak spots.
- **Script Grading** — upload an image or PDF of a filled-out script. Each question gets scored
  against grader-generated rubric criteria, annotated directly on the image, and flagged for
  review when the grader isn't confident.
- **Study** — flashcards auto-generated from your mistakes, plus a mastery tracker per concept.

## CLI

```bash
python scripts/grade_file.py data/samples/example_case.json
```

## Tests

```bash
pytest
```

Also included: `scripts/run_eval.py` (agreement against human-graded cases) and
`scripts/run_adversarial_eval.py` (robustness against deliberately tricky answers).
