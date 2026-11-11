import unittest
import httpx
from journal.model import LocalModel, validate_endpoint
from journal.obsidian import JournalError

class ModelTests(unittest.TestCase):
    def client(self, handler):
        return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False, trust_env=False)
    def test_endpoint(self):
        for url in ['http://example.com:1234/v1', 'http://localhost:1234/v1?x=1', 'https://localhost:1234/v1']:
            with self.assertRaises(JournalError): validate_endpoint(url)
    def test_response_and_redirect(self):
        def response(payload, status=200):
            return LocalModel(client=self.client(lambda request: httpx.Response(status, json=payload)))
        self.assertEqual(response({'choices':[{'finish_reason':'stop','message':{'content':'- Synthetic summary'}}]}).summarize('2025-01-01','Synthetic entry'), '- Synthetic summary')
        for payload in ({'choices':[{'finish_reason':'length','message':{'content':'- incomplete'}}]}, {'choices':[{'finish_reason':'stop','message':{'content':'<think>secret</think>'}}]}, {}):
            with self.assertRaises(JournalError): response(payload).summarize('2025-01-01','x')
        with self.assertRaises(JournalError): response({}, 302).summarize('2025-01-01','x')
