import tempfile
import unittest
from pathlib import Path
from journal.pipeline import ingest
from journal.obsidian import JournalError
class Model:
    def summarize(self,date,content): return '- synthetic'
class Store:
    def __init__(self): self.docs={}
    def save(self,doc,summary): self.docs[doc['id']]=(doc,summary)
class PipelineTests(unittest.TestCase):
    def test_single_and_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'2025-01-01.md'; path.write_text('- [ ] synthetic')
            store=Store()
            self.assertEqual(ingest(path,tmp,Model(),store),('succeeded',1))
            self.assertEqual(store.docs[str(path.resolve())][0]['document_date'],'2025-01-01')
            ingest(path,tmp,Model(),store)
            self.assertEqual(len(store.docs),1)
            path.write_text('')
            self.assertEqual(ingest(path,tmp,Model(),store),('skipped',0))

    def test_failure_never_writes(self):
        from journal.model import LocalModel
        class Broken:
            def summarize(self,*args): raise JournalError('model_unavailable')
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'2025-01-01.md'; path.write_text('synthetic')
            store=Store()
            for model in (Broken(), LocalModel(context_budget=1)):
                with self.assertRaises(JournalError): ingest(path,tmp,model,store)
                self.assertFalse(store.docs)

    def test_safe_cli_errors(self):
        import contextlib, io
        from unittest.mock import patch
        import ingest_journal
        output=io.StringIO()
        with contextlib.redirect_stderr(output), patch('ingest_journal.clients', side_effect=RuntimeError('private-sentinel')):
            self.assertEqual(ingest_journal.main(['obsidian','private-sentinel']),1)
        self.assertNotIn('private-sentinel',output.getvalue())
        output=io.StringIO()
        with contextlib.redirect_stderr(output):
            with self.assertRaises(SystemExit): ingest_journal.main(['private-sentinel','x'])
        self.assertNotIn('private-sentinel',output.getvalue())
