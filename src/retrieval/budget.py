"""Deterministic Token Budget Controller ensuring prompts fit within the fixed context window."""

from typing import Any, Dict, List, Optional


class TokenBudgetController:
    """
    Computes context budgets for Qwen models (num_ctx 2048 for 3B, 4096 for 7B)
    and crops ranked retrieval results deterministically to prevent silent Ollama truncations.
    """

    def __init__(self, chars_per_token: float = 3.5) -> None:
        self.chars_per_token = chars_per_token

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count from character length."""
        if not text:
            return 0
        return max(1, int(len(text) / self.chars_per_token))

    def calculate_evidence_budget(
        self,
        num_ctx: int,
        system_prompt: str,
        schema_definition: str,
        max_output_tokens: int = 500,
        safety_headroom_tokens: int = 150,
    ) -> int:
        """
        Calculate remaining token budget specifically allocated for retrieved evidence:
        budget = num_ctx - prompt_tokens - schema_tokens - max_output_tokens - headroom
        """
        system_tokens = self.estimate_tokens(system_prompt)
        schema_tokens = self.estimate_tokens(schema_definition)
        overhead = system_tokens + schema_tokens + max_output_tokens + safety_headroom_tokens
        remaining = num_ctx - overhead
        return max(0, remaining)

    def crop_chunks_to_budget(
        self,
        ranked_chunks: List[Dict[str, Any]],
        token_budget: int,
        text_key: str = "statement",
    ) -> List[Dict[str, Any]]:
        """
        Crop lowest-ranked chunks so total evidence remains strictly within the token budget.
        """
        current_tokens = 0
        accepted_chunks: List[Dict[str, Any]] = []

        for chunk in ranked_chunks:
            chunk_text = str(chunk.get(text_key, ""))
            chunk_tokens = self.estimate_tokens(chunk_text)

            if current_tokens + chunk_tokens <= token_budget:
                accepted_chunks.append(chunk)
                current_tokens += chunk_tokens
            else:
                # Discard lowest-ranked chunk rather than cutting it in half mid-statement
                break

        return accepted_chunks
