import tempfile
import unittest
from pathlib import Path

from journal.chunks import chunk_markdown, read_snapshot
from journal.obsidian import JournalError


class ChunkTests(unittest.TestCase):
    def test_short_empty_and_frontmatter(self):
        self.assertEqual(chunk_markdown(' ', len, 10, 2), [])
        self.assertEqual(chunk_markdown('Synthetic', len, 10, 2), ['Synthetic'])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'synthetic.MD'
            path.write_text('---\ndate: 2026-01-01\n---\nSynthetic body')
            snapshot = read_snapshot(path, directory)
            self.assertEqual(snapshot.body, 'Synthetic body')
            snapshot.unchanged()
            path.write_text('Changed synthetic body')
            with self.assertRaisesRegex(JournalError, 'source_changed'):
                snapshot.unchanged()

    def test_chunks_preserve_text_and_bounds(self):
        body = '# Synthetic heading\n\n' + ''.join(f'α garden paragraph {i:03}\n\n' for i in range(40))
        chunks = chunk_markdown(body, len, 80, 10)
        self.assertEqual(chunks, chunk_markdown(body, len, 80, 10))
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(c) <= 80 for c in chunks))
        restored = chunks[0]
        for chunk in chunks[1:]:
            overlap = max(n for n in range(min(len(restored), len(chunk)) + 1)
                          if not n or restored[-n:] == chunk[:n])
            restored += chunk[overlap:]
        self.assertEqual(restored, body)

    def test_containment_and_invalid_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'root'; root.mkdir()
            outside = Path(directory) / 'outside.md'; outside.write_text('synthetic')
            (root / 'escape.md').symlink_to(outside)
            for path in [outside, root / 'escape.md', root]:
                with self.assertRaises(JournalError):
                    read_snapshot(path, root)
        with self.assertRaises(JournalError):
            chunk_markdown('synthetic', len, 10, 10)
