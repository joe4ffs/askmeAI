import json
import re

from grader.providers.base import ChatMessage, ImageInput


class FakeProvider:
    """Deterministic, network-free stand-in for a real model provider.

    Grades by simple keyword overlap between each rubric criterion and the student answer, and
    "OCRs" any image by returning a fixed placeholder transcription. Good enough to exercise the
    full pipeline (schema validation, CLI, eval script) without an API key; not a real grader or
    real OCR.
    """

    def complete(self, system: str, prompt: str, image: ImageInput | None = None) -> str:
        if "questions" in prompt and "student_answer_as_written" in prompt:
            return self._fake_script_grade(image)
        if image is not None:
            return json.dumps(
                {
                    "extracted_text": "[FakeProvider placeholder transcription — no real OCR performed]",
                    "confidence": "low",
                    "is_illegible": True,
                    "notes": "FakeProvider does not perform real OCR; set a real provider to transcribe images.",
                }
            )
        return self._fake_grade(prompt)

    def complete_chat(self, system: str, history: list[ChatMessage]) -> str:
        last_user = history[-1].content if history else ""
        return (
            f"[FakeProvider placeholder tutor response — no real model configured]\n\n"
            f"You asked: {last_user!r}. Set a real provider (e.g. GEMINI_API_KEY) to get an actual answer."
        )

    def _fake_script_grade(self, image: ImageInput | None) -> str:
        return json.dumps(
            {
                "questions": [
                    {
                        "question_text": "[FakeProvider placeholder — no real script reading performed]",
                        "student_answer_as_written": "[FakeProvider does not perform real OCR]",
                        "is_correct": False,
                        "explanation": "FakeProvider does not grade real scripts; set a real provider.",
                        "correction": None,
                    }
                ],
                "overall_summary": "Graded by FakeProvider (placeholder, not a real evaluation).",
                "score_estimate": "0/1",
            }
        )

    def _fake_grade(self, prompt: str) -> str:
        rubric_items = re.findall(r"- \(([\d.]+) pts\) (.+)", prompt)
        student_match = re.search(r"Student answer:\n(.*?)\n\nGrade", prompt, re.DOTALL)
        student_answer = student_match.group(1).lower() if student_match else ""

        rubric_results = []
        total_score = 0.0
        total_possible = 0.0
        for points_str, criterion in rubric_items:
            points = float(points_str)
            total_possible += points
            keywords = [w for w in re.findall(r"[a-zA-Z]{4,}", criterion.lower())]
            overlap = sum(1 for w in keywords if w in student_answer)
            met = overlap >= max(1, len(keywords) // 2)
            awarded = points if met else 0.0
            total_score += awarded
            rubric_results.append(
                {
                    "criterion": criterion,
                    "status": "met" if met else "missed",
                    "points_awarded": awarded,
                    "points_possible": points,
                    "evidence": "FakeProvider keyword-overlap heuristic; not a real judgment.",
                }
            )

        return json.dumps(
            {
                "total_score": total_score,
                "total_possible": total_possible or 1.0,
                "rubric_results": rubric_results,
                "overall_rationale": "Graded by FakeProvider (keyword-overlap heuristic, not a real model).",
                "is_ambiguous": False,
                "ambiguity_reason": None,
                "corrected_answer": None,
            }
        )
