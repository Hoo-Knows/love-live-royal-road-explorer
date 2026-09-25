import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from catalog_update_report import GENERATED_FILES, capture, main, render_report  # noqa: E402


class CatalogUpdateReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in GENERATED_FILES:
            self.write(name, {})
        self.write('data/source/.snapshot.json', {'snapshotId': 'source', 'collection': {'startedAt': 'old'}})
        self.catalog = {'metrics': {'catalogSongCount': 1}, 'songs': [{'id': '1', 'titles': {'ja': '曲'}}]}
        self.write('data/catalog.json', self.catalog)
        self.manifest = {'sourceSnapshot': 'source', 'analysis': {'revision': 'revision', 'configVersion': 'config'},
                         'songs': {'1': {'status': 'analyzed', 'error': None}}}
        self.write('data/analysis-manifest.json', self.manifest)
        self.write('data/patterns.json', {})
        self.write('data/overrides.json', {})
        self.before = capture(self.root)

    def write(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')

    def test_noop_and_collection_times(self):
        self.assertEqual(self.before, capture(self.root))
        self.write('data/source/.snapshot.json', {'snapshotId': 'source', 'collection': {'startedAt': 'new'}})
        self.assertEqual(self.before, capture(self.root))

    def test_verification_changes(self):
        self.write('data/source/.snapshot.json', {'snapshotId': 'source', 'wiki': {'status': 'stale'}})
        self.assertNotEqual(self.before['hashes'], capture(self.root)['hashes'])

    def test_raw_additions_changes_and_deletions(self):
        self.write('data/raw/1.json', {'segments': [1]})
        added = capture(self.root)
        self.assertNotEqual(self.before['hashes'], added['hashes'])
        self.write('data/raw/1.json', {'segments': [2]})
        self.assertNotEqual(added['hashes'], capture(self.root)['hashes'])
        (self.root / 'data/raw/1.json').unlink()
        self.assertEqual(self.before['hashes'], capture(self.root)['hashes'])

    def test_audio_and_unrelated_files_excluded(self):
        self.write('.cache/audio/index.json', {'secret': 'ignored'})
        self.write('data/raw/recording.ogg', 'ignored')
        self.write('src/example.json', 'ignored')
        self.assertEqual(self.before, capture(self.root))

    def test_missing_output_fails_closed(self):
        (self.root / 'data/source/song-info.json').unlink()
        with self.assertRaises(FileNotFoundError):
            capture(self.root)

    def test_new_songs_status_changes_and_provenance(self):
        self.catalog['songs'].append({'id': '2', 'titles': {'en': 'New | song', 'ja': '新曲'}})
        self.catalog['metrics']['catalogSongCount'] = 2
        self.write('data/catalog.json', self.catalog)
        self.manifest['songs']['1'] = {'status': 'failed', 'error': 'HTTP failure'}
        self.manifest['songs']['2'] = {'status': 'unavailable'}
        self.write('data/analysis-manifest.json', self.manifest)
        after = capture(self.root)
        self.assertNotEqual(self.before['hashes'], after['hashes'])
        report = render_report(self.before, after, self.manifest, 'patterns', 'overrides', 'https://example.com/run')
        for expected in ('| catalogSongCount | 1 | 2 |', 'New &#124; song', '曲', 'HTTP failure',
                         'unavailable', '`source`', '`revision`', '`config`', '`patterns`', '`overrides`'):
            self.assertIn(expected, report)

    def test_cli_output(self):
        baseline = self.root / 'baseline.json'
        body = self.root / 'body.md'
        output = self.root / 'output.txt'
        summary = self.root / 'summary.md'
        args = ['--root', str(self.root), '--baseline', str(baseline)]
        self.assertEqual(main(['capture', *args]), 0)
        for changed in (False, True):
            if changed:
                self.manifest['songs']['1']['status'] = 'failed'
                self.write('data/analysis-manifest.json', self.manifest)
            with patch.dict(os.environ, {'GITHUB_OUTPUT': str(output), 'GITHUB_STEP_SUMMARY': str(summary)}):
                self.assertEqual(main(['report', *args, '--body', str(body),
                                       '--run-url', 'https://example.com/run']), 0)
            self.assertIn(f'changed={str(changed).lower()}', output.read_text(encoding='utf-8'))
            self.assertIn(body.read_text(encoding='utf-8'), summary.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
