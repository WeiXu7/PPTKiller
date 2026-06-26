import json

import httpx

from ..config import Settings


class DeepSeekClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def configured(self) -> bool:
        return bool(self.settings.deepseek_api_key)

    async def generate_json(self, system: str, prompt: str) -> dict:
        if not self.configured:
            raise RuntimeError("DEEPSEEK_API_KEY 未配置")
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(
                f"{self.settings.deepseek_base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {self.settings.deepseek_api_key}"},
                json={
                    "model": self.settings.deepseek_model,
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.3,
                },
            )
            response.raise_for_status()
        return json.loads(response.json()["choices"][0]["message"]["content"])

