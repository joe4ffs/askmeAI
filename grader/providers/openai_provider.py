import os

from openai import OpenAI

from grader.providers.base import ChatMessage, ImageInput

MODEL = "gpt-4.1"


class OpenAIProvider:
    def __init__(self, client: OpenAI | None = None, model: str = MODEL):
        self._client = client or OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        self._model = model

    def complete(self, system: str, prompt: str, image: ImageInput | None = None) -> str:
        content: str | list[dict] = prompt
        if image is not None:
            content = [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{image.media_type};base64,{image.base64_data}"},
                },
            ]

        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": content},
            ],
        )
        return response.choices[0].message.content

    def complete_chat(self, system: str, history: list[ChatMessage]) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "system", "content": system}]
            + [{"role": msg.role, "content": msg.content} for msg in history],
        )
        return response.choices[0].message.content
