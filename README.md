# AI Grader

An agentic grading system that evaluates student answers (numerical, science, English — any subject
with a rubric) against a reference answer and produces a score, rubric-item-by-item rationale, and
ambiguity flags for cases a human should review.

## Phased plan

- **Phase 0 (done)** — Core grading loop on clean typed text, one subject at a time. Get the
  grading logic trustworthy before touching OCR/handwriting at all.
- **Phase 1 (current)** — Add handwriting ingestion via vision-capable LLM OCR as a preprocessing
  step (`grader/ocr.py`). OCR runs as its own call producing an `OcrResult` (text, confidence,
  illegibility flag) before grading, so OCR accuracy and grading accuracy stay two separate,
  trackable numbers.
- **Phase 2** — Make the rubric/reference an input instead of hardcoded, so any subject/question can
  be graded.
- **Phase 3** — Evaluation study: run against real student answers with known human grades, report
  agreement rates and error patterns.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate      # Windows
pip install -r requirements.txt
```

Set your Anthropic API key:

```bash
setx ANTHROPIC_API_KEY "sk-ant-..."   # Windows, persists across sessions
```

## Usage

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

## Tests

```bash
pytest
```

Schema and engine tests run without any API key (the engine test mocks the Anthropic client).
