"""
Text chunking for embedding.

Splits documents into overlapping chunks of ~500 tokens. This is critical
for search quality — embedding an entire 50-page PDF produces a diluted
vector that matches nothing well. Chunking lets each piece of content
have a focused, searchable embedding.

Strategy: recursive character splitting
  1. Try to split on paragraph breaks (\n\n)
  2. Then on single newlines (\n)
  3. Then on sentences (. ! ?)
  4. Then on spaces (words)
  5. Last resort: hard character split
"""

from __future__ import annotations

from dataclasses import dataclass

import tiktoken


@dataclass
class Chunk:
    """A chunk of text with its position metadata."""

    text: str
    index: int          # Chunk number within the document
    start_char: int     # Character offset in original document
    end_char: int       # End character offset
    token_count: int    # Approximate token count


class TextChunker:
    """
    Splits text into overlapping chunks optimized for embedding.

    Args:
        chunk_size: Target number of tokens per chunk (default 500).
        chunk_overlap: Number of overlapping tokens between chunks (default 50).
        model: Tiktoken encoding model for token counting.
    """

    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        model: str = "cl100k_base",
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self._enc = tiktoken.get_encoding(model)
        self._separators = ["\n\n", "\n", ". ", "! ", "? ", " "]

    def chunk(self, text: str) -> list[Chunk]:
        """Split text into overlapping chunks."""
        if not text.strip():
            return []

        token_count = len(self._enc.encode(text))

        # If the text fits in a single chunk, return as-is
        if token_count <= self.chunk_size:
            return [
                Chunk(
                    text=text,
                    index=0,
                    start_char=0,
                    end_char=len(text),
                    token_count=token_count,
                )
            ]

        # Recursive split
        raw_chunks = self._split_recursive(text, self._separators)

        # Merge small chunks and apply overlap
        return self._merge_with_overlap(raw_chunks, text)

    def _split_recursive(self, text: str, separators: list[str]) -> list[str]:
        """Recursively split text using progressively finer separators."""
        if not separators:
            # Last resort: hard split by characters (approximate tokens)
            avg_chars_per_token = max(1, len(text) // max(1, len(self._enc.encode(text))))
            target_chars = self.chunk_size * avg_chars_per_token
            return [
                text[i : i + target_chars]
                for i in range(0, len(text), target_chars)
            ]

        sep = separators[0]
        remaining_seps = separators[1:]

        parts = text.split(sep)

        # If splitting didn't help (only 1 part), try the next separator
        if len(parts) <= 1:
            return self._split_recursive(text, remaining_seps)

        # Group parts back together into chunk-sized groups
        result = []
        current = ""
        for part in parts:
            candidate = current + sep + part if current else part
            if len(self._enc.encode(candidate)) > self.chunk_size and current:
                result.append(current)
                current = part
            else:
                current = candidate

        if current:
            result.append(current)

        # Recursively split any chunks that are still too large
        final = []
        for chunk_text in result:
            if len(self._enc.encode(chunk_text)) > self.chunk_size:
                final.extend(self._split_recursive(chunk_text, remaining_seps))
            else:
                final.append(chunk_text)

        return final

    def _merge_with_overlap(self, raw_chunks: list[str], original: str) -> list[Chunk]:
        """Merge very small chunks and create overlapping windows."""
        chunks: list[Chunk] = []
        current_pos = 0

        for i, text in enumerate(raw_chunks):
            # Find the actual position in the original text
            start = original.find(text, current_pos)
            if start == -1:
                start = current_pos
            end = start + len(text)

            # Add overlap from the previous chunk
            if i > 0 and self.chunk_overlap > 0:
                # Grab tokens from the end of the previous chunk
                prev_text = raw_chunks[i - 1]
                prev_tokens = self._enc.encode(prev_text)
                overlap_tokens = prev_tokens[-self.chunk_overlap :]
                overlap_text = self._enc.decode(overlap_tokens)
                text = overlap_text + " " + text
                start = max(0, start - len(overlap_text))

            token_count = len(self._enc.encode(text))

            chunks.append(
                Chunk(
                    text=text.strip(),
                    index=i,
                    start_char=start,
                    end_char=end,
                    token_count=token_count,
                )
            )

            current_pos = end

        return chunks

    def count_tokens(self, text: str) -> int:
        """Count the number of tokens in a text string."""
        return len(self._enc.encode(text))
