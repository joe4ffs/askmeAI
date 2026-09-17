"""Grade a full student script (multi-question answer sheet) from an uploaded image or PDF.

Unlike grader.engine.grade, this does not take a rubric or reference answer — the model reads
the whole script, identifies each question and the student's answer to it, and judges correctness
from its own subject knowledge. Used for "upload your script, get it marked" style grading.
"""

import base64
import json
import mimetypes
from pathlib import Path

from grader.providers import ImageInput, ModelProvider, get_provider
from grader.schema import ScriptGradingResult
from grader.storage import Storage

SYSTEM_PROMPT = """You are a strict, fair teacher marking a student's answer script. You are given an \
image or PDF of a script that may contain one or more questions with the student's written answers. You must:

1. Identify every distinct question and the student's answer to it, in the order they appear.
2. For each question, before judging it, write 2-4 specific `criteria` it should be graded against —
   e.g. "correct formula used" (2 pts), "correct final answer" (2 pts), "units included" (1 pt). No
   external answer key is provided, so derive these criteria yourself from established facts/methods
   for the subject. Split points across criteria so they add up to a sensible total for that question
   (you decide point values; there's no fixed total to hit).
3. Judge each criterion independently as met / partially_met / missed / not_applicable, with
   points_awarded never exceeding that criterion's points_possible, and `evidence` — a quote or
   paraphrase from the student's answer that specifically supports this judgment. Never award or
   deduct points without citing which criterion and why; "the answer is wrong" is not evidence,
   "third line: used addition instead of the product rule" is.
3b. For every criterion, also set `box_2d` — the bounding box, as [ymin, xmin, ymax, xmax] normalized
   to 0-1000 against the full image, tightly around the specific text on the page that is this
   criterion's evidence (e.g. just the wrong number, not the whole line). This is what lets a human
   see exactly where on the page each point was gained or lost, like a red pen. Only omit box_2d
   (leave it null) if the criterion is not_applicable and there is genuinely no relevant text to point
   at — every met/partially_met/missed criterion must have one.
4. In `explanation`, summarize by referencing the criteria — don't just restate the verdict.
5. If any criteria were missed or only partially met, provide a `correction`.
6. Tag every question with a short `concept` (2-5 words) naming the underlying skill/topic it tests
   — e.g. "quadratic factoring", "thread synchronization" — consistent enough that the same concept
   across different questions gets the same tag.
7. Set confidence and needs_human_review HONESTLY for every question — these matter as much as the
   grade itself. Use confidence=low or medium, and needs_human_review=true, whenever:
   - Handwriting is unclear enough that your transcription could be wrong.
   - The student used a method or reasoning path you don't recognize as standard, but it might still
     be a valid alternate approach — don't silently mark it wrong just because it doesn't match the
     expected method.
   - The question or answer is ambiguous enough that a reasonable grader could go either way.
   Do NOT default to high confidence to seem authoritative — a wrong confident grade is worse than an
   honest "a human should check this." Most straightforward, clearly-correct-or-clearly-wrong answers
   should still be confidence=high with needs_human_review=false; reserve the flag for genuine cases.
8. Give an overall_summary of how the student did, and a score_estimate like "6/8 correct". Mention
   in the summary if any questions were flagged for review.

Respond with ONLY a JSON object matching the required schema. No prose outside the JSON.
"""


def _file_to_input(path: str) -> ImageInput:
    media_type, _ = mimetypes.guess_type(path)
    if media_type is None:
        raise ValueError(f"Could not determine file type for {path!r}")
    data = base64.standard_b64encode(Path(path).read_bytes()).decode("utf-8")
    return ImageInput(media_type=media_type, base64_data=data)


def grade_script(file_path: str, provider: ModelProvider | None = None) -> ScriptGradingResult:
    return grade_script_input(_file_to_input(file_path), provider)


def grade_script_input(
    file_input: ImageInput,
    provider: ModelProvider | None = None,
    subject: str = "general",
    storage: Storage | None = None,
) -> ScriptGradingResult:
    """Grade a script. If `storage` is given, each question's concept/correctness is logged for
    weak-area tracking (subject is a free-text label, e.g. "math" — used to group concepts).
    """
    provider = provider or get_provider()
    prompt = (
        "Read this script, identify each question and answer (student_answer_as_written), and grade "
        "each one. Return JSON matching this schema:\n"
        f"{json.dumps(ScriptGradingResult.model_json_schema(), indent=2)}"
    )
    text = provider.complete(system=SYSTEM_PROMPT, prompt=prompt, image=file_input)
    result = ScriptGradingResult.model_validate_json(_extract_json(text))

    if storage is not None:
        for q in result.questions:
            storage.record_question_result(subject=subject, concept=q.concept, is_correct=q.is_correct)
            storage.record_grading_event(
                subject=subject,
                concept=q.concept,
                is_correct=q.is_correct,
                confidence=q.confidence.value,
                needs_human_review=q.needs_human_review,
            )

    return result


def _extract_json(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON object found in model response: {text!r}")
    return text[start : end + 1]
