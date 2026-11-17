#!/usr/bin/env python3
"""Measure warmed Ollama decoding speed without changing server configuration."""
import argparse
import json
import statistics
import urllib.request
from pathlib import Path


def measure(request, model, context, runs=3, tokens=256):
    body = {
        'model': model, 'stream': False, 'keep_alive': '30m',
        'prompt': 'Write a detailed numbered guide to implementing a reliable task queue in Python. Include code and explanations.',
        'options': {'num_ctx': context, 'num_predict': tokens, 'temperature': 0, 'seed': 42},
    }
    # Warm the model before collecting samples; model load time is separate.
    request('/api/generate', {**body, 'options': {**body['options'], 'num_predict': 1}})
    samples = []
    for _ in range(runs):
        result = request('/api/generate', body)
        count, duration = result.get('eval_count', 0), result.get('eval_duration', 0)
        if not result.get('done') or count <= 0 or duration <= 0:
            raise ValueError('Incomplete generation or missing positive timing/token counts')
        samples.append({'tokens': count, 'tokens_per_second': count * 1e9 / duration,
                        'load_seconds': result.get('load_duration', 0) / 1e9,
                        'total_seconds': result.get('total_duration', 0) / 1e9})
    return {'model': model, 'context': context, 'runs': runs, 'samples': samples,
            'median_tokens_per_second': statistics.median(s['tokens_per_second'] for s in samples),
            'loaded_models': request('/api/ps').get('models', [])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', required=True)
    parser.add_argument('--context', type=int, required=True)
    parser.add_argument('--runs', type=int, default=3)
    parser.add_argument('--tokens', type=int, default=256)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.context <= 0 or args.runs <= 0 or args.tokens <= 0:
        parser.error('--context, --runs, and --tokens must be positive')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(route, body=None):
        req = urllib.request.Request('http://127.0.0.1:11434' + route,
                                     data=None if body is None else json.dumps(body).encode(),
                                     headers={'Content-Type': 'application/json'})
        with opener.open(req, timeout=900) as response:
            result = json.load(response)
        if not isinstance(result, dict) or result.get('error'):
            raise ValueError(f'Ollama request failed: {result}')
        return result

    result = measure(request, args.model, args.context, args.runs, args.tokens)
    text = json.dumps(result, indent=2) + '\n'
    if args.output:
        # Retain prior measurements rather than silently overwriting them.
        with args.output.open('x') as output:
            output.write(text)
    print(text, end='')


if __name__ == '__main__':
    main()
