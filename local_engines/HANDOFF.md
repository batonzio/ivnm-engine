# Cross-repository compatibility notes

Reviewed private integration pilot contracts at 42ced0edb7f125b5d65e7473c3184d675d02110e.
No private code, lesson data, secrets or fixtures copied into this public repository.

- Existing real LanguageTool pilot checks provider version, en-GB and converts UTF-16
  offsets. The earlier public proofreading adapter returns upstream offsets and
  a different schema. Do not treat these contracts as interchangeable or run both
  for one request. Recommend private pilot as the single canonical production
  adapter after compatibility and license/security review. Keep public adapter
  as standalone prototype until integration chooses the canonical interface.
- Existing axe pilot and quality_browser remain authoritative for browser orchestration,
  accessibility and interaction checks. New responsive module is only a mobile
  measurement/coverage helper; do not create a duplicate browser service.
- WordNet results are external sense evidence (versioned POS/offset identity).
  Existing Language Core graph requires explicit sense binding and review.
  Do not merge lexemes by surface form or infer CEFR/mastery.
- Memory remains a SQLite reference implementation. Private PostgreSQL identity,
  grading and resource receipts stay independent. No separate production database
  or publishing permission is introduced.
- Existing publisher and audio importer still require their own contracts and
  review. Cross-repository status is not proof of runtime interoperability.
