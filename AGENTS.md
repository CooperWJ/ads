# AGENTS.md

This is an **AI software-engineering evaluation benchmark** for a *fictional* app ("Project Echo"), not production code. Do not treat `fixtures/project_board/` as a real app to develop. Its job: grade candidate patches against a fixed set of source-derived acceptance obligations and report `PASS`/`FAIL`/`GAP` honestly. Many docs (`README.md`, `docs/TRUST-MODEL.md`, `CHANGELOG.md`, fixture briefs/PRD) are written in Chinese.

## Commands (run from repo root)

All Python unless noted; backend requires only the stdlib on Python 3.10+. There is **no dependency manifest** (no `requirements.txt`, `pyproject.toml`, or `package.json`).

```bash
python3 -m unittest discover -s tests -p 'test*.py' -v   # all tests
python3 evaluator/calibrate.py                            # backend + Node 校准
python3 evaluator/calibrate.py --require-browser          # requires Playwright chromium; strict
python3 evaluator/grade.py --candidate reference --profile backend --out artifacts/foo
python3 discovery/cli.py --inventory-only                 # enumerate sources only (no claims)
python3 discovery/cli.py                                  # full source→obligation gap audit
python3 poc/probe.py                                      # read-only availability probe
python3 tools/build_variants.py                           # regenerate patch files from base seed
```

- `integration` and `full` profiles need Node.js 20+ (`evaluator/js_runtime_check.cjs`). `full` additionally needs `pip install 'playwright==1.57.0'` + `python -m playwright install chromium`.
- Browser integration is **not** run/verified on a local host by default; do not claim it passed without `--require-browser`.

## Exit codes are load-bearing

- `grade.py`: `0` = PASS, `1` = FAIL/REJECTED, `2` = INFRA_ERROR or (`--require-delivery` active AND deliveries not verified). A nonzero exit from a strict run can be **expected behavior**, not a bug.
- `discovery/cli.py`: `0` = PASS (or `--inventory-only`), `2` = **GAP/BLOCKED**. A full audit of the current fixtures is expected to return `2` (new unverified obligations exist).
- `calibrate.py --require-browser`: nonzero if real Chromium reference does not PASS and bad variant does not FAIL.

## Reading `grade.json`

- `status` = result of the *selected profile* (backend/integration/full).
- `delivery_verdict.status` = the complete 18-obligation acceptance. This is the only field that can justify "delivery complete".
- Backend PASS ≠ delivery. Never claim delivery or full verification from a backend/integration-only result.

## Trust model (non-negotiable)

- `tempfile` + `git apply` in `grade.py` is **not** a security/OS sandbox. A custom `.patch` candidate requires explicit `--allow-untrusted-local-candidate`; prefer isolated execution.
- Do not describe local results as independent, protected, or supply-chain verified. `check_evidence()`/`check_qa()` use synthetic inputs, not real attestation/QA.
- The evaluator and its acceptance data are owned by a separate role and must not be handed to a *tested* agent. Do not weaken or edit the acceptance scope to make a candidate pass.

## Structure & conventions

- `fixtures/project_board/raw/` = fictitious source material (`brief.md`, `prd.md`, `wireframe.svg`, `data_dictionary.xlsx`); `base/` = deliberately unfinished seed; `patches/` = reference, equivalent, and intentionally-faulty variants.
- **Do not hand-edit `patches/*.patch`** — they are generated deterministically by `tools/build_variants.py` from the frozen `base/` seed; regenerate instead.
- Only these paths are editable for a candidate (see `ALLOWED_PATHS` in `evaluator/grade.py`): `app.py`, `web/index.html`, `web/app.js`. Anything else is rejected.
- Evaluator-owned acceptance data: `evaluator/raw_obligations.json` (18 obligations) and `evaluator/source_review.json` (independent per-fragment review of 4 sources / 44 units). `evaluator/requirements.py` enforces they are fully audited and cross-referenced.
- Version is single-sourced in `VERSION`; M1 discovery lives in `discovery/`, M0 grading in `evaluator/`.
- Current capability status is maintained in `docs/PROJECT-STATUS.md`. Recovery audit checks local export consistency only; synthetic fixtures and prior-schema PASS do not prove a current native OpenCode run.
- OpenSpec-driven changes: see `.opencode/commands/opsx-*.md` and `openspec/config.yaml` (schema `spec-driven`); change artifacts live under `openspec/`.