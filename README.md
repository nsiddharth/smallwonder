# 🎭 smallwonder

**A troupe of small local models on your Mac that act like one big one.**

One command installs a private, $0/month AI stack on Apple Silicon: a coding
model, a general/vision model, a fast model, and (optionally) image
generation — behind a single OpenAI-compatible endpoint with automatic
routing, a ChatGPT-style web UI, and swap-on-demand memory management so it
all fits alongside your real work.

```sh
brew install nsiddharth/smallwonder/smallwonder
smallwonder setup
```

Then open http://localhost:8080 and talk to it, or point any OpenAI client at
`http://localhost:4000/v1`.

## What you get

| Ask for | You get |
|---|---|
| `coder` | The best coding model your RAM fits (48GB tier: Qwen3.6-27B, ~73%+ SWE-bench) |
| `general` | Chat + reasoning + **vision** (attach images) |
| `fast` | Small model for instant, cheap queries |
| `auto` | A local embedding router picks the right one per query |
| `image` | Image generation via Draw Things (optional module) |
| `local/<id>` | Any model you've downloaded, zero config |

- **Private by construction**: every service binds to `127.0.0.1`; inference,
  embeddings, and images never leave the machine. Telemetry off. Works with
  Wi-Fi disabled. See [docs/privacy.md](docs/privacy.md).
- **Fits your machine**: RAM-tiered model presets (16/32/48GB+); models
  JIT-load on first use and auto-evict when idle.
- **Two runtimes**: LM Studio's MLX engine (default, fastest on Apple
  Silicon) or a fully open-source profile (llama.cpp + llama-swap).
- **Stays honest**: a golden-prompt eval suite (`smallwonder evals`) so you
  can compare models before switching, instead of vibes.
- **Optional daily news brief**: RSS → digested by your own models → RAG
  collection, so answers stay current without sending queries anywhere.

## Requirements

- Apple Silicon Mac, 16GB+ RAM (48GB recommended for the full experience)
- macOS 14+, [Homebrew](https://brew.sh), ~25-45GB disk for models

## Commands

```
smallwonder setup        # install + configure everything (idempotent)
smallwonder status       # health + models
smallwonder up / down    # start / stop services
smallwonder doctor       # diagnose known failure modes
smallwonder evals        # golden-prompt quality suite
smallwonder models add <ref> [--role coder]
smallwonder image enable # Draw Things + OpenAI-images shim
smallwonder news enable  # daily local news digest
smallwonder tutorial     # print the quick-start card
```

## Architecture

```
Open WebUI :8080 ─┐
your editor ──────┼─► LiteLLM :4000 ─► LM Studio or llama-swap :1234 (LLMs)
any script ───────┘        │
                           └─────────► images shim :7861 ─► Draw Things :7860
```

Roles are stable names; the models behind them are one line of config each.
`smallwonder` renders all configs from `~/.smallwonder/config.yaml` — edit,
`smallwonder up`, done.

## Also works with

Claude Code (`ANTHROPIC_BASE_URL=http://localhost:1234`), Aider, Continue.dev,
Cline, OpenCode — anything that speaks OpenAI or Anthropic APIs.

## License

MIT. Model licenses are all Apache 2.0 in the default tiers; LM Studio is
freeware installed via its official installer (or use `--backend llamaswap`
for a fully open-source stack).

*Model presets last verified: July 2026 on a Mac Mini M4 Pro 48GB.*
