# Contributing

## Dev setup

```sh
git clone https://github.com/nsiddharth/smallwonder && cd smallwonder
uv venv .venv && uv pip install -e . ruff pytest --python .venv/bin/python
.venv/bin/pytest && .venv/bin/ruff check src tests
```

## Testing

- `pytest` — unit tests (no models needed; CI runs these).
- `scripts/integration.sh` — full-stack test on real hardware (downloads
  models, starts services, runs the eval suite). Run before release.

## Updating model tiers

The model landscape moves fast. Tier presets live in ONE place:
`src/smallwonder/tiers.py`. To propose a change:

1. Verify the refs exist: LM Studio hub page + `https://huggingface.co/api/models/<repo>`
   (watch for gated repos — they break zero-friction setup).
2. Run `smallwonder models add <ref> --role <role>` locally, then
   `smallwonder evals`, and include the before/after eval output in your PR.
3. Update the "last verified" date in `tiers.py` and README.

## Principles

- Localhost-only by default; anything that sends bytes off-machine must be
  opt-in and documented in docs/privacy.md.
- Never bundle third-party binaries (LM Studio's ToS prohibits
  redistribution; we invoke their official installer instead).
- Role names (`coder`/`general`/`fast`/`auto`) are a stable public API.
