import os
from pathlib import Path

from groq import Groq
from dotenv import load_dotenv

load_dotenv()


class GroqSummarizer:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        self._client: Groq | None = None

    def is_available(self) -> bool:
        return bool(self.api_key)

    def _get_client(self) -> Groq:
        if not self._client:
            if not self.api_key:
                raise ValueError(
                    "Clé API Groq non trouvée. Passez --groq-key ou définissez GROQ_API_KEY dans .env"
                )
            self._client = Groq(api_key=self.api_key)
        return self._client

    def summarize(self, html_content: str, max_chars: int = 8000) -> str:
        if not self.is_available():
            return ""

        client = self._get_client()

        import re
        text = re.sub(r"<[^>]+>", " ", html_content)
        text = re.sub(r"\s+", " ", text).strip()
        text = text[:max_chars]

        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Tu es un assistant qui analyse des pages web clonées. "
                        "Résume le contenu principal de la page en français en 5-10 lignes. "
                        "Identifie le type de site, son objectif principal, et les sections clés."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Voici le contenu texte de la page web clonée :\n\n{text}",
                },
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.3,
            max_tokens=512,
        )

        return chat_completion.choices[0].message.content or ""

    def save_summary(self, html_content: str, output_dir: str) -> Path | None:
        if not self.is_available():
            return None

        summary = self.summarize(html_content)
        if not summary:
            return None

        output_path = Path(output_dir) / "resume.md"
        content = f"# Résumé IA du site cloné\n\n{summary}\n"
        output_path.write_text(content, encoding="utf-8")
        return output_path
