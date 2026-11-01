"""Static workflow policy checks, not hosted CI or action-runtime acceptance.

Run directly with an existing PyYAML 6.0.3 environment. The workflow invokes this
entrypoint explicitly; it does not join Hermes' native product test population.
"""
from __future__ import annotations
import copy
import json
from pathlib import Path
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[5]
WORKFLOW = ROOT / '.github/workflows/stateful-context-offline.yml'
CHECKOUT = 'actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1'
PYTHON = 'actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0'
ARTIFACT = 'actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9'
EXAMPLE = 'skills/autonomous-ai-agents/hermes-agent/examples/stateful-context'
SHA_INPUT = '${{ inputs.expected_sha }}'


def contract_errors(document):
    """Return policy violations in the parsed workflow; never execute its steps."""
    events = document.get('on', {})
    inputs = events.get('workflow_dispatch', {}).get('inputs', {})
    jobs = document.get('jobs', {})
    job = jobs.get('offline', {})
    steps = job.get('steps', [])
    by_id = {step.get('id'): step for step in steps}
    checkout = by_id.get('checkout', {})
    python = by_id.get('python', {})
    artifact = by_id.get('artifacts', {})
    install = by_id.get('install', {}).get('run', '')
    guard = by_id.get('guard', {})
    compare = by_id.get('commit', {})
    conditions = [
        ('manual-only', set(events) == {'workflow_dispatch'}),
        ('required-sha', inputs.get('expected_sha', {}).get('required') == 'true'
         and inputs.get('expected_sha', {}).get('type') == 'string'
         and 'default' not in inputs.get('expected_sha', {})),
        ('read-only', document.get('permissions') == {'contents': 'read'}),
        ('one-standard-runner', set(jobs) == {'offline'} and job.get('runs-on') == 'ubuntu-24.04'),
        ('bounded-time', job.get('timeout-minutes') == '10'),
        ('owner-event', job.get('if') == "github.repository == 'daegunsoftDev/hermes-agent' && github.event_name == 'workflow_dispatch'"),
        ('pinned-actions', checkout.get('uses') == CHECKOUT and python.get('uses') == PYTHON
         and artifact.get('uses') == ARTIFACT),
        ('immutable-checkout', checkout.get('with') == {'ref': SHA_INPUT, 'persist-credentials': 'false', 'fetch-depth': '1'}),
        ('pinned-python', python.get('with') == {'python-version': '3.14.7', 'check-latest': 'false', 'allow-prereleases': 'false'}),
        ('sha-validation', guard.get('env', {}).get('EXPECTED_SHA') == SHA_INPUT
         and '^[0-9a-f]{40}$' in guard.get('run', '')
         and 'workflow_dispatch' in guard.get('run', '')),
        ('commit-readback', compare.get('env', {}).get('EXPECTED_SHA') == SHA_INPUT
         and 'git rev-parse HEAD' in compare.get('run', '') and '$EXPECTED_SHA' in compare.get('run', '')),
        ('isolated-pins', 'python -m venv "$RUNNER_TEMP/stateful-ci-venv"' in install
         and all(pin in install for pin in ['openai==2.24.0', 'httpx==0.28.1', 'PyYAML==6.0.3'])
         and '--no-input' in install),
        ('static-entry', EXAMPLE + '/test_workflow_contract.py' in by_id.get('static', {}).get('run', '')),
        ('behavior-entry', EXAMPLE + '/run.py' in by_id.get('behavior', {}).get('run', '')
         and '--output "$RUNNER_TEMP/stateful-results"' in by_id.get('behavior', {}).get('run', '')),
        ('failure-propagates', job.get('continue-on-error', 'false') == 'false'
         and all(step.get('continue-on-error', 'false') == 'false' for step in steps)),
        ('bounded-artifacts', artifact.get('if') == 'always()'
         and artifact.get('with', {}).get('retention-days') == '1'
         and artifact.get('with', {}).get('path') == '${{ runner.temp }}/stateful-results/'),
        ('no-secret-input', 'secrets.' not in json.dumps(document)),
        ('bash', document.get('defaults', {}).get('run', {}).get('shell') == 'bash'),
        ('no-cancellation', document.get('concurrency', {}).get('cancel-in-progress') == 'false'),
    ]
    return [name for name, valid in conditions if not valid]


class WorkflowContracts(unittest.TestCase):
    def document(self):
        self.assertTrue(WORKFLOW.is_file(), 'Manual-only workflow source is not implemented')
        # BaseLoader preserves GitHub's `on` key instead of YAML 1.1 boolean coercion.
        with WORKFLOW.open(encoding='utf-8') as stream:
            document = yaml.load(stream, Loader=yaml.BaseLoader)
        self.assertIsInstance(document, dict)
        return document

    def test_source_meets_contract(self):
        self.assertEqual(contract_errors(self.document()), [])

    def test_static_contract_rejects_policy_mutations(self):
        base = self.document()
        mutations = [
            ('manual-only', lambda d: d['on'].update(push={})),
            ('read-only', lambda d: d['permissions'].update(contents='write')),
            ('one-standard-runner', lambda d: d['jobs']['offline'].update({'runs-on': 'self-hosted'})),
            ('bounded-time', lambda d: d['jobs']['offline'].update({'timeout-minutes': '0'})),
            ('immutable-checkout', lambda d: d['jobs']['offline']['steps'][1]['with'].update(ref='main')),
            ('immutable-checkout', lambda d: d['jobs']['offline']['steps'][1]['with'].update({'persist-credentials': 'true'})),
            ('failure-propagates', lambda d: d['jobs']['offline'].update({'continue-on-error': 'true'})),
            ('bounded-artifacts', lambda d: d['jobs']['offline']['steps'][-1]['with'].update({'retention-days': '90'})),
        ]
        for expected, mutate in mutations:
            with self.subTest(policy=expected):
                changed = copy.deepcopy(base)
                mutate(changed)
                self.assertIn(expected, contract_errors(changed))


if __name__ == '__main__':
    unittest.main(verbosity=2)
