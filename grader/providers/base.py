from dataclasses import dataclass
from typing import Protocol


@dataclass
class ImageInput:
    media_type: str
    base64_data: str


@dataclass
class ChatMessage:
    role: str  # "user" or "assistant"
    content: str


class ModelProvider(Protocol):
    """A swappable interface for the underlying model that generates grading/OCR completions.

    Implementations receive a system prompt and a user prompt (with an optional image) and
    must return raw text expected to contain a JSON object matching the caller's schema.
    """

    def complete(self, system: str, prompt: str, image: ImageInput | None = None) -> str: ...

    def complete_chat(self, system: str, history: list[ChatMessage]) -> str:
        """Multi-turn free-text completion for conversational use (e.g. tutoring chat).

        `history` is the full conversation so far, ending with the latest user message.
        Default implementations may collapse this to a single prompt if the underlying
        client has no native multi-turn support.
        """
        ...
