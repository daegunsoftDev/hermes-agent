# Stateful context: offline source-subset example

This is an isolated worked example, **not a Hermes plugin, production patch,
installation recipe, or enabled backend**. Nothing imports it during normal
Hermes startup. No real endpoint, credential or personal execution receipt is
shipped.

## Run

Use `terminal` with an **existing** Python environment containing OpenAI 2.24.0
and HTTPX 0.28.1. Pass an existing private scratch parent outside this directory:

```text
python run.py --output <private-scratch-parent>
```

The runner does not install dependencies or bootstrap Hermes. It prints its new
owned output directory immediately, verifies source hashes, copies only the
manifest's source files, builds a minimal runtime-only lease, and runs each child
with `-I -B -X utf8` and a credential-free environment. Results/logs remain in the
new output directory and are not written into the source checkout.

## Contents and provenance

- `context_binding.py`: immutable run/call scope, strict durable-boundary reader,
  explicit executor handoff, ContextVar token restoration, per-call SDK/client
  ownership, main/auxiliary route checks and stale-result/stream rejection.
- `public_connection.py`, `validation.py`: public OpenAI/HTTPX construction and
  final serialized-request validation. The inner transport is recording RAM IO.
- `source_defs.py`, `exercise.py`, `extended.py`, `context_tests.py`,
  `retry_control.py`: source-subset loaders and the existing synthetic harnesses.
- `fixture-definitions.json`: bundles the `snapshot/`, `candidate/` and
  `candidate-context/` fixture modules materialized in the owned output tree.
  These are only the inspected definitions
  needed by those harnesses, extracted from pinned source revision
  `d923a5eb487a17c0a68801bba9ef0f56c81040a8` and its offline candidate copies.
  Their syntax trees are preserved, with formatting regenerated for portability.
  Bundling keeps the existing skill below the native 50-file structural limit.
  `source-manifest.json` records original file fingerprints and selected names.
  These modules are fixture inputs, not drop-in replacements for current modules.

## Acceptance contract

The runner checks the same 34 context cases and 38 public-API cases normally and
with `-O`, plus one retry-control case. Seven context mutations must produce
1/1/1/1/1/1/2 assertion failures, three public-path mutations 6/17/1, and the retry
mutation one. All expected mutations must have zero setup errors and zero skips.
The manifest's hashes bind this exported copy, not an earlier execution receipt.
Original RED histories and private preservation receipts are deliberately not
included; their absence does not create a new RED claim for this packaging.

The checks distinguish SDK entry from downstream forwarding: a pre-SDK denial
requires both zero; a late serialized-request denial may have SDK entry one but
must have forward zero. Already-forwarded stale responses retain forward one and
are discarded. Shared-thread author attribution does not rotate conversation
identity. Child and auxiliary lanes remain separate.

## Deliberate limits

The pinned definitions are older than this fork's integration base. Passing this
example is **not** compatibility testing of the current checkout or SDK pin.
Host workspace discovery, admission, authorization, cache collaborators,
provider resolution and the durable boundary DB reader are synthetic. The host
attachment and callback bindings are proposed seams supplied by the harness, not
an already-installed Gateway API. No full Hermes package is bootstrapped.

`contract-v1` is a fixed synthetic revision; no system/tools fingerprint is
implemented. Real Gateway reset/compression, persistence, server tenant auth,
async clients, sockets/TLS/proxies, physical cancellation and avoided billing are
not accepted by these tests. Python audit hooks preserve accident-prevention
checks but are not an operating-system sandbox. Blocked hostname metadata probes
are recorded separately from actual connection/process attempts.

Keep this source example, native integration, installation and live acceptance
as separate decisions. Do not copy these fixtures over product modules.
