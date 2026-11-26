# MD-first voice production

Write ordinary lesson Markdown and add fenced ivnm-voice YAML blocks. Each block is one track, with a unique id, lesson/slide binding, preset, speaker mapping and script. Settings are resolved from voice/presets.json. Scene direction and turn direction are metadata, not spoken text.

Compile: python md-first/compile.py md-first/examples/studio.md out/plan.json

Render: python md-first/render.py out/plan.json out

The public workflow uses synthetic examples only. Do not commit private materials or student information. Experimental voices are not accent-certified. Native emotional instruction, multi-take selection, verified accent routing and the final publisher are not implemented yet. The compiler blocks expressive requirements rather than silently weakening them. The renderer currently accepts only neutral single-take Pocket tracks. Human listening review is required.

## Voice categories
Use `speakers: {Oliver: UK-T-M, Emily: UK-T-F}` or `Oliver: {category: UK-T-M, variant: alternate}`. The compiler resolves approved mappings in `voice/voice-bank.json`; unassigned categories are blocked, never substituted with a different age, gender or accent. Raw engine identifiers are retained for laboratory tests, not approved production voices.
