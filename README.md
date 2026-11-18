# AuditProxy — Offline Audit Analysis Assistant (v0.3.0 / PyQt6)

**Purpose:** A standalone desktop application for government-audit training and basic offline transaction review. AuditProxy turns a private CSV schema and a generic audit question into a programming specification that can be shared **only with an approved AI system**, without attaching original CSV records. It runs the Python script prepared for the auditor’s requested task against the actual CSV locally. This is an independent demonstration, **not an official CAG application**.

## Start here: platform launchers

Python **3.10+** must already be installed. The `setup` scripts create a reusable local virtual environment called `.venv` (only if missing) and install **PyQt6**. The `run` scripts **activate the environment and launch `app.py`**, invoking setup themselves when needed.

| Platform | First-time setup (optional) | Normal launch |
|---|---|---|
| macOS | `bash setup.sh` | `./run.sh` (or `bash run.sh`) |
| Linux | `bash setup.sh` | `./run.sh` (or `bash run.sh`) |
| Windows Command Prompt | `setup.bat` | `run.bat` |

On Windows, users can **double-click `run.bat`** in File Explorer. Run it from a normal command prompt to see setup diagnostics. On macOS/Linux, open a terminal in the extracted folder and run `bash run.sh`. All scripts resolve their own directory, so the user does not need to be in the project folder.

**The first setup can require internet access:** PyQt6 must be installed into `.venv`. **Normal app use needs no internet**, except that the user must already have Ollama and model weights locally before using the application.

### Fully air-gapped initial setup

On an internet-connected computer **of the same operating system, CPU architecture, and compatible Python version** as the target computer, download wheels:

```bash
python -m pip download -r requirements.txt -d wheels
```

On Windows, use `py -3 -m pip download -r requirements.txt -d wheels` (if the Python launcher is installed).

Copy the complete project directory, including `wheels/`, to the target machine. Then run its corresponding **setup** or **run** script. The scripts automatically detect `wheels/*.whl` and use:

```bash
python -m pip install --no-index --find-links ./wheels -r requirements.txt
```

**Important:** PyQt6 wheels are platform-specific, so a wheelhouse downloaded on macOS generally **will not** install on Windows or Linux. Build separate offline bundles for each target platform/architecture/Python version. `wheels/` is **not** included in this source-code ZIP. An isolated computer without preinstalled PyQt6 or compatible wheels **cannot run the initial setup** without some authorized offline package transfer.

Linux distributions may require additional GUI-system libraries (e.g. Qt/XCB runtime dependencies). Install those using approved OS installation media or local package mirrors before disconnecting.

To select a particular Python on macOS/Linux, run e.g. `PYTHON_BIN=python3.12 bash setup.sh`. To force a clean environment, close the application, delete `.venv` and run setup again. Do not copy an existing `.venv` between different computers or operating systems.

## Workflow

1. **Connect:** start Ollama. AuditProxy finds installed text models and checks the selected model automatically. Use Reconnect after starting Ollama or installing a model.
2. **Choose data:** open a CSV or try the sample. Inspect the field list; double-click to exclude a field. Invented examples are available in a collapsed preview.
3. **Prepare prompt:** describe the audit task and click **Prepare prompt with local AI**. Edit, copy or save the programming prompt, then download the `analysis.py` file from your preferred coding LLM.
4. **Analyse & review:** click **Choose Python file…**, select `analysis.py` (or any other `.py` file) returned by your coding LLM, then click **Run analysis**. The app prepares the working CSV and runs the script in a temporary workspace automatically; no output-folder selection is needed. It does not run predefined audit checks.
5. **Review raw results:** the script must write all analytical output to one UTF-8 file named `results.txt` inside its `--output` directory. The app displays the complete report first. Old scripts that write only `summary.txt`, CSVs, or console output must be updated using the new prompt.
6. **Optional interpretation:** click **Get interpretation from local AI**. A reliability alert appears; cancelling makes no interpretation request. After accepting, the app shows the unchanged raw report and local AI interpretation side by side. Long reports are shown in full, but only the first 12,000 characters are sent to the model; this scope is displayed beside the interpretation.
7. **Save independently:** **Save raw results…** exports an exact copy of the report. **Save interpretation…** saves only a successful interpretation. Interpretation is kept in memory unless you choose to save it; it never overwrites the script's raw report.

The script writes `results.txt` inside its temporary workspace during execution; Save raw results keeps a permanent copy at a location you choose. All analytical outputs, tables, row references, methodology and limitations belong in that one report. AI interpretation is optional and must be verified manually. Script results are displayed as reported by the script; its numerical logic is not independently certified.

Each analysis run uses a fresh temporary workspace that is cleaned up after the report is loaded, including on script errors. Raw results remain in memory for review and optional export. Only Save/Export asks for a destination; unsaved results are lost when you close the app or start another analysis. Working CSV exports reject source-file collisions, validate the complete input, and replace an existing destination only after the save dialog confirms replacement and processing succeeds. Rows with missing or extra fields are rejected; explicitly empty CSV cells remain valid.

## Required local model

The only HTTP endpoint called by AuditProxy is **`http://127.0.0.1:11434`**, served by Ollama on the same machine. AuditProxy does not download or install models.

Before entering an air-gapped environment, install Ollama and download a small model, for example:

```bash
ollama pull llama3.2:1b
```

Make sure the local Ollama server is running. Use **Reconnect** if the app was opened before Ollama started. The app connects automatically and verifies that the selected model can generate text. Prompt preparation and analysis require a running local text model. Embedding-only and cloud-labelled models are excluded from the model list. The underlying core tests still run without Ollama.

## Files in this project

| Path | Purpose |
|---|---|
| `app.py` | PyQt6 desktop UI (three tabs) |
| `core.py` | Offline CSV profiling, synthetic examples, aliased exports |
| `ollama_local.py` | Local model readiness, constrained planning and results interpretation |
| `results_local.py` | Single results.txt reader and bounded local interpretation input |
| `requirements.txt` | PyQt6 GUI dependency |
| `setup.sh` / `run.sh` | macOS and Linux setup + launcher |
| `setup.bat` / `run.bat` | Windows setup + launcher |
| `sample_data/` | Synthetic transactions + example reviewed script |
| `tests/` | Core and workflow regression tests |

Run the offline core tests with:

```bash
# macOS/Linux
.venv/bin/python -m unittest discover -s tests -v

# Windows
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Technical limits

- The original CSV is processed **locally**. The external prompt only uses neutral field aliases, inferred generic types/roles, and invented rows. **The auditor's free-text question is not automatically anonymized**; never enter case identifiers or secrets into it. Field roles and derived schema could themselves be sensitive.
- The **private aliased CSV contains unchanged REAL transactions**, merely with different column headers. It is **not** anonymized and must never be shared as a sanitised input.
- Neither AuditProxy nor a small LLM is a certified anonymization or data-loss-prevention system. Schema abstraction is not a guarantee. Institutional approval is necessary before disclosure.
- **Executing generated code is not sandboxed.** `python -I` only changes interpreter startup behaviour; it cannot prevent filesystem or network access. Run any reviewed generated script only in a **separate, disposable, offline VM with limited file access**. Do not use this feature on a production workstation or confidential departmental system without a proper security review.
- The app cannot stop other processes or the executed script from using the network; disconnect it at OS/network level for a genuine offline exercise.
- Audit heuristics and suggestions are not legal findings. Repeated transaction numbers can describe legitimate multi-line entries; they must not automatically be called duplicate payments.
- Original records and generated outputs can be confidential. Keep them in approved private folders and follow local retention policy.
- CSV profiling samples up to 500 rows, which may not reflect all data types. Analysis logic comes from the supplied Python script.

## Packaging note

For distribution, package **source files**, `requirements.txt`, the four scripts, sample data and tests. Exclude `.venv/`, `__pycache__/`, original real CSVs, and sensitive output files. For air-gapped classrooms, include a separate compatible `wheels/` bundle for each distinct platform.

## Use an existing Python environment

Activate your existing environment, install `requirements.txt` there if necessary, then run `python app.py` directly. No project `.venv` is needed for this route.

Script files are copied byte-for-byte into the temporary workspace and re-read on each run. Replacing the selected file with a corrected version is enough; the original script is never modified by the runner. Syntax errors, runtime errors, missing `results.txt`, timeouts and file-loading failures all show a follow-up prompt containing the actual error and a **Copy follow-up prompt** button. Send it to the coding LLM to request a replacement Python file.

## Desktop packaging

See [PACKAGING.md](PACKAGING.md) for native DMG/EXE builds, bundled script execution and release-signing requirements. The source folder retains its original name so existing launch commands remain valid.

## GitHub collaboration

See [GITHUB.md](GITHUB.md) for the first source push, fine-grained token permissions, building both installers with GitHub Actions, and attaching them to one GitHub Release. Installers and local analysis outputs are excluded from Git history.
