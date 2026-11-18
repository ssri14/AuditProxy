"""Read the script's single raw report; bound only the local model's input."""
from pathlib import Path

MAX_INTERPRETATION_CHARS = 12000


def read_results(directory):
    directory = Path(directory)
    path = directory / 'results.txt'
    if not path.is_file():
        raise ValueError(f'The script did not create results.txt. Ask your coding LLM to write '
                         'a UTF-8 results.txt inside the --output directory.')
    raw_bytes = path.read_bytes()
    try:
        raw_text = raw_bytes.decode('utf-8-sig')
    except UnicodeDecodeError:
        raise ValueError('results.txt must be UTF-8 text. Update the script and run it again.') from None
    truncated = len(raw_text) > MAX_INTERPRETATION_CHARS
    evidence = raw_text[:MAX_INTERPRETATION_CHARS]
    if truncated:
        evidence = (f'Only the first {MAX_INTERPRETATION_CHARS} characters of a '
                    f'{len(raw_text)}-character report follow. Do not generalize to omitted content.\n\n' + evidence)
    return {'raw_text': raw_text, 'raw_bytes': raw_bytes, 'evidence': evidence,
            'truncated': truncated}
