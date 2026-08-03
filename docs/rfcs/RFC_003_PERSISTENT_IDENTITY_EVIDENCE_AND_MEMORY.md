# RFC 003: Persistent Identity, Evidence Model & Memory Semantics

> **Amended by RFC 004.** Three changes since this RFC was approved:
> persistent entity IDs hash the canonical name **only**, never the entity type
> (§7); `SupersessionEdge` carries `source_artifact_id`, `recorded_at` and
> `basis` (§5); and `EvidenceRecord` carries real claim confidence and artifact
> authority rather than a hardcoded value (§6). RFC 004 also adds read-side
> non-goals mirroring §6 below.

**Status:** APPROVED ARCHITECTURAL SPECIFICATION  
**Scope:** MemoryPatch Linker Architecture, Identity System, Evidence Model, Analysis Rules  
**Authors:** Systems Engineering Team  

---

## 1. Executive Summary

This RFC formalizes the core architectural concepts behind **Persistent Identity**, the **Evidence Model**, the **Three-Pass Linker Pipeline**, and the explicit **Non-Goals** of the `MemoryPatch` engine.

---

## 2. Persistent Identity vs. Compiler-Local Identity

Identity operates at two distinct layers in the Project Memory Engine:

1. **Compiler-Local Identity**:
   - **Scope**: Single artifact compilation pass.
   - **Format**: Deterministic local ordinals (`obs:0`, `seg:1`, `stmt:2`, `claim:3`).
   - **Purpose**: Provenance linking and pass diagnostics. Transient; discarded after compilation.
2. **Persistent Identity**:
   - **Scope**: System-wide across space and time.
   - **Format**: Content-addressed cryptographic hashes (`deterministic_id`).
   - **Target**: Reserved strictly for `Artifact` (`hash(URI + Content)`), `Entity` (`hash(NormalizedCanonicalName)`), and `PersistedFact` (`hash(SubjRef + Pred + ObjRef)`).

---

## 3. The Evidence Model: One PersistedFact $\rightarrow$ Many EvidenceRecords

Compiler output represents **evidence asserted by an artifact**. Persistent Memory represents **accumulated structured knowledge**.

```
                           ┌─────────────────────────┐
                           │      PersistedFact      │
                           │  (Subject, Pred, Obj)   │
                           └────────────┬────────────┘
                                        │ 1
                                        │
                                        │ N
                                        ▼
                   ┌──────────────────────────────────────────┐
                   │             EvidenceRecord               │
                   │ • Source Artifact ID                     │
                   │ • Source Compiler Fact ID                │
                   │ • Confidence & Supporting Statements     │
                   └──────────────────────────────────────────┘
```

When multiple artifacts across time assert the exact same relationship (e.g. Commit 042 and ADR 001 both assert `API Gateway -> uses -> JWT validation`):
* The Linker does **NOT** create duplicate `PersistedFact` graph nodes.
* The Linker appends a new **`EvidenceRecord`** linking the new artifact to the existing `PersistedFact`.
* Provenance accumulates cleanly without graph duplication or fact mutation.

---

## 4. Ontology Preservation: `ArtifactRef` vs. Domain `Entity`

An **Artifact** is a source of evidence (a document, PR, ADR, or commit). An **Entity** is a domain architecture concept (`JWT validation`, `API Gateway`, `Redis`).

To prevent blurring these concepts:
* `$ARTIFACT_SELF` / `CURRENT_CHANGE` references resolve to an explicit **`ArtifactRef(artifact_id)`** symbol rather than a domain `Entity`.
* Facts whose subject is the artifact itself (e.g. `[ArtifactRef] --describes--> "Move JWT validation into Gateway"`) maintain strict ontology separation.

---

## 5. Three-Pass Linker Pipeline Architecture

The `ThreePassMemoryPatchLinker` operates in three deterministic internal passes:

1. **Pass 1 — `BindingPass`**:
   - Binds local artifact entities to global persistent Entity IDs.
   - Resolves `$ARTIFACT_SELF` / `CURRENT_CHANGE` to `ArtifactRef(artifact_id)`.
   - Unresolved entities safely remain unresolved. Zero semantic reasoning.
2. **Pass 2 — `PersistencePass`**:
   - Promotes compiler facts to content-addressed `PersistedFact` nodes.
   - Accumulates `EvidenceRecord` items for existing facts ($O(1)$ deduplication).
   - Emits immutable `MemoryDelta`.
3. **Pass 3 — `AnalysisPipeline`**:
   - Executes a sequence of independent, composable **`AnalysisRule`** plugins (like compiler optimization passes):
     - `ExplicitDeprecationRule`: Detects `DEPRECATED` and `REPLACED_BY` facts.
     - `SingleOccupancyDecisionRule`: Detects `SELECTED` decision overrides.
     - `DirectNegationConflictRule`: Detects direct contradiction facts.

---

## 6. Non-Goals: What MemoryPatch Will NEVER Do

To keep the Linker deterministic, inspectable, and robust, `MemoryPatch` explicitly defines the following **Non-Goals**:

1. **Never Parse Source Documents**: Document chunking and syntax parsing belong strictly to the Compiler.
2. **Never Call LLMs**: Linker passes are 100% deterministic algorithms.
3. **Never Perform Vector/Embedding Retrieval**: Linking operates on exact symbol and entity bindings.
4. **Never Guess Unresolved Entities**: If an entity mention is ambiguous or unknown, it remains unresolved.
5. **Never Mutate Compiler Output**: Compiler output is immutable evidence.
6. **Never Delete Historical Evidence or Facts**: Memory is monotonic append-only. Invalidation is expressed strictly via `SupersessionEdge`.
7. **Never Infer Missing Ontology Taxonomy**: Missing predicates stay unpromoted; the Linker never invents ontology types.
