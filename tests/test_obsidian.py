import tempfile
import unittest
from pathlib import Path
from journal.obsidian import JournalError, read_obsidian, resolve_date, tasks_from_markdown

class ObsidianTests(unittest.TestCase):
    def test_dates(self):
        self.assertEqual(resolve_date(['12/31/2025']), '2025-12-31')
        self.assertEqual(resolve_date(['2024-02-29']), '2024-02-29')
        for values in ([], ['2023-02-29'], ['2025-01-01', '2025-01-02']):
            with self.assertRaises(JournalError): resolve_date(values)
        self.assertEqual(resolve_date(['invalid'], '2025-01-02'), '2025-01-02')

    def test_tasks(self):
        body = '- [ ] one\n  - [X] two ^xyz\n- [ ] one\n\n```\n- [ ] ignored\n```\n\n    - [ ] ignored\n'
        tasks = tasks_from_markdown(body)
        self.assertEqual(len(tasks), 3)
        self.assertEqual(tasks[1], {'id': 'block:xyz', 'text': 'two', 'checked': True})
        self.assertNotEqual(tasks[0]['id'], tasks[2]['id'])
        self.assertEqual(tasks[0]['id'], tasks_from_markdown(body.replace('[ ] one', '[x] one'))[0]['id'])
        self.assertNotEqual(tasks[0]['id'], tasks_from_markdown('- [ ] edited')[0]['id'])

    def test_paths_and_frontmatter(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'root'; root.mkdir()
            a = root / '2025-12-31.md'; a.write_text('---\ndate: 2025-12-31\n---\n- [ ] task\n')
            doc = read_obsidian(a, root)
            self.assertEqual(doc['id'], str(a.resolve()))
            self.assertEqual(doc['document_date'], '2025-12-31')
            outside = Path(tmp) / 'outside.md'; outside.write_text('')
            (root / 'escape.md').symlink_to(outside)
            with self.assertRaises(JournalError): read_obsidian(root / 'escape.md', root)

    def test_code_dates_and_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            entry = root / '2025-01-01.md'
            entry.write_text('Text\n\n```\nDate: 2020-01-01\n```\n\n    Date: 2019-01-01\n')
            self.assertEqual(read_obsidian(entry, root)['document_date'], '2025-01-01')
            blank = root / 'blank.md'
            for text in ('   \n', '---\ndate: 2020-01-01\n---\n  \n'):
                blank.write_text(text)
                self.assertTrue(read_obsidian(blank, root)['empty'])
