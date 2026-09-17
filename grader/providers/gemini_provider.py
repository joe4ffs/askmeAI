import base64
import os

from google import genai
from google.genai import types

from grader.providers.base import ChatMessage, ImageInput

MODEL = "gemini-3.1-flash-lite"


class GeminiProvider:
    """Google Gemini, via GEMINI_API_KEY. Free tier available with no billing setup
    (https://aistudio.google.com/apikey).
    """

    def __init__(self, client: genai.Client | None = None, model: str = MODEL):
        self._client = client or genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        self._model = model

    def complete(
        self, system: str, prompt: str, image: ImageInput | None = None, thinking: bool = True
    ) -> str:
        parts = [types.Part.from_text(text=prompt)]
        if image is not None:
            parts.append(
                types.Part.from_bytes(
                    data=base64.standard_b64decode(image.base64_data), mime_type=image.media_type
                )
            )

        response = self._client.models.generate_content(
            model=self._model,
            contents=[types.Content(role="user", parts=parts)],
            config=types.GenerateContentConfig(
                system_instruction=system, thinking_config=_thinking_config(thinking)
            ),
        )
        return response.text

    def complete_chat(self, system: str, history: list[ChatMessage], thinking: bool = True) -> str:
        contents = [
            types.Content(
                role="model" if msg.role == "assistant" else "user",
                parts=[types.Part.from_text(text=msg.content)],
            )
            for msg in history
        ]
        response = self._client.models.generate_content(
            model=self._model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system, thinking_config=_thinking_config(thinking)
            ),
        )
        return response.text


def _thinking_config(thinking: bool) -> types.ThinkingConfig:
    return types.ThinkingConfig(thinking_budget=None if thinking else 0)
