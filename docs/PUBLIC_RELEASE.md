# Public research release — October 15, 2026

This standalone GitHub repository is derived from the reviewed source archive with SHA-256 `ec0a97a4dbd230a6004b38e28c3d826d2691853af009cd7f18688e773b23d84a`. The original private research repository and its Git history were not published. No portfolio website publication is included.

## Publication checks

- All 118 original archive members were checked against the reviewed manifest. Research package code, tests, numerical evidence, locks and notebooks remain byte-identical. Reader-facing documentation and publication metadata were adapted for this public checkout; the public replay receipt has a new execution timestamp.
- Executing this checkout's package code with the existing pinned Windows/Python 3.12 dependency environment reproduced **720 forecast records, 30 metric rows and both primary paired comparisons**. No source data were downloaded and no models were fitted.
- The public checkout's test suite completed with **126 passed and one skipped**. The skipped test requires locally retained source acquisition, which is not distributed. Two Shapely deprecation warnings were reported. The original full-evidence workspace had 127 passing tests; that is a different scope.
- Publication review found no broken Markdown file links, private machine paths, credentials, raw source panels or vessel identifiers. Aggregate evidence and source attribution are retained.

These are local release checks using the pinned existing dependency environment, not a fresh dependency-installation test, remote CI result, independent human review or production validation. See [reproduction scope](REPRODUCIBILITY.md) and [data terms](../DATA_LICENSES.md).

The conclusion is unchanged: the validation-selected calls-to-TEU benchmark achieved **7.34% WAPE**, versus **11.21%** for geography-aware shipping and **11.89%** for aggregate shipping, across 24 monthly test origins. The study does not justify preferring the geography-aware model.
