# IVNM local engine adapters v0.1

Independent adapters for parallel integration. Python standard library only.
No changes to voice, Factory, publisher or production data. No hosted AI APIs.

- `proofreading.check(text, port=8081)`: LanguageTool local HTTP server, en-GB, advisory findings only. Offsets are passed through from upstream; the consumer must verify offset semantics before highlighting. Never computes a school mark.
- `drafting.draft(prompt, context, model=..., port=11434)`: Ollama chat JSON schema, outputs draft title, rationale, Markdown. Does not validate LessonSpec or curriculum continuity. Core must validate and review before compilation. No execution of model output.

Both accept only loopback 127.0.0.1; no remote URLs, proxy or redirects. Deployment must run local services with cloud disabled and network egress denied after installation; loopback transport alone cannot prove service internals never send data outside. Do not pass student personal data. Select and approve exact model versions, weights, checksums and licenses separately. No automatic fallback to a cloud model.

## Run

```sh
python -m unittest local_engines.test_adapters -v
```

CI uses synthetic HTTP fixtures only. Real runtime, model quality, resource footprint and server licenses remain acceptance gates. No claim of real synthesis or production readiness.

## Upstream

LanguageTool core: LGPL-2.1-or-later, https://github.com/languagetool-org/languagetool ; resources may have different licenses. Local HTTP: https://dev.languagetool.org/http-server.html .
Ollama runtime: https://github.com/ollama/ollama ; API: https://github.com/ollama/ollama/blob/main/docs/api.md . Runtime and model weights require separate license review. No third-party binaries or weights are redistributed here.

## Handoff

Versioned JSON response, schema_version=1; failures raise EngineError or ValueError. On error the caller should block the corresponding stage or flag it for review, not silently accept it. publication_allowed=false is invariant. The integration branch can pin the exact commit and import local_engines, with private inputs held outside the public repo.
