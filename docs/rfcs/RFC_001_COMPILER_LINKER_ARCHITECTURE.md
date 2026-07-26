# RFC 001: Compiler-Linker Architecture & Output Contract

**Status:** APPROVED ARCHITECTURAL SPECIFICATION  
**Scope:** Memory Engine Architecture, `CompiledArtifact` API, Identity System, MemoryPatch Interface  
**Authors:** Systems Engineering Team  

---

## 1. Context & Motivation

The **Project Memory Engine** transforms raw software artifacts (PRs, ADRs, commits, issues) into structured architectural knowledge. 

As the project scales across repositories and years of architectural history, isolating single-artifact extraction from multi-artifact memory persistence is essential. This RFC formalizes the **Compiler/Linker boundary**, the **`CompiledArtifact` output contract**, and the **`MemoryPatch` linker specification**.

---

## 2. The Compiler-Linker Boundary

```
 ┌────────────────────────┐
 │ Source Artifact (Input)│ (PR, ADR, Commit, Issue)
 └───────────┬────────────┘
             │
             ▼
 ┌────────────────────────┐
 │   MemoryCompiler       │ STATALESS COMPILER: Pure function.
 │ (Single Artifact Pass) │ Operates strictly on 1 artifact. No database/memory access.
 └───────────┬────────────┘ Emits CompiledArtifact.
             │
             ▼
 ┌────────────────────────┐
 │   CompiledArtifact     │ TYPED COMPILER OUTPUT: Immutable typed IR unit containing
 │    Output Contract     │ local symbols, observations, statements, claims, facts, relations.
 └───────────┬────────────┘
             │
             ▼
 ┌────────────────────────┐
 │   MemoryPatch Linker   │ STATEFUL LINKER: Unifies local entities to global persistent IDs,
 │ (Cross-Artifact Pass)  │ binds $ARTIFACT_SELF references, computes supersessions & conflicts.
 └───────────┬────────────┘
             │
             ▼
 ┌────────────────────────┐
 │  MemoryDelta Output    │ APPEND-ONLY DELTA: Immutable patch package appended
 │   (Persistent Store)   │ to Persistent Memory. Contains ZERO deletion commands.
 └────────────────────────┘
```

---

## 3. Compiler Invariants

1. **Deterministic Execution**: Compiling the exact same artifact content twice yields equivalent compiler output.
2. **Stateless Isolation**: No compiler pass queries Persistent Memory or repository history.
3. **Representation Separation**: `Statement` (Syntax IR), `Claim` (Epistemic IR), and `Fact` (Ontology IR) remain distinct typed classes.
4. **Hierarchical Document Invariant**: Observations and Segments preserve `section_header` and parent observation IDs so structural context survives compilation.
5. **Evidence vs. Knowledge**: Compiler output is evidence asserted by an artifact; Persistent Memory is consolidated knowledge.

---

## 4. Identity System Specification

Identity operates at two distinct layers:
* **Compiler-Local Identity**: Scoped strictly to one artifact compilation pass. Formatted as local ordinals (`obs:0`, `seg:1`, `stmt:2`). Used for provenance and pass diagnostics.
* **Global Persistent Identity**: Scoped system-wide. Formatted as content-addressed hashes (`deterministic_id(scope, *components)`). Reserved for `Artifact`, `Entity`, and `PersistedFact`.

---

## 5. `MemoryPatch` Linker Contract Specification

Interface signature:
```python
class MemoryPatchLinker(ABC):
    @abstractmethod
    def link(self, reader: MemoryReader, compiled_artifact: CompiledArtifact) -> MemoryDelta:
        """Cross-artifact symbol resolution, deduplication, and supersession linking."""
```

### Linker Invariants
* **Monotonic Append-Only**: MemoryDelta never deletes historical facts. Updates are expressed as explicit `SupersessionEdge(Fact_B, Fact_A)` records.
* **Strict Idempotency**: $\text{link}(M, A) \cup \text{link}(M, A) \equiv \text{link}(M, A)$.
* **Chronological Precedence**: Supersession is governed by source artifact timestamps/version vectors, not linker execution order.
