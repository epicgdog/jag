import unittest
import httpx
from journal.storage import Storage
class StorageTests(unittest.TestCase):
    def test_ready_and_save(self):
        calls=[]
        def handler(request):
            calls.append(request)
            return httpx.Response(200, json=True)
        storage=Storage('https://example.invalid','sb_secret_synthetic',httpx.Client(transport=httpx.MockTransport(handler)))
        storage.ready()
        storage.save({'source':'obsidian','id':'/synthetic/a.md','document_date':'2025-01-01','content':'synthetic','tasks':[]},'- synthetic')
        self.assertEqual(len(calls),2)
        self.assertTrue(str(calls[0].url).endswith('/journal_ingest_ready'))

    def test_headers_and_reject_public_key(self):
        from journal.obsidian import JournalError
        calls=[]
        client=httpx.Client(transport=httpx.MockTransport(lambda r: (calls.append(r), httpx.Response(200,json=True))[1]))
        Storage('https://example.invalid', 'sb_secret_synthetic', client).ready()
        self.assertNotIn('authorization', calls[0].headers)
        self.assertEqual(calls[0].headers['apikey'], 'sb_secret_synthetic')
        with self.assertRaises(JournalError): Storage('https://example.invalid', 'sb_publishable_synthetic')
