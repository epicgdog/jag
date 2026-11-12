"""Private Markdown snapshots and deterministic chunks with an injected size bound."""
from dataclasses import dataclass, field
from pathlib import Path
import re
import stat

from journal.obsidian import JournalError, split_frontmatter

CHUNK_VERSION = 'markdown-v2-ollama-bytes'
CHUNK_BYTES = 512
OVERLAP_BYTES = 64


@dataclass(repr=False)
class Snapshot:
    path: Path
    root: Path
    body: str = field(repr=False)
    stamp: tuple

    def unchanged(self):
        current = read_snapshot(self.path, self.root)
        if current.stamp != self.stamp or current.body != self.body:
            raise JournalError('source_changed')


def read_snapshot(reference, directory):
    try:
        root = Path(directory).resolve(strict=True)
        path = Path(reference).resolve(strict=True)
        if not root.is_dir() or not path.is_relative_to(root) or path.suffix.lower() != '.md':
            raise JournalError('invalid_path')
        before = path.stat()
        if not stat.S_ISREG(before.st_mode):
            raise JournalError('invalid_path')
        text = path.read_text(encoding='utf-8')
        after = path.stat()
        stamp = lambda s: (s.st_dev, s.st_ino, s.st_mtime_ns, s.st_size)
        if stamp(before) != stamp(after):
            raise JournalError('source_changed')
        _, body = split_frontmatter(text)
        return Snapshot(path, root, body, stamp(after))
    except (OSError, UnicodeError, RuntimeError):
        raise JournalError('read_failed') from None


def chunk_markdown(body, count_tokens, budget=CHUNK_BYTES, overlap=OVERLAP_BYTES):
    """Return original text slices within count_tokens' bound, preferring Markdown boundaries."""
    if type(budget) is not int or type(overlap) is not int or not 0 <= overlap < budget:
        raise JournalError('chunk_configuration')
    if not body.strip():
        return []

    def fitting_prefix(text, limit):
        low, high = 0, len(text)
        while low < high:
            middle = (low + high + 1) // 2
            if count_tokens(text[:middle]) <= limit:
                low = middle
            else:
                high = middle - 1
        while low and count_tokens(text[:low]) > limit:
            low -= 1
        return low

    chunks = []
    start = previous_end = 0
    while start < len(body):
        length = fitting_prefix(body[start:], budget)
        if not length:
            raise JournalError('chunk_token_limit')
        end = start + length
        if end < len(body):
            boundaries = [m.end() for m in re.finditer(r'\n\s*\n|\n(?=#{1,6} )', body[start:end])]
            preferred = [position for position in boundaries if position >= length // 2]
            if preferred and start + preferred[-1] > previous_end:
                end = start + preferred[-1]
        if end <= previous_end:
            raise JournalError('chunk_no_progress')
        text = body[start:end]
        if count_tokens(text) > budget:
            raise JournalError('chunk_token_limit')
        chunks.append(text)
        if end == len(body):
            break
        previous_end = end
        # Use the same size bound for overlap; slices never split Unicode bytes.
        suffix_start = end
        if overlap:
            low, high = start + 1, end
            while low < high:
                mid = (low + high) // 2
                if count_tokens(body[mid:end]) <= overlap:
                    high = mid
                else:
                    low = mid + 1
            suffix_start = low
        start = suffix_start
    return chunks
