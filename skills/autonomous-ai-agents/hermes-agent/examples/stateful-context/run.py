"""Run the pinned offline example in a fresh, credential-free output tree."""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import sysconfig
import tempfile


def need(value, message):
    if not value:
        raise RuntimeError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path,
                        help='Existing private scratch parent; never a Hermes home.')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    manifest = json.loads((root / 'source-manifest.json').read_text(encoding='utf-8'))
    for package, version in manifest['sdk_versions'].items():
        need(importlib.metadata.version(package) == version,
             'Use an existing environment with ' + package + '==' + version + '; no automatic install.')
    output = args.output.resolve(strict=True)
    need(output.is_dir() and not output.is_relative_to(root), 'Output must be outside source.')
    work = Path(tempfile.mkdtemp(prefix='stateful-context-', dir=output))
    print(json.dumps({'owned_output': str(work)}, sort_keys=True), flush=True)
    fixture_bytes = (root / 'fixture-definitions.json').read_bytes()
    need(hashlib.sha256(fixture_bytes).hexdigest() == manifest['fixture_bundle_sha256'],
         'Fixture bundle drift')
    fixtures = json.loads(fixture_bytes)
    for relative, digest in manifest['code_sha256'].items():
        source = root / relative
        data = fixtures[relative].encode('utf-8') if relative in fixtures else source.read_bytes()
        need(hashlib.sha256(data).hexdigest() == digest, 'Source drift: ' + relative)
        target = work / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(data)
    lease = dict(site_packages=sysconfig.get_path('purelib'),
                 openai_version=manifest['sdk_versions']['openai'],
                 httpx_version=manifest['sdk_versions']['httpx'])
    with (work / 'lease.json').open('x', encoding='utf-8') as stream:
        json.dump(lease, stream, indent=2)
    home = work / 'synthetic-home'
    home.mkdir()
    env = {key: os.environ[key] for key in ('SystemRoot', 'WINDIR', 'COMSPEC') if key in os.environ}
    env.update(HOME=str(home), USERPROFILE=str(home), TEMP=str(work), TMP=str(work),
               TMPDIR=str(work), PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1',
               PYTHONUTF8='1', NO_PROXY='*')
    modes = [('context_tests.py', 'context-normal', False, 34, 0),
             ('context_tests.py', 'context-optimized', True, 34, 0),
             ('extended.py', 'public-normal', False, 38, 0),
             ('extended.py', 'public-optimized', True, 38, 0),
             ('retry_control.py', 'retry-control', False, 1, 0)]
    for mode, count in [('mutation-no-rebind', 1), ('mutation-author-key', 1),
                        ('mutation-epoch-ignore', 1), ('mutation-final-scope', 1),
                        ('mutation-post-response', 1), ('mutation-context-restore', 1),
                        ('mutation-aux-route', 2)]:
        modes.append(('context_tests.py', mode, False, count, count))
    for mode, failures in [('mutation-wire', 6), ('mutation-main', 17), ('mutation-aux', 1)]:
        modes.append(('extended.py', mode, False, 38, failures))
    modes.append(('retry_control.py', 'mutation-retry-setting', False, 1, 1))
    runs = []
    for script, mode, optimized, count, failures in modes:
        command = [sys.executable, '-I', '-B', '-X', 'utf8']
        if optimized:
            command.append('-O')
        command.extend([str(work / script), mode])
        with (work / (mode + '.stdout.log')).open('xb') as stdout, (work / (mode + '.stderr.log')).open('xb') as stderr:
            child = subprocess.run(command, cwd=work, env=env, stdout=stdout, stderr=stderr, timeout=90)
        result_path = work / (mode + '_result.json')
        need(result_path.exists(), 'Missing child result: ' + mode)
        result = json.loads(result_path.read_text(encoding='utf-8'))
        observed = dict(mode=mode, actual_exit=child.returncode, tests=result['tests'],
                        failures=len(result['failures']), errors=len(result['errors']),
                        skips=result.get('skips', result.get('skipped', 0)))
        runs.append(observed)
        print(json.dumps(observed, sort_keys=True), flush=True)
        need(observed == dict(mode=mode, actual_exit=1 if failures else 0, tests=count,
                              failures=failures, errors=0, skips=0), 'Unexpected result: ' + mode)
    summary = dict(verdict='PORTABLE_SOURCE_SUBSET_ACCEPTANCE_PASS', runs=runs,
                   original_source_revision=manifest['original_source_revision'],
                   sdk_versions=manifest['sdk_versions'], native_activation=False,
                   host_admission_and_DB='synthetic collaborators',
                   revision_fingerprint_implemented=False,
                   current_checkout_integration_tested=False)
    with (work / 'acceptance.json').open('x', encoding='utf-8') as stream:
        json.dump(summary, stream, indent=2)
    print(json.dumps({'verdict': summary['verdict'], 'receipt': str(work / 'acceptance.json')}, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
