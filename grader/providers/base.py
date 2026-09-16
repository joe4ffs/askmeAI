from dataclasses import dataclass
from typing import Protocol


@dataclass
class ImageInput:
    media_type: str
    base64_data: str


class ModelProvider(Protocol):
    """A swappable interface for the underlying model that generates grading/OCR completions.

    Implementations receive a system prompt and a user prompt (with an optional image) and
    must return raw text expected to contain a JSON object matching the caller's schema.
    """

    def complete(self, system: str, prompt: str, image: ImageInput | None = None) -> str: ...
