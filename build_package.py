"""Build native AuditProxy packages using the current Python environment."""
import argparse
import hashlib
from pathlib import Path
import platform
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-dir', type=Path, default=Path(tempfile.gettempdir()) / 'AuditProxy-build',
                        help='Local, non-synced scratch directory for native framework links')
    parser.add_argument('--skip-build', action='store_true', help='Package an already built application')
    args = parser.parse_args()
    if sys.platform not in ('darwin', 'win32'):
        raise SystemExit('Build the DMG on macOS or the EXE on Windows.')
    scratch = args.build_dir.resolve()
    scratch.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ)
    environment.setdefault('PYINSTALLER_CONFIG_DIR', str(scratch / 'cache'))
    native_dist = scratch / 'dist'
    if not args.skip_build:
        subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm',
                        '--workpath', str(scratch / 'work'), '--distpath', str(native_dist),
                        str(ROOT / 'AuditProxy.spec')], cwd=ROOT, check=True, env=environment)
    dist = ROOT / 'dist'
    dist.mkdir(exist_ok=True)
    name = f'AuditProxy-0.3.0-macOS-{platform.machine()}.dmg' if sys.platform == 'darwin' else 'AuditProxy.exe'
    destination = dist / name
    if destination.exists():
        raise SystemExit(f'Existing package preserved: {destination}. Move it before rebuilding.')
    if sys.platform == 'darwin':
        with tempfile.TemporaryDirectory(prefix='auditproxy-dmg-') as td:
            staging = Path(td) / 'volume'
            staging.mkdir()
            shutil.copytree(native_dist / 'AuditProxy.app', staging / 'AuditProxy.app', symlinks=True)
            (staging / 'Applications').symlink_to('/Applications')
            image = Path(td) / name
            subprocess.run(['hdiutil', 'create', '-volname', 'AuditProxy', '-srcfolder', str(staging),
                            '-format', 'UDZO', str(image)], check=True)
            shutil.copy2(image, destination)
    else:
        shutil.copy2(native_dist / 'AuditProxy.exe', destination)
    checksum = hashlib.sha256()
    with destination.open('rb') as package:
        for chunk in iter(lambda: package.read(1024 * 1024), b''):
            checksum.update(chunk)
    checksum_file = destination.with_name(destination.name + '.sha256')
    checksum_file.write_text(checksum.hexdigest() + '  ' + destination.name + '\n', encoding='utf-8')
    print(f'Checksum: {checksum_file}')
    print(f'Native app: {native_dist}')
    print(f'Package: {destination}')


if __name__ == '__main__':
    main()
