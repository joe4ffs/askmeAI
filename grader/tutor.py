"""Open-ended academic tutoring chat — no rubric, no grading, just Q&A with memory."""

from grader.providers import ModelProvider, get_provider
from grader.providers.base import ChatMessage
from grader.storage import WeakArea

BASE_SYSTEM_PROMPT = """You are a patient, knowledgeable academic tutor. A student will ask you \
questions on any subject (math, science, English, history, programming, etc.). You must:

1. Give correct, clear, well-explained answers — show your reasoning or working, not just the answer.
2. Match your explanation to what the student seems to already understand, based on the conversation.
3. If a question is ambiguous, ask a brief clarifying question rather than guessing.
4. Encourage understanding over rote answers — where useful, explain the "why", not just the "what".
5. Keep responses focused and not unnecessarily long.
6. After answering, end with one short, natural follow-up question — check understanding, offer to \
go deeper, or suggest a related idea worth exploring. Skip this only if the student's message was \
already just a quick clarification or a "thanks"/closing remark.

Respond in plain text (not JSON) — this is a normal conversational reply.
"""


def _calibration_note(accuracy: float | None) -> str:
    if accuracy is None:
        return ""
    if accuracy < 0.5:
        return (
            "\n\nCalibration: this student has been getting less than half of graded questions "
            "right recently. Default to more foundational, step-by-step explanations and simpler "
            "vocabulary unless they show they're following along."
        )
    if accuracy > 0.85:
        return (
            "\n\nCalibration: this student has been getting most graded questions right recently. "
            "You can move faster, use more precise/technical language, and skip basics they've "
            "already demonstrated."
        )
    return ""


def _weak_areas_note(weak_areas: list[WeakArea]) -> str:
    if not weak_areas:
        return ""
    lines = "\n".join(f"- {w.concept} ({w.subject}): missed {w.miss_count}x" for w in weak_areas)
    return (
        "\n\nKnown weak areas from past graded work (don't force these into every reply — bring "
        f"one up only if it's naturally relevant to what the student just asked):\n{lines}"
    )


def build_system_prompt(
    weak_areas: list[WeakArea] | None = None, accuracy: float | None = None
) -> str:
    return BASE_SYSTEM_PROMPT + _calibration_note(accuracy) + _weak_areas_note(weak_areas or [])


def ask_tutor(
    history: list[ChatMessage],
    provider: ModelProvider | None = None,
    weak_areas: list[WeakArea] | None = None,
    accuracy: float | None = None,
    thinking: bool = True,
) -> str:
    provider = provider or get_provider()
    system = build_system_prompt(weak_areas, accuracy)
    return provider.complete_chat(system=system, history=history, thinking=thinking)
