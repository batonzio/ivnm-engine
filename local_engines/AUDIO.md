# Audio handoff and reuse contract v0.1

Existing Chatterbox/Pocket production pipeline and postprocessing are unchanged.
No extra TTS model, cache, or database. Factory Asset Manager remains the owner of
approved audio bytes, request receipts and storage.

request_key accepts a resolved, ready track with approved voice statuses and
exact runtime, reference and processing fingerprints provided by a trusted
inventory. Include model weights, TTS version, seed policy, ASR/QA and mastering
settings in fingerprints. Lesson/slide IDs do not determine audio identity;
binding must be checked independently before reuse. Fingerprints are not
independently verified by this helper. Key is a candidate lookup only, not a
replacement for Factory's request_sha256 or explicit approved-version selection.

inspect_package verifies the existing production manifest and qa-report checksums,
human review record bound to that manifest and each track, safe file paths,
expected lesson/slide and minimum duration metadata. It does not decode MP3,
verify reviewer identity, independently check the measured duration or authorize
publication. Keep existing importer ffprobe and Factory receipt validation;
trusted caller must supply review records and expected bindings. No automatic
approval, no demo import. Never publish private references or real student data.

CI runs synthetic tests, including deliberately fake MP3 bytes to test metadata
integrity only. Real audio generation, listening approval, measured duration,
runtime fingerprints and Factory integration remain separate gates. Existing
voice-bank slots require human audition; no automatic voice approval.

Run: python -m unittest local_engines.test_audio -v
