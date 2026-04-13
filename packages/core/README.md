# bifrost-core (`grafana-mcp`)

Python MCP server at the heart of Bifröst. See [the Bifröst README](../../README.md) and [docs/packages/core.md](../../docs/packages/core.md) for the full story.

```bash
uv sync
uv run grafana-mcp serve --transport sse --env dev --role viewer --port 8765
```
