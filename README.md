# Mimir

Self-hosted smart contract auditing platform. You give it Solidity source, an LLM
reviews it, and you get back a list of findings mapped to the exact lines they
came from.

Chain-agnostic. Avalanche C-Chain and the Fuji testnet are wired up by default.

## Input

- Upload `.sol` files, or a zip of a project
- Paste a verified contract address — the source is pulled from Snowtrace
- Paste a GitHub URL — the repo is cloned and Solidity files are extracted

Model is picked per run (`gpt-5.4`, `gpt-5.2-codex`, `gpt-5.1-codex-max`).

## Stack

- **Backend** — Python, FastAPI, SQLAlchemy, PostgreSQL, RabbitMQ
- **Frontend** — Next.js, React, Tailwind, shadcn/ui
- **Worker** — a throwaway Docker or Kubernetes container per job

## Running it

```bash
cp backend/.env.example backend/.env
# edit backend/.env — set passwords and API keys

cd backend
docker compose up -d
```

That brings up the database, queue, API, worker manager, secret store, result
service and frontend.

- Frontend: http://localhost:50300
- API: http://localhost:50337

### Without Docker

```bash
cd backend
uv sync
uv run python -m api
```

```bash
cd frontend
bun install
bun run dev
```

## Configuration

Everything is in `backend/.env`. `backend/.env.example` documents every option.

The ones that usually need attention:

| Variable | What it does |
| --- | --- |
| `BACKEND_OAI_KEY_MODE` | How OpenAI keys are handled: `direct`, `proxy` or `subscription` |
| `INSTANCER_CODEX_AUTH_DIR` | Path to Codex CLI auth, only used in `subscription` mode |
| `AUTH_BACKEND` | Set to `github` to put the app behind GitHub OAuth |
| `SNOWTRACE_API_KEY` | Required for fetching verified contract source |

## Layout

```
backend/
  api/            FastAPI server
  instancer/      queue consumer, spawns worker containers
  prunner/        worker lifecycle and cleanup
  secretsvc/      short-lived secret bundles handed to workers
  resultsvc/      collects results from finished workers
  oai_proxy/      optional proxy so workers never see a real API key
  ghbot/          GitHub app integration
  indexer/        on-chain event indexer
  worker_runner/  audit prompt and runner script
  docker/         Dockerfiles
frontend/         Next.js app, exported statically
```

## License

Apache 2.0
