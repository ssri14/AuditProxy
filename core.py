"""Standard-library-only CSV profiling, prompt preparation and aliased exports.

Privacy boundary: generate_prompt() sees column aliases/types/roles and caller text,
not original column names, original row values, local filenames or transaction data.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import math
import os
import re
import tempfile

MAX_PROFILE_ROWS = 500
MAX_PROMPT_COLUMNS = 100


@dataclass
class Column:
    alias: str
    original: str
    kind: str
    role: str
    include: bool = True


@dataclass
class Profile:
    path: Path
    encoding: str
    delimiter: str
    columns: list[Column] = field(default_factory=list)
    sampled_rows: int = 0
    sampled_only: bool = True


def _open_readable(path: Path):
    for encoding in ('utf-8-sig', 'cp1252', 'latin-1'):
        try:
            with path.open('r', encoding=encoding, newline='') as handle:
                sample = handle.read(8192)
            if '\x00' in sample:
                raise ValueError('This looks like a binary file, not a CSV.')
            return encoding, sample
        except UnicodeDecodeError:
            continue
    raise ValueError('Cannot decode the CSV file.')


def _sniff(sample: str) -> str:
    try:
        return csv.Sniffer().sniff(sample, delimiters=',;\t|').delimiter
    except csv.Error:
        return ','


def _detect_role(header: str) -> str:
    h = re.sub(r'[^a-z0-9]+', '_', header.casefold()).strip('_')
    matchers = (
        ('amount', ('amount', 'amt', 'value', 'total', 'gross', 'net', 'expenditure', 'payment_value', 'cost', 'paid', 'price')),
        ('supplier', ('vendor', 'supplier', 'contractor', 'payee', 'seller', 'beneficiary')),
        ('transaction_reference', ('transaction_id', 'transaction_no', 'transaction_number', 'reference', 'invoice_no', 'invoice_id', 'voucher', 'bill_no', 'payment_id', 'txn_id')),
        ('date', ('date', 'period', 'timestamp', 'month')),
        ('department', ('department', 'division', 'unit', 'office', 'ministry', 'agency')),
        ('expense_category', ('category', 'account', 'expense_type', 'expense_head', 'object_head', 'purpose', 'classification')),
        ('status', ('status', 'approval', 'approved', 'verified')),
    )
    for role, tokens in matchers:
        if any(h == token or h.startswith(token + '_') or h.endswith('_' + token) or ('_' + token + '_') in ('_' + h + '_') for token in tokens):
            return role
    if h in ('id', 'transaction', 'invoice', 'voucher_no', 'bill_id', 'record_id'):
        return 'transaction_reference'
    return 'other'


def _number(s: str):
    x = s.strip().replace(',', '').replace('₹', '').replace('£', '').replace('$', '').replace('€', '')
    if x.startswith('(') and x.endswith(')'):
        x = '-' + x[1:-1]
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except ValueError:
        return None


def _looks_date(s: str) -> bool:
    formats = ('%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%Y/%m/%d', '%m/%d/%Y', '%d-%b-%Y', '%d %b %Y')
    return any(_date_match(s, f) for f in formats)


def _date_match(s: str, fmt: str) -> bool:
    try:
        datetime.strptime(s, fmt)
        return True
    except ValueError:
        return False


def _infer(values: list[str], role: str) -> str:
    populated = [v.strip() for v in values if v is not None and v.strip()]
    if not populated:
        return 'text (all sampled values blank)'
    n = len(populated)
    if role == 'date' and sum(_looks_date(s) for s in populated) >= 0.8*n:
        return 'date'
    if all(re.fullmatch(r'[+-]?\d+', s) for s in populated):
        # Preserve identifiers with leading zeros as strings.
        if role == 'transaction_reference' or any(len(s.lstrip('+-')) > 1 and s.lstrip('+-').startswith('0') for s in populated):
            return 'text (identifier)'
        return 'integer'
    if sum(_number(s) is not None for s in populated) >= 0.9*n:
        return 'decimal'
    if sum(_looks_date(s) for s in populated) >= 0.85*n:
        return 'date'
    if all(s.casefold() in ('yes', 'no', 'true', 'false') for s in populated):
        return 'boolean'
    return 'text'


def profile_csv(path: str | Path) -> Profile:
    path = Path(path).expanduser().resolve()
    if not path.is_file() or path.suffix.lower() != '.csv':
        raise ValueError('Choose an existing .csv file.')
    encoding, sample = _open_readable(path)
    delimiter = _sniff(sample)
    with path.open('r', encoding=encoding, newline='') as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        headers = reader.fieldnames
        if not headers or not any(h.strip() for h in headers if h):
            raise ValueError('CSV is missing a header row.')
        if any(h is None or not h.strip() for h in headers):
            raise ValueError('All columns must have a nonblank header.')
        if len(set(headers)) != len(headers):
            raise ValueError('Duplicate CSV headers found. Rename them before import.')
        samples = {h: [] for h in headers}
        rows = 0
        for row in reader:
            _validate_record(row, rows + 2)
            rows += 1
            for h in headers:
                samples[h].append(row.get(h) or '')
            if rows >= MAX_PROFILE_ROWS:
                break
    columns = []
    for index, header in enumerate(headers, 1):
        role = _detect_role(header)
        columns.append(Column(f'f{index:03d}', header, _infer(samples[header], role), role))
    return Profile(path=path, encoding=encoding, delimiter=delimiter, columns=columns, sampled_rows=rows)


def _synthetic_value(column: Column, index: int) -> str:
    role = column.role
    kind = column.kind
    if role == 'supplier':
        return ('Supplier_A', 'Supplier_B', 'Supplier_A', 'Supplier_C', 'Supplier_D')[index % 5]
    if role == 'transaction_reference':
        return f'DEMO-TXN-{(index + 1):04d}'
    if role == 'date' or kind == 'date':
        return ('2025-04-01', '2025-04-05', '2025-04-12', '2025-04-18', '2025-04-25')[index % 5]
    if role == 'amount':
        return ('12500.00', '48500.00', '18000.00', '96000.00', '22500.00')[index % 5]
    if role == 'department':
        return ('Department_A', 'Department_B', 'Department_A', 'Department_C', 'Department_A')[index % 5]
    if role == 'expense_category':
        return ('Services', 'Supplies', 'Maintenance', 'Equipment', 'Services')[index % 5]
    if role == 'status':
        return ('Approved', 'Pending', 'Approved', 'Reviewed', 'Approved')[index % 5]
    if kind == 'integer':
        return str((index+1)*10)
    if kind == 'decimal':
        return f'{(index+1)*135.5:.2f}'
    if kind == 'boolean':
        return 'true' if index % 2 == 0 else 'false'
    return f'Example_{index + 1}'


def synthetic_csv(profile: Profile, n: int = 4) -> str:
    import io
    selected = [c for c in profile.columns if c.include][:MAX_PROMPT_COLUMNS]
    out = io.StringIO()
    writer = csv.writer(out, lineterminator='\n')
    writer.writerow([c.alias for c in selected])
    for i in range(n):
        writer.writerow([_synthetic_value(c, i) for c in selected])
    return out.getvalue().rstrip('\n')


def generate_prompt(profile: Profile, audit_question: str) -> str:
    selected = [c for c in profile.columns if c.include]
    if not selected:
        raise ValueError('Include at least one CSV column.')
    if len(selected) > MAX_PROMPT_COLUMNS:
        raise ValueError(f'Select at most {MAX_PROMPT_COLUMNS} columns for the prompt.')
    if not audit_question.strip():
        raise ValueError('Describe your audit question first.')
    table = '\n'.join(f'- {c.alias}: {c.kind}; semantic role: {c.role}' for c in selected)
    example = synthetic_csv(profile)
    return f'''ROLE: You are a careful audit data analyst and Python programmer.

OBJECTIVE (provided by auditor; review text for confidential information):
{audit_question.strip()}

CONFIDENTIALITY AND DATA CONTRACT:
- The actual CSV is confidential and is NOT supplied to you.
- Every field name below is a neutral alias; original headers are withheld.
- All records below are invented examples, NOT transformed real records.
- The real CSV will be used only on a local, offline computer.
- Work only from the stated schema, examples and objective. Do not fabricate findings.

CSV SCHEMA (aliased field names to use exactly):
{table}

SYNTHETIC EXAMPLE ROWS (entirely fabricated):
```csv
{example}
```

REQUIRED PYTHON SOLUTION:
1. Return one complete, runnable Python 3 script, preferably standard-library only.
   Include every function, argument parsing, the analysis, report writing, and a
   main() entry point invoked by if __name__ == "__main__": main(). Never stop
   after helper functions. No placeholders, omitted sections or "continue here".
   If necessary, simplify the implementation so the entire script fits.
2. Support arguments: --input PATH --output DIRECTORY (argparse).
3. Read the aliased CSV from --input via csv.DictReader; never hardcode filenames.
4. Handle blank cells, malformed amounts and varying date formats gracefully.
5. Calculate metrics and detect candidates for auditor REVIEW, not proven violations.
6. Write ALL analytical output to one UTF-8 plain-text file named exactly results.txt
   inside the directory supplied through --output. Do not create separate CSV,
   summary, spreadsheet or other report files. Include the requested calculations,
   tables/aggregations in readable text, source row references, supporting values,
   methodology, assumptions and limitations in this single file. Printing to the
   console is not a substitute for writing results.txt.
7. Preserve source row numbers for traceability; avoid modifying the input CSV.
8. Do not access the internet, add cloud dependencies, or make external requests.
9. Be careful about line-item vs payment-level transaction references: a repeated
   reference is not automatically a duplicate payment.
10. Explain assumptions and do not make legal/compliance determinations without rules.
11. If audit conditions are ambiguous (e.g. splitting thresholds), implement
    clearly labelled heuristics and explain what evidence is still necessary.
12. Put the command example `python analysis.py --input input.csv --output results`
    in a comment inside the script. End the complete script with # END OF SCRIPT.

Provide the complete script as a downloadable Python file named analysis.py,
not as escaped rich text or a code block to copy and paste. Verify that running the script calls main(), reads --input,
creates the --output directory if needed, and writes results.txt there, including
when there are no matching records. Do not claim findings about unseen records.'''


def privacy_warnings(text: str) -> list[str]:
    """Heuristic reminders, never a reliable data-loss-prevention guarantee."""
    warnings = []
    if re.search(r'\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b', text):
        warnings.append('Possible email address detected')
    if re.search(r'\b(?:\+?91[-\s]?)?[6-9]\d{9}\b', text):
        warnings.append('Possible Indian mobile number detected')
    if re.search(r'\b\d{12,18}\b', text):
        warnings.append('Long number detected (possibly an identifier)')
    return warnings


def _check_output_path(destination: Path, source: Path) -> None:
    if destination.resolve() == source.resolve() or (
        destination.exists() and destination.samefile(source)
    ):
        raise ValueError('Destination cannot overwrite the source CSV.')


def _validate_record(row: dict, rownum: int) -> None:
    if None in row or any(value is None for value in row.values()):
        raise ValueError(f'CSV record {rownum} has missing or extra fields. Please repair the file.')


def export_aliased_csv(profile: Profile, destination: str | Path, *, overwrite: bool = False) -> int:
    """Copy actual records locally with renamed headers. NOT a sanitized dataset."""
    selected = [c for c in profile.columns if c.include]
    if not selected:
        raise ValueError('Include at least one column.')
    dest = Path(destination).absolute()
    _check_output_path(dest, profile.path)
    if dest.is_symlink():
        raise ValueError('Choose a destination that is not a symbolic link.')
    if dest.exists() and not overwrite:
        raise FileExistsError('Destination already exists. Choose a new filename.')
    dest.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    # Stage privately on the same filesystem; publish only after complete validation.
    with tempfile.TemporaryDirectory(prefix='.auditproxy-', dir=dest.parent) as staging:
        staged = Path(staging) / 'export.csv'
        with profile.path.open('r', encoding=profile.encoding, newline='') as fin, \
             staged.open('w', encoding='utf-8', newline='') as fout:
            reader = csv.DictReader(fin, delimiter=profile.delimiter)
            if reader.fieldnames != [c.original for c in profile.columns]:
                raise ValueError('Source CSV headers changed. Re-profile the file first.')
            writer = csv.DictWriter(fout, fieldnames=[c.alias for c in selected])
            writer.writeheader()
            for rownum, row in enumerate(reader, 2):
                _validate_record(row, rownum)
                writer.writerow({c.alias: row[c.original] for c in selected})
                count += 1
        _check_output_path(dest, profile.path)
        if overwrite:
            os.replace(staged, dest)
        else:
            # Exclusive publication: a competing export cannot be overwritten.
            os.link(staged, dest)
    return count



def script_error_prompt(error: str) -> str:
    return ("There is a problem with the code you generated. The exact error is as shown below:\n\n"
            "---- Received Error START-----\n\n" + str(error) +
            "\n\n---- Received Error END -----\n\n"
            "Please provide a replacement Python file which can overwrite the previous file on my machine")
