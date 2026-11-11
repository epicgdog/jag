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
