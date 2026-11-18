"""Smoke-test the actual bundled runner, without an Ollama server or a Python dependency in the app."""
import argparse
from pathlib import Path
import subprocess
import sys
import tempfile

from core import export_aliased_csv, profile_csv

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-dir', type=Path, default=Path(tempfile.gettempdir()) / 'AuditProxy-build')
    args = parser.parse_args()
    dist = args.build_dir / 'dist'
    if sys.platform == 'darwin':
        executable = dist / 'AuditProxy.app' / 'Contents' / 'MacOS' / 'AuditProxy'
    elif sys.platform == 'win32':
        executable = dist / 'AuditProxy.exe'
    else:
        raise SystemExit('Run this smoke test on macOS or Windows after building.')
    if not executable.is_file():
        raise SystemExit(f'Build the app first: missing {executable}')
    with tempfile.TemporaryDirectory(prefix='auditproxy-verify-') as directory:
        folder = Path(directory)
        script = folder / 'analysis.py'
        script.write_bytes((ROOT / 'sample_data' / 'example_reviewed_analysis.py').read_bytes())
        input_path = folder / 'input.csv'
        export_aliased_csv(profile_csv(ROOT / 'sample_data' / 'synthetic_government_expenses.csv'), input_path)
        output, error = folder / 'stdout.txt', folder / 'stderr.txt'
        results = folder / 'results'
        command = [str(executable), '--run-analysis', str(script), str(output), str(error),
                   '--input', str(input_path), '--output', str(results)]
        process = subprocess.run(command, capture_output=True, text=True, timeout=60)
        if process.returncode != 0:
            detail = error.read_text(encoding='utf-8') if error.exists() else process.stderr
            raise SystemExit(f'Packaged runner failed: {detail}')
        report = (results / 'results.txt').read_text(encoding='utf-8')
        if 'Groups flagged for REVIEW: 1' not in report:
            raise SystemExit('Packaged sample analysis did not produce the expected report.')
        script.write_text('raise ValueError("packaged error capture test")', encoding='utf-8')
        process = subprocess.run(command, capture_output=True, text=True, timeout=60)
        if process.returncode != 1 or not error.exists() or 'ValueError: packaged error capture test' not in error.read_text(encoding='utf-8'):
            raise SystemExit('Packaged error capture did not work.')
    print('Packaged sample analysis and traceback capture passed.')


if __name__ == '__main__':
    main()
