#!/usr/bin/env python3
"""Offline corpus provisioning gate.

Verifies that every declared document is actually provisioned and that its
bytes — not its filename — match the tracked manifest. No network access and
no PDF is ever written into the repository by this script.

    python scripts/verify_corpus.py                 # all declared documents
    python scripts/verify_corpus.py --canonical     # also re-derive canonical hash
    python scripts/verify_corpus.py --document 600760-2026H1 --pdf /path/to.pdf

Exit code 0 means every selected document is provisioned and verified.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "services/api"))

from app.evidence import corpus_manifest  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify the authorized corpus.")
    parser.add_argument("--document", help="document_id or report key (ticker-period)")
    parser.add_argument("--pdf", help="operator-supplied PDF path for one document")
    parser.add_argument("--canonical", action="store_true",
                        help="also re-derive the canonical text hash and page count")
    args = parser.parse_args(argv)

    manifest = corpus_manifest.load_corpus_manifest()
    if args.document is None:
        documents = list(manifest.documents)
    elif args.pdf and args.document in manifest.document_ids:
        documents = [manifest.require(args.document)]
    else:
        documents = [manifest.require_report_key(args.document)]

    failures = 0
    for document in documents:
        label = corpus_manifest.report_key_of(document)
        try:
            corpus_manifest.verify_document(
                document,
                pdf_path=Path(args.pdf) if args.pdf else None,
                verify_canonical=args.canonical,
            )
        except corpus_manifest.CorpusManifestError as exc:
            failures += 1
            print(f"FAIL {label} {exc.code}: {exc}")
            continue
        print(f"OK   {label} source={document.source_sha256[:16]}… "
              f"canonical={document.canonical_sha256[:16]}…"
              + (" (canonical re-derived)" if args.canonical else ""))

    print(f"\n{len(documents) - failures}/{len(documents)} declared document(s) verified.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
