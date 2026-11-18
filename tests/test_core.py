import csv
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import (export_aliased_csv, generate_prompt, privacy_warnings,
                  profile_csv, synthetic_csv, script_error_prompt)


class AuditProxyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'confidential.csv'
        with self.path.open('w', newline='', encoding='utf-8') as fp:
            writer = csv.writer(fp)
            writer.writerow(['SecretProjectVendor', 'Invoice_Number', 'Amount_INR', 'Payment_Date', 'Department'])
            for i in range(14):
                writer.writerow([f'ConfidentialVendor{i}', f'INV-{i//2}', 750 if i < 13 else 150000,
                                 f'2025-04-{i+1:02d}', 'PrivateUnit'])
        self.profile = profile_csv(self.path)

    def test_profile_and_synthetic_sample_never_include_actual_data(self):
        sample = synthetic_csv(self.profile)
        self.assertIn('f001', sample)
        self.assertNotIn('SecretProjectVendor', sample)
        self.assertNotIn('ConfidentialVendor', sample)
        self.assertNotIn('PrivateUnit', sample)
        self.assertNotIn('150000', sample)

    def test_prompt_has_no_actual_names_or_values(self):
        prompt = generate_prompt(self.profile, 'Analyse repeated references and unusually large payments')
        for secret in ('SecretProjectVendor', 'ConfidentialVendor', 'PrivateUnit', '150000', str(self.path)):
            self.assertNotIn(secret, prompt)
        self.assertIn('f003', prompt)
        self.assertIn('invented', prompt.lower())
        self.assertIn('--input PATH --output DIRECTORY', prompt)
        self.assertIn('file named exactly results.txt', prompt)
        self.assertIn('Do not create separate CSV', prompt)
        self.assertIn('main() entry point', prompt)
        self.assertIn('# END OF SCRIPT', prompt)
        self.assertIn('downloadable Python file named analysis.py', prompt)

    def test_aliased_export_preserves_values_locally(self):
        target = Path(self.tmp.name) / 'alias.csv'
        count = export_aliased_csv(self.profile, target)
        self.assertEqual(14, count)
        with target.open(newline='', encoding='utf-8') as fp:
            reader = csv.DictReader(fp)
            self.assertEqual('f001', reader.fieldnames[0])
            rows = list(reader)
            self.assertEqual('ConfidentialVendor0', rows[0]['f001'])
            self.assertEqual('150000', rows[-1]['f003'])

    def test_column_exclusion(self):
        self.profile.columns[0].include = False
        prompt = generate_prompt(self.profile, 'Check payments')
        self.assertNotIn('f001:', prompt)
        self.assertIn('f002:', prompt)

    def test_privacy_warning(self):
        self.assertTrue(privacy_warnings('help@example.com'))

    def test_export_requires_explicit_overwrite(self):
        target = Path(self.tmp.name) / 'alias.csv'
        target.write_bytes(b'previous results')
        with self.assertRaises(FileExistsError):
            export_aliased_csv(self.profile, target)
        self.assertEqual(target.read_bytes(), b'previous results')
        self.assertEqual(export_aliased_csv(self.profile, target, overwrite=True), 14)
        self.assertTrue(target.read_text().startswith('f001,'))

    def test_export_preserves_destination_when_headers_change(self):
        target = Path(self.tmp.name) / 'alias.csv'
        target.write_bytes(b'previous results')
        self.path.write_text('different_header\n100\n')
        with self.assertRaisesRegex(ValueError, 'headers changed'):
            export_aliased_csv(self.profile, target, overwrite=True)
        self.assertEqual(target.read_bytes(), b'previous results')

    def test_malformed_rows_do_not_publish_partial_exports(self):
        for malformed in ('too,few\n', 'a,b,c,d,e,extra\n'):
            for existing in (False, True):
                with self.subTest(row=malformed, existing=existing):
                    target = Path(self.tmp.name) / 'alias.csv'
                    target.unlink(missing_ok=True)
                    if existing:
                        target.write_bytes(b'previous results')
                    source = self.path.read_bytes()
                    try:
                        with self.path.open('a') as fp:
                            fp.write(malformed)
                        with self.assertRaisesRegex(ValueError, 'missing or extra fields'):
                            export_aliased_csv(self.profile, target, overwrite=True)
                        if existing:
                            self.assertEqual(target.read_bytes(), b'previous results')
                        else:
                            self.assertFalse(target.exists())
                    finally:
                        self.path.write_bytes(source)
                    self.assertFalse(list(Path(self.tmp.name).glob('.auditproxy-*')))

    def test_export_failure_preserves_existing_file_and_cleans_staging(self):
        target = Path(self.tmp.name) / 'alias.csv'
        target.write_bytes(b'previous results')
        with patch('core.os.replace', side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):
                export_aliased_csv(self.profile, target, overwrite=True)
        self.assertEqual(target.read_bytes(), b'previous results')
        self.assertFalse(list(Path(self.tmp.name).glob('.auditproxy-*')))

    def test_export_never_overwrites_source_or_link_to_source(self):
        original = self.path.read_bytes()
        hardlink = Path(self.tmp.name) / 'hardlink.csv'
        os.link(self.path, hardlink)
        symlink = Path(self.tmp.name) / 'symlink.csv'
        targets = [self.path, hardlink]
        try:
            symlink.symlink_to(self.path)
        except (OSError, NotImplementedError):
            pass  # Some Windows accounts cannot create symbolic links.
        else:
            targets.append(symlink)
        for target in targets:
            with self.subTest(target=target.name):
                with self.assertRaisesRegex(ValueError, 'source CSV'):
                    export_aliased_csv(self.profile, target, overwrite=True)
                self.assertEqual(self.path.read_bytes(), original)

    def test_short_row_is_rejected_during_profile(self):
        with self.path.open('a') as fp:
            fp.write('too,few\n')
        with self.assertRaisesRegex(ValueError, 'missing or extra fields'):
            profile_csv(self.path)

    def test_export_does_not_overwrite_a_destination_created_during_export(self):
        target = Path(self.tmp.name) / 'alias.csv'
        real_link = os.link
        def competing_export(src, dest):
            Path(dest).write_bytes(b'other export')
            return real_link(src, dest)
        with patch('core.os.link', side_effect=competing_export):
            with self.assertRaises(FileExistsError):
                export_aliased_csv(self.profile, target)
        self.assertEqual(target.read_bytes(), b'other export')

    def test_followup_prompt_contains_the_complete_actual_error(self):
        error = 'Traceback:\nValueError: ' + 'x' * 12000 + '\nend'
        expected = ('There is a problem with the code you generated. The exact error is as shown below:\n\n'
                    '---- Received Error START-----\n\n' + error +
                    '\n\n---- Received Error END -----\n\n'
                    'Please provide a replacement Python file which can overwrite the previous file on my machine')
        self.assertEqual(script_error_prompt(error), expected)


if __name__ == '__main__':
    unittest.main()
