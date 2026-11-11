"""Read and parse an Obsidian journal without leaking its contents."""
import datetime as dt
import hashlib
import re
from pathlib import Path

import yaml
from markdown_it import MarkdownIt

class JournalError(Exception):
    pass

def parse_date(value):
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    value = str(value).strip()
    for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%m-%d-%Y'):
        try:
            result = dt.datetime.strptime(value, fmt).date()
            if result.strftime(fmt) == value:
                return result
        except ValueError:
            pass
    raise JournalError('invalid_date')

def resolve_date(candidates, override=None):
    if override is not None:
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', override):
            raise JournalError('invalid_date')
        return parse_date(override).isoformat()
    dates = {parse_date(value) for value in candidates}
    if len(dates) != 1:
        raise JournalError('date_missing_or_conflicting')
    return dates.pop().isoformat()

def marked_dates(body):
    return re.findall(r'(?im)^\s*(?:#{1,6}\s*)?(?:journal[ -]date|date)\s*:\s*(\S+)\s*$', body)

def split_frontmatter(text):
    if not re.match(r'^---\s*\r?\n', text):
        return {}, text
    match = re.search(r'(?m)^---\s*\r?$', text[text.find('\n') + 1:])
    if not match:
        raise JournalError('invalid_frontmatter')
    start = text.find('\n') + 1
    try:
        data = yaml.safe_load(text[start:start + match.start()]) or {}
    except yaml.YAMLError:
        raise JournalError('invalid_frontmatter') from None
    if not isinstance(data, dict):
        raise JournalError('invalid_frontmatter')
    return data, text[start + match.end():].lstrip('\r\n')

def tasks_from_markdown(body):
    tokens = MarkdownIt().parse(body)
    result, occurrences, ids = [], {}, set()
    # Inline tokens in list paragraphs exclude fenced/indented code and HTML blocks.
    depth = 0
    for token in tokens:
        if token.type == 'list_item_open':
            depth += 1
        elif token.type == 'list_item_close':
            depth -= 1
        elif token.type == 'inline' and depth and token.map:
            first = token.content.split('\n', 1)[0]
            match = re.match(r'^\[([ xX])\]\s+(.+?)\s*$', first)
            if not match:
                continue
            text = match.group(2)
            block = re.search(r'\s+\^([A-Za-z0-9-]+)\s*$', text)
            if block:
                text = text[:block.start()].rstrip()
                task_id = 'block:' + block.group(1)
            else:
                normalized = ' '.join(text.split())
                occurrences[normalized] = occurrences.get(normalized, 0) + 1
                task_id = 'sha256:' + hashlib.sha256(f'{normalized}\0{occurrences[normalized]}'.encode()).hexdigest()
            if not text.strip() or task_id in ids:
                raise JournalError('invalid_tasks')
            ids.add(task_id)
            result.append({'id': task_id, 'text': text, 'checked': match.group(1).lower() == 'x'})
    return result

def read_obsidian(path, root, override=None):
    try:
        root = Path(root).resolve(strict=True)
        path = Path(path).resolve(strict=True)
        if not root.is_dir() or not path.is_relative_to(root) or not path.is_file() or path.suffix.lower() != '.md':
            raise JournalError('invalid_path')
        for _ in range(2):
            before = path.stat()
            text = path.read_text(encoding='utf-8')
            after = path.stat()
            if (before.st_mtime_ns, before.st_size) == (after.st_mtime_ns, after.st_size):
                break
        else:
            raise JournalError('source_changed')
    except (OSError, UnicodeError, RuntimeError, ValueError):
        raise JournalError('read_failed') from None
    front, body = split_frontmatter(text)
    candidates = []
    if 'date' in front:
        candidates.append(front['date'])
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}|\d{2}-\d{2}-\d{4}', path.stem):
        candidates.append(path.stem)
    candidates.extend(marked_dates(body))
    return {'source': 'obsidian', 'id': str(path), 'title': path.stem, 'content': body,
            'document_date': resolve_date(candidates, override),
            'source_updated_at': dt.datetime.fromtimestamp(after.st_mtime, dt.timezone.utc).isoformat(),
            'tasks': tasks_from_markdown(body)}
