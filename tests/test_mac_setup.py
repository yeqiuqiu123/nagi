"""mac/setup_helper.py: quiet credential, policy and LaunchAgent steps for setup-mac.sh."""
import json
import os
import plistlib
import stat
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / 'mac' / 'setup_helper.py'
TOKEN = 'synthetic-token-' + 'x' * 32


def run(*args, stdin=''):
    return subprocess.run([sys.executable, '-B', str(HELPER), *args], input=stdin, capture_output=True, text=True, timeout=30)


class Helper(TestCase):
    def setUp(self):
        self.home = Path(self.enterContext(TemporaryDirectory()))
        self.home.chmod(0o700)
        self.credential = self.home / 't3-credential.json'

    def test_piped_token_lands_in_a_private_file_and_is_never_printed(self):
        result = run('credential-from-stdin', str(self.credential), stdin=TOKEN + '\n')
        self.assertEqual(result.returncode, 0)
        self.assertNotIn(TOKEN, result.stdout + result.stderr)
        self.assertEqual(stat.S_IMODE(self.credential.stat().st_mode), 0o600)
        self.assertEqual(json.loads(self.credential.read_text()), {'token': TOKEN, 'scopes': ['orchestration:read']})
        self.assertEqual(run('credential-ok', str(self.credential)).returncode, 0)
        self.assertEqual([p.name for p in self.home.iterdir()], ['t3-credential.json'])

    def test_an_existing_credential_is_kept(self):
        run('credential-from-stdin', str(self.credential), stdin=TOKEN)
        before = self.credential.read_bytes()
        self.assertEqual(run('credential-from-stdin', str(self.credential), stdin='other-token-' + 'y' * 20).returncode, 0)
        self.assertEqual(self.credential.read_bytes(), before)
        self.credential.chmod(0o644)
        self.assertEqual(run('credential-ok', str(self.credential)).returncode, 1)
        self.assertEqual(run('credential-from-stdin', str(self.credential), stdin=TOKEN).returncode, 3)

    def test_bad_tokens_save_nothing(self):
        for value in ('', 'short', 'has space ' + 'x' * 20, 'x' * 9000):
            with self.subTest(size=len(value)):
                self.assertNotEqual(run('credential-from-stdin', str(self.credential), stdin=value).returncode, 0)
                self.assertFalse(self.credential.exists())

    def test_policy_uses_the_reader_origin_rule(self):
        data = self.home / 'data'
        data.mkdir(mode=0o700)
        self.assertEqual(run('policy', str(data), 'http://100.101.102.103:3773', str(self.credential)).returncode, 0)
        policy = data / 'nagi-t3.json'
        self.assertEqual(json.loads(policy.read_text()), {'version': 1, 'origin': 'http://100.101.102.103:3773', 'credentialFile': str(self.credential)})
        self.assertEqual(stat.S_IMODE(policy.stat().st_mode), 0o600)
        self.assertNotEqual(run('policy', str(data), 'http://100.128.0.1:3773', str(self.credential)).returncode, 0)
        self.assertNotEqual(run('policy', str(data), 'http://127.0.0.1:3773', 'relative.json').returncode, 0)
        self.assertEqual(json.loads(policy.read_text())['origin'], 'http://100.101.102.103:3773')
        self.assertEqual(run('origin-kind', 'https://box.tail1.ts.net').stdout.strip(), 'tls')
        self.assertEqual(run('origin-kind', 'http://example.com:3773').returncode, 1)

    def test_app_agent_launches_the_installed_app_at_login(self):
        plist = self.home / 'LaunchAgents' / 'local.nagi.app.plist'
        app = self.home / 'Applications' / 'Nagi.app'
        self.assertEqual(run('app-agent', str(plist), str(app)).returncode, 0)
        value = plistlib.loads(plist.read_bytes())
        self.assertEqual(value['Label'], 'local.nagi.app')
        self.assertEqual(value['ProgramArguments'], [str(app / 'Contents/MacOS/Nagi')])
        self.assertTrue(value['RunAtLoad'])
        self.assertEqual(value['KeepAlive'], {'SuccessfulExit': False})
        self.assertEqual(stat.S_IMODE(plist.stat().st_mode), 0o600)
