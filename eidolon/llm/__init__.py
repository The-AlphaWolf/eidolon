"""Phase 5: the LLM boundary. Layering (§23.1): world <- minds <- evidence <- decision <- llm.
`decision` never imports this package; it exposes a `Renderer` port and this package plugs in."""
