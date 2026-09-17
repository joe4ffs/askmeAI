# AI Grader

An agentic grading system that evaluates student answers (numerical, science, English — any subject
with a rubric) against a reference answer and produces a score, rubric-item-by-item rationale, and
ambiguity flags for cases a human should review.

## Phased plan

- **Phase 0 (done)** — Core grading loop on clean typed text, one subject at a time. Get the
  grading logic trustworthy before touching OCR/handwriting at all.
- **Phase 1 (done)** — Add handwriting ingestion via vision-capable LLM OCR as a preprocessing
  step (`grader/ocr.py`). OCR runs as its own call producing an `OcrResult` (text, confidence,
  illegibility flag) before grading, so OCR accuracy and grading accuracy stay two separate,
  trackable numbers.
- **Phase 2 (done)** — Subject-specific grading presets (`presets/*.json`, loaded via
  `grader/presets.py`). A case file's `subject` is looked up against `presets/<subject>.json`; if
  found, its `grading_instructions` are appended to the engine's system prompt. question,
  reference_answer, and rubric remain per-case inputs (already not hardcoded since Phase 0).
- **Phase 3 (current)** — Evaluation study (`scripts/run_eval.py`): grades every case in an eval
  directory (`EvalCase` = a `GradingRequest` plus human `HumanRubricJudgment`s) and reports mean
  absolute error, exact/near agreement rates, and how many cases the model flagged ambiguous. Writes
  per-case results to CSV with `--out`.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate      # Windows
pip install -r requirements.txt
```

No API key is required to run the full pipeline — see [Model providers](#model-providers) below. To
grade with a real model, set a key for the provider you want:

```bash
setx ANTHROPIC_API_KEY "sk-ant-..."   # Windows, persists across sessions
setx OPENAI_API_KEY "sk-..."          # or, for the OpenAI provider
setx GEMINI_API_KEY "..."             # or, for the Gemini provider (no billing required)
```

Anthropic and OpenAI both require billing to be set up before you can create a key. If you want a
real model without setting up billing, get a free Gemini key at https://aistudio.google.com/apikey
(no card needed) and set `GEMINI_API_KEY` — it's picked up automatically.

## Usage

### Web dashboard

A local dashboard (no framework dependency, pure stdlib `http.server`) with two modes:

```bash
python scripts/web_ui.py            # http://127.0.0.1:8000
python scripts/web_ui.py --port 8080
```

- **Tutor Chat** — open-ended academic Q&A (`grader/tutor.py`). Ask anything; an optional subject
  field adds context and pulls in that subject's tracked weak areas. Each answer ends with a short
  follow-up question to keep the conversation going. Chats persist to `data/app.db` (SQLite) — the
  sidebar lists past sessions, click one to resume it, even after restarting the server.
- **Script Grading** — upload an image or PDF of a full answer script. The model (no teacher-supplied
  rubric required) segments it into individual questions, tags the underlying concept, and marks
  which ones are wrong with a correction (`grader/script_grader.py`). Wrong answers are logged per
  subject+concept; once a concept has more misses than correct answers, it shows up as a "weak area"
  the tutor can reference in later chats for that subject, and the tutor also calibrates explanation
  depth from recent accuracy.
  - **Rubric-cited feedback**: for each question, the grader generates its own 2-4 specific criteria
    (e.g. "correct formula used", "correct final answer", "units included") and judges each one
    independently — met/partially_met/missed/not_applicable, with points and an `evidence` quote from
    the student's actual answer. Every point gained or lost cites a specific criterion instead of a
    bare "wrong" verdict — the basis a student could actually appeal. `is_correct` and per-question/
    total points are computed from these criteria, not asserted separately
    (`ScriptQuestionResult.criteria`, `.points_awarded`/`.points_possible`, `ScriptGradingResult.
    total_points_awarded`/`.total_points_possible`).
  - **On-image annotation**: each criterion also carries a `box_2d` — `[ymin, xmin, ymax, xmax]`
    normalized to 0-1000 — locating the exact text on the page that criterion's evidence refers to
    (Gemini supports this as a grounded-detection prompting convention, verified accurate against
    real handwriting-style images before building on it). The dashboard overlays these as colored
    boxes directly on the uploaded script (green/amber/red by status); click one to see the
    criterion, points, and evidence — the "red pen" view. Image uploads only (PDFs can't be
    canvas-overlaid in a browser the same way, so `source_image` is omitted for those and the
    dashboard falls back to the plain criteria list).
  - **Confidence + abstention**: every question also gets a `confidence` (high/medium/low) and, when
    the grader isn't sure — unclear handwriting, a nonstandard-but-possibly-valid method, a genuine
    judgment call — `needs_human_review=true` with a `review_reason` explaining what's uncertain,
    instead of silently picking an interpretation. Each graded question is logged to
    `grading_events` in `data/app.db`, so the grader's actual abstention rate (how often it flags
    itself) is a real, queryable number via `Storage.reliability_stats()` /
    `GET /api/reliability?subject=...`, not just a per-question UI badge.

Uses whichever provider `get_provider()` resolves to (see [Model providers](#model-providers)) — set
`GEMINI_API_KEY` etc. before starting the server to use a real model instead of the `fake` provider,
which returns placeholder text/results for both modes so the UI is exercisable offline.

### CLI

Grade a single case file:

```bash
python scripts/grade_file.py data/samples/example_case.json
```

Case file format — see `data/samples/example_case.json`:

```json
{
  "subject": "operating_systems",
  "question": "...",
  "reference_answer": "...",
  "rubric": [{ "criterion": "...", "points": 2 }],
  "student_answer": "..."
}
```

For a handwritten answer, omit `student_answer` and set `student_answer_image_path` to an image
file instead. `grade_file.py` OCRs it first (via `grader/ocr.py`) and prints the OCR confidence
(and any illegibility warning) to stderr before grading:

```json
{
  "subject": "operating_systems",
  "question": "...",
  "reference_answer": "...",
  "rubric": [{ "criterion": "...", "points": 2 }],
  "student_answer_image_path": "data/samples/answer1.png"
}
```

## Model providers

The engine, OCR, script grading, and tutor chat all talk to a swappable `ModelProvider`
(`grader/providers/`) instead of a hardcoded client, so grading/chat logic never has to know which
model is behind it. Each provider implements `complete()` (single-turn, optional image) and
`complete_chat()` (multi-turn, for the tutor):

- `anthropic` — Claude, via `ANTHROPIC_API_KEY` (default when that key is set). Requires billing.
- `openai` — GPT, via `OPENAI_API_KEY` (default when set and no Anthropic key). Requires billing.
- `gemini` — Gemini, via `GEMINI_API_KEY` (default when set and no Anthropic/OpenAI key). Free tier,
  no billing setup — get a key at https://aistudio.google.com/apikey.
- `ollama` — a local Ollama server (https://ollama.com), no key required; needs a vision model
  pulled locally (e.g. `ollama pull llava`).
- `fake` — no key, no network, deterministic. Grades by keyword overlap between rubric criteria and
  the student answer, and returns a placeholder OCR transcription. Used automatically when no
  provider is configured and no API key is set, so the whole pipeline (CLI, eval script, tests) runs
  out of the box. Not a real grader — good for wiring/plumbing, not for real scores.

Pick a provider explicitly with the `AI_GRADER_PROVIDER` env var (`anthropic`, `openai`, `gemini`,
`ollama`, or `fake`), or pass one directly: `grade(req, provider=get_provider("gemini"))`.

## Subject presets

`presets/<subject>.json` files supply subject-specific grading guidance, appended to the engine's
system prompt when a case file's `subject` matches a preset name (e.g. `subject: "math"` picks up
`presets/math.json`). Bundled presets: `math`, `english`, `operating_systems`. A subject without a
matching preset file just uses the base grading prompt.

```json
{
  "subject": "math",
  "grading_instructions": "Award partial credit when the method is correct but there's an arithmetic slip..."
}
```

## Evaluation study

Run the grading engine against a directory of human-graded cases and report agreement:

```bash
python scripts/run_eval.py data/eval --out results.csv
```

The free Gemini tier is rate-limited per model (5 requests/minute, 20 requests/day for
`gemini-3.6-flash` as of writing — the default provider model is `gemini-3.1-flash-lite`, which has
a separate, higher free-tier quota).
Use `--delay 15` to pace requests within a run; if you hit a 429 quota error, the eval script skips
that case and keeps going — rerun later to fill in the gaps.

Eval case file format — see `data/eval/case_001.json`:

```json
{
  "case_id": "case_001",
  "request": { ...same fields as a grading case file... },
  "human_judgments": [
    { "criterion": "...", "status": "met", "points_awarded": 2, "points_possible": 2 }
  ]
}
```

## Adversarial eval suite

A standing set of deliberately tricky question+answer pairs (`data/adversarial/`), checking
*behavioral* robustness rather than numeric score agreement — does the grader get fooled by a
confident-sounding wrong answer, does it unfairly penalize a valid-but-unusual method, does it
flag genuinely illegible input instead of confidently guessing. Each case is rendered as an image
(so grading goes through the real vision pipeline `grade_script_input()` uses, not a text
shortcut) via `scripts/run_adversarial_eval.py`:

```bash
python scripts/run_adversarial_eval.py data/adversarial --delay 5 --out adversarial_results.csv
```

Trap categories (`grader/schema.py: AdversarialTrap`):

- `right_answer_wrong_reasoning` — correct final answer, but the shown work doesn't actually derive it
- `keyword_stuffed_nonsense` — every relevant term present, zero coherent content
- `confident_but_irrelevant` — fluent, accurate-sounding, answers a different question entirely
- `nonstandard_valid_method` — correct answer via an unusual but legitimate approach (should NOT be
  marked wrong for not matching the "expected" method)
- `illegible_or_garbled` — visually degraded input (low contrast, jitter, noise — see
  `render_case_image`'s `render_illegible` path); should be flagged for human review, not confidently
  transcribed and graded

Each case declares `expect_correct` and/or `expect_flagged` — what a robust grader should output —
and the run reports a pass rate per trap type plus the specific failures.

**Current finding** (run against `gemini-3.1-flash-lite`): 5/6 cases passed (one 503
API error on that run, excluded). The one reproducible failure — `case_005`
(`illegible_or_garbled`) — is genuinely informative: the model transcribed visually degraded,
jittered, low-contrast text with `confidence=high` and `needs_human_review=false`, i.e. it did not
recognize its own transcription as uncertain even though the input was deliberately hard to read.
This is a real, measured limitation of the confidence/abstention mechanism (see
[Script Grading](#web-dashboard) above), not a test-harness artifact — the suite is doing its job.

## Tests

```bash
pytest
```

No tests require an API key — engine/OCR tests mock a `ModelProvider` directly, and the `fake`
provider is exercised in `tests/test_providers.py`.
