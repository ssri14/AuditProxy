# Native PyInstaller build. Invoke on the operating system being packaged.
import importlib.util
import os
from pathlib import Path
import sys
from PyInstaller.utils.hooks import collect_submodules, copy_metadata
import sysconfig

root = Path(SPECPATH)
# Generated scripts import dynamically. Collect the host's stdlib explicitly,
# excluding interactive demos, test internals, Tk and installation tooling.
excluded = {'tkinter', '_tkinter', 'turtle', 'turtledemo', 'idlelib', 'test',
            'ensurepip', 'venv', 'antigravity', 'this', '__hello__', '__phello__'}
hidden = []
for name in sorted(sys.stdlib_module_names):
    if name in excluded or name.startswith(('_test', '_xx')):
        continue
    try:
        spec = importlib.util.find_spec(name)
    except (ImportError, ValueError, AttributeError):
        continue
    if spec is None:
        continue
    hidden.append(name)
    if spec.submodule_search_locations:
        hidden.extend(collect_submodules(name, filter=lambda n: not any(
            part in ('test', 'tests', '__main__') for part in n.split('.')), on_error='ignore'))

data_files = [(str(root / 'sample_data'), 'sample_data')]
for candidate in (Path(sysconfig.get_path('stdlib')) / 'LICENSE.txt', Path(sys.base_prefix) / 'LICENSE.txt'):
    if candidate.is_file():
        data_files.append((str(candidate), 'licenses/Python'))
        break
for package in ('PyQt6', 'PyQt6-Qt6', 'PyQt6-sip'):
    data_files.extend(copy_metadata(package))

analysis = Analysis([str(root / 'launcher.py')], pathex=[str(root)],
    datas=data_files,
    hiddenimports=sorted(set(hidden)), excludes=sorted(excluded), noarchive=False)
pyz = PYZ(analysis.pure)
signing = os.environ.get('AUDITPROXY_CODESIGN_IDENTITY') or None
if sys.platform == 'win32':
    # A single portable .exe, with Python and Qt included.
    exe = EXE(pyz, analysis.scripts, analysis.binaries, analysis.datas, [],
              name='AuditProxy', console=False, upx=False)
else:
    exe = EXE(pyz, analysis.scripts, [], exclude_binaries=True,
              name='AuditProxy', console=False, upx=False, codesign_identity=signing)
    collection = COLLECT(exe, analysis.binaries, analysis.datas, name='AuditProxy', upx=False)
    if sys.platform == 'darwin':
        bundle = BUNDLE(collection, name='AuditProxy.app', bundle_identifier='org.auditproxy.desktop',
                        version='0.3.0', codesign_identity=signing,
                        info_plist={'CFBundleDisplayName': 'AuditProxy',
                                    'CFBundleShortVersionString': '0.3.0',
                                    'NSHighResolutionCapable': True, 'LSMinimumSystemVersion': '14.0'})
