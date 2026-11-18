# Source repository and shared GitHub release

Use Git for the source code. Upload the DMG and EXE as **GitHub Release assets**;
do not commit installers, environments, confidential datasets or analysis outputs.
`.gitignore` excludes these files while keeping the bundled synthetic CSV.

## First push from this Mac

Create an **empty** GitHub repository named `AuditProxy` (without an initial
README, license or .gitignore, because this checkout already has its own history).
Then, in this project directory, replace `OWNER` in these commands:

```sh
git remote add origin https://github.com/OWNER/AuditProxy.git
git push -u origin main
```

Authenticate locally using GitHub CLI or Git Credential Manager. For a
fine-grained token, select only the AuditProxy repository and grant repository
**Contents: Read and write** and **Workflows: Read and write** (Metadata access is supplied automatically). Contents covers source pushes and release assets; Workflows permits pushing `.github/workflows/build-desktop.yml`. Actions permission is needed only if you also want to trigger or manage runs through the API/CLI; the browser workflow button does not require a separate token. Do not embed a token in the remote URL, files
or shell commands. GitHub CLI documents `GH_TOKEN` for fine-grained tokens; load
it privately into the local session rather than committing it or sharing it in chat.
The Windows collaborator should use their own GitHub account and repository access.

## Recommended: build both packages on GitHub

After the initial push, open **Actions → Build desktop packages → Run workflow**.
The manually triggered workflow runs two independent native jobs:

- `macos-15` (Apple Silicon/arm64): builds the macOS DMG.
- `windows-2022` (x64): builds the Windows EXE.

Each job installs the build dependencies, runs the tests, builds its native
package and SHA-256 checksum, and smoke-tests the bundled script runner and
traceback capture. No Ollama model, user dataset, signing secret or custom PAT is
needed by the workflow. It uses the automatic GitHub Actions token with source
read permission. Both jobs build the same selected workflow revision.

Download **AuditProxy-macOS-Apple-Silicon** and **AuditProxy-Windows-x64** from the
completed run's **Artifacts** section. Artifacts are retained for 30 days. Extract
the artifact ZIP to obtain the installer and its checksum. You do not need a
student or local Windows machine for these builds. Signing/notarization is not
performed; target-machine testing remains necessary before distributing.

The workflow does not publish a release automatically. Attach the downloaded
packages to one draft GitHub Release using the web UI, or use the commands below.
Runner availability and billing follow your GitHub repository/account plan.

References: [GitHub-hosted runner architectures](https://docs.github.com/en/actions/reference/runners/github-hosted-runners),
[workflow artifacts](https://github.com/actions/upload-artifact).

## Optional local builds on Mac and Windows

Build using Python 3.11 or 3.12 and the machine's existing chosen environment.
The Windows collaborator clones the repo; on this Mac use the existing checkout:

```sh
git clone https://github.com/OWNER/AuditProxy.git
cd AuditProxy
git pull --ff-only
python -m pip install -r requirements-build.txt
python -m unittest discover -s tests -v
python build_package.py
```

The clone/cd steps apply only to a new checkout. Existing Mac checkouts start at
`git pull --ff-only`. Both platforms must build from the commit used for the
release tag. Do not change application code just to upload the other platform's
installer. GUI tests require a desktop session; core tests need no Ollama server.
Actual Ollama and packaged-app checks are still needed before distributing.

On macOS the output is `dist/AuditProxy-0.3.0-macOS-arm64.dmg` (or `x86_64` for
an Intel interpreter). On Windows it is `dist/AuditProxy.exe`. Each package gets
its own adjacent `.sha256` file. Existing package files are preserved; move an old
build before rebuilding. See PACKAGING.md for signing and native build details.

## One draft release, two uploads

After the source has been pushed and authenticated GitHub CLI is available, the
release owner creates a draft. Replace `COMMIT_SHA` with `git rev-parse HEAD` from
the exact source revision both machines will build:

```sh
gh release create v0.3.0 --target COMMIT_SHA --title "AuditProxy v0.3.0" --notes-file RELEASE_NOTES.md --draft
```

The Mac contributor uploads its assets (adjust the architecture if needed):

```sh
gh release upload v0.3.0 dist/AuditProxy-0.3.0-macOS-arm64.dmg dist/AuditProxy-0.3.0-macOS-arm64.dmg.sha256
```

The Windows contributor uploads to **the same release**:

```sh
gh release upload v0.3.0 dist/AuditProxy.exe dist/AuditProxy.exe.sha256
```

The second machine should run `git fetch origin` and `git switch --detach COMMIT_SHA`
using the shared revision before building. Once the tag exists, `git fetch --tags`
and `git switch --detach v0.3.0` also select the exact release revision. Keep the release
a draft until both installers have been tested and the notes accurately describe
their signing status. Then publish it through GitHub's Releases page. The GitHub
web UI can also attach the files to the same draft release without CLI commands.

References: [release assets](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository),
[GitHub CLI authentication](https://cli.github.com/manual/gh_auth_login),
[release creation](https://cli.github.com/manual/gh_release_create),
[release uploads](https://cli.github.com/manual/gh_release_upload).
