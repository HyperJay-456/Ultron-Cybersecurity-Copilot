"""Deterministic duplicate and overlap detection and chunk merging for M11.5 Long Response Subsystem.
Guarantees exact chunk provenance reconstruction while producing clean, seamless combined responses.
"""

from dataclasses import dataclass
import re
from typing import Optional, Tuple
from pydantic import BaseModel


class OverlapDetectionResult(BaseModel):
    """Details of overlap detection between adjacent chunks."""
    overlap_detected: bool
    overlap_type: str  # 'exact', 'sentence', 'paragraph', 'normalized_whitespace', 'meta_preface', 'none'
    overlap_length: int
    overlap_snippet: str
    cleaned_chunk: str
    original_chunk: str
    confidence: float


class ResponseMerger:
    """
    Detects and resolves accidental repetitive overlaps between sequential chunks
    without discarding legitimate repeated technical content.
    """

    # Common meta prefaces models occasionally generate upon continuation requests
    META_PREFACES = [
        re.compile(r"^(?:here is the continuation[:\s]*)+", re.IGNORECASE),
        re.compile(r"^(?:continuing from (?:above|where (?:we|i) left off)[:\s]*)+", re.IGNORECASE),
        re.compile(r"^(?:to continue(?: the (?:explanation|analysis|code))?[:\s]*)+", re.IGNORECASE),
        re.compile(r"^(?:resuming from (?:the )?interruption[:\s]*)+", re.IGNORECASE),
    ]

    def __init__(self, min_exact_overlap: int = 4, max_overlap_window: int = 400) -> None:
        self.min_exact_overlap = min_exact_overlap
        self.max_overlap_window = max_overlap_window

    def merge_chunks(self, accumulated_text: str, next_chunk: str) -> Tuple[str, OverlapDetectionResult]:
        """
        Merge next_chunk onto accumulated_text, removing accidental overlaps.
        Returns (merged_text, OverlapDetectionResult).
        """
        if not accumulated_text:
            return next_chunk, OverlapDetectionResult(
                overlap_detected=False,
                overlap_type="none",
                overlap_length=0,
                overlap_snippet="",
                cleaned_chunk=next_chunk,
                original_chunk=next_chunk,
                confidence=1.0,
            )

        if not next_chunk:
            return accumulated_text, OverlapDetectionResult(
                overlap_detected=False,
                overlap_type="none",
                overlap_length=0,
                overlap_snippet="",
                cleaned_chunk="",
                original_chunk="",
                confidence=1.0,
            )

        raw_chunk = next_chunk
        working_chunk = next_chunk

        # 1. Check and prune meta preface if present
        for pattern in self.META_PREFACES:
            m = pattern.match(working_chunk)
            if m:
                preface = m.group(0)
                working_chunk = working_chunk[len(preface):].lstrip()
                break

        # 2. Exact Suffix-Prefix overlap
        # Check window: trailing tail of accumulated_text vs leading head of working_chunk
        tail_window = accumulated_text[-self.max_overlap_window:]
        head_window = working_chunk[:self.max_overlap_window]

        exact_overlap_len = 0
        # Find longest matching suffix of tail_window that is a prefix of head_window
        max_possible = min(len(tail_window), len(head_window))
        for l in range(max_possible, self.min_exact_overlap - 1, -1):
            if tail_window.endswith(head_window[:l]):
                exact_overlap_len = l
                break

        if exact_overlap_len >= self.min_exact_overlap:
            overlap_str = head_window[:exact_overlap_len]
            cleaned = working_chunk[exact_overlap_len:]
            merged = accumulated_text + cleaned
            return merged, OverlapDetectionResult(
                overlap_detected=True,
                overlap_type="exact",
                overlap_length=exact_overlap_len,
                overlap_snippet=overlap_str,
                cleaned_chunk=cleaned,
                original_chunk=raw_chunk,
                confidence=0.99,
            )

        # 3. Sentence-level Overlap
        # If the continuation repeats the entire final sentence of accumulated_text
        sentences = re.split(r"(?<=[.!?])\s+", accumulated_text.strip())
        if sentences:
            last_sentence = sentences[-1].strip()
            if len(last_sentence) >= 15:  # Require meaningful length to avoid false positives
                # Check if working_chunk starts with last_sentence (case-insensitive / normalized)
                norm_chunk = working_chunk.lstrip()
                if norm_chunk.lower().startswith(last_sentence.lower()):
                    overlap_len = len(last_sentence)
                    cleaned = norm_chunk[overlap_len:].lstrip()
                    merged = accumulated_text + ("\n" if not accumulated_text.endswith(("\n", " ")) else "") + cleaned
                    return merged, OverlapDetectionResult(
                        overlap_detected=True,
                        overlap_type="sentence",
                        overlap_length=overlap_len,
                        overlap_snippet=last_sentence,
                        cleaned_chunk=cleaned,
                        original_chunk=raw_chunk,
                        confidence=0.95,
                    )

        # 4. Paragraph-level Overlap
        paragraphs = [p.strip() for p in accumulated_text.split("\n\n") if p.strip()]
        if paragraphs:
            last_para = paragraphs[-1]
            if len(last_para) >= 30:
                norm_chunk = working_chunk.lstrip()
                if norm_chunk.lower().startswith(last_para.lower()):
                    overlap_len = len(last_para)
                    cleaned = norm_chunk[overlap_len:].lstrip()
                    merged = accumulated_text + "\n\n" + cleaned
                    return merged, OverlapDetectionResult(
                        overlap_detected=True,
                        overlap_type="paragraph",
                        overlap_length=overlap_len,
                        overlap_snippet=last_para[:60] + "...",
                        cleaned_chunk=cleaned,
                        original_chunk=raw_chunk,
                        confidence=0.95,
                    )

        # 5. Normalized Whitespace Overlap
        # Normalize internal whitespace in tail and head to see if there is an exact token match
        tail_words = tail_window.split()
        head_words = head_window.split()
        if len(tail_words) >= 3 and len(head_words) >= 3:
            max_words = min(len(tail_words), len(head_words), 20)
            for w in range(max_words, 2, -1):
                if [tw.lower() for tw in tail_words[-w:]] == [hw.lower() for hw in head_words[:w]]:
                    # Matched w words
                    matched_phrase = " ".join(head_words[:w])
                    # Locate position in head_window
                    regex = re.compile(re.escape(head_words[0]) + r"(?:\s+" + re.escape(head_words[1]) + r")?", re.IGNORECASE)
                    match_pos = 0
                    for token in head_words[:w]:
                        idx = working_chunk.lower().find(token.lower(), match_pos)
                        if idx != -1:
                            match_pos = idx + len(token)
                    cleaned = working_chunk[match_pos:].lstrip()
                    merged = accumulated_text + " " + cleaned
                    return merged, OverlapDetectionResult(
                        overlap_detected=True,
                        overlap_type="normalized_whitespace",
                        overlap_length=len(matched_phrase),
                        overlap_snippet=matched_phrase,
                        cleaned_chunk=cleaned,
                        original_chunk=raw_chunk,
                        confidence=0.88,
                    )

        # No overlap detected; natural concatenation
        # Ensure smooth join (if accumulated_text ended mid-word without space or newline, concatenate directly;
        # otherwise preserve whitespace formatting)
        merged = accumulated_text + working_chunk
        return merged, OverlapDetectionResult(
            overlap_detected=False,
            overlap_type="none",
            overlap_length=0,
            overlap_snippet="",
            cleaned_chunk=working_chunk,
            original_chunk=raw_chunk,
            confidence=1.0,
        )
