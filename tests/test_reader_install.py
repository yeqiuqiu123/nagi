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
                    self.assertFalse((home / '.config/systemd/user/nagi-tray.service').exists())
                    entry = (home / '.config/autostart/local.nagi.tray.desktop').read_text()
                    self.assertIn('linux/tray.py" "--port" "47841" "--login"', entry)
                    self.assertTrue(entry.startswith('[Desktop Entry]\n'))

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


class TrayLaunchTests(TestCase):
    def test_dollars_and_percents_in_a_path_survive_systemd_and_the_desktop_entry(self):
        import shutil
        try:
            from gi.repository import GLib
        except ImportError:
            self.skipTest('GLib is needed to parse the desktop entry the way desktops do')
        with TemporaryDirectory() as temp:
            home = Path(temp)
            weird = home / 'Nagi ${USER} 100% \\ "q"'
            shutil.copytree(install_reader.ROOT / 'linux', weird / 'linux', ignore=shutil.ignore_patterns('__pycache__'))
            with patch.object(install_reader, 'ROOT', weird):
                install_reader.install('linux', home / 'data', 47841, sys.executable, home)
            unit = (home / '.config/systemd/user/nagi-reader.service').read_text()
            exec_line = next(line for line in unit.splitlines() if line.startswith('ExecStart='))
            self.assertIn('Nagi $${USER} 100%%', exec_line)
            # GLib's strict key-file reader and its Exec parser give back the exact path.
            for entry in (home / install_reader.LOGIN_ENTRY, home / '.local/share/applications/local.nagi.notifications.desktop'):
                keys = GLib.KeyFile()
                keys.load_from_file(str(entry), GLib.KeyFileFlags.NONE)
                ok, argv = GLib.shell_parse_argv(keys.get_string('Desktop Entry', 'Exec').replace('%%', '%'))
                self.assertTrue(ok)
                self.assertTrue(any(arg.startswith(str(weird / 'linux')) for arg in argv), argv)

    def test_login_entry_never_writes_through_a_symlinked_folder(self):
        with TemporaryDirectory() as temp, TemporaryDirectory() as elsewhere:
            home = Path(temp)
            (home / '.config').mkdir()
            (home / '.config/autostart').symlink_to(elsewhere)
            with self.assertRaises(OSError):
                install_reader.write_login_entry(home, sys.executable, 47841)
            self.assertEqual(os.listdir(elsewhere), [])

    def test_login_entry_respects_a_switched_off_or_foreign_entry(self):
        with TemporaryDirectory() as temp:
            home = Path(temp)
            path = home / install_reader.LOGIN_ENTRY
            path.parent.mkdir(parents=True)
            for text in ('[Desktop Entry]\nExec=python3 linux/tray.py\nHidden=true\n',
                         '[Desktop Entry]\nExec=python3 linux/tray.py\nX-GNOME-Autostart-enabled=false\n',
                         '[Desktop Entry]\nExec=someone-else\n'):
                path.write_text(text)
                self.assertIsNone(install_reader.write_login_entry(home, sys.executable, 47841))
                self.assertEqual(path.read_text(), text)
            # Hidden in another group is not the entry being switched off.
            path.write_text('[Desktop Entry]\nExec=python3 linux/tray.py\n[Desktop Action x]\nHidden=true\n')
            self.assertIsNotNone(install_reader.write_login_entry(home, sys.executable, 47841))
            self.assertIn('--login', path.read_text())

    def test_the_login_supervisor_restarts_a_crash_and_stops_on_quit_lock_or_a_loop(self):
        sys.path.insert(0, str(install_reader.ROOT / 'linux'))
        import tray
        def run(codes, stopping=lambda: False):
            seq = iter(codes)
            waits = []
            now = [0.0]
            def sleep(seconds):
                waits.append(seconds)
                now[0] += seconds
            result = tray.supervise(lambda: next(seq), sleep, lambda: now[0], stopping)
            return result, len(waits)
        self.assertEqual(run([1, -11, 0]), (0, 2))   # two crashes restarted, then Quit
        self.assertEqual(run([2]), (2, 0))           # already running: nothing to do
        self.assertEqual(run([1] * 9), (1, 4))       # five crashes inside a minute: give up
        self.assertEqual(run([-15], stopping=lambda: True), (-15, 0))  # logout or SIGTERM
