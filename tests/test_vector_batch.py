import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import ingest_all_vectors as batch
from journal.obsidian import JournalError
from journal.updater import update_file
from test_updater import Director, Model, Store


class VectorBatchTests(unittest.TestCase):
    def fixture(self, directory):
        root = Path(directory)
        (root / 'sub').mkdir()
        (root / '.hidden').mkdir()
        (root / 'one.md').write_text('SYNTHETIC_PRIVATE_SENTINEL')
        (root / 'sub' / 'two.MD').write_text('Synthetic second')
        (root / '.hidden' / 'ignored.md').write_text('Synthetic hidden')
        (root / 'attachment.txt').write_text('Synthetic ignored')
        (root / 'alias.md').symlink_to(root / 'one.md')
        return batch.discover(root)

    def test_discovery_batch_rerun_and_safe_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root, paths = self.fixture(directory)
            self.assertEqual(len(paths), 2)
            store = Store()
            def local_update(path, root, model, storage, dry_run):
                return update_file(path, root, model, storage, dry_run, Director())
            with patch.object(batch, 'update_file', side_effect=local_update):
                output = []
                for _ in range(2):
                    self.assertEqual(batch.run(root, paths, Model(), store, output=output.append), 0)
                self.assertEqual(len(store.writes), 4)
                self.assertEqual(batch.run(root, paths, Model(), store, True, output.append), 0)
                self.assertEqual(len(store.writes), 4)
            text = '\n'.join(output)
            self.assertNotIn(directory, text)
            self.assertNotIn('SYNTHETIC_PRIVATE_SENTINEL', text)
            self.assertIn('written=0', text)
            self.assertIn('succeeded=2', text)

    def test_file_failure_continues_and_shared_failure_stops(self):
        for code, expected_unprocessed in [('parent_missing', 0), ('model_unavailable', 1)]:
            output = []
            with patch.object(batch, 'update_file', side_effect=[JournalError(code), ('succeeded', 1, 1)]) as update:
                self.assertEqual(batch.run('/synthetic', ['a.md', 'b.md'], None, None, output=output.append), 1)
            self.assertEqual(update.call_count, 2 - expected_unprocessed)
            self.assertIn(f'unprocessed={expected_unprocessed}', output[-1])

    def test_interruption_and_unexpected_error_are_safe(self):
        for error, unprocessed in [(KeyboardInterrupt(), 2), (ValueError('PRIVATE_SENTINEL'), 0)]:
            output = []
            with patch.object(batch, 'update_file', side_effect=error):
                self.assertEqual(batch.run('/synthetic', ['a.md', 'b.md'], None, None, output=output.append), 1)
            self.assertIn(f'unprocessed={unprocessed}', output[-1])
            self.assertNotIn('PRIVATE_SENTINEL', '\n'.join(output))

    def test_empty_main_avoids_services(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(batch, 'load_config'), patch.object(batch, 'clients') as clients:
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(batch.main(['--directory', directory]), 0)
                clients.assert_not_called()
                self.assertIn('discovered=0', output.getvalue())

    def test_discovery_failure_is_safe(self):
        with patch.object(batch, 'load_config'), patch.object(batch, 'discover', side_effect=JournalError('discovery_failed')):
            with contextlib.redirect_stderr(io.StringIO()) as output:
                self.assertEqual(batch.main(['--directory', '/synthetic/not-opened']), 1)
        self.assertEqual(output.getvalue(), 'failed code=discovery_failed\n')

    def test_main_closes_clients_and_forwards_dry_run(self):
        from unittest.mock import Mock
        model, storage = Mock(), Mock()
        with patch.object(batch, 'load_config'), patch.object(batch, 'discover', return_value=('/synthetic', ['a.md'])):
            with patch.object(batch, 'clients', return_value=(model, storage)), patch.object(batch, 'run', return_value=0) as run:
                self.assertEqual(batch.main(['--directory', '/synthetic', '--dry-run']), 0)
        run.assert_called_once_with('/synthetic', ['a.md'], model, storage, True)
        model.close.assert_called_once()
        storage.client.close.assert_called_once()
