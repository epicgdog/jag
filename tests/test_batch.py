import tempfile
import unittest
from pathlib import Path
from ingest_all_journals import discover,run
from journal.obsidian import JournalError
from test_pipeline import Model, Store
class BatchTests(unittest.TestCase):
    def test_discovery_and_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'sub').mkdir(); (root/'.hidden').mkdir()
            (root/'2025-01-01.md').write_text('- [ ] synthetic')
            (root/'sub'/'2025-01-02.MD').write_text('- [x] synthetic')
            (root/'sub'/'bad.md').write_text('synthetic')
            (root/'.hidden'/'2025-01-03.md').write_text('hidden')
            (root/'alias.md').symlink_to(root/'2025-01-01.md')
            root,paths=discover(root); self.assertEqual(len(paths),3)
            out=[]; store=Store(); self.assertEqual(run(root,paths,Model(),store,out.append),1)
            self.assertEqual(len(store.docs),2); self.assertTrue(any('failed=1' in x for x in out))
            self.assertFalse(any('synthetic' in x or str(root) in x for x in out))
            out=[]; self.assertEqual(run(root,paths,Model(),None,out.append),1)
    def test_shared_failure_stops(self):
        class Broken:
            def summarize(self,*args): raise JournalError('model_unavailable')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for day in (1,2): (root/f'2025-01-0{day}.md').write_text('synthetic')
            root,paths=discover(root); out=[]; store=Store()
            self.assertEqual(run(root,paths,Broken(),store,out.append),1)
            self.assertIn('unprocessed=1',out[-1]); self.assertFalse(store.docs)
    def test_empty_and_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'root'; root.mkdir()
            self.assertEqual(discover(root)[1],[])
            outside=Path(tmp)/'outside.md'; outside.write_text('synthetic')
            (root/'escape.md').symlink_to(outside)
            with self.assertRaises(JournalError): discover(root)
    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'2025-01-01.md').write_text('synthetic')
            root,paths=discover(root); out=[]
            self.assertEqual(run(root,paths,Model(),None,out.append),0)
            self.assertIn('succeeded=1',out[-1])
    def test_interrupt_totals(self):
        class Interrupted:
            def summarize(self,*args): raise KeyboardInterrupt()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'2025-01-01.md').write_text('synthetic')
            root,paths=discover(root); out=[]
            self.assertEqual(run(root,paths,Interrupted(),None,out.append),1)
            self.assertIn('unprocessed=1',out[-1])
    def test_empty_main_no_services_and_config_root(self):
        import contextlib, io, os
        from unittest.mock import patch
        import ingest_all_journals
        with tempfile.TemporaryDirectory() as tmp:
            def config(): os.environ['OBSIDIAN_JOURNAL_DIR']=tmp
            with patch.dict(os.environ,{},clear=True), patch.object(ingest_all_journals,'load_config',side_effect=config), patch.object(ingest_all_journals,'clients',side_effect=AssertionError()), contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(ingest_all_journals.main([]),0)
                self.assertIn('discovered=0',out.getvalue())
