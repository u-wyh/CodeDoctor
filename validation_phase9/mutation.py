"""Deterministic bounded numeric mutation for Phase 9 differential tests."""

import hashlib
import re
from dataclasses import dataclass
from typing import Iterable


INTEGER_TOKEN = re.compile(r"(?<!\S)[+-]?\d+(?!\S)")
MIN_INT64 = -(2**63)
MAX_INT64 = 2**63 - 1


@dataclass(frozen=True)
class MutationCandidate:
    input_text: str
    mutation_value: int
    order_hash: str
    source_test_id: str
    token_index: int

    @property
    def input_hash(self) -> str:
        return hashlib.sha256(self.input_text.encode("utf-8")).hexdigest()


def _order_hash(
    seed: int, case_id: str, source_test_id: str, token_index: int, value: int
) -> str:
    identity = f"{seed}\0{case_id}\0{source_test_id}\0{token_index}\0{value}"
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def generate_numeric_mutations(
    *,
    case_id: str,
    seed: int,
    seed_inputs: Iterable[tuple[str, str]],
    proposal_cap: int = 500,
) -> list[MutationCandidate]:
    candidates = []
    for source_test_id, input_text in seed_inputs:
        for token_index, match in enumerate(INTEGER_TOKEN.finditer(input_text)):
            original = int(match.group())
            if not MIN_INT64 <= original <= MAX_INT64:
                continue
            values = {0, 1, -1}
            if original > MIN_INT64:
                values.add(original - 1)
            if original < MAX_INT64:
                values.add(original + 1)
            for value in values:
                if value == original:
                    continue
                mutated = input_text[: match.start()] + str(value) + input_text[match.end() :]
                candidates.append(
                    MutationCandidate(
                        mutated,
                        value,
                        _order_hash(seed, case_id, source_test_id, token_index, value),
                        source_test_id,
                        token_index,
                    )
                )
    candidates.sort(key=lambda item: item.order_hash)
    unique = []
    seen = set()
    for item in candidates:
        if item.input_hash in seen:
            continue
        seen.add(item.input_hash)
        unique.append(item)
        if len(unique) == proposal_cap:
            break
    return unique
