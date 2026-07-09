# Privacy: what stays local, what touches the network

## Guaranteed local

- **All inference** — chat, coding, vision, embeddings, image generation,
  auto-router classification. Every service binds to `127.0.0.1` (verify:
  `lsof -nP -iTCP -sTCP:LISTEN | grep -E '1234|4000|8080|7861'`).
- **All stored data** — chats, notes, uploaded documents, generated images,
  news briefs — in local databases under `~/.smallwonder/`.
- The stack is fully functional with Wi-Fi off. That's the real guarantee.

## What does use the network (never your queries)

| Traffic | When | Content |
|---|---|---|
| Model downloads | `setup`, `models add` | Weights from Hugging Face / LM Studio hub |
| Runtime installs | `setup` | LM Studio installer or brew formulas |
| Update checks | LM Studio / Open WebUI launch | Version numbers only |
| News module (opt-in) | Daily, if enabled | Fetches YOUR configured RSS feeds |

Disabled by configuration: LiteLLM telemetry (`telemetry: false` is baked
into the rendered config). Open WebUI community sharing and web search are
off unless you enable them — enabling web search sends query text to the
search provider you choose, by definition.

## Hardening further

- Watch outbound connections with [LuLu](https://objective-see.org/products/lulu.html)
  (free, open source) — during chats you should see nothing.
- Air-gap: after setup, everything works offline; download model updates
  manually when you choose.
