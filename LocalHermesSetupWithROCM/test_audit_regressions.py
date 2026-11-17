"""Regression checks from the twenty-pass setup audit; no live services."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import yaml
import configure
import verify


class AuditRegressions(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)

    def apply(self, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()):
            configure.configure(self.home, ['example:latest'], 'example:latest', **kwargs)

    def test_small_memory_budgets_are_respected(self):
        root = self.home / '.hermes'
        root.mkdir()
        (root / 'config.yaml').write_text('memory:\n  memory_char_limit: 32\n  user_char_limit: 20\n')
        self.apply()
        self.assertLessEqual(len((root / 'memories/MEMORY.md').read_text()), 32)
        self.assertLessEqual(len((root / 'memories/USER.md').read_text()), 20)
        self.assertIn('session_search', (root / 'SOUL.md').read_text())

    def test_memory_directory_in_place_of_file_fails_before_writes(self):
        root = self.home / '.hermes'
        (root / 'memories/USER.md').mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, 'regular file'):
            self.apply()
        self.assertFalse((root / 'config.yaml').exists())
        self.assertFalse((self.home / '.ollama').exists())

    def test_empty_existing_memories_are_preserved(self):
        root = self.home / '.hermes/memories'
        root.mkdir(parents=True)
        for name in ('MEMORY.md', 'USER.md'):
            (root / name).touch()
        self.apply()
        for name in ('MEMORY.md', 'USER.md'):
            self.assertEqual((root / name).read_bytes(), b'')

    def test_symlinked_new_memory_is_rejected_without_writes(self):
        root = self.home / '.hermes/memories'
        root.mkdir(parents=True)
        (root / 'USER.md').symlink_to(self.home / 'missing-target')
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.apply()
        self.assertFalse((self.home / '.hermes/config.yaml').exists())
        self.assertFalse((self.home / 'missing-target').exists())

    def test_preflight_preserves_existing_files_and_mtimes(self):
        self.apply()
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.home.rglob('*') if p.is_file()}
        self.apply(context=32768, check_only=True)
        after = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.home.rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def test_memory_yaml_alias_does_not_modify_unrelated_settings(self):
        root = self.home / '.hermes'
        root.mkdir()
        (root / 'config.yaml').write_text('memory: &shared\n  memory_enabled: false\nother: *shared\n')
        self.apply()
        config = yaml.safe_load((root / 'config.yaml').read_text())
        self.assertFalse(config['other']['memory_enabled'])
        self.assertTrue(config['memory']['memory_enabled'])

    def catalog(self, payload):
        opener = MagicMock()
        opener.open.return_value = contextlib.closing(io.StringIO(json.dumps(payload)))
        with patch('configure.urllib.request.build_opener', return_value=opener), \
             patch.dict(os.environ, {'OLLAMA_MODELS': str(self.home / 'models')}), \
             patch('configure.Path.home', return_value=self.home):
            return configure.installed_models()

    def test_malformed_catalog_falls_back_to_local_manifests(self):
        for payload in (None, [], {'models': None}, {'models': [None, 123]}):
            with self.subTest(payload=payload):
                self.assertEqual(self.catalog(payload), [])

    def test_catalog_excludes_cloud_and_deduplicates_local_models(self):
        result = self.catalog({'models': [
            {'name': 'local:latest'}, {'name': 'local:latest'},
            {'name': 'remote:cloud'}, {'name': 'remote:latest', 'remote_host': 'https://example.com'},
            {'name': 'remote2:latest', 'remote_model': 'remote2'}, {'name': ''},
        ]})
        self.assertEqual(result, ['local:latest'])

    def test_custom_registry_manifest_keeps_registry_name(self):
        path = self.home / 'models/manifests/example.com/team/model/tag'
        path.parent.mkdir(parents=True)
        path.write_text('{}')
        opener = MagicMock()
        opener.open.side_effect = OSError('offline')
        with patch('configure.urllib.request.build_opener', return_value=opener), \
             patch.dict(os.environ, {'OLLAMA_MODELS': str(self.home / 'models')}), \
             patch('configure.Path.home', return_value=self.home):
            self.assertEqual(configure.installed_models(), ['example.com/team/model:tag'])

    def test_journal_timeout_bytes_produce_actionable_error(self):
        error = subprocess.TimeoutExpired(['journalctl'], 30, stderr=b'journal timed out')
        with patch('verify.subprocess.check_output', side_effect=error):
            with self.assertRaisesRegex(SystemExit, 'sudo -v'):
                verify.current_logs('invocation')

    def test_invalid_verification_context_rejected_before_commands(self):
        for value in ('0', '-1'):
            with self.subTest(value=value), \
                 patch('sys.argv', ['verify.py', '--model', 'example', '--context', value]), \
                 patch('verify.subprocess.check_output') as command, \
                 contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    verify.main()
                command.assert_not_called()

    def test_failed_atomic_replace_preserves_original_and_cleans_temp(self):
        path = self.home / 'notes'
        path.write_text('original')
        with patch('configure.os.replace', side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):
                configure.save(path, 'new')
        self.assertEqual(path.read_text(), 'original')
        self.assertEqual(len(list(self.home.glob('notes.backup-*'))), 1)
        self.assertEqual(len(list(self.home.iterdir())), 2)
