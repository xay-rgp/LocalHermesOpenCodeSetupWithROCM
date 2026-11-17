"""Benchmark accounting and request checks using simulated Ollama replies."""
import unittest
from unittest.mock import Mock

from benchmark import measure


class BenchmarkTests(unittest.TestCase):
    def test_warmup_excluded_and_median_computed(self):
        request = Mock(side_effect=[{},
            {'done': True, 'eval_count': 100, 'eval_duration': 2_000_000_000},
            {'done': True, 'eval_count': 60, 'eval_duration': 2_000_000_000},
            {'done': True, 'eval_count': 80, 'eval_duration': 2_000_000_000},
            {'models': [{'name': 'example', 'size_vram': 100}]}])
        result = measure(request, 'example', 32768)
        self.assertEqual(result['median_tokens_per_second'], 40)
        self.assertEqual(len(result['samples']), 3)
        self.assertEqual(request.call_args_list[0].args[1]['options']['num_predict'], 1)
        self.assertEqual(request.call_args_list[1].args[1]['options']['num_ctx'], 32768)
        self.assertEqual(request.call_args_list[1].args[1]['options']['num_predict'], 256)
        self.assertEqual(request.call_args_list[-1].args, ('/api/ps',))

    def test_missing_timings_and_incomplete_generations_rejected(self):
        for reply in ({}, {'done': True},
                      {'done': True, 'eval_count': 12, 'eval_duration': 0},
                      {'done': False, 'eval_count': 12, 'eval_duration': 123}):
            with self.subTest(reply=reply), self.assertRaises(ValueError):
                measure(Mock(side_effect=[{}, reply]), 'example', 32768)
