# Screening criteria (title + abstract), version 3
Research question of the review: Which tuning knobs ("Stellschrauben") do RAG systems have, and how well is their optimisation covered in the literature?

Use case behind the question: a domain-specific question-answering chatbot over a document collection (load documents, chunk, enrich chunks, index, retrieve, generate), whose pipeline should evaluate and improve itself while the LLM stays frozen (no training or fine-tuning of the generator).

Whether a paper reaches good results, and which metric it uses, is NOT an inclusion criterion; that is extracted later from the full text. The screening only decides whether the paper deals with the optimisation of a RAG knob in the sense below. The publication venue is not judged here (peer-review filtering is done in the report beforehand).

RAG system = a system in which an LLM generates answers using content retrieved at run time from an external store (documents, passages, knowledge graph, memory entries).

Knob = any element of a RAG pipeline that can be set, chosen, tuned or adapted without changing the weights of the generating LLM:

P1 context and data: parsing, chunking (size, strategy, semantic/agentic chunking), chunk enrichment (summaries, metadata, generated questions e.g. HyPE), indexing structure (vector, hybrid, graph, hierarchical), knowledge graph construction, long-term memory of the system.
P2 retrieval: embedding model choice, top-k and thresholds, hybrid search and fusion, query rewriting or expansion, reranking, context compression and selection.
P3 self-diagnosis and evaluation: automatic evaluation of retrieval and answers, failure detection, feedback signals used to adjust the pipeline.
P4 orchestration: prompts, tool descriptions, rules, routing, planning, iterative or agentic retrieval workflows, stopping and cost control.


## include

All of the following:

The paper proposes, studies or substantially extends a method for choosing, tuning, adapting or automatically optimising at least one knob (definition above), or for the self-evaluation or self-improvement of a RAG pipeline. A systematic comparison of settings of a knob counts as studying it.
The system is a RAG system (definition above); general-purpose or domain-specific both count.
The approach works on an existing LLM without training or fine-tuning it. Trained small helpers next to an unchanged LLM (a retriever, a reranker, a scorer, a router) do not count as Training.
The knob is the main subject of the paper, not a side remark in an application or a system description. Linear and agentic RAG both count. Text is the main modality.

Include reasons name the knob first, e.g. "Chunking: LLM decides chunk boundaries per document."

## exclude

The reason MUST start with one of these labels, followed by the concrete point:

"Application:" uses RAG with a fixed configuration for a domain or task (case study, tool, chatbot built with standard RAG) without studying or optimising a knob.
"Not RAG:" no external retrieval at generation time: pure LLM prompting, long-context only, in-model memory (KV cache, memory tokens), knowledge editing, or classical search/IR without an LLM generating the answer.
"Training:" the approach needs training or fine-tuning of the generating LLM (including reinforcement learning of the generator). Excluded, but counted: say which knob is addressed and what is trained.
"Hardware:" systems view: GPU memory, serving, latency engineering, caching of model states, cost of inference hardware.
"Visual:" the approach targets images, video, audio or other non-text modalities as its main content.
"Too general survey:" surveys or taxonomies of LLMs, agents or NLP in general, with RAG as one topic among many.
"Not a paper:" a whole proceedings volume, front matter, an index, or an entry without a paper behind it.
"Not in English:" title or abstract are not in English, or the abstract says the paper is not in English.
"Off-topic:" anything else: security or privacy attacks on RAG, governance and ethics analyses, user studies, evaluations of unrelated abilities, LLM use without retrieval. If several labels apply, use the most specific one.

## unsure

"Survey:" surveys, reviews, position papers or taxonomies specifically on RAG or on parts of the RAG pipeline.
"Benchmark:" benchmarks, datasets or evaluation frameworks for RAG, without their own optimisation method. (A paper that proposes a method AND a benchmark is judged as a method.)
"Metric:" papers mainly about how to measure a RAG component or the whole pipeline (retrieval or answer quality, faithfulness), with or without an LLM as judge. Kept for the review of optimisation metrics.
"Unclear:" the abstract does not make clear whether a knob is the main subject, whether the system is a RAG system, or whether the LLM is trained.


## Papers without abstract

Judge by the title alone; the reason starts with "Title only:". Use exclude only when the title clearly falls under an exclude rule (then: "Title only: <label> ..."), otherwise unsure.

## Output per paper (one JSON object per line)

{"id": "<id>", "verdict": "include" | "exclude" | "unsure", "reason": "<max. 25 words, English>", "conflicts": true | false}

reason: always the concrete deciding point; for exclude and unsure it starts with the label above, for include with the knob. Examples: "Chunking: LLM-guided chunk boundaries improve retrieval on domain documents." / "Application: standard RAG chatbot for a hospital, no pipeline component studied." / "Training: fine-tunes the generator to use retrieved passages." / "Metric: proposes LLM-judge metric for faithfulness of RAG answers."
conflicts: in this review the key name is kept for the tool, but the meaning is "self-improving". True only if the abstract explicitly says that the pipeline adjusts a knob automatically at run time or across iterations (feedback-driven, LLM-driven, self-evaluating, self-evolving, adaptive, auto-tuned); otherwise false.

