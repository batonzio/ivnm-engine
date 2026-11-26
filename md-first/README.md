# MD-first voice production

Write ordinary lesson Markdown and add fenced ivnm-voice YAML blocks. Each block is one track, with a unique id, lesson/slide binding, preset, speaker mapping and script. Settings are resolved from voice/presets.json. Scene direction and turn direction are metadata, not spoken text.

Compile: python md-first/compile.py md-first/examples/studio.md out/plan.json

Render: python md-first/render.py out/plan.json out

The public workflow uses synthetic examples only. Do not commit private materials or student information. Experimental voices are not accent-certified. Verified accent routing, full production multi-take selection and the final publisher are not implemented yet. Structured Kitten emotion and emphasis are experimental; free-form direction is blocked by default. Human listening review is required.

## Voice categories
Use `speakers: {Oliver: UK-T-M, Emily: UK-T-F}` or `Oliver: {category: UK-T-M, variant: alternate}`. The compiler resolves approved mappings in `voice/voice-bank.json`; unassigned categories are blocked, never substituted with a different age, gender or accent. Raw engine identifiers are retained for laboratory tests, not approved production voices.

## Unified renderer (experimental)
Pocket, Chatterbox Turbo and Kitten C++ (kitten_tts_cpp 0.2.0) have lazy engine workers. Chatterbox is the preferred engine, Pocket the alternative, Kitten C++ the experimental expressive engine; this preference is policy metadata, not automatic substitution. A mixed-engine plan is assembled at 24 kHz; configure `IVNM_PYTHON_POCKET`, `IVNM_PYTHON_CHATTERBOX`, and `IVNM_PYTHON_KITTEN` to point at separate installed Python environments when dependencies conflict. Smoke tests use one environment per engine; mixed-engine synthesis awaits an end-to-end test. `--production` requires approved category voices; the current bank has no approved slots. `direction_mode: advisory` explicitly permits free-form directions to remain unsynthesized; strict is default. Kitten supports the documented structured emotion and exact-phrase emphasis fields (beta); other engines block unsupported instructions. Three attempts are technical retries, not quality-ranked takes. Approved cloned references require a SHA-256-pinned file under voice-assets. Kitten C++ raw reference cloning is disabled in the router until offline prepared assets are implemented. The successful Python casting artifacts remain archived. No automatic fallback to a different voice.
