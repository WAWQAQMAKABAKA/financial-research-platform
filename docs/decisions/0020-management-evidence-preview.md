# 0020 — Management-explanation evidence preview (M5 v1)

Date: 2026-11-05
Status: accepted for M5 v1 (single document 600760, management discussion section)

## Context

Users ask why a figure moved ("净利润为什么下降"). Until now such questions fell
into the generic `AMBIGUOUS` intent and were withheld with no source pointer. The
platform has no qualified semantic reviewer, and the publication contract forbids
publishing management explanations without one.

## Decision

A new deterministic intent class, `MANAGEMENT_EXPLANATION`, is recognized from
explanation cues (为什么/为何/原因/解释/说明/管理层讨论/经营讨论/变动原因/什么原因/
如何解释/怎么解释). Forward-view cues still win first, then explanation cues, then
comparison, then ambiguity.

`build_management_report` returns a **withheld evidence preview**:

- manifest identity, PDF bytes, PIT and canonical binding are verified by the
  existing retrieval path;
- the management discussion section is located deterministically from the page
  headings (`管理层讨论与分析` up to the next `第…节`), so cover pages, governance
  and incentive tables are not offered as explanations;
- question metric grams drop explanation stopwords, generic time/company grams
  and digit-only grams, so `半年`, `年度` or `公司` cannot pull in unrelated prose;
- the **first line** of a candidate must itself contain both a metric gram and an
  explanation cue; a line without ending punctuation is joined with its next line
  only when that next line is prose, and checkbox/number-only lines are skipped;
- candidates are scored (metric hits, cue hits, an explanation-marker bonus for
  `变动原因`/`主要是`/`主要系`/`原因说明`, a small digit penalty), de-duplicated and
  capped at three pointers;
- each pointer carries a page number, a verbatim page-text excerpt (the literal
  reviewer scope is `VERIFIED_PAGE_TEXT_SUBSTRING`) and an explicit
  `explanation_cue_present` flag;
- the report is `REPORT_WITHHELD` with reason
  `MANAGEMENT_EXPLANATION_REQUIRES_SEMANTIC_REVIEW`, no facts, no claims, no
  review records and `semantic_review = NOT_PERFORMED`;
- the page renders the pointers under "原文摘录预览 · 未发布 · 语义审阅未执行".

If the section exists but no line matches, the report is withheld with
`NO_MANAGEMENT_EVIDENCE`; it never falls back to unrelated pages.

## Mixed question (v1.1)

A question can contain both kinds of sentence, e.g.
"营业收入是多少？管理层为什么说利润下降？". The builder splits on `？?。；;` and
newlines, classifies each sentence, and:

- publishes the fact sentence through the normal multi/single path (facts,
  literal review, `FACTS_ONLY` policy);
- attaches the management sentence as a withheld preview
  (`PREVIEW_ONLY_NOT_PUBLISHED`, `semantic_review = NOT_PERFORMED`);
- returns `FACTS_WITH_MANAGEMENT_PREVIEW_REPORT` with
  `management_publication.may_publish = false`;
- returns `None` when either part is missing or the fact part cannot publish, so
  the management-only preview path is used instead.

The published decision covers only the fact claims; the preview never enters the
policy's claims.

## Why not publish

The publication policy admits only `OBSERVED_FACT` claims under `FACTS_ONLY`.
Management explanations require a qualified semantic review, which this platform
does not implement. The preview is source localization, not a conclusion: it
does not answer the question, does not compare periods and does not state a cause.

## Limits

- Lexical preview only; a section that does not mention the metric yields
  `NO_MANAGEMENT_EVIDENCE`.
- Up to three pointers; no cross-page assembly, no paraphrase, no numbers.
- The model is not involved; no semantic review is claimed.
- The preview text is source content and must not be reused as a claim.

## Next

A semantic-review contract (reviewer identity, rubric, evidence standard) is a
prerequisite for any published management explanation. Until then this path stays
withheld.
