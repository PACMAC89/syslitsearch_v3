# Data extraction codebook (memory-framework review), version 1

Answers come from the full text; the abstract is used only when no full text is available
(`text_source` says which). Every answer gets a source (section, page, table or figure). Fixed categories:
several values are allowed (separated by "; "), each answer has a free-text note on how exactly.
"not stated" = the paper does not say; never guess.

## Q1 Core approach
- **dialogue memory**: memory of conversations and of the user (what was said, facts about the user, preferences)
- **knowledge RAG**: memory over documents or world knowledge that the system builds and maintains (e.g. HippoRAG)
- **procedural**: skills, strategies or experience of how to do tasks
- **mixed**: more than one of the above as equal parts (name them in the note)

## Q2 Memory unit (what one memory entry is)
fact · raw text (turn, message or chunk as written) · note (free-text note written by the system, e.g. A-MEM) ·
triple (subject-predicate-object) · profile (attributes of the user or an entity) · skill · summary ·
event/episode · other

## Q3 Structure (how the entries are organised)
flat store (list or log without index) · vector DB (embedding index) · graph (knowledge graph, linked notes) ·
hierarchical/tiered (levels such as working / short-term / long-term memory, e.g. MemGPT, MemoryOS) ·
key-value/relational DB · files (e.g. markdown files, ByteRover) · other

## Q4 Composition (who decides what is stored and how)
- **keywords/rules**: fixed rules, keyword or pattern matching, heuristics, embedding clustering without an LLM
- **LLM extraction**: a fixed pipeline of LLM prompts (e.g. Mem0: extract, then decide add/update/delete)
- **agent**: the LLM decides itself, via tool or function calls, what to store, change or delete (e.g. MemGPT)

## Q5 Ingestion (when new data goes into memory)
- **real-time per turn**: every turn or message is processed right away
- **batched**: after N turns, at the end of a session or when a buffer is full (give N or the trigger)
- **asynchronous background**: a separate process consolidates later (e.g. "sleep-time" consolidation)
- **combination**: e.g. real-time writes plus background consolidation

## Q6 Short-term / long-term (derived, not judged)
Facts collected: `persistent across sessions` (yes / no / not stated), `manages the context within a session`
(yes / no / not stated), `evaluated on a multi-session benchmark` (yes / no). Rule:
- **both**: persistent across sessions AND manages the context within a session (separate levels)
- **long-term**: persistent across sessions OR evaluated on a multi-session benchmark (LoCoMo, LongMemEval, MSC, ...)
- **short-term**: manages the context within a session and not persistent
- **unclear**: none of the above

## Q7 Update (what happens when stored information changes)
append only · overwrite · invalidate (old entry kept but marked invalid or expired) · version (old and new kept
with time or version) · forget/decay (weight or relevance fades over time) · delete · not stated

## Q8 Contradictions
- `detection`: yes / no / not stated: does the system explicitly detect that new information conflicts with stored information?
- `resolution`: recency wins · LLM decides · keep both with temporal validity · ask the user · confidence or
  evidence weighting · none · not stated · other
- note: how, in the paper's own terms

## Q9 Retrieval
BM25/keyword · ANN/embedding · RRF/hybrid (fusion of several rankings) · graph search (traversal, PageRank, paths) ·
LLM/agentic retrieval (the LLM chooses or queries itself) · reranking · whole memory in context (no retrieval) · other

## Q10-Q12 Benchmarks, metrics, results
- Q10 benchmarks: names as in the paper (LoCoMo, LongMemEval-S, MSC, ...); own new benchmarks marked "(own)".
- Q11 metrics: as in the paper (F1, BLEU-1, LLM-as-judge accuracy "J", Recall@k, latency, tokens, ...).
- Q12 results, one row per number: benchmark, subset or category ("overall" if none), metric, value as printed
  (unit: % or 0-1), system (own / strongest baseline / full-context baseline: the whole history in the prompt),
  backbone LLM, judge model (for LLM-as-judge), source table. Own system: the main results table; baselines:
  the strongest one and the full-context one if reported.

## Q13 Code and paper (start set first)
repo URL · code status: open / partial (parts missing) / closed / none · code version that matches the paper
(release, tag or commit date near the paper) · does the current code still follow the paper (yes / partly / no, how)
