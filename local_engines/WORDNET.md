# WordNet Adapter v0.1

One optional local corpus reader: Princeton WordNet 3.0 via NLTK.
No new dictionary, persistent database, external API, or automatic download.
Use `open_local(directory)` with a separately installed, verified WordNet 3.0
corpus, and `lookup(reader, term, pos="n")`. The NLTK runtime is optional and
must be version-pinned and license-reviewed in deployment. See official
https://www.nltk.org/api/nltk.corpus.reader.wordnet.html .

The output contains distinct POS/offset-based sense IDs, definitions, lemma
forms, hypernym/hyponym/similarity links, and lemma-level antonym relations.
Results are candidates for the existing language graph, not an alternative graph.
No automatic equivalence with a curriculum lexeme, no CEFR assignment,
translation, collocation verification, learner mastery or British usage claim.
An explicit reviewed sense binding is needed before importing evidence.

Source: WordNet 3.0 Copyright 2006 by Princeton University.
License: https://wordnet.princeton.edu/license-and-commercial-use
SPDX identifier: WordNet. Preserve the original copyright and complete license
notice with redistributed data or substantial extracts. No upstream dataset
or definitions are bundled in this repository.

Run: python -m unittest local_engines.test_wordnet -v
For the optional real corpus smoke, install a pinned NLTK runtime, provision
a verified local WordNet 3.0 directory and set IVNM_WORDNET_DIR. CI currently
uses synthetic fixtures; real corpus and British usage evaluation are pending.
