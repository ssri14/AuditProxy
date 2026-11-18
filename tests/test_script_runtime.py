import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
import unittest
from script_runtime import run_file, run_analysis_process


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.script = self.folder / 'selected.py'
        self.out = self.folder / 'stdout.txt'
        self.err = self.folder / 'stderr.txt'

    def test_bundled_runner_executes_main_and_captures_console_output(self):
        self.script.write_text('import sys\nfrom decimal import Decimal\nfrom pathlib import Path\n'
                               'assert __name__ == "__main__"\n'
                               'Path(sys.argv[1]).write_text(str(Decimal("1.25") * 2))\n'
                               'print("success")\n')
        previous = sys.argv
        report = self.folder / 'results.txt'
        self.assertEqual(run_file(self.script, [str(report)], self.out, self.err), 0)
        self.assertEqual(report.read_text(), '2.50')
        self.assertEqual(self.out.read_text(), 'success\n')
        self.assertEqual(self.err.read_text(), '')
        self.assertIs(sys.argv, previous)

    def test_bundled_runner_preserves_tracebacks(self):
        self.script.write_text('raise ValueError("test failure")')
        self.assertEqual(run_file(self.script, [], self.out, self.err), 1)
        self.assertIn('ValueError: test failure', self.err.read_text())

    def test_bundled_runner_preserves_exit_codes(self):
        self.script.write_text('raise SystemExit(3)')
        self.assertEqual(run_file(self.script, [], self.out, self.err), 3)

    def test_windowed_command_uses_internal_dispatch_and_explicit_logs(self):
        def fake_process(command, **kwargs):
            self.assertEqual(command[1], '--run-analysis')
            Path(command[3]).write_text('windowed stdout')
            Path(command[4]).write_text('windowed stderr')
            return subprocess.CompletedProcess(command, 1, '', '')
        with patch.object(sys, 'frozen', True, create=True):
            with patch('script_runtime.subprocess.run', side_effect=fake_process):
                result = run_analysis_process(self.script, self.folder/'input.csv', self.folder/'results', self.folder)
        self.assertEqual(result.stdout, 'windowed stdout')
        self.assertEqual(result.stderr, 'windowed stderr')

    def test_source_launch_remains_a_normal_python_process(self):
        self.script.write_text('print("source run")')
        result = run_analysis_process(self.script, self.folder/'input.csv', self.folder/'results', self.folder)
        self.assertEqual(result.returncode, 0)
        self.assertIn('source run', result.stdout)
