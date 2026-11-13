import sys
import stat
from pathlib import Path
import plistlib
from tempfile import TemporaryDirectory
from unittest import TestCase
import install_reader
import owner_auth
import runtime_paths
from unittest.mock import patch
import os
import subprocess
import json


class InstallerTests(TestCase):
    def test_idempotent_user_services_keep_secret_and_never_activate(self):
        with TemporaryDirectory() as temp:
            home = Path(temp)
            data = home / 'data'
            for platform in ('linux', 'darwin'):
                target = install_reader.install(platform, data, 47841, sys.executable, home)
                first = target.read_bytes()
                secret = owner_auth.owner_secret(data)
                self.assertEqual(install_reader.install(platform, data, 47841, sys.executable, home).read_bytes(), first)
                self.assertEqual(owner_auth.owner_secret(data), secret)
                self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
                self.assertNotIn(secret.encode(), first)
                if platform == 'darwin':
                    plist = plistlib.loads(first)
                    self.assertEqual(plist['Label'], 'local.nagi.reader')
                    self.assertIn(str(data), plist['ProgramArguments'])
                    self.assertEqual(plist['EnvironmentVariables']['NAGI_DATA_DIR'], str(data))
                else:
                    self.assertIn(b'--data-dir', first)
                    self.assertNotIn(b'gateway', first)

    def test_installer_rejects_outside_home_and_symlinked_destinations(self):
        with TemporaryDirectory() as temp:
            home = Path(temp)
            with self.assertRaises(ValueError):
                install_reader.install('linux', home.parent / 'elsewhere', 47841, sys.executable, home)
            (home / 'alias').symlink_to('/tmp')
            with self.assertRaises(ValueError):
                install_reader.install('linux', home / 'alias/data', 47841, sys.executable, home)

    def test_default_and_custom_runtime_resolver_agrees_with_installer_and_clients(self):
        for platform in ('linux','darwin'):
            with TemporaryDirectory() as temp, patch.dict(os.environ,{},clear=True), patch('runtime_paths.Path.home',return_value=Path(temp)), patch('sys.platform',platform):
                home=Path(temp)
                default=runtime_paths.data_directory()
                expected=home/('Library/Application Support/Nagi/data' if platform=='darwin' else '.local/share/nagi/data')
                self.assertEqual(default,expected)
                target=install_reader.install(platform,default,47841,sys.executable,home)
                self.assertEqual(runtime_paths.data_directory(),default)
                self.assertEqual(owner_auth.owner_secret(),owner_auth.owner_secret(default))
                custom=home/'custom-runtime'
                install_reader.install(platform,custom,47841,sys.executable,home)
                self.assertEqual(runtime_paths.data_directory(),custom)
                self.assertEqual(owner_auth.owner_secret(),owner_auth.owner_secret(custom))
                self.assertNotEqual(owner_auth.owner_secret(default),owner_auth.owner_secret())
                locator=runtime_paths.locator_path(home=home)
                self.assertEqual(stat.S_IMODE(locator.stat().st_mode),0o600)
                self.assertIn(str(custom).encode(),target.read_bytes())
                script = ('import json; from runtime_paths import data_directory; '
                          'print(json.dumps([str(data_directory())]))')
                child = subprocess.run([sys.executable,'-B','-c',script],env={**os.environ,'HOME':str(home)},capture_output=True,text=True,check=True,timeout=5)
                self.assertEqual(json.loads(child.stdout),[str(custom)])

    def test_insecure_locator_never_falls_back_to_checkout_data(self):
        with TemporaryDirectory() as temp, patch.dict(os.environ,{},clear=True), patch('runtime_paths.Path.home',return_value=Path(temp)):
            home=Path(temp)
            install_reader.install('linux',home/'custom',47841,sys.executable,home)
            locator=runtime_paths.locator_path(home=home)
            locator.chmod(0o644)
            with self.assertRaises(ValueError):runtime_paths.data_directory()
