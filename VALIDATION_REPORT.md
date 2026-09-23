# Spartan StudyBuddy — package validation

## Passed in packaging environment

- All Python source compiles with `py_compile`.
- All JSON parses.
- All shell scripts pass `bash -n`.
- All web/Chrome/VS Code/test JavaScript passes `node --check`.
- Chrome Manifest V3 contract test passes.
- Chrome service-worker API-routing contract test passes.
- Chrome content-script selection/assistant UI contract test passes.
- VS Code extension activation/commands/sidebar/save-listener/workspace-connect contract test passes.
- Chrome extension ZIP and VS Code VSIX are generated and included under `dist/extensions/`.
- PostgreSQL/pgvector structural gates confirm: `CREATE EXTENSION vector`, native `vector(1024)`, HNSW cosine index, `tsvector` GIN index, PostgreSQL lexical queries and pgvector cosine queries.
- No runtime `sqlite3`, FTS5 virtual table, or blob-vector database path exists in backend/scripts.

## Required first-run gate on DGX Spark

The packaging environment does not provide Docker, PostgreSQL, pgvector, or an NVIDIA GPU. Therefore it cannot honestly execute the live persistence/model stack.

On the DGX Spark run:

```bash
cp .env.example .env
make dgx-setup
make test
```

`make test` starts the real `pgvector/pgvector` container, runs backend integration tests against PostgreSQL, checks the vector schema, and reruns the extension contracts. It intentionally has no SQLite fallback.

For a full fresh deployment after configuring `.env`:

```bash
make deploy
```
