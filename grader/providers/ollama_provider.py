import os

import requests

from grader.providers.base import ImageInput

MODEL = "llava"
DEFAULT_HOST = "http://localhost:11434"


class OllamaProvider:
    """Talks to a local Ollama server (https://ollama.com) — no API key required.

    Requires Ollama running locally with a model pulled (`ollama pull llava` for vision support).
    """

    def __init__(self, model: str = MODEL, host: str | None = None):
        self._model = model
        self._host = host or os.environ.get("OLLAMA_HOST", DEFAULT_HOST)

    def complete(self, system: str, prompt: str, image: ImageInput | None = None) -> str:
        payload = {
            "model": self._model,
            "system": system,
            "prompt": prompt,
            "stream": False,
        }
        if image is not None:
            payload["images"] = [image.base64_data]

        response = requests.post(f"{self._host}/api/generate", json=payload, timeout=120)
        response.raise_for_status()
        return response.json()["response"]
