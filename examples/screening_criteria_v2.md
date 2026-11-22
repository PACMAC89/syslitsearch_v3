# Screening criteria (title + abstract), version 2

Research question of the review: **How do memory frameworks for LLM-based systems handle contradictions**
(conflicting, outdated or inconsistent information) in what they store?

Whether a paper actually handles contradictions is NOT an inclusion criterion; that is checked later in
the full text. The screening only decides whether the paper is a memory framework in the sense below.

**Explicit external memory** = readable entries (text, facts, summaries, records, profiles, graph nodes
and edges, documents in a vector store, files) kept outside the model weights and activations, and
written or updated at run time from interactions or data.

## include
All of the following:
1. The paper proposes, builds or substantially extends a memory system / memory framework.
2. It is for LLM-based conversational agents, assistants, chatbots or dialogue systems, OR it is a
   general-purpose memory framework for LLM agents that stores conversational, user or world knowledge
   (e.g. a "memory OS" or memory layer), OR it is a RAG system that is presented as (long-term) memory.
   General-purpose memory frameworks count here unless the abstract ties them to a non-dialogue
   environment (see "Not dialogue/RAG" below).
3. The memory is an explicit external memory (definition above).
4. The system has its own mechanisms for composing or storing memory, not only retrieval: e.g.
   extracting facts or events, summarising, consolidating, updating, overwriting, deleting/forgetting,
   linking, structuring (knowledge graph, hierarchy, timeline, episodic/semantic stores), reflecting on
   stored conversational/user/world content, memory write policies.
Short-term vs. long-term memory does not matter.

## exclude
The reason MUST start with one of these labels, followed by the concrete point:
- "Retrieval only:" RAG or retrieval work that indexes and retrieves a given corpus without its own
  mechanisms for building, updating or organising memory (better chunking, embeddings, reranking,
  query rewriting over static documents).
- "Hardware:" memory in the hardware/systems sense: DRAM, HBM, SRAM, GPU memory, bandwidth,
  offloading, memory-efficient training or inference, compute-in-memory.
- "In-model memory:" the memory is part of the neural network rather than readable external entries:
  KV-cache storage/compression/reuse, memory tokens, hidden-state or vector memories inside the
  network (e.g. past dialogue sessions encoded as vectors), context-window extension, knowledge editing,
  fine-tuning or adapters that put memories into the weights, and memory banks that belong to the model
  architecture and are filled during training, even if their content is human-readable (e.g. ExplicitLM).
- "Experience/strategy memory:" the memory mainly stores rules, strategies, playbooks, skills, lessons,
  reflections on task performance, or solutions of earlier tasks, so that an agent gets better at tasks
  (e.g. ACE / Agentic Context Engineering, Dynamic Cheatsheet, skill libraries). Reflection or
  summarisation over conversational, user or world content is NOT this case.
- "Not dialogue/RAG:" the memory serves an agent or model in a non-dialogue setting: games (e.g.
  Minecraft), embodied agents and robotics, autonomous driving, web/app/GUI automation, coding and
  software engineering, ML engineering, industrial inspection, scientific or business workflows, video
  or sensor stream understanding.
- "Application:" uses an existing memory framework or plain chat history without its own memory
  mechanism (name the framework or "plain history").
- "Off-topic:" anything else: memory in the psychological/educational sense, security attacks on
  memory, user studies, evaluations of unrelated abilities, planning/tool use without a memory system.
If several labels apply, use the most specific one.

## unsure
- "Survey:" surveys, reviews, position papers or taxonomies on LLM/agent memory.
- "Benchmark:" benchmarks or datasets for evaluating memory, without their own memory framework.
  (A paper that proposes a framework AND a benchmark is judged as a framework.)
- "Unclear:" the abstract does not make clear whether the memory is explicit and external, whether
  the system has its own memory mechanism, or whether it serves a dialogue/RAG setting.

## Papers without abstract
Judge by the title alone; the reason starts with "Title only:". Use exclude only when the title clearly
falls under an exclude rule (then: "Title only: <label> ..."), otherwise unsure.

## Output per paper (one JSON object per line)
{"id": "<id>", "verdict": "include" | "exclude" | "unsure", "reason": "<max. 25 words, English>", "conflicts": true | false}

- reason: always the concrete deciding point; for exclude and unsure it starts with the label above.
  Examples: "Graph memory with fact extraction and update operations for chat agents." /
  "Hardware: HBM bandwidth for LLM inference." / "Experience/strategy memory: evolving playbook of task
  strategies learned from execution feedback."
- conflicts: true only if the abstract explicitly mentions handling conflicting, contradictory, outdated
  or changing information in memory (conflict resolution, updates/overwrites of facts, temporal validity,
  forgetting outdated facts, consistency checks); otherwise false.
