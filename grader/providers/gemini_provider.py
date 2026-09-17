import base64
import os

from google import genai
from google.genai import types

from grader.providers.base import ImageInput

MODEL = "gemini-3.6-flash"


class GeminiProvider:
    """Google Gemini, via GEMINI_API_KEY. Free tier available with no billing setup
    (https://aistudio.google.com/apikey).
    """

    def __init__(self, client: genai.Client | None = None, model: str = MODEL):
        self._client = client or genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        self._model = model

    def complete(self, system: str, prompt: str, image: ImageInput | None = None) -> str:
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
            config=types.GenerateContentConfig(system_instruction=system),
        )
        return response.text
