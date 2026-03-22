from __future__ import annotations

import re
from collections import Counter

from pipeline.normalizers.base import BaseNormalizer
from pipeline.schemas.blocks import ContentBlock, TableBlock, TextBlock
from pipeline.schemas.canonical import CanonicalDocument


class CleaningNormalizer(BaseNormalizer):
    """Deterministic content cleaning normalizer."""

    name = "cleaning_normalizer"

    def normalize(self, doc: CanonicalDocument) -> CanonicalDocument:
        """Clean content blocks in-place. Returns the same doc."""
        cleaned_blocks: list[ContentBlock] = []
        for block in doc.content_blocks:
            cleaned = self._clean_block(block)
            if cleaned is not None:
                cleaned_blocks.append(cleaned)

        doc.content_blocks = cleaned_blocks

        # Detect and flag repeated headers/footers across blocks
        self._detect_repeated_text(doc)

        return doc

    def _clean_block(self, block: ContentBlock) -> ContentBlock | None:
        """Clean a single content block. Returns None to drop it."""
        if isinstance(block, TextBlock):
            cleaned = self._clean_text(block.content)
            if not cleaned or len(cleaned.split()) < 2:
                return None
            return TextBlock(content=cleaned, language=block.language)

        if isinstance(block, TableBlock):
            return self._clean_table(block)

        # HeadingBlock, CodeBlock, ImageBlock, ListBlock — pass through
        if hasattr(block, "content"):
            content = getattr(block, "content", "")
            if isinstance(content, str):
                cleaned = self._clean_text(content)
                if not cleaned:
                    return None
                # Return a copy with cleaned content
                data = block.model_dump()
                data["content"] = cleaned
                return type(block)(**data)

        return block

    def _clean_text(self, text: str) -> str:
        """Apply all text cleaning rules."""
        if not text:
            return text

        # 1. Strip zero-width characters
        text = re.sub(r"[\u200b\u200c\u200d\ufeff\u00ad]", "", text)

        # 2. Normalize Unicode spaces to regular spaces
        text = re.sub(r"[\u00a0\u2000-\u200a\u202f\u205f\u3000]", " ", text)

        # 3. Fix broken hyphenation from OCR/PDF extraction (word-\nword)
        text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)

        # 4. Collapse multiple newlines to double
        text = re.sub(r"\n{3,}", "\n\n", text)

        # 5. Collapse multiple spaces to single
        text = re.sub(r" {2,}", " ", text)

        # 6. Remove isolated single characters on their own line (OCR noise)
        text = re.sub(r"(?m)^\s*[^a-zA-Z0-9\n]\s*$", "", text)

        # 7. Remove excessive punctuation runs (OCR noise like ..... or ===)
        text = re.sub(r"([.=\-_*#])\1{4,}", r"\1\1\1", text)

        # 8. Strip Confluence/wiki macro syntax
        text = re.sub(r"\{(?:panel|status|code|expand|toc|anchor|color|noformat)(?::[^}]*)?\}", "", text)

        # 9. Strip common auto-generated footers
        text = re.sub(
            r"(?i)(?:^|\n)(?:page \d+ of \d+|confidential|draft|internal use only)\s*$",
            "",
            text,
        )

        # 10. Final trim
        text = text.strip()
        return text

    def _clean_table(self, block: TableBlock) -> TableBlock | None:
        """Clean a table block — remove empty rows/columns.

        Drops trivial tables: 0-1 rows with a single short/numeric header
        (common artifact from Docling spreadsheet extraction).
        """
        # Drop trivial empty tables: single header, no real data
        if not block.rows and block.headers:
            if len(block.headers) <= 1:
                hdr = block.headers[0].strip() if block.headers else ""
                # Drop if header is empty, very short, or purely numeric
                if not hdr or len(hdr) < 4:
                    return None
                try:
                    float(hdr.replace(",", "").replace(" ", ""))
                    return None
                except ValueError:
                    pass

        if not block.rows:
            return block

        # Remove completely empty rows
        cleaned_rows = [
            row for row in block.rows
            if any(cell.strip() for cell in row)
        ]

        if not cleaned_rows:
            return None

        # Remove completely empty columns
        if block.headers and cleaned_rows:
            num_cols = len(block.headers)
            non_empty_cols = set()
            for row in cleaned_rows:
                for i, cell in enumerate(row):
                    if i < num_cols and cell.strip():
                        non_empty_cols.add(i)

            # Only filter if some columns are entirely empty
            if len(non_empty_cols) < num_cols and non_empty_cols:
                sorted_cols = sorted(non_empty_cols)
                headers = [block.headers[i] for i in sorted_cols if i < len(block.headers)]
                rows = [
                    [row[i] for i in sorted_cols if i < len(row)]
                    for row in cleaned_rows
                ]
                return TableBlock(
                    headers=headers,
                    rows=rows,
                    markdown=block.markdown,
                    caption=block.caption,
                )

        return TableBlock(
            headers=block.headers,
            rows=cleaned_rows,
            markdown=block.markdown,
            caption=block.caption,
        )

    def _detect_repeated_text(self, doc: CanonicalDocument) -> None:
        """Detect text blocks that appear identically ≥3 times (headers/footers).

        Tags the document metadata with detected repeated blocks.
        """
        text_blocks = [
            (i, b.content.strip())
            for i, b in enumerate(doc.content_blocks)
            if isinstance(b, TextBlock) and b.content.strip()
        ]

        if len(text_blocks) < 6:
            return

        # Count occurrence of each text
        text_counts = Counter(text for _, text in text_blocks)
        repeated = {
            text for text, count in text_counts.items()
            if count >= 3 and len(text.split()) < 20  # short repeated text = likely header/footer
        }

        if repeated:
            doc.metadata["detected_repeated_text"] = list(repeated)
            # Remove the repeated blocks
            indices_to_remove = {
                i for i, text in text_blocks if text in repeated
            }
            doc.content_blocks = [
                b for idx, b in enumerate(doc.content_blocks)
                if idx not in indices_to_remove
            ]
