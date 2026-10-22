# M1.9A strictly offline development evaluation

This is a **versioned synthetic development challenge set**, NOT a protected
benchmark, NOT independent real-document semantic ground truth, and NOT a
customer-facing score. Only offline evaluation code reads the labelled corpus.
Nothing in the backend or Next.js imports this directory. No LLM, API, network,
secrets, trades, or model inference occur. Never move labels into runtime.

Two deliberately incorrect synthetic narrative claims (`S13`, `S14`) are
labelled `REJECT` by construction. The current defensive screen examines
structured value/source associations, **not the free-form claim meaning**, so
its actual `UNCERTAIN` outcome records missed contradictions. This is a
capability gap, **not unsafe ADMIT**: publication remains blocked. Do not
change labels or tests merely to erase failures. `PIT_AVAILABLE` means only
that source access is date-permitted, never a financial admit.

For Mac development, after verifying repository state and a clean baseline:

```
PYTHONPATH="$PWD/services/api" .venv/bin/python evaluations/offline/run_semantic_baseline.py
PYTHONPATH="$PWD/services/api:$PWD/evaluations/offline" .venv/bin/python -m unittest discover -s evaluations/offline -p 'test_*.py' -v
PYTHONPATH="$PWD/services/api" .venv/bin/python evaluations/offline/run_semantic_baseline.py --real-pdf "$HOME/.cache/frp-cn-table-pilot/sources/600276/2026H1/source.pdf"
```

The optional PDF diagnostic checks original hashes, native PDF evidence,
announcement date, and two existing screen outcomes, using the development
report already used to build the feature. **Not independent OOS qualification.**
Captured evaluation results should be saved outside the repository and never
committed as product runtime fixtures.

Next phase M1.9B should define a constrained semantic-assertion schema that
separates *claimed metric, denominator, period, scope, and causality* from
literal evidence. An independently verified source-side identity is needed to
reject a wrong denominator or growth scope; an Analyst's own labels must not
serve as both claim and oracle. Preserve `UNCERTAIN` where the source cannot
settle a claim. Run independent real-document validation subsequently, outside
this development set.
