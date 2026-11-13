"""T3 project icons, validated to T3's own schema and reduced to a closed DTO.

Precedence (T3's ProjectFavicon): a monogram, emoji or lucide override, else the
project's automatic favicon, else a monogram the panel derives from the title.
No workspace path ever leaves this module's callers: favicons travel by opaque key.
"""
import hashlib
import re
import unicodedata

COLORS = ('gray', 'red', 'orange', 'amber', 'yellow', 'lime', 'green', 'emerald', 'teal', 'cyan',
          'sky', 'blue', 'indigo', 'violet', 'purple', 'fuchsia', 'pink', 'rose')
LUCIDE_NAME = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*')
KEY = re.compile(r'[0-9a-f]{32}')


def _monogram_text(value):
    """T3's ProjectMonogramText: trimmed, <=32, a letter or number, then letters, numbers, marks, ZWNJ/ZWJ."""
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > 32:
        return None
    if unicodedata.category(value[0])[0] not in 'LN':
        return None
    if any(unicodedata.category(c)[0] not in 'LNM' and c not in '‌‍' for c in value[1:]):
        return None
    return value


def override(raw):
    """The validated override, or None (automatic). Unknown kinds are forward-compatible: None."""
    if not isinstance(raw, dict):
        return None
    kind = raw.get('kind')
    color = raw.get('color')
    if kind == 'monogram':
        text = _monogram_text(raw.get('text'))
        return {'kind': 'monogram', 'text': text, 'color': color} if text and color in COLORS else None
    if kind == 'emoji':
        emoji = raw.get('emoji')
        if isinstance(emoji, str) and emoji and emoji == emoji.strip() and len(emoji) <= 32 and all(ord(c) >= 32 for c in emoji):
            return {'kind': 'emoji', 'emoji': emoji}
        return None
    if kind == 'lucide':
        if color not in COLORS:
            return None
        # A legacy lucide override carrying monogram text is a monogram (T3's fromLegacyMonogram).
        legacy = raw.get('monogramText', raw.get('monogram'))
        if legacy is not None:
            text = _monogram_text(legacy)
            return {'kind': 'monogram', 'text': text, 'color': color} if text else None
        name = raw.get('name')
        if isinstance(name, str) and len(name) <= 64 and LUCIDE_NAME.fullmatch(name):
            return {'kind': 'lucide', 'name': name, 'color': color}
    return None


def key(environment, project, *, source_id=None):
    """An opaque, stable key for one project's favicon; reveals neither id nor path."""
    if source_id is not None:
        import json
        return hashlib.sha256(json.dumps([source_id, environment, project], separators=(',', ':')).encode()).hexdigest()[:32]
    return hashlib.sha256(f'nagi-project-icon\0{environment}\0{project}'.encode()).hexdigest()[:32]


def favicon_source(raw):
    """(workspaceRoot, faviconPath) for T3's automatic favicon lookup, or None."""
    if not isinstance(raw, dict):
        return None
    root, path = raw.get('workspaceRoot'), raw.get('faviconPath')
    if not isinstance(root, str) or not root.strip() or root != root.strip() or len(root) > 1024:
        return None
    if path is not None and (not isinstance(path, str) or not path.strip() or len(path) > 1024):
        path = None
    return root, path
