"""Only generated T3 thread links may open from the read-only native surfaces."""
import re
from urllib.parse import unquote,quote,urlsplit


def thread_links(value):
    if not isinstance(value,str) or len(value)>4096 or any(ord(c)<33 for c in value):return None
    parsed=urlsplit(value)
    if parsed.query or parsed.fragment or parsed.username or parsed.password:return None
    if parsed.scheme=='t3code' and parsed.netloc=='threads':parts=parsed.path.split('/')[1:]
    elif parsed.scheme=='https' and parsed.netloc=='app.t3.codes' and parsed.path.startswith('/threads/'):parts=parsed.path.split('/')[2:]
    else:return None
    if len(parts)!=2 or any(not part or not re.fullmatch(r'[A-Za-z0-9_.~%-]+',part) for part in parts):return None
    if any(re.search(r'%(?![0-9a-fA-F]{2})',part) for part in parts):return None
    decoded=[unquote(part,errors='strict') for part in parts]
    if any(not part or part in ('.','..') or len(part)>512 or any(ord(c)<33 for c in part) for part in decoded):return None
    path='/'.join(quote(part,safe='') for part in decoded)
    return {'desktop':'t3code://threads/'+path,'web':'https://app.t3.codes/threads/'+path}


def open_thread(value,opener,has_handler=None):
    try:links=thread_links(value)
    except (ValueError,UnicodeError):return False
    if not links:return False
    if has_handler is None or has_handler('t3code'):
        try:
            if opener(links['desktop']) is not False:return True
        except Exception:pass
    try:return opener(links['web']) is not False
    except Exception:return False
