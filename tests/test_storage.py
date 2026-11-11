import unittest
import httpx
from journal.storage import Storage
class StorageTests(unittest.TestCase):
    def test_ready_and_save(self):
        calls=[]
        def handler(request):
            calls.append(request)
            return httpx.Response(200, json=True)
        storage=Storage('https://example.invalid','synthetic',httpx.Client(transport=httpx.MockTransport(handler)))
        storage.ready()
        storage.save({'source':'obsidian','id':'/synthetic/a.md','document_date':'2025-01-01','content':'synthetic','tasks':[]},'- synthetic')
        self.assertEqual(len(calls),2)
        self.assertTrue(str(calls[0].url).endswith('/journal_ingest_ready'))
