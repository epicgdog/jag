import unittest
import httpx
from journal.model import LocalModel, validate_endpoint, validate_summary
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

    def test_wrapped_and_numbered_bullets(self):
        data = {'choices': [{'finish_reason': 'stop', 'message': {'content':
            '1. Completed a synthetic task\n   and felt relieved.\n\n2) Plan to walk tomorrow.'}}]}
        self.assertEqual(validate_summary(data),
                         '- Completed a synthetic task and felt relieved.\n- Plan to walk tomorrow.')

    def test_safe_failure_reasons(self):
        cases = [
            ('length', '- synthetic', 'model_response_truncated'),
            ('stop', '', 'model_response_empty'),
            ('stop', '<think>PRIVATE_SENTINEL</think>', 'model_response_reasoning'),
            ('stop', 'PRIVATE_SENTINEL', 'model_response_format'),
            ('stop', '- ' + 'PRIVATE_SENTINEL ' * 121, 'model_response_too_long'),
            ('content_filter', None, 'model_response_incomplete'),
        ]
        for finish_reason, content, expected in cases:
            with self.subTest(expected=expected):
                data = {'choices': [{'finish_reason': finish_reason, 'message': {'content': content}}]}
                with self.assertRaises(JournalError) as error:
                    validate_summary(data)
                self.assertEqual(str(error.exception), expected)
                self.assertNotIn('PRIVATE_SENTINEL', str(error.exception))
        with self.assertRaisesRegex(JournalError, '^model_invalid_response_schema$'):
            validate_summary({})
