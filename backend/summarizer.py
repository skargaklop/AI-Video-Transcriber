import os
import re
import openai
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class Summarizer:
    """Text summarizer, uses OpenAI API to generate multi-language summaries"""

    REASONING_EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh"}

    def __init__(
        self,
        api_key: str = None,
        base_url: str = None,
        model: str = None,
        reasoning_effort: str = None,
    ):
        """
        Initialize the summarizer.

        Priority: arguments > environment variables.
        When model is specified, it is used as both fast_model and advanced_model.
        """
        effective_key = api_key or os.getenv("OPENAI_API_KEY")
        effective_url = base_url or os.getenv("OPENAI_BASE_URL")

        if not effective_key:
            logger.warning(
                "OPENAI_API_KEY environment variable is not set, summary feature will not be available"
            )

        if effective_key:
            kwargs = {"api_key": effective_key}
            if effective_url:
                kwargs["base_url"] = effective_url
                logger.info(f"OpenAI client initialized, base_url={effective_url}")
            else:
                logger.info("OpenAI client initialized using default endpoint")
            self.client = openai.OpenAI(**kwargs)
        else:
            self.client = None

        # Allow frontend to specify model, overriding hardcoded gpt-3.5-turbo / gpt-4o
        self.fast_model = model or "gpt-3.5-turbo"
        self.advanced_model = model or "gpt-4o"
        self.reasoning_effort = self._normalize_reasoning_effort(reasoning_effort)

        # Supported language mappings
        self.language_map = {
            "en": "English",
            "zh": "Chinese (Simplified)",
            "es": "Español",
            "fr": "Français",
            "de": "Deutsch",
            "it": "Italiano",
            "pt": "Português",
            "ru": "Русский",
            "uk": "Українська",
            "ja": "日本語",
            "ko": "한국어",
            "ar": "العربية",
        }

    def _normalize_reasoning_effort(
        self, reasoning_effort: Optional[str]
    ) -> Optional[str]:
        normalized = (reasoning_effort or "").strip().lower()
        return normalized if normalized in self.REASONING_EFFORTS else None

    def _base_model_name(self, model: str) -> str:
        return (model or "").strip().lower().split("/")[-1]

    def _supports_reasoning_effort(self, model: str) -> bool:
        base = self._base_model_name(model)
        return base.startswith(("gpt-5", "o1", "o3", "o4"))

    def _uses_max_completion_tokens(self, model: str) -> bool:
        return self._supports_reasoning_effort(model)

    def _should_send_temperature(self, model: str) -> bool:
        if not self._supports_reasoning_effort(model):
            return True
        base = self._base_model_name(model)
        return self.reasoning_effort == "none" and base.startswith(
            ("gpt-5.4", "gpt-5.2")
        )

    def _chat_completion_create(
        self,
        model: str,
        messages: list,
        max_tokens: int,
        temperature: Optional[float] = None,
    ):
        kwargs = {
            "model": model,
            "messages": messages,
        }

        if self._uses_max_completion_tokens(model):
            kwargs["max_completion_tokens"] = max_tokens
        else:
            kwargs["max_tokens"] = max_tokens

        if self.reasoning_effort and self._supports_reasoning_effort(model):
            kwargs["reasoning_effort"] = self.reasoning_effort

        if temperature is not None and self._should_send_temperature(model):
            kwargs["temperature"] = temperature

        while True:
            try:
                return self.client.chat.completions.create(**kwargs)
            except Exception as e:
                message = str(e).lower()
                if (
                    "max_tokens" in message
                    and "max_completion_tokens" in message
                    and "max_tokens" in kwargs
                ):
                    kwargs["max_completion_tokens"] = kwargs.pop("max_tokens")
                    continue
                if (
                    "unsupported parameter" in message
                    and "temperature" in message
                    and "temperature" in kwargs
                ):
                    kwargs.pop("temperature", None)
                    continue
                if (
                    "unsupported parameter" in message
                    and "reasoning_effort" in message
                    and "reasoning_effort" in kwargs
                ):
                    kwargs.pop("reasoning_effort", None)
                    continue
                raise

    async def optimize_transcript(self, raw_transcript: str) -> str:
        """
        Optimize transcript text: fix typos, split into paragraphs by meaning
        Supports automatic chunking for long texts

        Args:
            raw_transcript: Original transcript text

        Returns:
            Optimized transcript text (Markdown format)
        """
        try:
            if not self.client:
                logger.warning("OpenAI API unavailable, returning original transcript")
                return raw_transcript

            # Preprocessing: remove only timestamps and meta info, keep all spoken/repeated content
            preprocessed = self._remove_timestamps_and_meta(raw_transcript)
            # Use JS strategy: chunk by character length (closer to tokens limit, avoids estimation errors)
            detected_lang_code = self._detect_transcript_language(preprocessed)
            max_chars_per_chunk = 4000  # Align with JS: max ~4000 chars per chunk

            if len(preprocessed) > max_chars_per_chunk:
                logger.info(
                    f"Text is long ({len(preprocessed)} chars), enabling chunk optimization"
                )
                return await self._format_long_transcript_in_chunks(
                    preprocessed, detected_lang_code, max_chars_per_chunk
                )
            else:
                return await self._format_single_chunk(preprocessed, detected_lang_code)

        except Exception as e:
            logger.error(f"Failed to optimize transcript text: {str(e)}")
            logger.info("Returning original transcript text")
            return raw_transcript

    def _estimate_tokens(self, text: str) -> int:
        """
        Improved token estimation algorithm
        More conservative estimation, considers system prompt and formatting overhead
        """
        # More conservative estimation: consider token inflation in actual use
        chinese_chars = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
        english_words = len(
            [word for word in text.split() if word.isascii() and word.isalpha()]
        )

        # Calculate base tokens
        base_tokens = chinese_chars * 1.5 + english_words * 1.3

        # Consider markdown format, timestamps etc overhead (approx 30% extra)
        format_overhead = len(text) * 0.15

        # Consider system prompt overhead (approx 2000-3000 tokens)
        system_prompt_overhead = 2500

        total_estimated = int(base_tokens + format_overhead + system_prompt_overhead)

        return total_estimated

    async def _optimize_single_chunk(self, raw_transcript: str) -> str:
        """
        Optimize a single text chunk
        """
        detected_lang = self._detect_transcript_language(raw_transcript)
        lang_instruction = self._get_language_instruction(detected_lang)

        system_prompt = f"""You are a professional text editing expert. Please optimize the provided video transcript text.

Special attention: This could be an interview, conversation, or speech. If there are multiple speakers, you must maintain the original perspective of each speaker.

Requirements:
1. **Strictly maintain the original language ({lang_instruction}), absolutely do not translate into other languages**
2. **Completely remove all timestamp markers (e.g., [00:00 - 00:05])**
3. **Intelligently identify and reconstruct complete sentences split by timestamps**, grammatically incomplete sentence fragments need to be merged with context
4. Correct obvious typos and grammatical errors
5. Divide the reconstructed complete sentences into natural paragraphs according to semantics and logical meaning
6. Separate paragraphs with blank lines
7. **Strictly keep the original meaning unchanged, do not add or delete actual content**
8. **Absolutely do not change personal pronouns (e.g., I, you, he, she, etc.)**
9. **Maintain the original perspective and context of each speaker**
10. **Identify conversation structure: interviewer uses "you", interviewee uses "I/we", never confuse them**
11. Ensure each sentence is grammatically complete, and the language is fluent and natural

Processing strategy:
- Prioritize identifying incomplete sentence fragments (e.g., ending with prepositions, conjunctions, adjectives)
- Look at adjacent text fragments, merge to form complete sentences
- Re-segment sentences, ensuring each sentence is grammatically complete
- Re-paragraph according to topics and logic

Paragraphing requirements:
- Paragraph by topic and logical meaning, each paragraph containing 1-8 related sentences
- Single paragraph length not exceeding 400 characters
- Avoid too many short paragraphs, merge related content
- Start a new paragraph when a complete idea or viewpoint is expressed

Output format:
- Plain text paragraphs, no timestamps or formatting markers
- Each sentence has complete structure
- Each paragraph discusses one main topic
- Paragraphs are separated by blank lines

Important reminder: This is {lang_instruction} content, please completely optimize using {lang_instruction}, focusing on solving the incoherence caused by sentences split by timestamps! Be sure to do reasonable paragraphing to avoid overly long paragraphs!

**Key requirement: This could be an interview conversation, absolutely do not change any personal pronouns or speaker perspective! The interviewer says "you", the interviewee says "I/we", this must be strictly maintained!**"""

        user_prompt = f"""Please optimize the following {lang_instruction} video transcript text into fluent paragraph text:

{raw_transcript}

Key tasks:
1. Remove all timestamp markers
2. Identify and reconstruct complete sentences that were split
3. Ensure each sentence is grammatically complete and coherent in meaning
4. Re-paragraph by meaning, separated by blank lines
5. Keep the {lang_instruction} language unchanged

Paragraphing guidance:
- Paragraph by topic and logical meaning, each paragraph containing 1-8 related sentences
- Single paragraph length not exceeding 400 characters
- Avoid too many short paragraphs, merge related content
- Ensure there are explicit blank lines between paragraphs

Please pay special attention to fixing incomplete sentences caused by timestamp splitting, and make reasonable paragraph divisions!"""

        response = self.client.chat.completions.create(
            model=self.fast_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=4000,  # Align with JS: max tokens for optimization/formatting phase ≈ 4000
            temperature=0.1,
        )

        return response.choices[0].message.content

    async def _optimize_with_chunks(self, raw_transcript: str, max_tokens: int) -> str:
        """
        Chunk optimization for long text
        """
        detected_lang = self._detect_transcript_language(raw_transcript)
        lang_instruction = self._get_language_instruction(detected_lang)

        # Split original transcript into paragraphs (keep timestamps as split reference)
        chunks = self._split_into_chunks(raw_transcript, max_tokens)
        logger.info(f"Split into {len(chunks)} chunks for processing")

        optimized_chunks = []

        for i, chunk in enumerate(chunks):
            logger.info(f"Optimizing chunk {i + 1}/{len(chunks)}...")

            system_prompt = f"""You are a professional text editing expert. Please perform a simple optimization on this transcript text segment.

This is part {i + 1} of the complete transcript, which has {len(chunks)} parts in total.

Simple optimization requirements:
1. **Strictly maintain the original language ({lang_instruction})**, absolutely do not translate
2. **Only correct obvious typos and grammatical errors**
3. **Slightly adjust sentence fluency**, but do not rewrite significantly
4. **Maintain original structure and length**, do not do complex paragraph reorganization
5. **Keep original meaning 100% unchanged**

Note: This is just preliminary cleaning, do not do complex rewriting or reorganization."""

            user_prompt = f"""Simply optimize the following {lang_instruction} text segment (only fix typos and grammar):

{chunk}

Output the cleaned text, keeping the original structure."""

            try:
                response = self.client.chat.completions.create(
                    model=self.fast_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    max_tokens=1200,  # Adapt to 4000 total tokens limit
                    temperature=0.1,
                )

                optimized_chunk = response.choices[0].message.content
                optimized_chunks.append(optimized_chunk)

            except Exception as e:
                logger.error(f"Failed to optimize chunk {i + 1}: {e}")
                # Fallback to basic cleanup
                cleaned_chunk = self._basic_transcript_cleanup(chunk)
                optimized_chunks.append(cleaned_chunk)

        # Merge all optimized chunks
        merged_text = "\n\n".join(optimized_chunks)

        # Do a secondary paragraph organization on the merged text
        logger.info("Performing final paragraph organization...")
        final_result = await self._final_paragraph_organization(
            merged_text, lang_instruction
        )

        logger.info("Chunk optimization complete")
        return final_result

    # ===== JS openaiService.js port: chunking/context/dedup/formatting =====

    def _ensure_markdown_paragraphs(self, text: str) -> str:
        """Ensure Markdown paragraphs have blank lines, empty lines after headings, and compress excess blank lines."""
        if not text:
            return text
        formatted = text.replace("\r\n", "\n")

        # Add empty line after heading
        formatted = re.sub(
            r"(^#{1,6}\s+.*)\n([^\n#])", r"\1\n\n\2", formatted, flags=re.M
        )
        # Compress ≥3 newlines to 2
        formatted = re.sub(r"\n{3,}", "\n\n", formatted)
        # Strip leading/trailing newlines
        formatted = re.sub(r"^\n+", "", formatted)
        formatted = re.sub(r"\n+$", "", formatted)
        return formatted

    async def _format_single_chunk(
        self, chunk_text: str, transcript_language: str = "zh"
    ) -> str:
        """Single chunk optimization (correction+formatting), adheres to 4000 tokens limit."""
        # Construct system/user prompts consistent with JS version
        if transcript_language == "zh":
            prompt = (
                "Please intelligently optimize and format the following audio transcript text, requirements:\n\n"
                "**Content Optimization (Correctness First):**\n"
                "1. Error correction (transcription errors/typos/homophones/proper nouns)\n"
                "2. Moderately improve grammar, complete incomplete sentences, keep original meaning and language unchanged\n"
                "3. Spoken language processing: keep natural spoken language and repeated expressions, do not delete content, only add necessary punctuation\n"
                "4. **Absolutely do not change personal pronouns (I, you, etc.) and speaker perspective**\n\n"
                "**Paragraphing Rules:**\n"
                "- Paragraph by topic and logical meaning, each paragraph containing 1-8 related sentences\n"
                "- Single paragraph length not exceeding 400 characters\n"
                "- Avoid too many short paragraphs, merge related content\n\n"
                "**Formatting Requirements:** Markdown paragraphs, separated by blank lines\n\n"
                f"Original transcript text:\n{chunk_text}"
            )
            system_prompt = (
                "You are a professional audio transcript formatting assistant, correcting errors, improving fluency and layout formatting, "
                "you must keep the original meaning, do not delete spoken language/repetitions/details; only remove timestamps or meta info. "
                "Absolutely do not change personal pronouns or speaker perspective. This could be an interview conversation, interviewer uses 'you', interviewee uses 'I/we'."
            )
        else:
            prompt = (
                "Please intelligently optimize and format the following audio transcript text:\n\n"
                "Content Optimization (Accuracy First):\n"
                "1. Error Correction (typos, homophones, proper nouns)\n"
                "2. Moderate grammar improvement, complete incomplete sentences, keep original language/meaning\n"
                "3. Speech processing: keep natural fillers and repetitions, do NOT remove content; only add punctuation if needed\n"
                "4. **NEVER change pronouns (I, you, he, she, etc.) or speaker perspective**\n\n"
                "Segmentation Rules: Group 1-8 related sentences per paragraph by topic/logic; paragraph length NOT exceed 400 characters; avoid too many short paragraphs\n\n"
                "Format: Markdown paragraphs with blank lines between paragraphs\n\n"
                f"Original transcript text:\n{chunk_text}"
            )
            system_prompt = (
                "You are a professional transcript formatting assistant. Fix errors and improve fluency "
                "without changing meaning or removing any content; only timestamps/meta may be removed; keep Markdown paragraphs with blank lines. "
                "NEVER change pronouns or speaker perspective. This may be an interview: interviewer uses 'you', interviewee uses 'I/we'."
            )

        try:
            response = self.client.chat.completions.create(
                model=self.fast_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=4000,  # Align with JS: max tokens for optimization/formatting phase ≈ 4000
                temperature=0.1,
            )
            optimized_text = response.choices[0].message.content or ""
            # Remove headings like "# Transcript" / "## Transcript"
            optimized_text = self._remove_transcript_heading(optimized_text)
            enforced = self._enforce_paragraph_max_chars(
                optimized_text.strip(), max_chars=400
            )
            return self._ensure_markdown_paragraphs(enforced)
        except Exception as e:
            logger.error(f"Single chunk optimization failed: {e}")
            return self._apply_basic_formatting(chunk_text)

    def _smart_split_long_chunk(self, text: str, max_chars_per_chunk: int) -> list:
        """Safely split super long text at sentence/space boundaries."""
        chunks = []
        pos = 0
        while pos < len(text):
            end = min(pos + max_chars_per_chunk, len(text))
            if end < len(text):
                # Prioritize sentence boundaries
                sentence_endings = ["。", "！", "？", ".", "!", "?"]
                best = -1
                for ch in sentence_endings:
                    idx = text.rfind(ch, pos, end)
                    if idx > best:
                        best = idx
                if best > pos + int(max_chars_per_chunk * 0.7):
                    end = best + 1
                else:
                    # Secondary: space boundaries
                    space_idx = text.rfind(" ", pos, end)
                    if space_idx > pos + int(max_chars_per_chunk * 0.8):
                        end = space_idx
            chunks.append(text[pos:end].strip())
            pos = end
        return [c for c in chunks if c]

    def _find_safe_cut_point(self, text: str) -> int:
        """Find a safe cutting point (paragraph > sentence > phrase)."""

        # Paragraph
        p = text.rfind("\n\n")
        if p > 0:
            return p + 2
        # Sentence
        last_sentence_end = -1
        for m in re.finditer(r"[。！？\.!?]\s*", text):
            last_sentence_end = m.end()
        if last_sentence_end > 20:
            return last_sentence_end
        # Phrase
        last_phrase_end = -1
        for m in re.finditer(r"[，；,;]\s*", text):
            last_phrase_end = m.end()
        if last_phrase_end > 20:
            return last_phrase_end
        return len(text)

    def _find_overlap_between_texts(self, text1: str, text2: str) -> str:
        """Detect overlapping content between adjacent paragraphs for deduplication."""
        max_len = min(len(text1), len(text2))
        # Try progressively from long to short
        for length in range(max_len, 19, -1):
            suffix = text1[-length:]
            prefix = text2[:length]
            if suffix == prefix:
                cut = self._find_safe_cut_point(prefix)
                if cut > 20:
                    return prefix[:cut]
                return suffix
        return ""

    def _apply_basic_formatting(self, text: str) -> str:
        """Fallback when AI fails: join by sentences, paragraphs ≤250 chars, double newline separation."""
        if not text or not text.strip():
            return text

        parts = re.split(r"([。！？\.!?]+\s*)", text)
        sentences = []
        current = ""
        for i, part in enumerate(parts):
            if i % 2 == 0:
                current += part
            else:
                current += part
                if current.strip():
                    sentences.append(current.strip())
                    current = ""
        if current.strip():
            sentences.append(current.strip())
        paras = []
        cur = ""
        sentence_count = 0
        for s in sentences:
            candidate = (cur + " " + s).strip() if cur else s
            sentence_count += 1
            # Improved paragraphing logic: consider sentence count and length
            should_break = False
            if len(candidate) > 400 and cur:  # Paragraph too long
                should_break = True
            elif (
                len(candidate) > 200 and sentence_count >= 3
            ):  # Medium length and enough sentences
                should_break = True
            elif sentence_count >= 6:  # Too many sentences
                should_break = True

            if should_break:
                paras.append(cur.strip())
                cur = s
                sentence_count = 1
            else:
                cur = candidate
        if cur.strip():
            paras.append(cur.strip())
        return self._ensure_markdown_paragraphs("\n\n".join(paras))

    async def _format_long_transcript_in_chunks(
        self, raw_transcript: str, transcript_language: str, max_chars_per_chunk: int
    ) -> str:
        """Smart chunking + context + deduplication to synthesize optimized text (JS strategy port)."""

        # First split by sentences, assemble chunks no larger than max_chars_per_chunk
        parts = re.split(r"([。！？\.!?]+\s*)", raw_transcript)
        sentences = []
        buf = ""
        for i, part in enumerate(parts):
            if i % 2 == 0:
                buf += part
            else:
                buf += part
                if buf.strip():
                    sentences.append(buf.strip())
                    buf = ""
        if buf.strip():
            sentences.append(buf.strip())

        chunks = []
        cur = ""
        for s in sentences:
            candidate = (cur + " " + s).strip() if cur else s
            if len(candidate) > max_chars_per_chunk and cur:
                chunks.append(cur.strip())
                cur = s
            else:
                cur = candidate
        if cur.strip():
            chunks.append(cur.strip())

        # Secondary safe split for chunks that are still too long
        final_chunks = []
        for c in chunks:
            if len(c) <= max_chars_per_chunk:
                final_chunks.append(c)
            else:
                final_chunks.extend(
                    self._smart_split_long_chunk(c, max_chars_per_chunk)
                )

        logger.info(f"Text split into {len(final_chunks)} chunks for processing")

        optimized = []
        for i, c in enumerate(final_chunks):
            chunk_with_context = c
            if i > 0:
                prev_tail = final_chunks[i - 1][-100:]
                marker = (
                    f"[Continued from above: {prev_tail}]"
                    if transcript_language == "zh"
                    else f"[Context continued: {prev_tail}]"
                )
                chunk_with_context = marker + "\n\n" + c
            try:
                oc = await self._format_single_chunk(
                    chunk_with_context, transcript_language
                )
                # Remove context marker
                oc = re.sub(
                    r"^\[(Continued from above|Context continued)：?:?.*?\]\s*",
                    "",
                    oc,
                    flags=re.S,
                )
                optimized.append(oc)
            except Exception as e:
                logger.warning(
                    f"Optimization of chunk {i + 1} failed, using basic formatting: {e}"
                )
                optimized.append(self._apply_basic_formatting(c))

        # Adjacent chunk deduplication
        deduped = []
        for i, c in enumerate(optimized):
            cur_txt = c
            if i > 0 and deduped:
                prev = deduped[-1]
                overlap = self._find_overlap_between_texts(prev[-200:], cur_txt[:200])
                if overlap:
                    cur_txt = cur_txt[len(overlap) :].lstrip()
                    if not cur_txt:
                        continue
            if cur_txt.strip():
                deduped.append(cur_txt)

        merged = "\n\n".join(deduped)
        merged = self._remove_transcript_heading(merged)
        enforced = self._enforce_paragraph_max_chars(merged, max_chars=400)
        return self._ensure_markdown_paragraphs(enforced)

    def _remove_timestamps_and_meta(self, text: str) -> str:
        """Remove only timestamp lines and obvious meta info (titles, detected language, etc.), keep original spoken language/repetitions."""
        lines = text.split("\n")
        kept = []
        for line in lines:
            s = line.strip()
            # Skip timestamps and meta info
            if s.startswith("**[") and s.endswith("]**"):
                continue
            if s.startswith("# "):
                # Skip top-level title (usually video title, can be added back at the end)
                continue
            if s.startswith("**Detected Language:**") or s.startswith(
                "**Language Probability:**"
            ):
                continue
            kept.append(line)
        # Normalize blank lines
        cleaned = "\n".join(kept)
        return cleaned

    def _enforce_paragraph_max_chars(self, text: str, max_chars: int = 400) -> str:
        """Split by paragraph and ensure each paragraph does not exceed max_chars, split into multiple paragraphs by sentence boundaries if necessary."""
        if not text:
            return text

        paragraphs = [p for p in re.split(r"\n\s*\n", text) if p is not None]
        new_paragraphs = []
        for para in paragraphs:
            para = para.strip()
            if len(para) <= max_chars:
                new_paragraphs.append(para)
                continue
            # Sentence splitting
            parts = re.split(r"([。！？\.!?]+\s*)", para)
            sentences = []
            buf = ""
            for i, part in enumerate(parts):
                if i % 2 == 0:
                    buf += part
                else:
                    buf += part
                    if buf.strip():
                        sentences.append(buf.strip())
                        buf = ""
            if buf.strip():
                sentences.append(buf.strip())
            cur = ""
            for s in sentences:
                candidate = (cur + (" " if cur else "") + s).strip()
                if len(candidate) > max_chars and cur:
                    new_paragraphs.append(cur)
                    cur = s
                else:
                    cur = candidate
            if cur:
                new_paragraphs.append(cur)
        return "\n\n".join([p.strip() for p in new_paragraphs if p is not None])

    def _remove_transcript_heading(self, text: str) -> str:
        """Remove heading lines titled Transcript (any # level) at the beginning or in paragraphs, without changing the body."""
        if not text:
            return text

        # Remove heading lines like '## Transcript', '# Transcript Text', '### transcript'
        lines = text.split("\n")
        filtered = []
        for line in lines:
            stripped = line.strip()
            if re.match(r"^#{1,6}\s*transcript(\s+text)?\s*$", stripped, flags=re.I):
                continue
            filtered.append(line)
        return "\n".join(filtered)

    def _split_into_chunks(self, text: str, max_tokens: int) -> list:
        """
        Intelligently split original transcript text into appropriately sized chunks
        Strategy: First extract plain text, split naturally by sentences and paragraphs
        """
        # 1. First extract pure text content (remove timestamps, titles, etc.)
        pure_text = self._extract_pure_text(text)

        # 2. Split by sentences, maintaining sentence integrity
        sentences = self._split_into_sentences(pure_text)

        # 3. Assemble chunks according to token limit
        chunks = []
        current_chunk = []
        current_tokens = 0

        for sentence in sentences:
            sentence_tokens = self._estimate_tokens(sentence)

            # Check if it can be added to the current chunk
            if current_tokens + sentence_tokens > max_tokens and current_chunk:
                # Current chunk is full, save and start new chunk
                chunks.append(self._join_sentences(current_chunk))
                current_chunk = [sentence]
                current_tokens = sentence_tokens
            else:
                # Add to current chunk
                current_chunk.append(sentence)
                current_tokens += sentence_tokens

        # Add the last chunk
        if current_chunk:
            chunks.append(self._join_sentences(current_chunk))

        return chunks

    def _extract_pure_text(self, raw_transcript: str) -> str:
        """
        Extract pure text from raw transcript, removing timestamps and metadata
        """
        lines = raw_transcript.split("\n")
        text_lines = []

        for line in lines:
            line = line.strip()
            # Skip timestamps, titles, and metadata
            if (
                line.startswith("**[")
                and line.endswith("]**")
                or line.startswith("#")
                or line.startswith("**Detected Language:**")
                or line.startswith("**Language Probability:**")
                or not line
            ):
                continue
            text_lines.append(line)

        return " ".join(text_lines)

    def _split_into_sentences(self, text: str) -> list:
        """
        Split text into sentences, considering differences between Chinese and English
        """

        # Chinese and English sentence ending punctuation
        sentence_endings = r"[.!?。！？;；]+"

        # Split sentences, preserving sentence-ending punctuation
        parts = re.split(f"({sentence_endings})", text)

        sentences = []
        current = ""

        for i, part in enumerate(parts):
            if re.match(sentence_endings, part):
                # This is a sentence ending punctuation, add to current sentence
                current += part
                if current.strip():
                    sentences.append(current.strip())
                current = ""
            else:
                # This is sentence content
                current += part

        # Handle trailing content without ending punctuation
        if current.strip():
            sentences.append(current.strip())

        return [s for s in sentences if s.strip()]

    def _join_sentences(self, sentences: list) -> str:
        """
        Recombine sentences into paragraphs
        """
        return " ".join(sentences)

    def _basic_transcript_cleanup(self, raw_transcript: str) -> str:
        """
        Basic transcript cleanup: remove timestamps and title information
        Fallback mechanism when GPT optimization fails
        """
        lines = raw_transcript.split("\n")
        cleaned_lines = []

        for line in lines:
            # Skip timestamp lines
            if line.strip().startswith("**[") and line.strip().endswith("]**"):
                continue
            # Skip title lines
            if line.strip().startswith("# ") or line.strip().startswith("## "):
                continue
            # Skip metadata lines like language detection
            if line.strip().startswith(
                "**Detected Language:**"
            ) or line.strip().startswith("**Language Probability:**"):
                continue
            # Keep non-empty text lines
            if line.strip():
                cleaned_lines.append(line.strip())

        # Recombine sentences and intelligently segment into paragraphs
        text = " ".join(cleaned_lines)

        # Smarter sentence splitting, considering Chinese/English differences

        # Split by periods, question marks, exclamation marks
        sentences = re.split(r"[.!?。！？]", text)
        sentences = [s.strip() for s in sentences if s.strip()]

        paragraphs = []
        current_paragraph = []

        for i, sentence in enumerate(sentences):
            if sentence:
                current_paragraph.append(sentence)

                # Smart paragraphing conditions:
                # 1. Break every 3 sentences (basic rule)
                # 2. Force break when encountering topic transition keywords
                # 3. Avoid overly long paragraphs
                topic_change_keywords = [
                    "首先",
                    "其次",
                    "然后",
                    "接下来",
                    "另外",
                    "此外",
                    "最后",
                    "总之",
                    "first",
                    "second",
                    "third",
                    "next",
                    "also",
                    "however",
                    "finally",
                    "现在",
                    "那么",
                    "所以",
                    "因此",
                    "但是",
                    "然而",
                    "now",
                    "so",
                    "therefore",
                    "but",
                    "however",
                ]

                should_break = False

                # Check if paragraph should be broken
                if len(current_paragraph) >= 3:  # Basic length condition
                    should_break = True
                elif (
                    len(current_paragraph) >= 2
                ):  # Shorter but encounters topic transition
                    for keyword in topic_change_keywords:
                        if sentence.lower().startswith(keyword.lower()):
                            should_break = True
                            break

                if should_break or len(current_paragraph) >= 4:  # Maximum length limit
                    # Combine current paragraph
                    paragraph_text = ". ".join(current_paragraph)
                    if not paragraph_text.endswith("."):
                        paragraph_text += "."
                    paragraphs.append(paragraph_text)
                    current_paragraph = []

        # Add remaining sentences
        if current_paragraph:
            paragraph_text = ". ".join(current_paragraph)
            if not paragraph_text.endswith("."):
                paragraph_text += "."
            paragraphs.append(paragraph_text)

        return "\n\n".join(paragraphs)

    async def _final_paragraph_organization(
        self, text: str, lang_instruction: str
    ) -> str:
        """
        Perform final paragraph organization on merged text
        Using improved prompts and engineering validation
        """
        try:
            # Estimate text length, use chunking if too long
            estimated_tokens = self._estimate_tokens(text)
            if estimated_tokens > 3000:  # Chunk processing for very long text
                return await self._organize_long_text_paragraphs(text, lang_instruction)

            system_prompt = f"""You are a professional {lang_instruction} text paragraph organization expert. Your task is to reorganize paragraphs according to semantics and logic.

🎯 **Core Principles**:
1. **Strictly maintain the original language ({lang_instruction})**, do not translate
2. **Keep all content complete**, do not delete or add any information
3. **Segment by semantic logic**: each paragraph should revolve around a complete idea or topic
4. **Strictly control paragraph length**: each paragraph must not exceed 250 words
5. **Maintain natural flow**: paragraphs should have logical connections

📏 **Segmentation Standards**:
- **Semantic completeness**: each paragraph tells a complete concept or event
- **Moderate length**: 3-7 sentences, each paragraph must not exceed 250 words
- **Logical boundaries**: segment at topic transitions, time changes, viewpoint shifts
- **Natural breakpoints**: follow the speaker's natural pauses and logic

⚠️ **Strictly prohibited**:
- Creating giant paragraphs exceeding 250 words
- Forcibly merging unrelated content
- Breaking up complete stories or narratives

Output format: separate paragraphs with blank lines."""

            user_prompt = f"""Please reorganize the paragraph structure of the following {lang_instruction} text. Strictly segment according to semantics and logic, ensuring each paragraph does not exceed 200 words:

{text}

Re-paragraphed text:"""

            response = self.client.chat.completions.create(
                model=self.advanced_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=4000,  # Align with JS: paragraph organization stage max tokens ≈ 4000
                temperature=0.05,  # Lower temperature for higher consistency
            )

            organized_text = response.choices[0].message.content

            # Engineering validation: check paragraph lengths
            validated_text = self._validate_paragraph_lengths(organized_text)

            return validated_text

        except Exception as e:
            logger.error(f"Final paragraph organization failed: {e}")
            # Fall back to basic paragraph handling on failure
            return self._basic_paragraph_fallback(text)

    async def _organize_long_text_paragraphs(
        self, text: str, lang_instruction: str
    ) -> str:
        """
        Organize paragraphs for very long text by processing in chunks
        """
        try:
            # Split by existing paragraphs
            paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
            organized_chunks = []

            current_chunk = []
            current_tokens = 0
            max_chunk_tokens = 2500  # Adapt to 4000 tokens limit chunk size

            for para in paragraphs:
                para_tokens = self._estimate_tokens(para)

                if current_tokens + para_tokens > max_chunk_tokens and current_chunk:
                    # Process current chunk
                    chunk_text = "\n\n".join(current_chunk)
                    organized_chunk = await self._organize_single_chunk(
                        chunk_text, lang_instruction
                    )
                    organized_chunks.append(organized_chunk)

                    current_chunk = [para]
                    current_tokens = para_tokens
                else:
                    current_chunk.append(para)
                    current_tokens += para_tokens

                    # Process last chunk
            if current_chunk:
                chunk_text = "\n\n".join(current_chunk)
                organized_chunk = await self._organize_single_chunk(
                    chunk_text, lang_instruction
                )
                organized_chunks.append(organized_chunk)

            return "\n\n".join(organized_chunks)

        except Exception as e:
            logger.error(f"Long text paragraph organization failed: {e}")
            return self._basic_paragraph_fallback(text)

    async def _organize_single_chunk(self, text: str, lang_instruction: str) -> str:
        """
        Organize paragraphs for a single text chunk
        """
        system_prompt = f"""You are a {lang_instruction} paragraph organization expert. Reorganize paragraphs by semantics, ensuring each paragraph does not exceed 200 words.

Core requirements:
1. Strictly maintain the original {lang_instruction} language
2. Organize by semantic logic, one theme per paragraph
3. Each paragraph must not exceed 250 words
4. Separate paragraphs with blank lines
5. Keep content complete, do not reduce information"""

        user_prompt = f"""Re-paragraph the following text in {lang_instruction}, ensuring each paragraph does not exceed 200 words:

{text}"""

        response = self.client.chat.completions.create(
            model=self.advanced_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=1200,  # Adapt to 4000 total tokens limit
            temperature=0.05,
        )

        return response.choices[0].message.content

    def _validate_paragraph_lengths(self, text: str) -> str:
        """
        Validate paragraph lengths, attempt to split overly long paragraphs
        """
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        validated_paragraphs = []

        for para in paragraphs:
            word_count = len(para.split())

            if word_count > 300:  # Split if paragraph exceeds 300 words
                logger.warning(
                    f"Detected overly long paragraph ({word_count} words), attempting to split"
                )
                # Attempt to split long paragraphs by sentences
                split_paras = self._split_long_paragraph(para)
                validated_paragraphs.extend(split_paras)
            else:
                validated_paragraphs.append(para)

        return "\n\n".join(validated_paragraphs)

    def _split_long_paragraph(self, paragraph: str) -> list:
        """
        Split overly long paragraphs
        """

        # Split by sentences
        sentences = re.split(r"[.!?。！？]\s+", paragraph)
        sentences = [s.strip() + "." for s in sentences if s.strip()]

        split_paragraphs = []
        current_para = []
        current_words = 0

        for sentence in sentences:
            sentence_words = len(sentence.split())

            if current_words + sentence_words > 200 and current_para:
                # Current paragraph reaches length limit
                split_paragraphs.append(" ".join(current_para))
                current_para = [sentence]
                current_words = sentence_words
            else:
                current_para.append(sentence)
                current_words += sentence_words

        # Add last paragraph
        if current_para:
            split_paragraphs.append(" ".join(current_para))

        return split_paragraphs

    def _basic_paragraph_fallback(self, text: str) -> str:
        """
        Basic paragraph fallback mechanism
        When GPT organization fails, use simple rule-based segmentation
        """

        # Remove excess blank lines
        text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)

        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        basic_paragraphs = []

        for para in paragraphs:
            word_count = len(para.split())

            if word_count > 250:
                # Split long paragraphs by sentences
                split_paras = self._split_long_paragraph(para)
                basic_paragraphs.extend(split_paras)
            elif word_count < 30 and basic_paragraphs:
                # Merge short paragraph with previous one (if combined <= 200 words)
                last_para = basic_paragraphs[-1]
                combined_words = len(last_para.split()) + word_count

                if combined_words <= 200:
                    basic_paragraphs[-1] = last_para + " " + para
                else:
                    basic_paragraphs.append(para)
            else:
                basic_paragraphs.append(para)

        return "\n\n".join(basic_paragraphs)

    def _format_custom_summary_prompt(
        self, custom_prompt: str = "", language_name: str = ""
    ) -> str:
        custom_prompt = (custom_prompt or "").strip()
        parts = []
        if custom_prompt:
            parts.append(
                "Additional user instructions for this summary. Follow them unless they conflict "
                "with the required output language, factual accuracy, or the source transcript:\n"
                f"{custom_prompt}"
            )
        if language_name:
            parts.append(f"Summary Language: {language_name}")
        return "\n\n" + "\n\n".join(parts) if parts else ""

    async def summarize(
        self,
        transcript: str,
        target_language: str = "zh",
        video_title: str = None,
        custom_prompt: str = "",
    ) -> str:
        """
        Generate summary for video transcript

        Args:
            transcript: Transcript text
            target_language: Target language code

        Returns:
            Summary text (Markdown format)
        """
        try:
            if not self.client:
                logger.warning("OpenAI API is unavailable, generating fallback summary")
                return self._generate_fallback_summary(
                    transcript, target_language, video_title
                )

            # Estimate transcript length to decide if chunked summarization is needed
            estimated_tokens = self._estimate_tokens(transcript)
            from settings import load_settings

            max_summarize_tokens = load_settings().get("summary_chunk_threshold", 15000)

            if estimated_tokens <= max_summarize_tokens:
                # Direct summarization for short text
                return await self._summarize_single_text(
                    transcript, target_language, video_title, custom_prompt
                )
            else:
                # Chunked summarization for long text
                logger.info(
                    f"Text is long ({estimated_tokens} tokens), enabling chunked summarization"
                )
                return await self._summarize_with_chunks(
                    transcript,
                    target_language,
                    video_title,
                    max_summarize_tokens,
                    custom_prompt,
                )

        except Exception as e:
            logger.error(f"Failed to generate summary: {str(e)}")
            raise

    async def _summarize_single_text(
        self,
        transcript: str,
        target_language: str,
        video_title: str = None,
        custom_prompt: str = "",
    ) -> str:
        """
        Summarize a single text
        """
        # Get target language name
        language_name = self.language_map.get(target_language, "Chinese (Simplified)")

        # Build English prompts applicable to all target languages
        custom_instruction = self._format_custom_summary_prompt(
            custom_prompt, language_name
        )

        system_prompt = f"""You are a professional content analyst. Please generate a comprehensive, well-structured summary in {language_name} for the following text.

Summary Requirements:
1. Extract the main topics and core viewpoints from the text
2. Maintain clear logical structure, highlighting the core arguments
3. Include important discussions, viewpoints, and conclusions
4. Use concise and clear language
5. Appropriately preserve the speaker's expression style and key opinions

Paragraph Organization Requirements (Core):
1. **Organize by semantic and logical themes** - Start a new paragraph whenever the topic shifts, discussion focus changes, or when transitioning from one viewpoint to another
2. **Each paragraph should focus on one main point or theme**
3. **Paragraphs must be separated by blank lines (double line breaks \\n\\n)**
4. **Consider the logical flow of content and reasonably divide paragraph boundaries**

Format Requirements:
1. Use Markdown format with double line breaks between paragraphs
2. Each paragraph should be a complete logical unit
3. Write entirely in {language_name}
4. Aim for substantial content (600-1200 words when appropriate)"""

        user_prompt = f"""Based on the following content, write a comprehensive, well-structured summary in {language_name}:

{transcript}

Requirements:
- Focus on natural paragraphs, avoiding decorative headings
- Cover all key ideas and arguments, preserving important examples and data
- Ensure balanced coverage of both early and later content
- Use restrained but comprehensive language
- Organize content logically with proper paragraph breaks{custom_instruction}"""

        logger.info(f"Generating {language_name} summary...")

        # Call OpenAI API
        response = self._chat_completion_create(
            model=self.advanced_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=3500,  # Keep within safe range to avoid model limits
            temperature=0.3,
        )

        summary = response.choices[0].message.content

        return self._format_summary_with_meta(summary, target_language, video_title)

    async def _summarize_with_chunks(
        self,
        transcript: str,
        target_language: str,
        video_title: str,
        max_tokens: int,
        custom_prompt: str = "",
    ) -> str:
        """
        Summarize long text using chunking approach
        """
        language_name = self.language_map.get(target_language, "Chinese (Simplified)")

        # Use JS strategy: intelligent chunking by characters (paragraphs > sentences)
        custom_instruction = self._format_custom_summary_prompt(
            custom_prompt, language_name
        )
        chunks = self._smart_chunk_text(transcript, max_chars_per_chunk=4000)
        logger.info(f"Split into {len(chunks)} chunks for summarization")

        chunk_summaries = []

        # Generate partial summary for each chunk
        for i, chunk in enumerate(chunks):
            logger.info(f"Summarizing chunk {i + 1}/{len(chunks)}...")

            system_prompt = f"""You are a summarization expert. Please write a high-density summary for this text chunk in {language_name}.

This is part {i + 1} of {len(chunks)} of the complete content (Part {i + 1}/{len(chunks)}).

Output preferences: Focus on natural paragraphs, use minimal bullet points if necessary; highlight new information and its relationship to the main narrative; avoid vague repetition and formatted headings; moderate length (suggested 120-220 words).{custom_instruction}"""

            user_prompt = f"""[Part {i + 1}/{len(chunks)}] Summarize the key points of the following text in {language_name} (natural paragraphs preferred, minimal bullet points, 120-220 words):

{chunk}

Avoid using any subheadings or decorative separators, output content only.{custom_instruction}"""

            try:
                response = self._chat_completion_create(
                    model=self.advanced_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    max_tokens=1000,  # Increase chunk summary capacity to cover more details
                    temperature=0.3,
                )

                chunk_summary = response.choices[0].message.content
                chunk_summaries.append(chunk_summary)

            except Exception as e:
                logger.error(f"Failed to summarize chunk {i + 1}: {e}")
                raise

        # Merge all chunk summaries (with numbering), integrate hierarchically if many chunks (no subheadings)
        combined_summaries = "\n\n".join(
            [f"[Part {idx + 1}]\n" + s for idx, s in enumerate(chunk_summaries)]
        )

        logger.info("Integrating final summary...")
        if len(chunk_summaries) > 10:
            grouped_summaries = []
            for group_start in range(0, len(chunk_summaries), 10):
                group = chunk_summaries[group_start : group_start + 10]
                group_text = "\n\n".join(
                    [
                        f"[Part {group_start + idx + 1}]\n" + s
                        for idx, s in enumerate(group)
                    ]
                )
                grouped_summaries.append(
                    await self._integrate_chunk_summaries(
                        group_text, target_language, custom_prompt
                    )
                )
            grouped_text = "\n\n".join(
                [f"[Group {idx + 1}]\n" + s for idx, s in enumerate(grouped_summaries)]
            )
            final_summary = await self._integrate_chunk_summaries(
                grouped_text, target_language, custom_prompt
            )
        else:
            final_summary = await self._integrate_chunk_summaries(
                combined_summaries, target_language, custom_prompt
            )

        return self._format_summary_with_meta(
            final_summary, target_language, video_title
        )

    def _smart_chunk_text(self, text: str, max_chars_per_chunk: int = 3500) -> list:
        """Smart chunking (paragraphs then sentences), split by character limit."""
        chunks = []
        paragraphs = [p for p in text.split("\n\n") if p.strip()]
        cur = ""
        for p in paragraphs:
            candidate = (cur + "\n\n" + p).strip() if cur else p
            if len(candidate) > max_chars_per_chunk and cur:
                chunks.append(cur.strip())
                cur = p
            else:
                cur = candidate
        if cur.strip():
            chunks.append(cur.strip())

        # Secondary sentence-based split for overly long chunks

        final_chunks = []
        for c in chunks:
            if len(c) <= max_chars_per_chunk:
                final_chunks.append(c)
            else:
                sentences = [
                    s.strip() for s in re.split(r"[。！？\.!?]+", c) if s.strip()
                ]
                scur = ""
                for s in sentences:
                    candidate = (scur + "。" + s).strip() if scur else s
                    if len(candidate) > max_chars_per_chunk and scur:
                        final_chunks.append(scur.strip())
                        scur = s
                    else:
                        scur = candidate
                if scur.strip():
                    final_chunks.append(scur.strip())
        return final_chunks

    async def _integrate_chunk_summaries(
        self, combined_summaries: str, target_language: str, custom_prompt: str = ""
    ) -> str:
        """
        Integrate chunk summaries into final coherent summary
        """
        language_name = self.language_map.get(target_language, "Chinese (Simplified)")

        custom_instruction = self._format_custom_summary_prompt(
            custom_prompt, language_name
        )

        try:
            system_prompt = f"""You are a content integration expert. Please integrate multiple segmented summaries into a complete, coherent summary in {language_name}.

Integration Requirements:
1. Remove duplicate content and maintain clear logic
2. Reorganize content by themes or chronological order
3. Each paragraph must be separated by double line breaks
4. Ensure output is in Markdown format with double line breaks between paragraphs
5. Use concise and clear language
6. Form a complete content summary
7. Cover all parts comprehensively without omission{custom_instruction}"""

            user_prompt = f"""Please integrate the following segmented summaries into a complete, coherent summary in {language_name}:

{combined_summaries}

Requirements:
- Remove duplicate content and maintain clear logic
- Reorganize content by themes or chronological order
- Each paragraph must be separated by double line breaks
- Ensure output is in Markdown format with double line breaks between paragraphs
- Use concise and clear language
- Form a complete content summary{custom_instruction}"""

            response = self._chat_completion_create(
                model=self.advanced_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=2500,  # Control output size while maintaining context safety
                temperature=0.3,
            )

            return response.choices[0].message.content

        except Exception as e:
            logger.error(f"Failed to integrate summary: {e}")
            raise

    def _format_summary_with_meta(
        self, summary: str, target_language: str, video_title: str = None
    ) -> str:
        """
        Add title and metadata to summary
        """
        if video_title:
            prefix = f"# {video_title}\n\n"
        else:
            prefix = ""
        return prefix + summary

    def _generate_fallback_summary(
        self, transcript: str, target_language: str, video_title: str = None
    ) -> str:
        """
        Generate fallback summary (when OpenAI API is unavailable)

        Args:
            transcript: Transcript text
            video_title: Video title
            target_language: Target language code

        Returns:
            Fallback summary text
        """
        language_name = self.language_map.get(target_language, "Chinese (Simplified)")

        # Simple text processing to extract key information
        lines = transcript.split("\n")
        content_lines = [
            line
            for line in lines
            if line.strip() and not line.startswith("#") and not line.startswith("**")
        ]

        # Calculate approximate length
        total_chars = sum(len(line) for line in content_lines)

        # Use labels in target language
        meta_labels = self._get_summary_labels(target_language)
        fallback_labels = self._get_fallback_labels(target_language)

        # Use video title directly as main heading
        title = video_title if video_title else "Summary"

        summary = f"""# {title}

**{meta_labels["language_label"]}:** {language_name}
**{fallback_labels["notice"]}:** {fallback_labels["api_unavailable"]}



## {fallback_labels["overview_title"]}

**{fallback_labels["content_length"]}:** {fallback_labels["about"]} {total_chars} {fallback_labels["characters"]}
**{fallback_labels["paragraph_count"]}:** {len(content_lines)} {fallback_labels["paragraphs"]}

## {fallback_labels["main_content"]}

{fallback_labels["content_description"]}

{fallback_labels["suggestions_intro"]}

1. {fallback_labels["suggestion_1"]}
2. {fallback_labels["suggestion_2"]}
3. {fallback_labels["suggestion_3"]}

## {fallback_labels["recommendations"]}

- {fallback_labels["recommendation_1"]}
- {fallback_labels["recommendation_2"]}


<br/>

<p style="color: #888; font-style: italic; text-align: center; margin-top: 16px;"><em>{fallback_labels["fallback_disclaimer"]}</em></p>"""

        return summary

    def _get_current_time(self) -> str:
        """Get current time string"""
        from datetime import datetime

        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def get_supported_languages(self) -> dict:
        """
        Get supported language list

        Returns:
            Mapping of language code to language name
        """
        return self.language_map.copy()

    def _detect_transcript_language(self, transcript: str) -> str:
        """
        Detect primary language of transcript

        Args:
            transcript: Transcript text

        Returns:
            Detected language code
        """
        # Simple language detection: look for language markers in transcript
        if "**Detected Language:**" in transcript:
            # Extract detected language from Whisper transcript
            lines = transcript.split("\n")
            for line in lines:
                if "**Detected Language:**" in line:
                    # Extract language code, e.g., "**Detected Language:** en"
                    lang = line.split(":")[-1].strip()
                    return lang

        # If no language marker found, use simple character-based detection
        # Calculate ratios of English chars, Chinese chars, etc.
        total_chars = len(transcript)
        if total_chars == 0:
            return "en"  # Default to English

        # Count Chinese characters
        chinese_chars = sum(1 for char in transcript if "\u4e00" <= char <= "\u9fff")
        chinese_ratio = chinese_chars / total_chars

        # Count English letters
        english_chars = sum(
            1 for char in transcript if char.isascii() and char.isalpha()
        )
        english_ratio = english_chars / total_chars

        # Determine based on ratios
        if chinese_ratio > 0.3:
            return "zh"
        elif english_ratio > 0.3:
            return "en"
        else:
            return "en"  # Default to English

    def _get_language_instruction(self, lang_code: str) -> str:
        """
        Get language instruction name for optimization prompts based on language code

        Args:
            lang_code: Language code

        Returns:
            Language name
        """
        language_instructions = {
            "en": "English",
            "zh": "中文",
            "ja": "日本語",
            "ko": "한국어",
            "es": "Español",
            "fr": "Français",
            "de": "Deutsch",
            "it": "Italiano",
            "pt": "Português",
            "ru": "Русский",
            "uk": "Українська",
            "ar": "العربية",
        }
        return language_instructions.get(lang_code, "English")

    def _get_summary_labels(self, lang_code: str) -> dict:
        """
        Get multilingual labels for summary page

        Args:
            lang_code: Language code

        Returns:
            Dictionary of labels
        """
        labels = {
            "en": {
                "language_label": "Summary Language",
                "disclaimer": "This summary is automatically generated by AI for reference only",
            },
            "zh": {
                "language_label": "Summary Language",
                "disclaimer": "This summary is automatically generated by AI for reference only",
            },
            "ja": {
                "language_label": "要約言語",
                "disclaimer": "この要約はAIによって自動生成されており、参考用です",
            },
            "ko": {
                "language_label": "요약 언어",
                "disclaimer": "이 요약은 AI에 의해 자동 생성되었으며 참고용입니다",
            },
            "es": {
                "language_label": "Idioma del Resumen",
                "disclaimer": "Este resumen es generado automáticamente por IA, solo para referencia",
            },
            "fr": {
                "language_label": "Langue du Résumé",
                "disclaimer": "Ce résumé est généré automatiquement par IA, à titre de référence uniquement",
            },
            "de": {
                "language_label": "Zusammenfassungssprache",
                "disclaimer": "Diese Zusammenfassung wird automatisch von KI generiert, nur zur Referenz",
            },
            "it": {
                "language_label": "Lingua del Riassunto",
                "disclaimer": "Questo riassunto è generato automaticamente dall'IA, solo per riferimento",
            },
            "pt": {
                "language_label": "Idioma do Resumo",
                "disclaimer": "Este resumo é gerado automaticamente por IA, apenas para referência",
            },
            "ru": {
                "language_label": "Язык резюме",
                "disclaimer": "Это резюме автоматически генерируется ИИ, только для справки",
            },
            "uk": {
                "language_label": "Мова зведення",
                "disclaimer": "Це зведення автоматично створене ШІ лише для довідки",
            },
            "ar": {
                "language_label": "لغة الملخص",
                "disclaimer": "هذا الملخص تم إنشاؤه تلقائياً بواسطة الذكاء الاصطناعي، للمرجع فقط",
            },
        }
        return labels.get(lang_code, labels["en"])

    def _get_fallback_labels(self, lang_code: str) -> dict:
        """
        Get multilingual labels for fallback summary

        Args:
            lang_code: Language code

        Returns:
            Dictionary of labels
        """
        labels = {
            "en": {
                "notice": "Notice",
                "api_unavailable": "OpenAI API is unavailable, this is a simplified summary",
                "overview_title": "Transcript Overview",
                "content_length": "Content Length",
                "about": "About",
                "characters": "characters",
                "paragraph_count": "Paragraph Count",
                "paragraphs": "paragraphs",
                "main_content": "Main Content",
                "content_description": "The transcript contains complete video speech content. Since AI summary cannot be generated currently, we recommend:",
                "suggestions_intro": "For detailed information, we suggest you:",
                "suggestion_1": "Review the complete transcript text for detailed information",
                "suggestion_2": "Focus on important paragraphs marked with timestamps",
                "suggestion_3": "Manually extract key points and takeaways",
                "recommendations": "Recommendations",
                "recommendation_1": "Configure OpenAI API key for better summary functionality",
                "recommendation_2": "Or use other AI services for text summarization",
                "fallback_disclaimer": "This is an automatically generated fallback summary",
            },
            "zh": {
                "notice": "Notice",
                "api_unavailable": "OpenAI API is unavailable, this is a simplified summary",
                "overview_title": "Transcript Overview",
                "content_length": "Content Length",
                "about": "About",
                "characters": "characters",
                "paragraph_count": "Paragraph Count",
                "paragraphs": "paragraphs",
                "main_content": "Main Content",
                "content_description": "The transcript contains complete video speech content. Since AI summary cannot be generated currently, we recommend:",
                "suggestions_intro": "For detailed information, we suggest you:",
                "suggestion_1": "Review the complete transcript text for detailed information",
                "suggestion_2": "Focus on important paragraphs marked with timestamps",
                "suggestion_3": "Manually extract key points and takeaways",
                "recommendations": "Recommendations",
                "recommendation_1": "Configure OpenAI API key for better summary functionality",
                "recommendation_2": "Or use other AI services for text summarization",
                "fallback_disclaimer": "This is an automatically generated fallback summary",
            },
        }
        return labels.get(lang_code, labels["en"])

    def is_available(self) -> bool:
        """
        Check if summary service is available

        Returns:
            True if OpenAI API is configured, False otherwise
        """
        return self.client is not None
