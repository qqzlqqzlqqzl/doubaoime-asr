from __future__ import annotations

from difflib import SequenceMatcher


def _common_prefix_len(left: str, right: str) -> int:
    size = min(len(left), len(right))
    for index in range(size):
        if left[index] != right[index]:
            return index
    return size


def merge_with_overlap(left: str, right: str, min_overlap: int = 6) -> str:
    if not left:
        return right
    if not right:
        return left
    if right in left:
        return left
    if left.endswith(right):
        return left

    max_overlap = min(len(left), len(right))
    for size in range(max_overlap, min_overlap - 1, -1):
        if left.endswith(right[:size]):
            return left + right[size:]
    return left + right


class TranscriptAccumulator:
    def __init__(self) -> None:
        self.committed = ""
        self.current = ""

    def update(self, text: str, *, is_final: bool = False) -> str:
        text = text.strip()
        if not text:
            return self.text

        if not self.current:
            self.current = text
        elif text == self.current:
            pass
        elif text.startswith(self.current):
            self.current = text
        elif self.current.startswith(text):
            # Ignore shorter interim revisions unless the service marks them final.
            if is_final:
                self.current = text
        else:
            prefix = _common_prefix_len(self.current, text)
            enough_shared_prefix = prefix >= min(len(self.current), len(text)) * 0.55
            similarity = SequenceMatcher(None, self.current, text).ratio()
            plausible_revision = (
                (enough_shared_prefix or similarity >= 0.72)
                and len(text) >= len(self.current) * 0.45
            )
            if plausible_revision:
                self.current = text
            else:
                self.commit()
                self.current = text

        if is_final:
            self.commit()
        return self.text

    def commit(self) -> None:
        if self.current:
            self.committed = merge_with_overlap(self.committed, self.current)
            self.current = ""

    @property
    def text(self) -> str:
        return merge_with_overlap(self.committed, self.current)
