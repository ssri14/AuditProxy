from pathlib import Path
import tempfile
import unittest
from results_local import read_results, MAX_INTERPRETATION_CHARS


class ResultTests(unittest.TestCase):
    def test_full_raw_report_is_preserved_and_only_model_input_is_bounded(self):
        with tempfile.TemporaryDirectory() as td:
            original = b'\xef\xbb\xbfRaw results\r\n' + b'x' * 15000 + b'\r\nEND'
            (Path(td) / 'results.txt').write_bytes(original)
            result = read_results(td)
            self.assertEqual(result['raw_bytes'], original)
            self.assertTrue(result['raw_text'].endswith('END'))
            self.assertTrue(result['truncated'])
            self.assertIn('Only the first', result['evidence'])
            self.assertNotIn('END', result['evidence'])
            self.assertLess(len(result['evidence']), MAX_INTERPRETATION_CHARS + 200)

    def test_missing_results_file_does_not_fall_back_to_old_reports(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / 'summary.txt').write_text('old report')
            with self.assertRaisesRegex(ValueError, 'did not create results.txt'):
                read_results(td)

    def test_non_utf8_results_are_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / 'results.txt').write_bytes(b'\xff')
            with self.assertRaisesRegex(ValueError, 'UTF-8'):
                read_results(td)
