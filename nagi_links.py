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
# The only pages the panel links to: a pull request, a repository's Actions page or one
# run, and its deployments. Ids are numbers. Nothing else under a repository opens, and
# the bare /owner/repo doesn't either: the panel never builds it.
GITHUB_ROUTE=re.compile(r'(?:pull/[1-9][0-9]{0,18}|actions(?:/runs/[1-9][0-9]{0,18})?|deployments)',re.ASCII)
# First segments that are GitHub's own pages and can never be an account: sign-in, SSO,
# settings, /new, /features and the rest. Source: Mottie/github-reserved-names 2.2.0 (MIT), https://github.com/Mottie/github-reserved-names, plus GitHub's sign-in and SSO segments.
# The same text is in web/glance-ci.js and
# mac/Sources/NagiCore/SourceLinks.swift; tests/test_github_links.py keeps the three in step.
GITHUB_RESERVED=frozenset((
    '300 302 400 401 402 403 404 405 406 407 408 409 410 411 412 413 414 415 416 417 418 419 420 421 422 423 424 425 426 427 428 429 430 431 500 501 502 503 504 505 506 507 508 509 510 511 693 694 695 900 about account admin advisories anonymous any api apps attributes auth billing blob blog bounty branches business businesses c cache careers case-studies categories central certification changelog chat cla cloud codereview codespaces collection collections comments commit commits companies compare contact contributing cookbook copilot coupons customer customer-stories customers dashboard dashboard-feed dashboards design develop developer diff discover discussions downloads downtime editor editors edu education enterprise enterprises events explore featured features feed files fixtures forked garage ghost gist gists git-guides github github-copilot graphs groups guide guides help help-wanted home hooks hosting hovercards identity images inbox individual info integration interfaces introduction invalid-email-address investors issues jobs join journal journals lab labs languages launch layouts learn legal library linux listings lists login logos logout mac maintenance malware man marketplace mcp mention mentioned mentioning mentions migrating milestones mine mirrors mobile navigation network new news newsletter newsroom none nonprofit nonprofits notices notifications oauth offer open-source organisations organizations orgs pages partners password-reset payments personal plans plugins popular popularity posts press preview pricing professional projects pulls raw readme recommendations redeem releases render reply repos repositories resources restore revert save-net-neutrality saved scraping search security services session sessions settings shareholders showcases signin signup site site-policy sitemap social-impact socials spam sponsors ssh sso staff starred stars static status statuses storage store stories styleguide subscriptions suggest suggestion suggestions support suspended talks teach teacher teachers teaching team teams ten terms timeline topic topics tos tour train training translations tree trending two-factor undefined updates user-attachments username users visualization w watching why-github wiki wikis windows works-with www0 www1 www2 www3 www4 www5 www6 www7 www8 www9'
).split())


def github_link(value):
    """https://github.com/<owner>/<repo>/ followed by pull/<n>, actions, actions/runs/<n>
    or deployments; anything else is None.

    The same rule as safeGithub in web/glance-ci.js and SourceLinks.githubLink: no
    credentials, port, query, fragment, percent sign or empty segment; no reserved first
    segment; no repository named `.` or `..` or ending in a dot; no other route."""
    if not isinstance(value,str) or len(value)>2048 or any(ord(c)<33 for c in value):return None
    if any(c in value for c in '%?#\\@'):return None
    prefix='https://github.com/'
    if not value.startswith(prefix):return None
    parts=value[len(prefix):].split('/',2)
    if len(parts)!=3 or not GITHUB_OWNER.fullmatch(parts[0]) or not GITHUB_REPO.fullmatch(parts[1]):return None
    if parts[0].lower() in GITHUB_RESERVED or parts[1].endswith('.'):return None
    if not GITHUB_ROUTE.fullmatch(parts[2]):return None
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
