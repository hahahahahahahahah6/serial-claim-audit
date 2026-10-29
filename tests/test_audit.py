import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from serial_claim_audit.audit import audit, claims, evidence
from serial_claim_audit.phrases import SERIAL, NOSERIAL
from tests.cases import GOOD, BAD

ROOT = Path(__file__).resolve().parents[1]


class AuditTests(unittest.TestCase):
    def project(self, doc, source=None, path='app.py'):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        (root / 'README.md').write_text(doc)
        if source is not None:
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source)
        return root

    def assert_high(self, result, rule='documented-serial-claim-false'):
        self.assertEqual(result['verdict'], 'FAIL')
        self.assertEqual(len(result['findings']), 1)
        self.assertEqual(result['findings'][0]['severity'], 'HIGH')
        self.assertEqual(result['findings'][0]['rule'], rule)

    def test_positive_phrases(self):
        self.assertEqual(len(SERIAL), 33)
        for phrase in SERIAL:
            with self.subTest(phrase=phrase):
                self.assertEqual(claims(phrase), (True, False))
                self.assert_high(audit(self.project(phrase)))

    def test_negative_phrases(self):
        self.assertEqual(len(NOSERIAL), 22)
        for phrase in NOSERIAL:
            with self.subTest(phrase=phrase):
                self.assertEqual(claims(phrase), (False, True))
                self.assertEqual(audit(self.project(phrase))['findings'], [])
                self.assert_high(audit(self.project(phrase, GOOD['serial'])), 'documented-no-serial-claim-false')

    def test_no_claim(self):
        self.assertEqual(audit(self.project('A device tool', GOOD['serial']))['findings'], [])

    def test_user_instructions(self):
        for doc in ('plug in the serial cable first', 'connect the serial cable before starting'):
            self.assertEqual(audit(self.project(doc))['verdict'], 'PASS')

    def test_bare_word(self):
        self.assertEqual(claims('# Serial'), (False, False))

    def test_fences(self):
        for fence in ('```', '~~~~'):
            self.assertEqual(claims(fence+'text\nsupports serial\n'+fence), (False, False))

    def test_inline(self):
        self.assert_high(audit(self.project('It `supports serial`.')))

    def test_normalization(self):
        self.assertEqual(claims("Doesn't communicate\nover-serial"), (False, True))
        self.assertEqual(claims('SUPPORTS-SERIAL'), (True, False))

    def test_boundaries(self):
        self.assertEqual(claims('misuses serially'), (False, False))
        self.assertEqual(claims('supports\n\nserial'), (False, False))

    def test_two_families(self):
        result = audit(self.project('Supports serial. No serial.'))
        self.assertEqual(len(result['findings']), 1)

    def test_docs_scope(self):
        root = self.project('neutral', GOOD['serial'])
        path = root / 'nested/docs/guide.md'
        path.parent.mkdir(parents=True)
        path.write_text('No serial')
        self.assert_high(audit(root), 'documented-no-serial-claim-false')
        self.assertEqual(audit(root, ['nested/docs/*'])['verdict'], 'PASS')

    def test_excluded_evidence(self):
        for path in ('fixtures/a.py', 'docs/a.py', 'examples/a.py'):
            self.assert_high(audit(self.project('supports serial', GOOD['serial'], path)))

    def test_test_scope(self):
        for path in ('tests/a.py', 'test_port.py', 'port_test.py'):
            root = self.project('supports serial', GOOD['serial'], path)
            result = audit(root)
            self.assertEqual(result['verdict'], 'PASS')
            self.assertEqual(result['findings'][0]['severity'], 'MEDIUM')
            self.assertEqual(result['findings'][0]['rule'], 'documented-serial-claim-false')
            self.assertEqual(audit(root, fail_on='MEDIUM')['verdict'], 'FAIL')

    def test_symlinks(self):
        root = self.project('supports serial')
        (root / 'linked.py').symlink_to(ROOT / 'tests/fixtures/good/app.py')
        (root / 'linked').symlink_to(ROOT / 'tests/fixtures/good', target_is_directory=True)
        self.assert_high(audit(root))

    def test_env_never_opened(self):
        original = Path.open
        def guarded(path, *args, **kwargs):
            self.assertNotEqual(path.name, '.env')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'open', guarded):
            self.assertEqual(audit(ROOT)['verdict'], 'PASS')

    def test_self_audit(self):
        self.assertEqual(claims((ROOT / 'README.md').read_text()), (False, False))
        self.assertEqual(audit(ROOT)['findings'], [])

    def cli(self, *args):
        return subprocess.run(['python3', '-m', 'serial_claim_audit', *map(str, args)], capture_output=True, text=True)

    def test_cli_version(self):
        result = self.cli('--version')
        self.assertEqual((result.returncode, result.stdout.strip()), (0, '0.1.0'))

    def test_cli_usage_error(self):
        self.assertEqual(self.cli("--unknown-option").returncode, 1)

    def test_cli_bad_path(self):
        self.assertEqual(self.cli(ROOT / 'nonexistent').returncode, 1)

    def test_cli_json(self):
        result = self.cli(ROOT / 'tests/fixtures/bad', '--json')
        self.assertEqual(result.returncode, 2)
        self.assert_high(json.loads(result.stdout))

    def test_cli_medium(self):
        root = ROOT / 'tests/fixtures/testonly'
        self.assertEqual(self.cli(root).returncode, 0)
        self.assertEqual(self.cli(root, '--fail-on', 'MEDIUM').returncode, 2)

    def test_cli_ignore_verbose(self):
        result = self.cli(ROOT / 'tests/fixtures/bad', '--ignore', 'README.md', '--verbose')
        self.assertEqual(result.returncode, 0)
        self.assertIn('Scanned', result.stdout)

    def test_packaging(self):
        config = (ROOT / 'pyproject.toml').read_text()
        self.assertIn('serial-claim-audit = "serial_claim_audit.__main__:main"', config)
        self.assertIn('requires-python = ">=3.9"', config)
        self.assertIn('MIT License', (ROOT / 'LICENSE').read_text())
        self.assertIn('recursive-include tests', (ROOT / 'MANIFEST.in').read_text())
        for name in ('good', 'bad', 'testonly', 'no-serial'):
            self.assertTrue((ROOT / 'tests/fixtures' / name / 'README.md').exists())

    def test_source_hygiene(self):
        for base in ('serial_claim_audit', 'tests'):
            for path in (ROOT / base).rglob('*.py'):
                text = path.read_text()
                self.assertIsNone(re.search(r'(?m)^\s*(?:\$ )?python' + r'\s+-m', text))
                self.assertIsNone(re.search('AKIA' + r'[A-Z0-9]{16}|-----BEGIN ' + 'PRIVATE KEY-----', text))


def good_test(source):
    def test(self):
        self.assertTrue(evidence(source))
        self.assertEqual(audit(self.project('supports serial', source))['findings'], [])
    return test


def bad_test(source):
    def test(self):
        self.assertFalse(evidence(source))
        self.assert_high(audit(self.project('supports serial', source)))
    return test


for name, source in GOOD.items():
    setattr(AuditTests, 'test_good_' + name, good_test(source))
for name, source in BAD.items():
    setattr(AuditTests, 'test_bad_' + name, bad_test(source))
