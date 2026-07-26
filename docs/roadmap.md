# Roadmap

## Phase 0 - done

- [x] Compiler pipeline skeleton (`observe -> segment -> extract_*`)
- [x] Rule-based statement extractor
- [x] Rule-based fact extractor (ontology normalization)
- [x] Naive entity extractor (fixed patterns - see note in `pipeline.py`)
- [x] Claim wrapping (fixed confidence, not yet computed)
- [x] Golden tests (`tests/golden/pr_001`, `tests/golden/pr_002`)

## Phase 1 - in progress

- [ ] `LLMStatementExtractor` - interface exists in `extractors.py`, raises
      `NotImplementedError`
- [ ] General entity recognizer (replace the fixed pattern list)
- [ ] Claim confidence actually computed instead of defaulted to 0.5
- [ ] Additional artifact shapes beyond PR-style (commit, ADR, issue)

## Phase 2 - not started

- [ ] `MemoryPatch` production (diffing new facts against existing memory)
- [ ] Project Memory storage layer

## Phase 3 - not started

- [ ] Explanation Engine
- [ ] Compliance Engine
