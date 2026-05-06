import logging
from openai import OpenAI
from typing import Optional
import re

logger = logging.getLogger(__name__)


class Translator:
    """Text translator, uses GPT-4o for high quality translation"""

    def __init__(self):
        self.client = None
        self._init_openai_client()

        # Language map
        self.language_map = {
            "zh": "中文（简体）",
            "zh-tw": "中文（繁体）",
            "en": "English",
            "ja": "日本語",
            "ko": "한국어",
            "fr": "Français",
            "de": "Deutsch",
            "es": "Español",
            "it": "Italiano",
            "pt": "Português",
            "ru": "Русский",
            "ar": "العربية",
            "hi": "हिन्दी",
        }

    def _init_openai_client(self):
        """Initialize OpenAI client"""
        try:
            import os

            api_key = os.getenv("OPENAI_API_KEY")
            base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

            if not api_key:
                logger.warning("OPENAI_API_KEY environment variable not set")
                return

            self.client = OpenAI(api_key=api_key, base_url=base_url)
            logger.info("OpenAI client initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {str(e)}")
            self.client = None

    def _detect_source_language(self, text: str) -> str:
        """Detect source text language"""
        # Simple language detection logic
        if "**Detected Language:**" in text:
            lines = text.split("\n")
            for line in lines:
                if "**Detected Language:**" in line:
                    lang = line.split(":")[-1].strip()
                    return lang

        # Simple detection based on character statistics
        total_chars = len(text)
        if total_chars == 0:
            return "en"

        # Count Chinese characters
        chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
        chinese_ratio = chinese_chars / total_chars

        # Count Japanese characters
        japanese_chars = len(re.findall(r"[\u3040-\u309f\u30a0-\u30ff]", text))
        japanese_ratio = japanese_chars / total_chars

        # Count Korean characters
        korean_chars = len(re.findall(r"[\uac00-\ud7af]", text))
        korean_ratio = korean_chars / total_chars

        if chinese_ratio > 0.1:
            return "zh"
        elif japanese_ratio > 0.05:
            return "ja"
        elif korean_ratio > 0.05:
            return "ko"
        else:
            return "en"

    def _smart_chunk_text(self, text: str, max_chars_per_chunk: int = 4000) -> list:
        """Smart chunk text for translation"""
        chunks = []

        # First split by paragraphs
        paragraphs = [p for p in text.split("\n\n") if p.strip()]
        current_chunk = ""

        for paragraph in paragraphs:
            # If current chunk plus new paragraph exceeds limit
            if (
                len(current_chunk) + len(paragraph) + 2 > max_chars_per_chunk
                and current_chunk
            ):
                chunks.append(current_chunk.strip())
                current_chunk = paragraph
            else:
                if current_chunk:
                    current_chunk += "\n\n" + paragraph
                else:
                    current_chunk = paragraph

        # Add the last chunk
        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        # If a chunk is still too long, split further by sentences
        final_chunks = []
        for chunk in chunks:
            if len(chunk) <= max_chars_per_chunk:
                final_chunks.append(chunk)
            else:
                # Split by sentences
                sentences = re.split(r"[.!?。！？]\s+", chunk)
                current_sub_chunk = ""

                for sentence in sentences:
                    if (
                        len(current_sub_chunk) + len(sentence) + 2 > max_chars_per_chunk
                        and current_sub_chunk
                    ):
                        final_chunks.append(current_sub_chunk.strip())
                        current_sub_chunk = sentence
                    else:
                        if current_sub_chunk:
                            current_sub_chunk += ". " + sentence
                        else:
                            current_sub_chunk = sentence

                if current_sub_chunk.strip():
                    final_chunks.append(current_sub_chunk.strip())

        return final_chunks

    async def translate_text(
        self, text: str, target_language: str, source_language: Optional[str] = None
    ) -> str:
        """
        Translate text to target language

        Args:
            text: Text to translate
            target_language: Target language code
            source_language: Source language code (optional, auto-detected)

        Returns:
            Translated text
        """
        try:
            if not self.client:
                logger.warning("OpenAI API not available, cannot translate")
                return text

            # Detect source language
            if not source_language:
                source_language = self._detect_source_language(text)

            # If source and target language are the same, return directly
            if source_language == target_language:
                return text

            source_lang_name = self.language_map.get(source_language, source_language)
            target_lang_name = self.language_map.get(target_language, target_language)

            logger.info(
                f"Starting translation: {source_lang_name} -> {target_lang_name}"
            )

            # Estimate text length to decide if chunking is needed
            if len(text) > 3000:
                logger.info(
                    f"Text is long ({len(text)} chars), enabling chunked translation"
                )
                return await self._translate_with_chunks(
                    text, target_lang_name, source_lang_name
                )
            else:
                return await self._translate_single_text(
                    text, target_lang_name, source_lang_name
                )

        except Exception as e:
            logger.error(f"Translation failed: {str(e)}")
            return text

    async def _translate_single_text(
        self, text: str, target_lang_name: str, source_lang_name: str
    ) -> str:
        """Translate a single text chunk"""
        system_prompt = f"""You are a professional translation expert. Please translate the {source_lang_name} text accurately to {target_lang_name}.

Translation requirements:
- Keep the original formatting and structure (including paragraph breaks, headings, etc.)
- Accurately convey the original meaning with natural and fluent language
- Maintain the accuracy of professional terms
- Do not add explanations or notes
- If Markdown formatting is encountered, keep the formatting unchanged"""

        user_prompt = f"""Please translate the following {source_lang_name} text to {target_lang_name}:

{text}

Only return the translated result, do not add any explanations."""

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=4000,
                temperature=0.1,
            )

            return response.choices[0].message.content

        except Exception as e:
            logger.error(f"Single text translation failed: {e}")
            return text

    async def _translate_with_chunks(
        self, text: str, target_lang_name: str, source_lang_name: str
    ) -> str:
        """Translate long text in chunks"""
        chunks = self._smart_chunk_text(text, max_chars_per_chunk=4000)
        logger.info(f"Split into {len(chunks)} chunks for translation")

        translated_chunks = []

        for i, chunk in enumerate(chunks):
            logger.info(f"Translating chunk {i + 1}/{len(chunks)}...")

            system_prompt = f"""You are a professional translation expert. Please translate the {source_lang_name} text accurately to {target_lang_name}.

This is part {i + 1} of the full document, out of {len(chunks)} parts.

Translation requirements:
- Keep the original formatting and structure
- Accurately convey the original meaning with natural and fluent language
- Maintain the accuracy of professional terms
- Do not add explanations or notes
- Maintain coherence with the surrounding text"""

            user_prompt = f"""Please translate the following {source_lang_name} text to {target_lang_name}:

{chunk}

Only return the translated result."""

            try:
                response = self.client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    max_tokens=4000,
                    temperature=0.1,
                )

                translated_chunk = response.choices[0].message.content
                translated_chunks.append(translated_chunk)

            except Exception as e:
                logger.error(f"Failed to translate chunk {i + 1}: {e}")
                # Keep the original text on failure
                translated_chunks.append(chunk)

        # Merge translation results
        return "\n\n".join(translated_chunks)

    def should_translate(self, source_language: str, target_language: str) -> bool:
        """Determine if translation is needed"""
        if not source_language or not target_language:
            return False

        # Normalize language code
        source_lang = source_language.lower().strip()
        target_lang = target_language.lower().strip()

        # If languages are the same, no translation needed
        if source_lang == target_lang:
            return False

        # Handle special cases for Chinese
        chinese_variants = ["zh", "zh-cn", "zh-hans", "chinese"]
        if source_lang in chinese_variants and target_lang in chinese_variants:
            return False

        return True
