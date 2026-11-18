"""Pre-reviewed demonstration script; NOT presented as AI-generated code.

Reads aliased CSV sample, identifies same-supplier/same-day groups which
may merit review for possible transaction splitting under a HYPOTHETICAL
threshold. This does NOT establish an actual compliance breach.
"""
import argparse
import csv
from collections import defaultdict
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--threshold', type=float, default=50000.0,
                        help='Hypothetical illustrative threshold; NOT a legal threshold')
    args = parser.parse_args()
    dest = Path(args.output)
    dest.mkdir(parents=True, exist_ok=True)
    groups = defaultdict(list)
    errors = []
    with open(args.input, newline='', encoding='utf-8-sig') as f:
        for rownum, row in enumerate(csv.DictReader(f), start=2):
            try:
                amount = float((row.get('f004') or '').replace(',', ''))
            except ValueError:
                errors.append(rownum)
                continue
            supplier = (row.get('f003') or '').strip()
            date = (row.get('f001') or '').strip()
            ref = (row.get('f002') or '').strip()
            if supplier and date and amount > 0:
                groups[(supplier, date)].append((rownum, ref, amount))

    matches = []
    for (supplier, date), lines in groups.items():
        total = sum(amount for _, _, amount in lines)
        distinct_refs = {reference for _, reference, _ in lines}
        if len(distinct_refs) >= 2 and total >= args.threshold and all(amount < args.threshold for _, _, amount in lines):
            matches.append({'supplier': supplier, 'date': date, 'rows': '; '.join(str(x[0]) for x in lines),
                            'references': '; '.join(sorted(distinct_refs)),
                            'line_count': len(lines), 'combined_amount': f'{total:.2f}',
                            'review_reason': 'Multiple subthreshold lines; check underlying invoices and rules'})
    report = (
        f'Hypothetical threshold: {args.threshold:.2f}\n'
        f'Groups flagged for REVIEW: {len(matches)}\n'
        f'Rows with unparseable or blank amounts: {len(errors)}\n\n'
        'Important: This is only an exploratory pattern.\n'
        'It cannot establish splitting or wrongdoing without the applicable\n'
        'rules, procurement evidence, payment approvals and business context.\n'
    )
    for match in matches:
        report += '\n' + '\n'.join(f'{key}: {value}' for key, value in match.items()) + '\n'
    (dest / 'results.txt').write_text(report, encoding='utf-8')
    print(report)
    print('Saved reports in:', dest)


if __name__ == '__main__':
    main()
