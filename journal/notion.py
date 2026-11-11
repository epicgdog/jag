"""Fetch one consistent Notion page snapshot, without following child pages."""
from extract_todos import todos_from_snapshot
from main import notion_id
from journal.obsidian import JournalError, marked_dates, resolve_date
import re

SUPPORTED = {'paragraph','heading_1','heading_2','heading_3','bulleted_list_item','numbered_list_item','to_do','quote','callout','divider','child_page','child_database','column_list','column','toggle','image','file','audio','video','pdf'}

def rich(parts):
    return ''.join(x.get('plain_text','') for x in parts)

def snapshot(client, reference, date_property=None, override=None):
    try:
        page_id=notion_id(reference)
        for attempt in range(2):
            page=client.pages.retrieve(page_id=page_id)
            blocks=[]
            def walk(parent, depth=0):
                cursor=None
                while True:
                    params={'block_id':parent,'page_size':100}
                    if cursor: params['start_cursor']=cursor
                    result=client.blocks.children.list(**params)
                    for block in result['results']:
                        kind=block['type']
                        if kind not in SUPPORTED: raise JournalError('unsupported_content')
                        blocks.append((block,depth))
                        if block.get('has_children') and kind not in ('child_page','child_database'):
                            walk(block['id'], depth+1)
                    if not result.get('has_more'): break
                    cursor=result.get('next_cursor')
                    if not cursor: raise JournalError('notion_incomplete')
            walk(page_id)
            after=client.pages.retrieve(page_id=page_id)
            if page.get('last_edited_time') and page.get('last_edited_time') == after.get('last_edited_time'): break
        else: raise JournalError('source_changed')
        props=page.get('properties',{})
        title=next((rich(p.get('title',[])) for p in props.values() if p.get('type')=='title'), '')
        lines=[]
        for block,depth in blocks:
            kind=block['type']
            if kind in ('child_page','child_database','divider','column_list','column','image','file','audio','video','pdf'): continue
            data=block.get(kind,{})
            text=rich(data.get('rich_text',[]))
            prefix={'heading_1':'# ', 'heading_2':'## ', 'heading_3':'### ', 'bulleted_list_item':'- ', 'numbered_list_item':'1. ', 'quote':'> ', 'to_do':'- [' + ('x' if data.get('checked') else ' ') + '] '}.get(kind,'')
            lines.append('  '*depth+prefix+text)
        content='\n'.join(lines)
        if not content.strip(): return {'empty':True}
        candidates=[]
        if date_property and not override:
            prop=props.get(date_property, {})
            date=prop.get('date') if prop.get('type') == 'date' else None
            if not date or not date.get('start'): raise JournalError('date_missing_or_conflicting')
            candidates.append(date['start'][:10])
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4}|\d{2}-\d{2}-\d{4}', title.strip()): candidates.append(title.strip())
        candidates.extend(marked_dates(content))
        return {'source':'notion','id':page_id,'title':title,'content':content,'source_updated_at':page.get('last_edited_time'), 'document_date':resolve_date(candidates,override), 'tasks':todos_from_snapshot([b for b,_ in blocks])}
    except JournalError: raise
    except Exception: raise JournalError('notion_unavailable') from None


def ingest_notion(reference, model, storage=None, date_property=None, override=None):
    import fcntl
    import hashlib
    import os
    import tempfile
    from pathlib import Path
    from notion_client import Client
    from main import DEFAULT_API_VERSION
    try:
        page_id=notion_id(reference)
        token=os.getenv('NOTION_API_KEY') or os.getenv('NOTION_API_TOKEN')
        if not token: raise JournalError('notion_configuration')
        lockpath=Path(tempfile.gettempdir()) / ('jag-ingest-' + hashlib.sha256(('notion:'+page_id).encode()).hexdigest()+'.lock')
        with lockpath.open('a') as lock:
            try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError: raise JournalError('already_running') from None
            with Client(auth=token, notion_version=os.getenv('NOTION_API_VERSION',DEFAULT_API_VERSION)) as client:
                doc=snapshot(client,page_id,date_property,override)
            if doc.get('empty'): return 'skipped',0
            summary=model.summarize(doc['document_date'],doc['content'])
            if storage: storage.save(doc,summary)
            return 'succeeded',len(doc['tasks'])
    except JournalError: raise
    except Exception: raise JournalError('notion_unavailable') from None
