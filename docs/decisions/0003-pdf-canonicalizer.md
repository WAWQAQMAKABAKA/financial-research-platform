# ADR 0003 — Native PDF canonicalization

Date: 2026-10-19
Status: PROPOSED; pending real-document verification

## Source reference

Legacy repository: WAWQAQMAKABAKA/quant-desk
Branch: lab/retrieval-v1
Commit: dadd16e646cddd654be6fa0e024a9189e36bbd7f
File: labs/retrieval_lab/src/retrieval_lab/parsing/pdf_canonicalizer.py
Git blob SHA: c262ff9126aa3ed0745552d9d107c60e7f7c7003

New implementation retains deterministic parsing semantics.
No runtime imports or paths reference the legacy repository.

## Dependency

PyMuPDF==1.28.2

## Source qualification candidate

Document: 600760-2026H1-cninfo-1225517994
Source: CNINFO
Source PDF SHA256:
d53ee98c091fdcbb8df3ebcc3f8d9bef87f61b374615dc3165dadb594f637d99

Historical canonical SHA256:
620d3a30f73423527dd662e21ebf3367b546dfa6795c6fcf618f35ebf0008aa5

## Limitations

Exact text reproduction does not establish financial
semantic correctness, evidence sufficiency, licensing,
redistribution rights, or report publication approval.

Raw PDFs and derived source text stay outside public Git.
