import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from PyQt6.QtWidgets import QApplication
    import app as gui
except ImportError:
    QApplication = None


@unittest.skipIf(QApplication is None, 'PyQt6 is not installed in this interpreter')
class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])
        cls.qt.setStyle('Fusion')
        cls.qt.setStyleSheet(gui.STYLE)

    def setUp(self):
        self.source = tempfile.TemporaryDirectory()
        self.addCleanup(self.source.cleanup)
        self.script_file = Path(self.source.name) / 'custom_analysis.py'
        self.script_file.write_bytes(gui.SAMPLE_CODE.read_bytes())
        self.workspaces = []
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patches = [patch.object(gui, 'local_models', return_value=['test:1b']),
                   patch.object(gui, 'check_model', side_effect=lambda name: name),
                   patch.object(gui, 'improve_prompt', return_value='Check repeated references.'),
                   patch.object(gui, 'interpret_results', return_value='Review the repeated references.')]
        for item in patches:
            mock = item.start()
            self.addCleanup(item.stop)
        self.model_interpret = mock
        self.window = gui.AuditProxyApp()
        self.addCleanup(self.window.close)
        self.wait_idle()
        self.window._load(gui.SAMPLE)
        with patch.object(gui.QFileDialog, 'getOpenFileName', return_value=(str(self.script_file), '')):
            self.window._choose_script()

    def wait_idle(self):
        deadline = time.monotonic() + 5
        for _ in range(2):
            self.qt.processEvents()
        while self.window._threads:
            self.qt.processEvents()
            if time.monotonic() > deadline:
                self.fail('Background operation did not finish')
            time.sleep(.01)
        self.qt.processEvents()

    def run_analysis(self):
        real_temporary_directory = tempfile.TemporaryDirectory
        def workspace(*args, **kwargs):
            if kwargs.get('prefix') == 'auditproxy_run_':
                kwargs['dir'] = self.tmp.name
            temporary = real_temporary_directory(*args, **kwargs)
            if kwargs.get('prefix') == 'auditproxy_run_':
                self.workspaces.append(Path(temporary.name))
            return temporary
        with patch.object(gui.tempfile, 'TemporaryDirectory', side_effect=workspace):
            with patch.object(gui.QFileDialog, 'getExistingDirectory', side_effect=AssertionError('Unexpected folder prompt')):
                with patch.object(gui.QFileDialog, 'getSaveFileName', side_effect=AssertionError('Unexpected save prompt')):
                    self.window._run_code()
                    self.wait_idle()
        self.assertTrue(self.workspaces)
        self.assertTrue(all(not path.exists() for path in self.workspaces))

    def accept_interpretation(self):
        with patch.object(gui.QMessageBox, 'warning', return_value=gui.QMessageBox.StandardButton.Ok) as alert:
            self.window._interpret()
            self.wait_idle()
        alert.assert_called_once()

    def test_raw_results_are_shown_first_without_interpretation(self):
        self.window._prepare_prompt()
        self.wait_idle()
        self.assertIn('results.txt', self.window.prompt_text.toPlainText())
        self.run_analysis()
        self.model_interpret.assert_not_called()
        self.assertTrue(self.window.interpretation_panel.isHidden())
        self.assertIsNone(self.window._interpretation_text)
        self.assertIn('Groups flagged for REVIEW: 1', self.window.core_results.toPlainText())
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [])
        self.assertTrue(self.window.save_raw_btn.isEnabled())
        self.assertFalse(self.window.save_interpretation_btn.isEnabled())

    def test_cancelling_alert_never_calls_model(self):
        self.run_analysis()
        with patch.object(gui.QMessageBox, 'warning', return_value=gui.QMessageBox.StandardButton.Cancel):
            self.window._interpret()
        self.model_interpret.assert_not_called()
        self.assertTrue(self.window.interpretation_panel.isHidden())

    def test_accepted_interpretation_is_side_by_side_and_not_saved_automatically(self):
        self.run_analysis()
        raw = self.window.result['raw_bytes']
        self.accept_interpretation()
        self.model_interpret.assert_called_once()
        self.assertFalse(self.window.interpretation_panel.isHidden())
        self.assertEqual(self.window.results_split.orientation(), gui.Qt.Orientation.Horizontal)
        self.assertEqual(self.window.interpretation.toPlainText(), 'Review the repeated references.')
        self.assertEqual(self.window.result['raw_bytes'], raw)
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [])
        self.assertTrue(self.window.save_interpretation_btn.isEnabled())

    def test_each_output_can_be_saved_independently(self):
        self.run_analysis()
        raw_copy = Path(self.tmp.name) / 'raw-copy.txt'
        with patch.object(gui.QFileDialog, 'getSaveFileName', return_value=(str(raw_copy), '')):
            self.window._save_raw_results()
        self.assertEqual(raw_copy.read_bytes(), self.window.result['raw_bytes'])
        self.accept_interpretation()
        interpretation_copy = Path(self.tmp.name) / 'interpretation-copy.txt'
        with patch.object(gui.QFileDialog, 'getSaveFileName', return_value=(str(interpretation_copy), '')):
            self.window._save_interpretation()
        self.assertEqual(interpretation_copy.read_text(), self.window._interpretation_text)
        self.assertEqual(raw_copy.read_bytes(), self.window.result['raw_bytes'])

    def test_interpretation_export_cannot_replace_raw_report(self):
        self.run_analysis()
        self.accept_interpretation()
        raw_path = Path(self.tmp.name) / 'saved-results.txt'
        with patch.object(gui.QFileDialog, 'getSaveFileName', return_value=(str(raw_path), '')):
            self.window._save_raw_results()
        original = raw_path.read_bytes()
        with patch.object(gui.QFileDialog, 'getSaveFileName', return_value=(str(raw_path), '')):
            with patch.object(self.window, '_error') as error:
                self.window._save_interpretation()
        error.assert_called_once()
        self.assertEqual(raw_path.read_bytes(), original)

    def test_unavailable_model_disables_processing(self):
        with patch.object(gui, 'check_model', side_effect=RuntimeError('Ollama stopped')):
            self.window._model_changed('test:1b')
            self.wait_idle()
        self.assertIsNone(self.window.ready_model)
        self.assertFalse(any(x.isEnabled() for x in self.window._actions))

    def test_interpretation_failure_preserves_raw_results(self):
        self.run_analysis()
        original = self.window.core_results.toPlainText()
        with patch.object(gui, 'interpret_results', side_effect=RuntimeError('Ollama stopped')):
            self.accept_interpretation()
        self.assertEqual(self.window.core_results.toPlainText(), original)
        self.assertIn('Interpretation unavailable', self.window.interpretation.toPlainText())
        self.assertFalse(self.window.save_interpretation_btn.isEnabled())

    def test_missing_results_contract_is_explained(self):
        self.script_file.write_text('print("Console output only")')
        with patch.object(self.window, '_script_error') as error:
            self.run_analysis()
        self.assertIsNone(self.window.result)
        self.model_interpret.assert_not_called()
        self.assertIn('did not create results.txt', error.call_args.args[0])

    def test_failed_script_cleans_up_its_temporary_workspace(self):
        self.script_file.write_text('raise RuntimeError("Example failure")')
        with patch.object(self.window, '_script_error') as error:
            self.run_analysis()
        self.assertIsNone(self.window.result)
        self.assertIn('Example failure', error.call_args.args[0])
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [])

    def test_timeout_cleans_up_its_temporary_workspace(self):
        with patch.object(gui.subprocess, 'run', side_effect=gui.subprocess.TimeoutExpired('analysis.py', 90)):
            with patch.object(self.window, '_script_error') as error:
                self.run_analysis()
        self.assertIsNone(self.window.result)
        error.assert_called_once()
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [])

    def test_helper_only_script_reports_missing_results(self):
        self.script_file.write_text('import re\nPATTERN = re.compile("x")\ndef parse_date(raw):\n    if raw:\n        day, month = 1, 2\n')
        with patch.object(self.window, '_script_error') as error:
            self.run_analysis()
        self.assertIsNone(self.window.result)
        self.assertIn('did not create results.txt', error.call_args.args[0])

    def test_syntax_error_uses_followup_dialog(self):
        self.script_file.write_text('def broken(:\n    pass\n')
        with patch.object(self.window, '_script_error') as error:
            self.run_analysis()
        self.assertIn('SyntaxError', error.call_args.args[0])
        self.assertIn('def broken(:', error.call_args.args[0])

    def test_missing_selected_file_uses_followup_dialog(self):
        self.script_file.unlink()
        with patch.object(self.window, '_script_error') as error:
            self.window._run_code()
            self.wait_idle()
        self.assertIn('FileNotFoundError', error.call_args.args[0])

    def test_runtime_error_details_are_not_truncated(self):
        self.script_file.write_text('raise RuntimeError("' + 'x' * 12000 + 'FINAL_MARKER")')
        with patch.object(self.window, '_script_error') as error:
            self.run_analysis()
        self.assertIn('x' * 12000 + 'FINAL_MARKER', error.call_args.args[0])

    def test_selected_file_is_reread_and_original_bytes_are_unchanged(self):
        code = (b'# coding: latin-1\nimport sys\nfrom pathlib import Path\n'
                b'Path(sys.argv[sys.argv.index("--output") + 1], "results.txt").write_text("caf\xe9", encoding="utf-8")\n')
        self.script_file.write_bytes(code)
        self.run_analysis()
        self.assertEqual(self.window.core_results.toPlainText(), 'caf\xe9')
        self.assertEqual(self.script_file.read_bytes(), code)
        self.script_file.write_bytes(code.replace(b'caf\xe9', b'replaced'))
        self.run_analysis()
        self.assertEqual(self.window.core_results.toPlainText(), 'replaced')

    def test_error_dialog_copy_button_copies_the_exact_followup_prompt(self):
        captured = {}
        def inspect_dialog():
            dialog = self.qt.activeModalWidget()
            captured['message'] = dialog.findChild(gui.QPlainTextEdit).toPlainText()
            for item in dialog.findChildren(gui.QPushButton):
                if item.text() == 'Copy follow-up prompt':
                    item.click()
            captured['clipboard'] = self.qt.clipboard().text()
            dialog.reject()
        gui.QTimer.singleShot(0, inspect_dialog)
        self.window._script_error('SyntaxError: example')
        expected = gui.script_error_prompt('SyntaxError: example')
        self.assertEqual(captured['message'], expected)
        self.assertEqual(captured['clipboard'], expected)
