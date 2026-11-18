AuditProxy prepares a programming prompt from an aliased CSV schema and invented
examples, assisted by a required local Ollama text model. The generated Python
file runs locally in a temporary workspace and produces `results.txt`.

Users review raw results first, optionally request local AI interpretation after
a reliability alert, and save either document independently. Script failures
provide a copyable follow-up prompt with the actual error.

The installers bundle Python and PyQt6. Install Ollama and a local text model
separately before use. Generated scripts should use the Python standard library;
additional third-party analysis packages are not bundled.

The macOS arm64 build targets macOS 14+. It is ad-hoc signed, not Developer ID
signed or notarized. The Windows executable is unsigned. Test each platform's
package on its target system before publishing this draft release.
