# M130-A: strictly offline retrieval-credibility instrument (development only)

**Boundary:** This is *not* a customer-facing quality score, independent financial
answer GT, or general RAG qualification. This runner does not change runtime
retrieval, agent behavior, prompts, or publication gates. No network, model
inference, trading state, or benchmark GT. The known Hengrui report was used
in M127–M129 development; do not treat it as an unseen holdout.

## Two independent commands

From a verified `financial-research-platform` checkout on the Mac, set
`PYTHONPATH="$PWD/services/api"`. For a *captured baseline*, choose outputs
outside the Git tree. Run commands in this order (example file names; do not
reuse an existing output path):

```zsh
mkdir -p "$HOME/.cache/frp-rag-eval"
PYTHONPATH="$PWD/services/api" .venv/bin/python \
  evaluations/offline/run_rag_retrieval_baseline.py capture \
  --pdf "$HOME/.cache/frp-cn-table-pilot/sources/600276/2026H1/source.pdf" \
  --out "$HOME/.cache/frp-rag-eval/m130_capture_v1.json"
PYTHONPATH="$PWD/services/api" .venv/bin/python \
  evaluations/offline/run_rag_retrieval_baseline.py score \
  --trace "$HOME/.cache/frp-rag-eval/m130_capture_v1.json" \
  --out "$HOME/.cache/frp-rag-eval/m130_score_v1.json"
```

**Capture** reads the *questions only*, the local original PDF and the current
runtime retriever. It verifies document hashes, PIT, canonical offsets, every
retrieved excerpt, publication blocked state, and records Git HEAD plus the
retriever source hash. It stores the original excerpts in a mode-0600 output,
so treat that file as source-document material. It never opens annotation
references and never calls an LLM. Do not commit captured outputs.

**Score** separately reads the captured trace and the
`rag_page_references_dev_v1.json` page list. Those pages are author-curated from
previously inspected development examples, **not independent annotations**.
Page-level Recall@1/3/5 = number of distinct annotated positive pages among
first K retrieved *chunks*, divided by distinct positive pages; duplicate
chunks from one page count once. First-relevant-page rank and MRR are likewise
page-relevance diagnostics. **These metrics do not measure passage-level
sufficiency, statement-value binding, answer completeness or truthfulness.**
Two broader questions are intentionally unannotated and must remain
`NOT_MEASURED` rather than quietly be dropped from the case count.

## What remains to qualify

1. Record an independent annotation protocol, including support for multiple
   valid passages, source scope, accounting period and explicitly unanswerable
   questions. Reviewers must check original PDFs rather than seeing retriever
   output as an oracle.
2. Freeze a separate *unseen*, authorized multi-report evaluation sample before
   tuning chunking/retrieval/reranking. Do not import or inspect protected GT in
   the API, Next app, Analyst, or Reviewer.
3. Run **the same frozen questions** over a lexical baseline and a general
   chunk/semantic-or-hybrid/rerank candidate. Compare recall/first relevant
   rank, costs, and failure cases without issuer-specific answer templates.
4. Separately evaluate model claim faithfulness, support at each citation,
   financial metric/period/scope accuracy, abstention, and answer coverage.
   Independent human financial review remains needed for contested semantics.
5. Preserve `NOT_PERFORMED` semantic review and `BLOCKED` research publication
   regardless of diagnostic scores.
