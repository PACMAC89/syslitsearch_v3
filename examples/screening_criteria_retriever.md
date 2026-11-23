Research question

Which retrieval strategies are proposed, applied, compared, or optimized in Retrieval-Augmented Generation (RAG) systems, and what empirical evidence exists regarding their effects on retrieval quality, answer quality, efficiency, robustness, and computational cost?

The review aims to identify, categorize, and evaluate retrieval approaches used in RAG pipelines, including their design principles, implementation characteristics, evaluation methods, and reported performance.

Use case and scope

The primary use case is a text-based Retrieval-Augmented Generation (RAG) system that retrieves information from an external knowledge source and supplies the retrieved context to a large language model (LLM) for answer generation.

The review focuses on the retrieval component responsible for identifying, selecting, and retrieving relevant information from external document collections, databases, knowledge bases, or other retrievable information sources.

The review is method-oriented rather than domain-specific. Studies conducted in medicine, law, education, finance, engineering, or other domains are eligible if they investigate a retrieval strategy in a RAG context.

Relevant approaches include, but are not limited to:

Sparse retrieval (e.g., BM25, TF-IDF, lexical retrieval)

Dense retrieval (embedding-based or vector retrieval)

Hybrid retrieval (combinations of sparse and dense retrieval)

Semantic retrieval

Multi-stage retrieval and candidate generation

Adaptive or dynamic retrieval

Iterative or multi-hop retrieval

Agentic retrieval and retrieval planning

Graph-based retrieval and knowledge graph retrieval

Hierarchical retrieval

Metadata-aware or filter-based retrieval

Query-aware and context-aware retrieval

Query rewriting, expansion, decomposition, and reformulation when explicitly investigated as retrieval strategies

Retrieval routing and source selection

Retrieval fusion and ensemble retrieval

Retrieval depth and top-k optimization

Retrieval confidence estimation and selective retrieval

Retrieval strategies for structured and semi-structured documents

Retrieval optimization under latency, token-budget, or computational constraints

These examples are illustrative, not exhaustive. Novel approaches should be considered if they satisfy the inclusion criteria.

The study does not need to introduce a novel retrieval algorithm. Empirical comparisons, ablation studies, and optimization experiments involving existing retrieval strategies are equally relevant.

Definition: Retrieval in RAG

Retrieval refers to the process of identifying and obtaining relevant information from an external knowledge source in response to a user query, task, or intermediate reasoning state, with the retrieved information subsequently used to support generation by a language model.

Retrieval may involve:

Selecting a retrieval algorithm or search strategy

Representing and matching queries and documents

Identifying relevant candidate documents or passages

Combining multiple retrieval methods

Determining which knowledge sources to search

Selecting retrieval depth or the number of retrieved candidates

Performing iterative or multi-step retrieval

Using metadata, semantic constraints, or structured relationships

Adapting retrieval behavior to query complexity or available context

Balancing retrieval effectiveness against computational cost

Retrieval must be distinguishable as a technical component of the RAG pipeline.

Important distinction: Information retrieval, search engines, or document matching without an identifiable retrieval-grounded generative system are not sufficient for inclusion.

Screening principle

The screening is based only on the title and abstract.

A paper should be included when the available information provides sufficient evidence that it investigates a retrieval strategy in a RAG system.

A paper does NOT need to demonstrate that its retrieval strategy improves performance. Positive, negative, and inconclusive experimental results are equally relevant.

The screening does NOT determine which retrieval strategy is best.

Detailed extraction of retrieval algorithms, datasets, embedding models, retrieval parameters, evaluation metrics, statistical results, and implementation details occurs during the full-text phase.

When the abstract is insufficient to determine whether retrieval is substantively investigated, use "unsure" rather than excluding a potentially relevant study.

include

All of the following conditions must be satisfied:

RAG context: The paper explicitly investigates a Retrieval-Augmented Generation system or an equivalent retrieval-grounded generative architecture in which retrieved external information is supplied to a generative language model.

Retrieval relevance: The paper proposes, implements, modifies, compares, evaluates, or optimizes at least one retrieval strategy, retrieval algorithm, or retrieval configuration.

Substantive contribution: Retrieval is a meaningful methodological or experimental component of the study, not merely an incidental implementation detail. A study qualifies if retrieval is a primary contribution OR if its effect is explicitly evaluated as part of a broader RAG study.

Research contribution: The paper provides a technical method, empirical investigation, experimental comparison, ablation study, or systematic analysis that can contribute evidence about retrieval decisions in RAG.

Text relevance: The approach applies to textual information or documents containing retrievable textual content, including PDFs, tables, structured documents, and text-based knowledge graphs.

The following studies should be included:

Papers proposing new retrieval algorithms or retrieval architectures for RAG.

Papers comparing sparse, dense, semantic, hybrid, graph-based, or other retrieval strategies.

Papers evaluating retrieval depth, top-k selection, candidate pool size, or retrieval thresholds.

Papers studying the influence of retrieval strategies on precision, recall, MRR, nDCG, answer correctness, faithfulness, latency, or computational cost.

Papers investigating adaptive, iterative, multi-hop, or agentic retrieval.

Papers comparing retrieval jointly with embeddings, rerankers, chunking, or LLMs, provided retrieval is independently varied or explicitly analyzed.

Papers proposing retrieval routing, source selection, metadata filtering, or retrieval fusion strategies.

Papers investigating query rewriting, expansion, decomposition, or reformulation when these are explicitly connected to retrieval effectiveness in RAG.

Papers studying graph-based retrieval, knowledge graph traversal, or hybrid graph-vector retrieval for RAG.

Papers evaluating retrieval strategies in domain-specific RAG systems, provided the retrieval method and its effects are sufficiently described.

Papers studying retrieval efficiency, robustness, scalability, or computational trade-offs in RAG.

Training or fine-tuning of an auxiliary retrieval model does not automatically exclude a paper. However, the trained model must be applicable to a retrieval-grounded generative pipeline.

Studies focused exclusively on retraining or fine-tuning the generative LLM, without a substantive retrieval contribution, are excluded.

exclude

The reason MUST start with one of these labels, followed by the concrete deciding point:

"Not RAG:" The study concerns information retrieval, search engines, document ranking, semantic search, or NLP without an identifiable retrieval-augmented generative system.

"No retrieval contribution:" The study investigates RAG but does not meaningfully propose, compare, evaluate, or optimize retrieval. Retrieval is absent or used only as an incidental standard component.

"Chunking only:" The study focuses exclusively on document segmentation, chunk size, chunk overlap, or chunk boundary optimization without investigating a retrieval strategy or retrieval configuration.

"Reranking only:" The study exclusively proposes or evaluates a post-retrieval reranking method without substantively investigating candidate retrieval or a broader retrieval strategy.

"Embedding only:" The study focuses exclusively on embedding model development or representation learning without an identifiable evaluation or optimization of retrieval behavior in RAG.

"Generation only:" The study focuses on prompting, LLM selection, answer generation, hallucination reduction, or output evaluation without examining retrieval.

"Training only:" The study focuses on training, fine-tuning, reinforcement learning, or modifying the generative LLM without a relevant retrieval contribution.

"Unrelated retrieval:" Retrieval refers to memory access, database operations, image retrieval, software retrieval, or other information-access tasks without an identifiable RAG architecture.

"Multimodal only:" The approach exclusively retrieves images, video, audio, or sensor data and does not investigate retrievable textual or document content.

"Application only:" The paper describes a domain-specific RAG application that merely uses an existing retrieval method without evaluating or contributing to retrieval.

"Hardware:" The study concerns GPU architecture, hardware acceleration, storage infrastructure, or networking without a relevant RAG retrieval investigation.

"Not peer-reviewed:" The available metadata explicitly identifies the work as a preprint or other non-peer-reviewed publication, with no evidence of an accepted peer-reviewed version. An arXiv copy of an accepted or published peer-reviewed paper is not excluded solely because it is hosted on arXiv.

"Not a paper:" The record is an editorial, conference front matter, table of contents, presentation, promotional material, or another item without an identifiable scientific paper.

"Not in English:" The title, abstract, or publication metadata clearly indicates that the paper is not available in English.

"Off-topic:" The study is unrelated to RAG retrieval and does not fit a more specific exclusion category.

If several labels apply, use the most specific one.

unsure

The reason MUST start with one of these labels, followed by the concrete uncertainty:

"Survey:" A survey, systematic review, taxonomy, or position paper substantially discusses retrieval in RAG but does not provide an original retrieval method or empirical evaluation. Retain for full-text inspection and backward citation searching.

"Benchmark:" A benchmark or evaluation dataset for RAG includes retrieval-related evaluation, but the abstract does not establish whether retrieval strategies are independently compared or analyzed.

"Unclear retrieval:" The paper mentions retrieval, search, indexing, or candidate selection, but the abstract does not clarify whether retrieval is substantively investigated.

"Unclear RAG:" The paper investigates retrieval or search-supported language models, but the abstract does not establish whether the architecture meets the RAG definition.

"Unclear component boundary:" The paper investigates embeddings, reranking, chunking, or query processing, but the abstract does not establish whether the contribution concerns retrieval strategy optimization.

"Unclear publication status:" The paper appears technically relevant, but the title and abstract do not establish whether it has undergone peer review.

"Unclear:" The abstract provides insufficient information to determine whether the inclusion criteria are satisfied.

Do not classify a study as "exclude" merely because it reports no improvement or because retrieval is not its only experimental variable.

Papers without abstract

Judge by the title alone.

The reason MUST start with "Title only:".

Use "exclude" only if the title clearly establishes an exclusion criterion.

Otherwise, use "unsure".

Examples:

"Title only: Unclear: retrieval contribution cannot be established."

"Title only: Not RAG: evaluates traditional information retrieval without generation."

"Title only: Unclear publication status: peer review cannot be verified."

Output per paper (one JSON object per line)

{"id": "<id>", "verdict": "include" | "exclude" | "unsure", "reason": "<max. 25 words, English>", "conflicts": true | false}

Rules:

Preserve the exact JSON keys: id, verdict, reason, conflicts.

Return exactly one JSON object per paper.

Do not add extra fields.

The reason must identify the concrete deciding point.

For "exclude" and "unsure", the reason must begin with one of the specified labels.

For "include", the reason should briefly identify the retrieval contribution.

Use English for every reason.

Interpretation of the conflicts field

The field name "conflicts" is retained solely for compatibility with the existing screening tool.

For this review, reinterpret it as a retrieval evaluation indicator:

true: The title or abstract explicitly indicates an empirical evaluation, comparison, ablation, or optimization of retrieval strategies or retrieval parameters in a RAG system.

false: No such explicit empirical investigation is established from the title and abstract.

This field is independent of the screening verdict.

Examples:

A hybrid retrieval method compared against sparse and dense retrieval baselines: "conflicts": true.

A conceptual agentic retrieval framework without explicit empirical evaluation: "conflicts": false.

A RAG application that only mentions using vector retrieval: "conflicts": false.

The field must not be interpreted as evidence of contradictory information or memory conflicts.

Examples

{"id": "P001", "verdict": "include", "reason": "Compares sparse, dense, and hybrid retrieval strategies across RAG configurations.", "conflicts": true}
{"id": "P002", "verdict": "include", "reason": "Introduces an adaptive retrieval architecture for retrieval-augmented question answering.", "conflicts": false}
{"id": "P003", "verdict": "include", "reason": "Evaluates iterative retrieval and query reformulation for multi-hop RAG questions.", "conflicts": true}
{"id": "P004", "verdict": "exclude", "reason": "No retrieval contribution: RAG system uses standard vector retrieval without investigating retrieval behavior.", "conflicts": false}
{"id": "P005", "verdict": "exclude", "reason": "Not RAG: compares sparse and dense search methods for traditional document retrieval.", "conflicts": true}
{"id": "P006", "verdict": "exclude", "reason": "Chunking only: evaluates document segmentation strategies without independently investigating retrieval methods.", "conflicts": false}
{"id": "P007", "verdict": "unsure", "reason": "Survey: reviews retrieval optimization strategies in RAG systems.", "conflicts": false}
{"id": "P008", "verdict": "unsure", "reason": "Unclear retrieval: RAG performance is evaluated, but the abstract does not specify whether retrieval strategies are compared.", "conflicts": false}
{"id": "P009", "verdict": "unsure", "reason": "Unclear publication status: relevant retrieval comparison but peer review cannot be verified.", "conflicts": true}