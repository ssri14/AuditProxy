"""Run selected analysis files in source and bundled desktop distributions."""
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
import runpy
import subprocess
import sys
import traceback
import os


def run_file(script, arguments, stdout_path, stderr_path):
    """Internal packaged-process entry point; this is not a security sandbox."""
    previous_argv = sys.argv
    try:
        with open(stdout_path, 'w', encoding='utf-8') as out, open(stderr_path, 'w', encoding='utf-8') as err:
            with redirect_stdout(out), redirect_stderr(err):
                sys.argv = [str(script), *arguments]
                try:
                    runpy.run_path(str(script), run_name='__main__')
                except SystemExit as exc:
                    if exc.code is None:
                        return 0
                    if isinstance(exc.code, int):
                        return exc.code
                    print(exc.code, file=sys.stderr)
                    return 1
                except BaseException:
                    traceback.print_exc()
                    return 1
        return 0
    finally:
        sys.argv = previous_argv


def run_analysis_process(script, input_path, results, folder):
    folder = Path(folder)
    if getattr(sys, 'frozen', False):
        stdout_path, stderr_path = folder / 'runner.stdout.txt', folder / 'runner.stderr.txt'
        command = [sys.executable, '--run-analysis', str(script), str(stdout_path), str(stderr_path)]
    else:
        command = [sys.executable, '-I', '-B', str(script)]
    command += ['--input', str(input_path), '--output', str(results)]
    proc = subprocess.run(command, cwd=folder, stdin=subprocess.DEVNULL, capture_output=True,
                          text=True, timeout=90,
                          env={k: v for k, v in os.environ.items() if not k.lower().endswith('_proxy')})
    if getattr(sys, 'frozen', False):
        # Windowed executables have no console streams on Windows. Read explicit logs.
        for field, path in (('stdout', stdout_path), ('stderr', stderr_path)):
            if path.exists():
                setattr(proc, field, path.read_text(encoding='utf-8', errors='replace'))
    return proc
