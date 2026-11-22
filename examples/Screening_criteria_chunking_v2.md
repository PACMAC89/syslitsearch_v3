Screening principle

The screening process distinguishes between two independent dimensions:

Topical eligibility: Whether the study substantively investigates chunking strategies in a Retrieval-Augmented Generation (RAG) system.

Publication eligibility: Whether the study has been published as a peer-reviewed journal article or a peer-reviewed conference paper.

These dimensions must not be conflated.

The LLM-based title and abstract screening primarily evaluates topical eligibility. Publication eligibility must be verified separately using reliable bibliographic metadata or publisher records.

A paper may be topically relevant but ineligible for the final systematic review because its peer-reviewed publication status cannot be established.

A paper must not be considered peer-reviewed merely because it is indexed by Semantic Scholar, Scopus, IEEE Xplore, or another scholarly database.

The presence of a DOI, citations, a PDF, or an arXiv record does not constitute proof of peer review.

Topical screening

The topical screening is based on the title and abstract.

A paper should receive "include" when the available information provides sufficient evidence that it substantively investigates chunking in a RAG system.

A paper does NOT need to demonstrate improved performance. Positive, negative, and inconclusive findings are equally relevant.

When the abstract does not provide sufficient information to establish substantive chunking relevance, use "unsure".

Do not reject an otherwise relevant study solely because its publication status is unknown.

Publication eligibility

Only the following publication types are eligible for the final evidence synthesis:

Peer-reviewed journal articles

Full research papers published in peer-reviewed conference proceedings

The following publication types are not eligible unless a corresponding peer-reviewed version can be verified:

arXiv-only preprints

Other non-peer-reviewed preprints

Working papers

Unreviewed technical reports

Posters, presentation abstracts, and conference front matter

Editorials and other non-research publications

An arXiv version of a peer-reviewed paper is not automatically excluded. When a corresponding peer-reviewed version exists, use the published or accepted peer-reviewed version.

A journal or conference name alone is not always sufficient evidence of peer review. Publication type and review status must be verified.

Publication-status verification

For each topically relevant paper, independently verify:

Publication venue

Publication type

DOI and publisher record, where available

Whether the specific work underwent peer review

Whether a preprint has a corresponding peer-reviewed version

Assign one of the following publication-status classifications:

verified_peer_reviewed: A qualifying peer-reviewed publication has been verified.

verified_preprint_only: Only a non-peer-reviewed preprint has been identified after verification.

unverified: Available evidence is insufficient to establish publication eligibility.

A missing publication record must not be interpreted as definitive evidence that a paper has never been peer-reviewed.

Record the source used for verification and the date of the check.

Final inclusion decision

A paper is eligible for final inclusion only when:

Its topical screening decision is "include", or its initial "unsure" decision has been resolved positively through further inspection.

Its publication status is "verified_peer_reviewed".

Its full text satisfies the substantive inclusion criteria.

A paper with "verified_preprint_only" status is excluded from the final evidence synthesis under the predefined publication criteria.

A paper with "unverified" publication status remains pending until its status is resolved.

Preprints may be retained in a separate supplementary reading list for identifying emerging methods, discovering related work, and backward or forward citation searching.

LLM screening output compatibility

The existing screening tool requires the following JSON structure:

{"id": "<id>", "verdict": "include", "reason": "<max. 25 words, English>", "conflicts": false}

Preserve the exact JSON keys:

id

verdict

reason

conflicts

Do not add publication-status fields to this JSON output.

The "verdict" field represents topical eligibility at the title-and-abstract screening stage.

The "conflicts" field retains its existing interpretation as an indicator of explicit empirical chunking evaluation.

Publication-status verification must be stored in a separate screening or validation dataset.

Do not claim that publication status has been verified unless independent bibliographic evidence has actually been checked.

Examples

Example 1: Relevant arXiv-only preprint

Title and abstract describe a systematic comparison of semantic, fixed-size, and hierarchical chunking methods in RAG.

Topical screening: include

Publication verification: verified_preprint_only, if no peer-reviewed version is identified after verification.

Final decision: exclude from the peer-reviewed evidence synthesis.

Example 2: Relevant peer-reviewed conference paper

Title and abstract describe an empirical comparison of chunking strategies in RAG.

Topical screening: include

Publication verification: verified_peer_reviewed.

Final decision: eligible for full-text screening.

Example 3: Relevant paper with unclear publication status

Title and abstract describe a new structure-aware chunking method for RAG.

Topical screening: include

Publication verification: unverified.

Final decision: pending publication verification.

Example 4: Peer-reviewed paper without a chunking contribution

The paper evaluates a RAG chatbot using fixed-size chunks but does not investigate the chunking strategy.

Topical screening: exclude

Publication verification: verified_peer_reviewed.

Final decision: exclude because the study does not meet the substantive inclusion criteria.