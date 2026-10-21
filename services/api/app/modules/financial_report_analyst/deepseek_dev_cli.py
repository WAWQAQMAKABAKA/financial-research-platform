"""Explicit one-shot local DeepSeek call; credentials entered in hidden prompt."""
from __future__ import annotations

import argparse
from datetime import datetime
import getpass
from pathlib import Path
from zoneinfo import ZoneInfo

from app.modules.financial_report_analyst import deepseek_draft, revenue_scope


def main() -> int:
    parser = argparse.ArgumentParser(description="One paid DeepSeek development draft (no publication)")
    parser.add_argument("--pdf", type=Path, required=True, help="Original hash-pinned local source PDF")
    parser.add_argument("--live", action="store_true", help="Explicitly authorize one paid API call")
    args = parser.parse_args()
    if not args.live:
        print("STOP: PASS --live TO AUTHORIZE ONE PAID REQUEST")
        return 2
    # Read/verify original disclosure BEFORE prompting for any credential.
    try:
        packet = revenue_scope.build_source_draft(
            revenue_scope.SOURCE, args.pdf,
            as_of=datetime.now(ZoneInfo("Asia/Shanghai")),
        )
    except (OSError, ValueError, RuntimeError):
        print("STOP: SOURCE_UNAVAILABLE")
        return 1
    if packet.get("status") != "SOURCE_DRAFT_READY":
        print("STOP: SOURCE_NOT_QUALIFIED")
        return 1
    key = getpass.getpass("DeepSeek API key (hidden, not stored): ").strip()
    try:
        result = deepseek_draft.draft_verified_cells(packet, api_key=key)
    finally:
        key = ""  # Python cannot guarantee secure memory erasure.
    print("MODEL:", result["model"])
    print("STATUS:", result["status"])
    if result["status"] != "LLM_PROPOSAL_PACKET_MATCHED":
        print("REASON:", result["reason"])
        if "usage" in result:
            print("TOKEN_USAGE:", result["usage"])
        print("RESEARCH_PUBLICATION: BLOCKED")
        return 1
    for claim in result["claims"]:
        print("CLAIM:", claim["claim_id"], claim["text"])
        print("SOURCE_PAGE:", claim["source_page"])
        print("EVIDENCE_ID:", claim["evidence_id"])
        print("CLAIM_VERIFICATION:", claim["verification"])
    print("TOKEN_USAGE:", result["usage"])
    print("FINANCIAL_SEMANTIC_REVIEW: NOT_PERFORMED")
    print("RESEARCH_PUBLICATION: BLOCKED")
    print("M16A_ONE_SHOT_LLM_DRAFT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
