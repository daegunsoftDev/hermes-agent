# Providers & Model Aliases

Set via `hermes model` (picker) or `hermes setup`. 35+ provider profiles ship as
plugins under `plugins/model-providers/`; user plugins of the same name override.
Full docs: https://hermes-agent.nousresearch.com/docs/integrations/providers

### Providers

| Provider | Auth | Key env var(s) |
|----------|------|----------------|
| openrouter | API key | `OPENROUTER_API_KEY` |
| anthropic | API key | `ANTHROPIC_API_KEY` (also `CLAUDE_CODE_OAUTH_TOKEN`) |
| nous | OAuth device code | `hermes auth add nous` (or `NOUS_API_KEY`) |
| openai-codex | OAuth | `hermes auth add openai-codex` |
| qwen-oauth | OAuth | `hermes auth add qwen-oauth` |
| minimax-oauth | OAuth | `hermes auth add minimax-oauth` |
| gemini | API key | `GOOGLE_API_KEY` or `GEMINI_API_KEY` |
| xai | API key | `XAI_API_KEY` (SuperGrok OAuth also supported) |
| deepseek | API key | `DEEPSEEK_API_KEY` |
| zai (GLM) | API key | `GLM_API_KEY` / `ZAI_API_KEY` |
| minimax / minimax-cn | API key | `MINIMAX_API_KEY` / `MINIMAX_CN_API_KEY` |
| kimi-coding / -cn | API key | `KIMI_API_KEY` / `KIMI_CN_API_KEY` |
| alibaba (+coding-plan) | API key | `DASHSCOPE_API_KEY` / `ALIBABA_CODING_PLAN_API_KEY` |
| xiaomi | API key | `XIAOMI_API_KEY` |
| huggingface | Token | `HF_TOKEN` |
| fireworks / novita / nvidia / deepinfra / gmi / arcee / stepfun / upstage / kilocode / ai-gateway / opencode-zen / opencode-go / ollama-cloud | API key | `<NAME>_API_KEY` |
| bedrock / vertex / azure-foundry | Cloud SDK / key | AWS SDK creds / Vertex ADC / `AZURE_FOUNDRY_API_KEY` |
| custom | Config | `model.base_url` + `model.api_key` in config.yaml |

GitHub Copilot (`copilot`, `copilot-acp`) is a labs plugin, not core: `hermes plugins install github-copilot`, then `hermes auth add copilot` (https://github.com/NousResearch/hermes-labs-plugins/tree/main/github-copilot).

Multiple credentials per provider pool and rotate automatically (`hermes auth`).
Fallback chain when the primary fails: `hermes fallback add|remove|list`.

### Stateful provider session validation

Use this procedure before connecting a stateful OpenAI-compatible backend.
Cache affinity, a prompt-cache key and a stateful conversation ID are different
contracts; an opaque session key is not authentication or authorization.

1. **Bind the evidence.** Resolve the intended home/profile, launcher and installed
   source revision. Compare the backend's primary contract with that revision's
   selected API transport. Keep disk support separate from the serving revision;
   changing a base URL does not establish compatibility with another API mode.
2. **Trace trusted identity.** Follow identity from the platform producer through
   the runner, agent and request builder. Verify which profile, workspace,
   conversation, independent child, auxiliary lane, engine/model and context
   generation actually reach the request. Preserve an answered thread-sharing
   policy: do not impose per-author key rotation on a deliberately shared thread.
   Keep author attribution and authorization distinct from shared conversation
   identity; model-supplied IDs and a shared parent's root are not isolation proof.
   For a selected stateful path, rebind trusted run identity on fresh and cached
   agent turns; derive an immutable policy and owned client for each call. Require
   an explicit workspace, child, lane and resolved engine/model; do not recover
   missing values from request text or ambient state. Reuse the existing durable
   conversation boundary only after a successful non-negative integer read;
   reject missing/error/boolean/coerced values rather than substituting zero or
   a run-generation counter. Carry policy explicitly across thread/executor
   boundaries and restore ContextVar tokens in finally, including nested failures.
   Recheck the boundary before SDK entry and final forwarding, after a response,
   and while consuming streams; discard stale results and close owned resources.
   A post-send rejection does not prove physical cancellation or avoided cost.
   Declare synthetic producer, admission and DB collaborators; passing a source
   subset does not establish native Gateway binding or real reset/compression.
3. **Inspect final header precedence.** Trace explicit affinity opt-in and existing
   headers through main and auxiliary requests, middleware and SDK dispatch.
   Check client defaults and request headers together, including case-insensitive
   duplicates. Do not assume `setdefault` replaces a conflicting key or that a
   body cache-scope field controls a stateful session header. Bind streaming,
   retries and fallback to the same intended route and conversation contract.
4. **Verify rejection semantics.** Inspect the installation's middleware chain
   and final transport callback (for example, `hermes_cli/middleware.py` and
   `agent/turn_api_call.py`). Determine whether an exception before `next_call`
   propagates or is reported and followed by downstream execution. Never claim
   fail-closed behavior merely because a guard raises `RuntimeError` or
   `PermissionError`, or because a normal short-circuit returns without calling
   the SDK. Check call inputs after mutable middleware and before SDK entry,
   then validate the serialized request at the final outbound transport before
   forwarding. Bind both checks to host-trusted context, because SDK merging and
   HTTP-client hooks can alter an earlier-validated request. Missing context,
   missing or conflicting keys and route/model mismatches must prevent downstream
   transmission; policy rejection must not trigger retry or provider fallback.
   Classify that dedicated rejection before auxiliary stream-to-nonstream fallback
   and before an outer handler enters pre-classification recovery, not only in a
   later generic API-error classifier. If rejection can originate inside the SDK,
   exercise its actual exception wrapping and automatic retry path: the outer
   exception type alone may no longer identify the policy denial. Retain a trusted
   rejection outcome across that boundary and prove no denied dispatch or retry.
   Do not reconstruct a trusted policy outcome from an exception message.
   Preserve unrelated provider and ordinary middleware behavior. This boundary
   does not sandbox arbitrary plugin code or replace server-side authorization.
5. **Use bounded source tests when authorized.** Freeze exact source bytes and
   extract only inspected pure definitions into owned scratch. Use synthetic
   identities and recording callbacks/clients; exclude real credentials, SDK
   bootstrap, model calls and network/process side effects. Test positive
   forwarding, pre-next exceptions, downstream exception propagation, normal
   short-circuit and repeated `next_call` separately. Assert recorded dispatch
   counts and ordering, not only returned values or logged errors. Preserve the
   original source and every failed readiness result. For separately authorized
   real-SDK tests, follow the memory-transport procedure below; source-test
   approval alone does not authorize SDK loading or provider connections.
6. **Keep readiness independent.** A behavior suite can pass while mandatory
   rejection or conversation separation fails. Require zero SDK API entries for
   pre-SDK denials. For denials discovered after serialization, retain any SDK
   entry already observed and require zero downstream transport forwards and
   zero retry preparation after denial; do not report this as zero SDK entries.
   Verify permitted sharing, independent-child/lane separation and streaming,
   auxiliary, retry and fallback coverage before accepting the proposed boundary.
   Do not waive failed readiness with positive behavior tests, a static scan or
   a matching source hash.
7. **Report the measured layer.** Distinguish source tracing, recording-client
   behavior, real-SDK memory-transport behavior, native enforcement and authorized
   wire/server acceptance. Recording clients do not prove SDK serialization or
   parsing. A real-SDK memory transport proves only the exercised serialization
   and HTTP/JSON/SSE parsing paths, not physical network behavior, the serving
   Gateway's loaded SDK, tenant authorization, cancellation, concurrency or
   billing. Ask only for genuinely new execution scope; preserve answered
   policies and unanswered installation/runtime questions without treating
   silence as consent.

### Real-SDK offline boundary checks

Use this recipe only when actual SDK loading and owned offline fixtures are
explicitly within scope. Keep native adoption and live-server acceptance separate.

1. **Inspect host policy before choosing hooks.** Read the actual main and
   auxiliary constructors, including forced values, defaults and caller
   overrides for `max_retries`. Inspect request-client checkout/release and
   auxiliary caches before attaching a request-bound policy object: a cached
   SDK client can outlive that binding. Trace default, mounted and proxy
   transports and shared-pool close ownership; wrapping only a default transport
   does not establish coverage of every dispatch route. Consider supported
   constructor/transport seams first. Keep any untested replacement a design,
   not a working migration recipe; private-hook candidates require their own
   SDK-version and source binding.
   On a selected guarded path, verify that failure to build the policy, wrapping
   transport or owned HTTP client stops the call: `None` or an empty kwargs dict
   must not reopen the SDK default transport. A constructor exception alone does
   not prove that downstream retry or fallback is stopped. Bind the policy snapshot
   and physical SDK/HTTP client to the call; do not store them on a shared cached
   client or the underlying shared pool. Keep the owned client alive while its
   stream is active, then close it exactly once on exhaustion, error or explicit
   close/cancel without closing a pool still used by another call. Measure failed
   construction, cache reuse and overlapping streams with ownership counters;
   memory-transport cleanup is not proof of live socket cancellation.
2. **Freeze the complete experiment.** Resolve the existing SDK-owning
   interpreter, package versions and relevant source hashes without installing
   replacements. Preserve the original policy, baseline failures and complete
   fixture dependency closure, including helper snapshots and descriptor files.
   Keep installed-library and scratch locations separate from the Git-owned
   publication source; source delivery does not install or activate the skill.
   Declare the exported dependency closure, including every selected definition
   and required loader input. Preserve selected definition ASTs if formatting is
   regenerated. Bind exported fixture manifests to their materialized bytes and
   paths, not merely an archive hash or an earlier experiment receipt. Use the
   exact supported mutation-mode identifiers; require the intended assertion
   failures with zero setup errors rather than accepting a successful no-op.
   Exercise the exported closure in a fresh output tree without the original
   scratch inputs. Preserve incomplete or failed exports as separate evidence;
   packaging acceptance is not current-product or native-integration acceptance.
   Invoke the verified interpreter directly with `-I -B -X utf8` and an explicit
   owned test entrypoint. Use synthetic identities, a credential-free environment
   and `httpx.MockTransport` through an explicit `httpx.Client` with
   `trust_env=False`, or the inspected equivalent. Enumerate the intended test
   classes and unique case IDs rather than discovering unrelated live suites.
   Record blocked metadata lookups separately from connection/process attempts;
   Python audit hooks are not an operating-system sandbox.
3. **Exercise actual serialization without a GREEN shim.** Record the final
   `httpx.Request`, not just the input kwargs. Test SDK-added base-URL trailing
   slashes without broadening accepted hosts or paths. Inspect header
   `multi_items()` or raw pairs, because a dict view can hide case-insensitive
   duplicates introduced by default/request merging. Reject conflicting session
   values; consolidate equivalent values to exactly one final session header.
   Compare the serialized JSON model with trusted context as well as validating
   the top-level model, because `extra_body` can replace it. Include streaming
   and ordinary JSON parsing. A route-metadata shim may isolate downstream
   failures, but keep its diagnostic results separate and remove it from every
   claimed compatibility pass.
4. **Measure denial through wrapping and retry.** Retain a request-bound typed
   denial that survives SDK connection-error wrapping; never infer authority
   from exception prose. Count SDK API entry, request preparation, final
   transport checks and inner recording-transport forwards separately. Exercise
   a deliberately retry-enabled fault case to detect repeated preparation, but
   do not attribute that injected configuration to the native host. Classify
   denial before auxiliary nonstream fallback and outer recovery; preserve
   ordinary retry behavior wherever the inspected contract permits it.
5. **Prove sensitivity and preserve failure identity.** Run both the new SDK
   acceptance cases and the unchanged earlier source-bound regression suite
   against the candidate. Disable final transport validation and mutate the
   inspected retry-denial mechanism independently in memory; target its actual
   setting or hook rather than requiring a particular implementation. Require
   assertion failures, not import/setup errors. Keep exception-class identity and dependent references coherent when
   replacing definitions, because stale imported classes can manufacture a
   false mutation detection. Correct a missing copied fixture without changing
   the candidate or weakening assertions; retain that setup failure and rerun
   under a fresh result label. Leave installed SDK/product files untouched.
6. **Bind the report to the tested bytes.** Save versions, candidate/test hashes,
   unique populations, exit/failure/error/skip counts, per-stage dispatch counts
   and actual audit events. Preserve original failures and diagnostic shims as
   separate evidence. Recheck source preservation, and distinguish synchronous
   SDK coverage from async clients, host-context production, native cache and
   stream-lifecycle integration. Do not promote a passing isolated candidate or
   an untested public-interface design into serving readiness.

The pinned [offline worked example](../examples/stateful-context/README.md)
ships synthetic source-subset checks only; it does not activate a Gateway path
or establish compatibility with the current product revision.

### User-defined model aliases

Work with `/model <name>` in CLI and every gateway platform. Resolved by
`hermes_cli/model_switch.py::resolve_alias()`; user aliases are checked BEFORE
the built-in table, so a user `sonnet`/`grok` shadows the built-in.

```yaml
# Full form
model_aliases:
  fav:
    model: claude-sonnet-4.6
    provider: anthropic
  local-qwen:
    model: qwen3.5:397b
    provider: custom
    base_url: "https://ollama.com/v1"
  theta:
    model: theta-1
    provider: custom
    base_url: "https://theta.example.com/v1"
    key_env: THETA_API_KEY        # or: api_key: "${THETA_API_KEY}"

# Short form ("provider/model"), also via CLI:
#   hermes config set model.aliases.fav openrouter/anthropic/claude-sonnet-4.6
model:
  aliases:
    fav: openrouter/anthropic/claude-sonnet-4.6
```

`/model fav` — session-scoped; add `--global` to persist as default.

An alias with its own `base_url` authenticates with its own credential
(`api_key`, which also accepts a `"${VAR}"` reference, or `key_env`). With
neither set the key is resolved from the alias HOST, never carried over from
the provider that was active before the switch.

Built-in aliases (catalog-resolved against the active provider): `sonnet`,
`opus`, `haiku`, `claude`, `gpt5`, `gpt`, `codex`, `o3`, `o4`, `gemini`,
`deepseek`, `grok`, `llama`, `qwen`, `minimax`, `nemotron`, `kimi`, `glm`,
`step`, `mimo`, `trinity`.
