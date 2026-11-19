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


GITHUB_OWNER=re.compile(r'[A-Za-z0-9-]{1,39}',re.ASCII)
GITHUB_REPO=re.compile(r'[A-Za-z0-9._-]{1,100}',re.ASCII)
GITHUB_SEGMENT=re.compile(r'[A-Za-z0-9._-]{1,200}',re.ASCII)


def github_link(value):
    """A plain https://github.com/<owner>/<repo>[/up to 6 segments] link, or None.

    The same rule as safeGithub in web/glance-ci.js and SourceLinks.githubLink: no
    credentials, port, query, fragment, percent sign, `.`/`..` or empty segment."""
    if not isinstance(value,str) or len(value)>2048 or any(ord(c)<33 for c in value):return None
    if any(c in value for c in '%?#\\@'):return None
    prefix='https://github.com/'
    if not value.startswith(prefix):return None
    parts=value[len(prefix):].split('/')
    if not 2<=len(parts)<=8:return None
    if not GITHUB_OWNER.fullmatch(parts[0]) or not GITHUB_REPO.fullmatch(parts[1]):return None
    if not all(GITHUB_SEGMENT.fullmatch(part) for part in parts[2:]):return None
    if any(part in ('.','..') for part in parts):return None
    parsed=urlsplit(value)
    if (parsed.scheme,parsed.netloc,parsed.query,parsed.fragment)!=('https','github.com','',''):return None
    return prefix+'/'.join(parts)


def open_link(value,opener,has_handler=None):
    """A T3 thread link (desktop first, then web), else a GitHub link in the browser."""
    if open_thread(value,opener,has_handler):return True
    try:link=github_link(value)
    except (ValueError,UnicodeError):return False
    if not link:return False
    try:return opener(link) is not False
    except Exception:return False
