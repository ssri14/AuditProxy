# AuditProxy desktop packages

Participants install Ollama and download a local text model beforehand. The
packages include Python and PyQt6; participants do not need Python, pip or a
virtual environment. Models and original datasets are never bundled.

## Build using an existing environment

Install the build requirements into your chosen environment, then build:

```
python -m pip install -r requirements-build.txt
python build_package.py
```

Build on macOS for a `.app` and DMG; build on Windows for a portable single
`AuditProxy.exe`. PyInstaller is not a cross-compiler. A Windows build and an
Intel Mac build must be produced and tested on suitable native build hosts.
Native build files are kept in the local OS temporary directory (`AuditProxy-build`) to preserve macOS framework links outside cloud-sync folders. Only the finished DMG/EXE is copied into the project’s `dist/`. Use `--build-dir PATH` to choose a different non-synced scratch directory, or `--skip-build` to package an already built app.

The macOS architecture matches the build interpreter. Qt/Python's minimum OS
requirements also apply; the current Apple Silicon test build uses Qt 6.12 and targets macOS 14 or later.

Python and PyQt package license metadata are included in the app bundle.

The bundle is allowlisted to application code and `sample_data/`. It does not
include `sample_output/`, tests, private CSVs, existing environments or results.

## Analysis files in the packaged app

A separate process runs the selected `.py` using the packaged Python runtime,
without opening a second GUI. Stdlib modules are collected explicitly so scripts
can import them dynamically. Platform-specific modules remain platform-specific.
Tk, Python installation tooling and test/demo internals are excluded. Third-party
analysis libraries (for example pandas or NumPy) are not included; request
standard-library-only scripts. Source launches can use packages already present
in the chosen environment. Execution remains unsandboxed, as documented in README.

Windowed builds capture script stdout/stderr in temporary files so errors remain
available in the follow-up prompt, including on Windows. Inputs, scripts and logs
are removed after each run. Only explicit Save/Export persists reports.

## Signing and release

The locally produced DMG is a test package, ad-hoc signed by PyInstaller. It is
not Developer ID signed or notarized. No signing identities are installed on this
build machine. For a public macOS release, build with a Developer ID identity via
`AUDITPROXY_CODESIGN_IDENTITY`, then notarize and staple the distribution using
your Apple Developer account. Do not distribute it as a notarized release before
those steps and clean-machine testing are complete. Windows release signing also
requires an appropriate certificate; the build script does not sign the EXE.

Before workshop distribution, test launch, Ollama connection, CSV selection,
prompt preparation, script execution, error-prompt copying, optional interpretation
and both Save buttons on clean target machines without Python installed.

## Sharing Mac and Windows builds

Each completed package has an adjacent `<filename>.sha256` checksum. Commit source changes using Git, then attach the platform packages and their checksums to the same GitHub Release. See [GITHUB.md](GITHUB.md).

## Build both platforms with GitHub Actions

The manually triggered `Build desktop packages` workflow runs native Apple Silicon macOS and Windows x64 builds, tests both, and uploads installers and checksums as downloadable workflow artifacts. No personal access token is stored in the workflow. See [GITHUB.md](GITHUB.md). Automated release publication and certificate-based signing are not enabled.
