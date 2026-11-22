# Screening criteria (title + abstract), version 3

Research question of the review: **How do memory frameworks for LLM-based systems handle contradictions**
(conflicting, outdated or inconsistent information) in what they store?

Use case: an **open-domain conversational chatbot** that one can talk with about anything. The memory system
should work with any such chatbot; it is not a memory for one task, domain or goal.

Whether a paper actually handles contradictions is NOT an inclusion criterion; that is checked later in
the full text. The screening only decides whether the paper is a memory framework in the sense below.

**Explicit external memory** = readable entries (text, facts, summaries, records, profiles, graph nodes
and edges, documents in a vector store, files) kept outside the model weights and activations, and
written or updated at run time from interactions or data.

Changes from version 2 (from the manual revision of the 2026-10-12 screening): new exclude labels "Full
system", "Not my use case", "RL", "Training", "Visual", "Too general survey", "Not a paper" and "Not in
English"; new unsure label "Role-play"; include reasons may start with "Domain-specific".

## include
All of the following:
1. The paper proposes, builds or substantially extends a memory system / memory framework, and the memory
   is the main contribution (not one building block of a larger system, see "Full system").
2. It is for LLM-based conversational agents, assistants, chatbots or dialogue systems, OR it is a
   general-purpose memory framework for LLM agents that stores conversational, user or world knowledge
   (e.g. a "memory OS" or memory layer), OR it is a RAG system that is presented as (long-term) memory.
   General-purpose memory frameworks count here unless the abstract ties them to a non-dialogue
   environment (see "Not dialogue/RAG") or to one task or domain (see "Not my use case").
3. The memory is an explicit external memory (definition above) and works on text.
4. The system has its own mechanisms for composing or storing memory, not only retrieval: e.g.
   extracting facts or events, summarising, consolidating, updating, overwriting, deleting/forgetting,
   linking, structuring (knowledge graph, hierarchy, timeline, episodic/semantic stores), reflecting on
   stored conversational/user/world content, memory write policies.
5. It can be put onto an existing chatbot without training or fine-tuning the LLM (see "Training", "RL").
Short-term vs. long-term memory does not matter.

A paper evaluated in one domain (e.g. health, manufacturing, knowledge management) is include if its memory
mechanism itself is general and could serve any chatbot; its reason then starts with "Domain-specific:".
Multimodal frameworks whose memory also covers text conversations and that are evaluated on text dialogue
benchmarks (e.g. LoCoMo, LongMemEval) are include as well; see "Visual" for the others.

## exclude
The reason MUST start with one of these labels, followed by the concrete point:
- "Retrieval only:" RAG or retrieval work that indexes and retrieves a given corpus without its own
  mechanisms for building, updating or organising memory (better chunking, embeddings, reranking,
  query rewriting over static documents, conversational question answering over documents).
- "Hardware:" memory in the hardware/systems sense: DRAM, HBM, SRAM, GPU memory, bandwidth,
  offloading, memory-efficient training or inference, compute-in-memory, LLM serving.
- "In-model memory:" the memory is part of the neural network rather than readable external entries:
  KV-cache storage/compression/reuse, memory tokens, hidden-state or vector memories inside the
  network (e.g. past dialogue sessions encoded as vectors), context-window extension, knowledge editing,
  fine-tuning or adapters that put memories into the weights, and memory banks that belong to the model
  architecture and are filled during training, even if their content is human-readable (e.g. ExplicitLM).
- "Training:" the approach needs training or fine-tuning of the LLM or of a dedicated dialogue model, so it
  cannot be put onto an existing chatbot (e.g. a trained speaker-state model). Trained small helpers next to
  an unchanged LLM (a retriever, a scorer) do not count as Training.
- "RL:" memory construction or memory management learned with reinforcement learning (a policy trained by
  reward). Excluded, but counted: say what is learned.
- "Experience/strategy memory:" the memory mainly stores rules, strategies, playbooks, skills, lessons,
  reflections on task performance, thought templates, or solutions of earlier tasks, so that an agent gets
  better at tasks (e.g. ACE / Agentic Context Engineering, Dynamic Cheatsheet, skill libraries).
  Reflection or summarisation over conversational, user or world content is NOT this case.
- "Full system:" a complete LLM application, assistant, robot or multi-agent pipeline in which memory is only
  one building block next to others (perception, planning, tools, emotion modules, safety layers) and not the
  main contribution (e.g. an empathetic-dialogue pipeline with a memory stage, a customer-support assistant,
  a "unified agentic framework integrating memory, learning, reasoning").
- "Not my use case:" the memory is built for one goal-directed task or domain application instead of open
  conversation: recommender systems, tutoring and coaching, customer service and task-oriented dialogue
  (booking, slot filling), classification or decision support in one domain, emotional-support or
  personality modelling, service composition, game NPCs. (A general memory merely evaluated in a domain is
  include, "Domain-specific".)
- "Not dialogue/RAG:" the memory serves an agent or model in a non-dialogue setting: games (e.g.
  Minecraft), embodied agents and robotics, autonomous driving, web/app/GUI automation, coding and
  software engineering, ML engineering, industrial inspection, scientific or business workflows, video
  or sensor stream understanding.
- "Visual:" the memory stores or relies on images, video, audio or other non-text modalities, or targets
  vision/multimodal models, and it is not also a text conversation memory evaluated on text dialogue.
- "Application:" uses an existing memory framework or plain chat history without its own memory
  mechanism (name the framework or "plain history").
- "Too general survey:" surveys, reviews or taxonomies whose scope is broader than LLM memory (LLM agents,
  multi-agent systems, LLM systems, world models in general), with memory as one topic among many.
- "Not a paper:" a whole proceedings volume, front matter, an index, or an entry without a paper behind it.
- "Not in English:" title or abstract are not in English, or the abstract says the paper is not in English.
- "Off-topic:" anything else: memory in the psychological/educational sense, security attacks on
  memory, governance and ethics analyses, user studies, evaluations of unrelated abilities,
  planning/tool use without a memory system.
If several labels apply, use the most specific one.

## unsure
- "Survey:" surveys, reviews, position papers or taxonomies specifically on LLM/agent memory.
- "Benchmark:" benchmarks or datasets for evaluating memory, without their own memory framework.
  (A paper that proposes a framework AND a benchmark is judged as a framework.)
- "Role-play:" memory for role-playing agents or characters. Say where the memory comes from: from the
  ongoing conversation with the user, or from source material such as novels or character sheets.
- "Unclear:" the abstract does not make clear whether the memory is explicit and external, whether
  the system has its own memory mechanism, whether memory is the main contribution, or whether it
  serves open conversation.

## Papers without abstract
Judge by the title alone; the reason starts with "Title only:". Use exclude only when the title clearly
falls under an exclude rule (then: "Title only: <label> ..."), otherwise unsure.

## Output per paper (one JSON object per line)
{"id": "<id>", "verdict": "include" | "exclude" | "unsure", "reason": "<max. 25 words, English>", "conflicts": true | false}

- reason: always the concrete deciding point; for exclude and unsure it starts with the label above, for
  include it may start with "Domain-specific:".
  Examples: "Graph memory with fact extraction and update operations for chat agents." /
  "Full system: companion robot architecture; memory is one of five modules." / "Not my use case:
  memory of user preferences for movie recommendation." / "RL: memory write policy trained with PPO."
- conflicts: true only if the abstract explicitly mentions handling conflicting, contradictory, outdated
  or changing information in memory (conflict resolution, updates/overwrites of facts, temporal validity,
  forgetting outdated facts, consistency checks); otherwise false.
