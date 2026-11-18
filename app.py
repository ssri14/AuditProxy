#!/usr/bin/env python3
"""AuditProxy — PyQt6 offline-first desktop GUI.

The only application HTTP endpoint is the loopback Ollama API, managed by
ollama_local.py. The optional reviewed-script runner is NOT a sandbox.
"""
from __future__ import annotations

import os
from copy import deepcopy
from pathlib import Path
import traceback
import subprocess
import sys
import tempfile

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFrame, QDialog, QDialogButtonBox,
    QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPlainTextEdit,
    QPushButton, QSplitter, QStatusBar, QTabWidget, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget, QHeaderView,
)

from core import (
    export_aliased_csv, generate_prompt, profile_csv,
    synthetic_csv, script_error_prompt,
)
from ollama_local import improve_prompt, local_models, check_model, interpret_results
from results_local import read_results
from script_runtime import run_analysis_process

ROOT = Path(__file__).resolve().parent
SAMPLE = ROOT / "sample_data" / "synthetic_government_expenses.csv"
SAMPLE_CODE = ROOT / "sample_data" / "example_reviewed_analysis.py"

STYLE = """
/* Do NOT set background on all QWidget descendants: on macOS this paints
   opaque light rectangles behind labels inside the dark header. */
QWidget { color: #1a2b43; font-size: 12px; }
QMainWindow, QWidget#appRoot, QWidget#tabPage {
    background-color: #f5f7fb;
}
QFrame#topbar { background-color: #152c4f; border: none; border-radius: 12px; }
QFrame#topbar QLabel { background-color: transparent; border: none; }
QLabel#brand { color: #ffffff; font-weight: 700; font-size: 24px; }
QLabel#subtitle { color: #d5e2f4; font-size: 12px; }
QLabel#section { font-size: 17px; font-weight: 700; color: #172b4d; }
QLabel#hint { color: #526477; font-size: 11px; }
QLabel#warning { color: #a1432c; font-size: 11px; font-weight: 600; }
QPushButton {
    background-color: #ffffff; color: #1a2b43;
    border: 1px solid #cdd7e4; border-radius: 7px;
    padding: 8px 12px; font-weight: 600;
}
QPushButton:hover { border-color: #6d92c0; background-color: #f0f5fb; }
QPushButton:disabled { color: #788698; background-color: #e8edf3; }
QPushButton#primary {
    background-color: #145c9a; color: #ffffff; border: 1px solid #145c9a;
}
QPushButton#primary:hover { background-color: #0c477d; }
QPlainTextEdit, QTableWidget, QComboBox {
    background-color: #ffffff; color: #1a2b43;
    border: 1px solid #cbd5e1; border-radius: 7px;
    padding: 5px;
    selection-background-color: #d8e9fb;
    selection-color: #172b4d;
}
QPlainTextEdit {
    font-family: 'Consolas', 'Menlo', 'DejaVu Sans Mono', monospace;
    font-size: 11px;
}
QComboBox QAbstractItemView {
    background-color: #ffffff; color: #1a2b43;
    selection-background-color: #d8e9fb; selection-color: #172b4d;
}
QTabWidget::pane {
    border: 1px solid #dae3ed;
    background-color: #f5f7fb; border-radius: 8px;
}
QTabBar::tab {
    color: #213b59; padding: 11px 19px; margin-right: 3px;
    background-color: #e9eff7; border: 1px solid #d6dfeb;
    border-radius: 6px; font-weight: 600;
}
QTabBar::tab:selected { background-color: #ffffff; color: #145c9a; }
QHeaderView::section {
    background-color: #eaf0f7; color: #233d5b;
    font-weight: 600; padding: 7px 5px; border: none;
    border-right: 1px solid #d5e0ed;
}
QTableWidget {
    gridline-color: #e8edf2;
    alternate-background-color: #f8fbff;
}
QSplitter::handle { background-color: #d5dfeb; }
QCheckBox { spacing: 8px; }
QStatusBar { background-color: #e8eef6; color: #344b63; }
QStatusBar QLabel { background-color: transparent; color: #344b63; }
QToolTip { background-color: #ffffff; color: #1a2b43; border: 1px solid #cbd5e1; }
"""


class TaskThread(QThread):
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, fn, parent=None, error_details=False):
        super().__init__(parent)
        self.fn = fn
        self.error_details = error_details

    def run(self):
        try:
            self.succeeded.emit(self.fn())
        except Exception as exc:
            self.failed.emit(''.join(traceback.format_exception(type(exc), exc, exc.__traceback__))
                             if self.error_details else str(exc))


def label(text: str, kind: str = "hint", wrap: bool = True) -> QLabel:
    widget = QLabel(text)
    widget.setObjectName(kind)
    widget.setWordWrap(wrap)
    return widget


def button(text: str, handler, primary: bool = False) -> QPushButton:
    btn = QPushButton(text)
    if primary:
        btn.setObjectName("primary")
    btn.clicked.connect(handler)
    return btn


class AuditProxyApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('AuditProxy')
        self.resize(1180, 870)
        self.setMinimumSize(940, 700)
        self.profile = None
        self.script_path = None
        self.ready_model = None
        self.result = None
        self._raw_export_path = None
        self._interpretation_text = None
        self._threads = set()
        self._closing = False
        self._busy = False
        self._actions = []
        self._build_ui()
        QTimer.singleShot(0, self._refresh_models)

    def _action(self, text, fn, primary=False):
        item = button(text, fn, primary)
        self._actions.append(item)
        return item

    def _build_ui(self):
        central = QWidget(objectName='appRoot')
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(18, 14, 18, 12)
        head = QFrame(objectName='topbar')
        head_layout = QVBoxLayout(head)
        head_layout.addWidget(label('AuditProxy', 'brand'))
        head_layout.addWidget(label('Your CSV → AI programming prompt → local analysis', 'subtitle'))
        outer.addWidget(head)
        model_row = QHBoxLayout()
        model_row.addWidget(label('Local model', wrap=False))
        self.model = QComboBox()
        self.model.setMinimumWidth(200)
        self.model.currentTextChanged.connect(self._model_changed)
        model_row.addWidget(self.model)
        self.reconnect = button('Reconnect', self._refresh_models)
        model_row.addWidget(self.reconnect)
        self.connection = label('Connecting to Ollama…')
        model_row.addWidget(self.connection, 1)
        outer.addLayout(model_row)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._data_tab(), '1  Choose data')
        self.tabs.addTab(self._prompt_tab(), '2  Prepare prompt')
        self.tabs.addTab(self._analysis_tab(), '3  Analyse and review')
        outer.addWidget(self.tabs, 1)
        self.setStatusBar(QStatusBar(self))
        self._update_actions()

    def _pane(self):
        pane = QWidget(objectName='tabPage')
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        return pane, layout

    def _details(self, title, parent_layout):
        toggle = QPushButton('▸ ' + title)
        toggle.setCheckable(True)
        parent_layout.addWidget(toggle)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body.hide()
        parent_layout.addWidget(body)
        def expanded(checked):
            body.setVisible(checked)
            toggle.setText(('▾ ' if checked else '▸ ') + title)
        toggle.toggled.connect(expanded)
        return body_layout

    def _data_tab(self):
        pane, layout = self._pane()
        layout.addWidget(label('Choose a CSV to analyse', 'section'))
        row = QHBoxLayout()
        self.open_btn = button('Open CSV…', self._browse, True)
        self.sample_btn = button('Try sample data', lambda: self._load(SAMPLE))
        row.addWidget(self.open_btn)
        row.addWidget(self.sample_btn)
        self.file_label = label('No CSV selected')
        row.addWidget(self.file_label, 1)
        layout.addLayout(row)
        layout.addWidget(label('Double-click a field to include or exclude it. Aliases are used in the programming prompt.'))
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(['Use', 'Alias', 'CSV field', 'Type', 'Role'])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 45)
        self.table.setColumnWidth(1, 65)
        self.table.cellDoubleClicked.connect(self._toggle_column)
        layout.addWidget(self.table, 1)
        self.schema_label = label('')
        layout.addWidget(self.schema_label)
        details = self._details('Preview invented example rows', layout)
        self.synthetic = QPlainTextEdit()
        self.synthetic.setReadOnly(True)
        self.synthetic.setMaximumHeight(140)
        details.addWidget(self.synthetic)
        layout.addWidget(button('Next: describe the task →', lambda: self.tabs.setCurrentIndex(1), True))
        return pane

    def _prompt_tab(self):
        pane, layout = self._pane()
        layout.addWidget(label('What would you like to check?', 'section'))
        self.question = QPlainTextEdit()
        self.question.setPlainText('Identify high-value payments, repeated transaction references, missing key fields, and supplier expenditure totals.')
        self.question.setMaximumHeight(95)
        self.question.textChanged.connect(self._invalidate_prompt)
        layout.addWidget(self.question)
        layout.addWidget(self._action('Prepare prompt with local AI', self._prepare_prompt, True))
        layout.addWidget(label('Edit the prepared prompt, then copy it to your preferred coding LLM.'))
        self.prompt_text = QPlainTextEdit()
        self.prompt_text.setPlaceholderText('Your programming prompt will appear here.')
        layout.addWidget(self.prompt_text, 1)
        row = QHBoxLayout()
        row.addWidget(button('Copy prompt', self._copy_prompt))
        row.addWidget(button('Save prompt…', self._save_prompt))
        row.addStretch()
        row.addWidget(button('Next: run analysis →', lambda: self.tabs.setCurrentIndex(2), True))
        layout.addLayout(row)
        return pane

    def _analysis_tab(self):
        pane, layout = self._pane()
        layout.addWidget(label('Run analysis and review the results', 'section'))
        layout.addWidget(label('Choose the Python file created by your coding LLM, then run it against your CSV.'))
        script_row = QHBoxLayout()
        self.choose_script_btn = button('Choose Python file…', self._choose_script, True)
        script_row.addWidget(self.choose_script_btn)
        self.script_label = label('No Python file selected')
        script_row.addWidget(self.script_label, 1)
        layout.addLayout(script_row)
        row = QHBoxLayout()
        self.run_btn = self._action('Run analysis', self._run_code, True)
        row.addWidget(self.run_btn)
        row.addWidget(self._action('Export working CSV…', self._export))
        row.addStretch()
        layout.addLayout(row)
        self.results_split = QSplitter(Qt.Orientation.Horizontal)
        core = QWidget()
        core_layout = QVBoxLayout(core)
        core_layout.setContentsMargins(0, 0, 0, 0)
        core_layout.addWidget(label('Raw results · results.txt', 'section'))
        self.core_results = QPlainTextEdit()
        self.core_results.setReadOnly(True)
        self.core_results.setPlaceholderText('The complete contents of results.txt will appear here after analysis.')
        core_layout.addWidget(self.core_results, 1)
        self.save_raw_btn = button('Save raw results…', self._save_raw_results)
        core_layout.addWidget(self.save_raw_btn)
        self.results_split.addWidget(core)
        self.interpretation_panel = QWidget()
        il = QVBoxLayout(self.interpretation_panel)
        il.setContentsMargins(0, 0, 0, 0)
        il.addWidget(label('Local AI interpretation', 'section'))
        self.interpretation_scope = label('')
        il.addWidget(self.interpretation_scope)
        self.interpretation = QPlainTextEdit()
        self.interpretation.setReadOnly(True)
        il.addWidget(self.interpretation, 1)
        self.save_interpretation_btn = button('Save interpretation…', self._save_interpretation)
        il.addWidget(self.save_interpretation_btn)
        self.results_split.addWidget(self.interpretation_panel)
        self.interpretation_panel.hide()
        layout.addWidget(self.results_split, 1)
        row = QHBoxLayout()
        self.retry_btn = self._action('Get interpretation from local AI', self._interpret)
        row.addWidget(self.retry_btn)
        row.addStretch()
        layout.addLayout(row)
        return pane

    def _status(self, text):
        self.statusBar().showMessage(text)

    def _error(self, title, text):
        self._status(text)
        QMessageBox.information(self, title, text)

    def _update_actions(self):
        enabled = bool(self.ready_model) and not self._busy
        for action in self._actions:
            action.setEnabled(enabled and self.profile is not None)
        self.run_btn.setEnabled(enabled and self.profile is not None and self.script_path is not None)
        self.retry_btn.setEnabled(enabled and self.result is not None)
        self.save_raw_btn.setEnabled(self.result is not None)
        self.save_interpretation_btn.setEnabled(self._interpretation_text is not None)

    def _set_busy(self, busy):
        self._busy = busy
        for widget in (self.open_btn, self.sample_btn, self.table, self.question,
                       self.prompt_text, self.choose_script_btn, self.model, self.reconnect):
            widget.setEnabled(not busy)
        self._update_actions()

    def _job(self, fn, done, fail, error_details=False):
        self._set_busy(True)
        worker = TaskThread(fn, self, error_details=error_details)
        self._threads.add(worker)
        def success(value):
            self._set_busy(False)
            if not self._closing:
                done(value)
        def failure(error):
            self._set_busy(False)
            if not self._closing:
                fail(error)
        worker.succeeded.connect(success)
        worker.failed.connect(failure)
        def cleanup():
            self._threads.discard(worker)
            worker.deleteLater()
            if self._closing and not self._threads:
                self.close()
        worker.finished.connect(cleanup)
        worker.start()

    def closeEvent(self, event):
        if self._threads:
            self._closing = True
            self._set_busy(True)
            self._status('Finishing the current operation before closing…')
            event.ignore()
        else:
            event.accept()

    def _refresh_models(self):
        self.ready_model = None
        self.connection.setText('Connecting to Ollama…')
        previous = self.model.currentText()
        def done(models):
            self.model.blockSignals(True)
            self.model.clear()
            self.model.addItems(models)
            preferred = previous if previous in models else ('llama3.2:1b' if 'llama3.2:1b' in models else '')
            if preferred:
                self.model.setCurrentText(preferred)
            self.model.blockSignals(False)
            if models:
                self._model_changed(self.model.currentText())
            else:
                self.connection.setText('No text model found. Install a local model in Ollama, then reconnect.')
                self._update_actions()
        self._job(local_models, done, self._connection_failed)

    def _connection_failed(self, error):
        self.ready_model = None
        self.connection.setText(error)
        self._update_actions()

    def _model_changed(self, model):
        self.ready_model = None
        self._update_actions()
        if not model:
            return
        self.connection.setText('Starting local model…')
        def ready(name):
            self.ready_model = name
            self.connection.setText('● Running locally')
            self._status('Local model ready. Choose your CSV to begin.')
            self._update_actions()
        self._job(lambda: check_model(model), ready, self._connection_failed)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Open CSV', str(Path.home()), 'CSV files (*.csv)')
        if path:
            self._load(path)

    def _load(self, path):
        try:
            self.profile = profile_csv(path)
        except Exception as exc:
            self._error('Cannot open CSV', str(exc))
            return
        self.file_label.setText(self.profile.path.name)
        self._refresh_table()
        self._invalidate_prompt()
        self.result = None
        self._raw_export_path = None
        self._interpretation_text = None
        self.core_results.clear()
        self.interpretation_panel.hide()
        self.interpretation.clear()
        self.schema_label.setText(f'{len(self.profile.columns)} fields · {self.profile.sampled_rows} records sampled')
        self._update_actions()
        self._status('CSV loaded. Continue to Prepare prompt.')

    def _refresh_table(self):
        self.table.setRowCount(len(self.profile.columns))
        for row, column in enumerate(self.profile.columns):
            for col, value in enumerate(('✓' if column.include else '—', column.alias,
                                         column.original, column.kind, column.role)):
                self.table.setItem(row, col, QTableWidgetItem(value))
        self.synthetic.setPlainText(synthetic_csv(self.profile))

    def _toggle_column(self, row, _column):
        self.profile.columns[row].include = not self.profile.columns[row].include
        self._refresh_table()
        self._invalidate_prompt()
        self.result = None
        self._raw_export_path = None
        self._interpretation_text = None
        self.core_results.clear()
        self.interpretation_panel.hide()
        self.interpretation.clear()
        self._update_actions()

    def _invalidate_prompt(self):
        if hasattr(self, 'prompt_text'):
            self.prompt_text.clear()

    def _prepare_prompt(self):
        if not self.ready_model or not self.profile:
            return
        try:
            base = generate_prompt(self.profile, self.question.toPlainText())
        except ValueError as exc:
            self._error('Describe your task', str(exc))
            return
        model = self.ready_model
        context = ('Task: ' + self.question.toPlainText().strip() + '\nFields:\n'
                   + '\n'.join(f'{c.alias}: {c.kind}, {c.role}' for c in self.profile.columns if c.include))
        self._status('Local model is preparing your analysis plan…')
        def done(plan):
            self.prompt_text.setPlainText(base + '\n\nANALYSIS PLAN:\n' + plan)
            self._status('Prompt ready. Edit or copy it, then continue to analysis.')
        self._job(lambda: improve_prompt(model, context), done,
                  lambda err: self._error('Could not prepare prompt', err))

    def _copy_prompt(self):
        if self.prompt_text.toPlainText().strip():
            QApplication.clipboard().setText(self.prompt_text.toPlainText())
            self._status('Prompt copied.')

    def _save_prompt(self):
        if not self.prompt_text.toPlainText().strip():
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Save prompt', str(Path.home() / 'audit_prompt.txt'), 'Text files (*.txt)')
        if path:
            try:
                Path(path).write_text(self.prompt_text.toPlainText() + '\n', encoding='utf-8')
                self._status('Prompt saved.')
            except OSError as exc:
                self._error('Cannot save prompt', str(exc))

    def _export(self):
        if not self.profile or not self.ready_model:
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Export working CSV', str(Path.home() / 'working_data.csv'), 'CSV files (*.csv)')
        if path:
            profile = deepcopy(self.profile)
            self._job(lambda: export_aliased_csv(profile, path, overwrite=True),
                      lambda count: self._status(f'Exported {count} records.'),
                      lambda err: self._error('Cannot export CSV', err))

    def _choose_script(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Choose analysis script', str(Path.home()), 'Python files (*.py *.PY)')
        if path:
            self.script_path = Path(path).resolve()
            self.script_label.setText(self.script_path.name)
            self.script_label.setToolTip(str(self.script_path))
            self._update_actions()
            self._status('Python file selected. Run analysis when ready.')

    def _script_error(self, error):
        prompt = script_error_prompt(error)
        self._status('Script execution failed. A follow-up prompt is ready to copy.')
        dialog = QDialog(self)
        dialog.setWindowTitle('Script execution error')
        dialog.resize(820, 540)
        layout = QVBoxLayout(dialog)
        layout.addWidget(label('There was an error in executing the script. You may paste the following follow-up prompt to the LLM:'))
        details = QPlainTextEdit()
        details.setReadOnly(True)
        details.setPlainText(prompt)
        layout.addWidget(details, 1)
        copy_btn = button('Copy follow-up prompt', lambda: QApplication.clipboard().setText(prompt), True)
        layout.addWidget(copy_btn)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(dialog.reject)
        layout.addWidget(close)
        dialog.exec()

    def _run_code(self):
        if not self.ready_model or not self.profile:
            return
        if self.script_path is None:
            self._script_error('No Python file is selected. Choose an analysis.py or another .py file first.')
            return
        selected_script = self.script_path
        profile, model = deepcopy(self.profile), self.ready_model
        self.result = None
        self._raw_export_path = None
        self._interpretation_text = None
        self.core_results.clear()
        self.interpretation_panel.hide()
        self.interpretation.clear()
        self._status('Running analysis locally…')
        def execute():
            source_bytes = selected_script.read_bytes()  # Re-read replacements on each run.
            check_model(model)  # Actual inference is required before processing.
            with tempfile.TemporaryDirectory(prefix='auditproxy_run_') as workspace:
                folder = Path(workspace)
                input_path = folder / 'working_data.csv'
                script_path = folder / selected_script.name
                results = folder / 'results'
                results.mkdir()
                export_aliased_csv(profile, input_path)
                script_path.write_bytes(source_bytes)
                proc = run_analysis_process(script_path, input_path, results, folder)
                if proc.returncode:
                    raise RuntimeError(f'Python exited with status {proc.returncode}.\n'
                                       f'STDERR:\n{proc.stderr}\nSTDOUT:\n{proc.stdout}')
                return read_results(results)
        def done(result):
            self.result = result
            self.core_results.setPlainText(result['raw_text'])
            self._update_actions()
            self._status('Raw results ready. Read them, save a copy, or request a local AI interpretation.')
        def failed(err):
            self.interpretation_panel.hide()
            self.interpretation.clear()
            self._script_error(err)
        self._job(execute, done, failed, error_details=True)

    def _interpret(self):
        if not self.result or not self.ready_model:
            return
        choice = QMessageBox.warning(
            self, 'Local AI interpretation',
            'Local LLMs may not be reliable at interpretation. The interpretation may be wrong, '
            'incomplete or misleading. Verify it manually against the raw results and source records.\n\n'
            'Continue with local AI interpretation?',
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel)
        if choice != QMessageBox.StandardButton.Ok:
            return
        result, model = self.result, self.ready_model
        self._interpretation_text = None
        self.interpretation_panel.show()
        self.results_split.setSizes([550, 550])
        self.interpretation_scope.setText(
            'Based on the first 12,000 characters; the complete report remains on the left.'
            if result['truncated'] else 'Based on the raw results shown on the left.')
        self.interpretation.setPlainText('Local model is interpreting the results…')
        self._status('Preparing local AI interpretation…')
        def done(text):
            self._interpretation_text = text
            self.interpretation.setPlainText(text)
            self._update_actions()
            self._status('Interpretation ready. Save either document if useful.')
        def failed(err):
            self.interpretation.setPlainText('Interpretation unavailable. ' + err)
            self._status('Raw results remain available. Reconnect or retry interpretation.')
        self._job(lambda: interpret_results(model, result['evidence']), done, failed)

    def _save_raw_results(self):
        if self.result:
            saved = self._save_document('Save raw results', 'results.txt', self.result['raw_bytes'])
            if saved is not None:
                self._raw_export_path = saved

    def _save_interpretation(self):
        if self._interpretation_text is not None:
            self._save_document('Save interpretation', 'interpretation.txt',
                                self._interpretation_text.encode('utf-8'), interpretation=True)

    def _save_document(self, title, filename, contents, interpretation=False):
        path, _ = QFileDialog.getSaveFileName(self, title, str(Path.home() / filename), 'Text files (*.txt)')
        if not path:
            return
        destination = Path(path).absolute()
        protected = [self.profile.path] if self.profile else []
        if interpretation and self._raw_export_path is not None:
            protected.append(self._raw_export_path)
        try:
            for source in protected:
                if destination.resolve() == source.resolve() or (destination.exists() and destination.samefile(source)):
                    raise ValueError('Choose a different filename to preserve the source data and raw results.')
            with tempfile.TemporaryDirectory(prefix='.auditproxy-', dir=destination.parent) as staging:
                staged = Path(staging) / filename
                staged.write_bytes(contents)
                os.replace(staged, destination)
            self._status(f'Saved {destination.name}.')
            return destination
        except (OSError, ValueError) as exc:
            self._error('Cannot save', str(exc))


def main():
    if sys.version_info < (3, 10):
        raise SystemExit("Python 3.10 or later is required.")
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    # Explicit light palette avoids unreadable native text / placeholder colors
    # when macOS or Windows is configured for dark appearance.
    palette = app.palette()
    role_colors = {
        QPalette.ColorRole.Window: "#f5f7fb",
        QPalette.ColorRole.WindowText: "#1a2b43",
        QPalette.ColorRole.Base: "#ffffff",
        QPalette.ColorRole.AlternateBase: "#f8fbff",
        QPalette.ColorRole.Text: "#1a2b43",
        QPalette.ColorRole.Button: "#ffffff",
        QPalette.ColorRole.ButtonText: "#1a2b43",
        QPalette.ColorRole.Highlight: "#d8e9fb",
        QPalette.ColorRole.HighlightedText: "#172b4d",
        QPalette.ColorRole.PlaceholderText: "#687c92",
    }
    for role, hex_color in role_colors.items():
        palette.setColor(role, QColor(hex_color))
    app.setPalette(palette)
    app.setStyleSheet(STYLE)
    window = AuditProxyApp()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
