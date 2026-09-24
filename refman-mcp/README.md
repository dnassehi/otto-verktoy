# refman-mcp

Skrivebeskyttet MCP-server rundt [`../lib/refdb.py`](../lib/refdb.py) (se
[`../reference-manager/`](../reference-manager/)). Den er laget for at en avgrenset agent (uten
shell og filsystem) skal kunne søke i referansedatabasen. Den eksponerer bevisst bare lesing.
`add_article`, `attach_pdf` og import/eksport er ikke med.

## Verktøy

1. `refman_search(query, limit)`
2. `refman_find_by_doi(doi)`
3. `refman_find_by_pmid(pmid)`
4. `refman_stats()`

## Oppsett

```bash
cd refman-mcp
python3 -m venv .venv && .venv/bin/pip install "mcp" requests
openclaw mcp add refman --command "$PWD/.venv/bin/python" --arg "$PWD/server.py"
openclaw mcp doctor refman --probe
```

`server.py` importerer `lib/refdb.py` direkte, så mappen må ligge ved siden av `lib/` og
`reference-manager/` slik den gjør i dette repoet.
