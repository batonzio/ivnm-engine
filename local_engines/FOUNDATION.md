# IVNM Core foundation v0.1

Three independent standard-library modules:
- Memory: immutable revisions, explicit approval/retirement, optimistic write checks, shared/private scope. SQLite is a portable reference backend only; production should use the existing PostgreSQL architecture via the same interface. A trusted caller must enforce teacher authorization and avoid student PII.
- Context: mandatory approved standard and course records; optional course-key-prefixed resources and decisions; actual progress if recorded. Ambiguity and insufficient context budget fail closed. Returns exact revision/digest references. Budget is characters, not tokens.
- Curriculum: deterministic sequencing of explicit units and prerequisites, fixed lesson duration/capacity, review links, planned state. Does not infer mastery, generate linguistic content or replace existing language/methodology engines. No automatic approval or publication. Assessment slots and per-day durations must be supplied by the caller in a later integration contract; not implemented in this minimal planner.

Usage: python -m unittest discover -s . -p 'test_*.py' is NOT needed; use python -m unittest local_engines.test_adapters local_engines.test_foundation -v.

Handoff: caller provides verified standards, units and authorized scope; Context returns a string suitable for drafting.draft. Course plan remains a draft and requires methodological validation. No teacher/student identity, live LLM calls, deployment or storage access in tests. No new external dependencies.
