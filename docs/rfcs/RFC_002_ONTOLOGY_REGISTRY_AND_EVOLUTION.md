# RFC 002: Ontology Registry & Schema Evolution

**Status:** APPROVED ARCHITECTURAL SPECIFICATION  
**Scope:** Ontology Layer, Predicate Taxonomy, Versioning, Linker Migration Mapping  
**Authors:** Systems Engineering Team  

---

## 1. Executive Summary

The **Ontology Layer** defines the vocabulary (`EntityType`, `Predicate`) into which free text is normalized. 

This RFC establishes the **`OntologyRegistry`** as an explicit, versioned architectural component owned independently of compiler logic.

---

## 2. Ownership & Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           ONTOLOGY REGISTRY                             │
│                     (Schema: OntologyVersion.V1_0)                      │
├─────────────────────────────────────────────────────────────────────────┤
│ • EntityTypes  : COMPONENT, FEATURE, DATABASE, FRAMEWORK, PROTOCOL, ...│
│ • Predicates   : DESCRIBES, HAS_REASON, HAS_TRADEOFF, SELECTED, ...    │
│ • PredicateMap : Free-text mapping rules -> Ontology Predicate Enum     │
└─────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ├──► Reads by Compiler (Extract & Validate)
                                     └──► Reads by Linker (Migrate & Map)
```

1. **Standalone Layer**: The ontology is owned by `OntologyRegistry`, not hardcoded inside extractor functions.
2. **Compiler Consumption**: Extractors (`RuleBasedFactExtractor`, `RuleBasedStatementExtractor`) query the registry to normalize segment kinds and predicate strings.
3. **Version Metadata**: Every `CompiledArtifact` header records `ontology_version: "1.0"`.

---

## 3. Schema Evolution & Linker Migration

When the ontology evolves over time (e.g. splitting `DEPENDS_ON` into `RUNTIME_DEPENDS_ON` vs `BUILD_DEPENDS_ON`):
* Old compiled artifacts preserve their original `ontology_version` header (`"1.0"`).
* The Linker (`MemoryPatchLinker`) reads `CompiledArtifact.ontology_version`. If linking an older artifact into a memory store operating on a newer ontology version, the Linker applies a versioned **Ontology Migration Map** during symbol and fact linking.
* This guarantees backwards compatibility across years of architectural history.
