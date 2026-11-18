import unittest
from unittest.mock import patch
import ollama_local as local


class OllamaTests(unittest.TestCase):
    def test_model_list_filters_embeddings_and_cloud(self):
        with patch.object(local, '_request', return_value={'models': [
            {'name': 'llama3.2:1b'}, {'name': 'nomic-embed-text:latest'},
            {'name': 'example:cloud'}, {'name': 'example-cloud:latest'}, {'name': 'org/model:1b'}]}):
            self.assertEqual(local.local_models(), ['llama3.2:1b', 'org/model:1b'])

    def test_model_readiness_requires_actual_generation(self):
        with patch.object(local, '_request', return_value={'response': 'ready', 'done': True}) as request:
            self.assertEqual(local.check_model('llama3.2:1b'), 'llama3.2:1b')
            path, payload = request.call_args.args
            self.assertEqual(path, '/api/generate')
            self.assertEqual(payload['model'], 'llama3.2:1b')

    def test_empty_or_truncated_output_is_rejected(self):
        for response in ({'response': ''}, {'response': 'partial', 'done_reason': 'length'},
                         {'response': 'partial', 'done': False}):
            with self.subTest(response=response), patch.object(local, '_request', return_value=response):
                with self.assertRaises(RuntimeError):
                    local.improve_prompt('test', 'Specification')

    def test_advice_rejects_code(self):
        with patch.object(local, '_request', return_value={'response': '```python\nimport os\n```'}):
            with self.assertRaises(RuntimeError):
                local.improve_prompt('test', 'Specification')

    def test_interpretation_receives_computed_evidence_separately(self):
        with patch.object(local, '_request', return_value={'response': 'Inspect underlying records.'}) as request:
            self.assertIn('Inspect', local.interpret_results('test', '55 rows, 16 flags'))
            payload = request.call_args.args[1]
            self.assertEqual(payload['prompt'], '55 rows, 16 flags')
            self.assertIn('Use only the supplied figures', payload['system'])

    def test_cloud_model_cannot_generate(self):
        with patch.object(local, '_request') as request:
            with self.assertRaises(ValueError):
                local.check_model('example:cloud')
            request.assert_not_called()

    def test_advice_rejects_invented_thresholds(self):
        with patch.object(local, '_request', return_value={'response': 'Check payments above $10,000.'}) as request:
            with self.assertRaises(RuntimeError):
                local.improve_prompt('test', 'Check high-value payments.')
            self.assertEqual(request.call_count, 1)

    def test_model_selected_checks_have_stable_definitions(self):
        with patch.object(local, '_request', return_value={'response': '{"checks":["high_value","repeated_reference"]}'}) as request:
            plan = local.improve_prompt('test', 'High value and repeated references; amount and reference fields')
            self.assertIn('configurable percentile', plan)
            self.assertIn('legitimate line items', plan)
            self.assertIn('format', request.call_args.args[1])
