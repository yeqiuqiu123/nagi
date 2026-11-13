"""Strict, bounded JSON for everything Nagi reads: unique keys, finite numbers, bounded nesting."""
from __future__ import annotations

import json
import math
import os
import stat
from typing import Any

MAX_READ = 65536


def require(ok, message):
    if not ok:
        raise ValueError(message)


MAX_JSON_DEPTH = 24


def _object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'Duplicate JSON object key')
        result[key] = value
    return result


def _constant(_value):
    raise ValueError('Nonfinite JSON number')


def _float(value):
    parsed = float(value)
    require(math.isfinite(parsed), 'Nonfinite JSON number')
    return parsed


def _check_depth(raw, max_depth=MAX_JSON_DEPTH):
    """Bound container nesting BEFORE the recursive stdlib decoder runs."""
    depth, quoted, escaped = 0, False, False
    for char in raw:
        if quoted:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in '{[':
            depth += 1
            require(depth <= max_depth, 'JSON nesting limit exceeded')
        elif char in '}]':
            depth -= 1
    # Matching brackets, unterminated strings and all syntax remain json.loads'
    # responsibility. This scan only guards decoder recursion on bounded input.


def strict_json_loads(raw: bytes | bytearray | str, max_bytes: int, *, max_depth: int = MAX_JSON_DEPTH) -> Any:
    """Decode bounded UTF-8 JSON with unique keys, finite numbers and bounded nesting (default 24).

    max_bytes is the existing owner's byte cap (positive integer). Accepts bytes,
    bytearray or text; text is counted as strict UTF-8, not character count.
    All rejected input raises a generic ValueError without echoing source data.
    """
    require(type(max_depth) is int and 1 <= max_depth <= 160, 'Invalid JSON depth limit')
    require(type(max_bytes) is int and max_bytes > 0, 'Invalid JSON byte limit')
    require(type(raw) in (bytes, bytearray, str), 'Expected UTF-8 JSON bytes or text')
    try:
        if isinstance(raw, str):
            require(len(raw) <= max_bytes, 'JSON byte limit exceeded')
            require(len(raw.encode('utf-8')) <= max_bytes, 'JSON byte limit exceeded')
            decoded = raw
        else:
            require(len(raw) <= max_bytes, 'JSON byte limit exceeded')
            decoded = raw.decode('utf-8', errors='strict')
        _check_depth(decoded, max_depth)
        value = json.loads(decoded, object_pairs_hook=_object,
                           parse_constant=_constant, parse_float=_float)
        # Escaped unpaired surrogates are accepted by json.loads but cannot form
        # valid UTF-8. Reject these in keys/values as well as invalid raw UTF-8.
        pending = [value]
        while pending:
            item = pending.pop()
            if isinstance(item, dict):
                pending.extend(item.keys())
                pending.extend(item.values())
            elif isinstance(item, list):
                pending.extend(item)
            elif isinstance(item, str):
                item.encode('utf-8', errors='strict')
        return value
    except (ValueError, RecursionError, OverflowError):
        raise ValueError('Invalid or over-limit UTF-8 JSON') from None


def private_json(path):
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError('Expected an owner-only regular file')
        return strict_json_loads(stream.read(MAX_READ + 1), MAX_READ)
