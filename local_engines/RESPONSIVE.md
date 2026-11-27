# Responsive QA evidence v0.1

Use existing private Factory quality_browser / axe pilot to drive actual compiled
slides and phase/transcript states. This module does NOT launch a second browser
in production, rewrite HTML or duplicate axe accessibility checks.

probe(page) reads counts and geometry only on a trusted local Playwright page.
aggregate(samples, expected_states=...) requires each state at 360x800,
390x844 and 430x932; pass require_slide=False for portals. Each state has
width, height, state and metrics. Integrators provide the exact state inventory
and existing navigation/interaction/audio/JS-error/network guards.

G4/G5 rows use existing status/code/detail vocabulary; hard failures are missing
coverage, wrong viewport, horizontal overflow, clipped content or invalid
slide visibility. Vertical mobile scrolling is permitted. A 16px text floor
and 24px touch target floor are review diagnostics, not universal accessibility
compliance or physical readability guarantees. These geometric heuristics can
flag intentional clipping and do not prove visibility of all controls,
correct scoring, touch drag-drop, keyboard access or real iOS/Android.
Those remain existing browser/axe and manual device gates. Never authorize publication.

Unit tests are standard-library. Explicit CI browser smoke uses Playwright
1.51.0 (the existing Factory pin) with disposable synthetic HTML, not pupil data.
No new permanent dependency or service. No real Factory package is claimed tested
by this repository; private integration must call the adapter on its own output.
