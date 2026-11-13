"""Strict, bounded JSON: the parser every Nagi read goes through."""
import json
import unittest
from typing import Any, cast
from unittest.mock import patch

import jsonio


class StrictJSONTests(unittest.TestCase):
    def test_valid_utf8_bytearray_text_and_scalars(self):
        value = {'title': 'Fictional \U0001f600', 'items': [0, None, False, 1.25]}
        encoded = json.dumps(value, ensure_ascii=False).encode('utf-8')
        for raw in (encoded, bytearray(encoded), encoded.decode('utf-8')):
            with self.subTest(raw_type=type(raw)):
                self.assertEqual(jsonio.strict_json_loads(raw, len(encoded)), value)
        for raw, value in (('0', 0), ('false', False), ('null', None), ('1.25', 1.25)):
            self.assertEqual(jsonio.strict_json_loads(raw, 100), value)
        self.assertEqual(jsonio.strict_json_loads('"\\ud83d\\ude00"', 100), '\U0001f600')

    def test_duplicate_keys_at_every_depth_including_escaped_aliases(self):
        for raw in ('{"x":1,"x":2}', '{"nested":[{"x":1,"x":1}]}',
                    '{"x":1,"\\u0078":2}', '{"x":null,"x":false}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                jsonio.strict_json_loads(raw, 1024)

    def test_nonfinite_literals_and_float_overflow(self):
        for raw in ('NaN', 'Infinity', '-Infinity', '[NaN]', '{"x":Infinity}',
                    '1e400', '-1e400', '{"x":1e99999}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                jsonio.strict_json_loads(raw, 1024)
        self.assertEqual(jsonio.strict_json_loads('{"x":"NaN"}', 100), {'x': 'NaN'})

    def test_invalid_utf8_surrogates_syntax_and_types_safe_value_error(self):
        invalid = (b'"\xff"', b'"\xc0\xaf"', b'"\xe2\x82"', b'\xff\xfe{\x00}\x00',
                   '\ud800', '"\\ud800"', '{"\\udfff":0}', '', '{', '[}',
                   '{"x":1,}', '{}{}', '"unterminated', '{"secret-marker":}', None, 1, {})
        for raw in invalid:
            with self.subTest(raw=repr(raw)), self.assertRaises(ValueError) as error:
                jsonio.strict_json_loads(cast(Any, raw), 1024)
            self.assertNotIn('secret-marker', str(error.exception))
            self.assertNotIn('secret-marker', repr(error.exception))

    def test_byte_limits_count_utf8_and_original_whitespace(self):
        raw = '"\U0001f600"'
        size = len(raw.encode('utf-8'))
        self.assertEqual(jsonio.strict_json_loads(raw, size), '\U0001f600')
        for value in (raw, raw.encode('utf-8')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                jsonio.strict_json_loads(value, size - 1)
        with self.assertRaises(ValueError):
            jsonio.strict_json_loads(' ' * 100 + '{}', 100)
        for limit in (0, -1, True, 1.5, '100', None):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                jsonio.strict_json_loads('{}', cast(Any, limit))

    def test_depth_guard_before_decoder_and_escaped_brackets_are_not_nesting(self):
        limit = jsonio.MAX_JSON_DEPTH
        raw = '[' * limit + '0' + ']' * limit
        jsonio.strict_json_loads(raw, len(raw))
        raw = '[' * (limit + 1) + '0' + ']' * (limit + 1)
        with patch.object(jsonio.json, 'loads') as decoder:
            with self.assertRaises(ValueError):
                jsonio.strict_json_loads(raw, len(raw))
            decoder.assert_not_called()
        raw = '{"x":' * (limit + 1) + '0' + '}' * (limit + 1)
        with self.assertRaises(ValueError):
            jsonio.strict_json_loads(raw, len(raw))
        quoted = {'text': ('[{\\"}]' * 100)}
        self.assertEqual(jsonio.strict_json_loads(json.dumps(quoted), 10000), quoted)
        raw = '[' * 10000 + '0' + ']' * 10000
        with self.assertRaises(ValueError):
            jsonio.strict_json_loads(raw, len(raw))


