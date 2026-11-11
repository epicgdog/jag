"""Backend RPC client; never include provider errors in output."""
import datetime as dt
import base64
import json
import httpx
from journal.model import MODEL
from journal.obsidian import JournalError

class Storage:
    def __init__(self, url, key, client=None):
        if not url or not url.startswith('https://') or not key:
            raise JournalError('storage_configuration')
        headers = {'apikey': key}
        if not key.startswith('sb_secret_'):
            try:
                parts = key.split('.')
                if len(parts) != 3:
                    raise ValueError()
                claims = json.loads(base64.urlsafe_b64decode(parts[1] + '=' * (-len(parts[1]) % 4)))
                if claims.get('role') != 'service_role':
                    raise ValueError()
            except (ValueError, TypeError, UnicodeError):
                raise JournalError('storage_configuration') from None
            headers['Authorization'] = 'Bearer ' + key
        self.url = url.rstrip('/') + '/rest/v1/rpc/'
        self.client = client or httpx.Client(timeout=30, follow_redirects=False, trust_env=False, headers=headers)
        if client is not None:
            self.client.headers.update(headers)
    def rpc(self, name, payload):
        for attempt in range(3):
            try:
                response = self.client.post(self.url + name, json=payload)
            except httpx.TransportError:
                if attempt < 2: continue
                raise JournalError('storage_unavailable') from None
            if response.status_code in (429, 500, 502, 503, 504) and attempt < 2: continue
            if response.status_code >= 300:
                raise JournalError('storage_unavailable')
            return response
        raise JournalError('storage_unavailable')
    def ready(self):
        try:
            if self.rpc('journal_ingest_ready', {}).json() is not True:
                raise JournalError('storage_unavailable')
        except ValueError:
            raise JournalError('storage_unavailable') from None
    def save(self, doc, summary):
        document = {k: doc.get(k) for k in ('source','id','document_date','title','content','source_updated_at')}
        self.rpc('ingest_journal', {'p_document': document, 'p_summary': {'summary':summary, 'model':MODEL, 'generated_at':dt.datetime.now(dt.timezone.utc).isoformat()}, 'p_tasks':doc['tasks']})
