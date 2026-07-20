# llm-cost-router

An LLM API gateway / cost router. A FastAPI service that routes requests to
multiple LLM providers (OpenAI, Anthropic), caches semantically similar
requests, collects cost/latency metrics (Prometheus), and exposes an admin
view for spend analysis.

## Stack
- FastAPI (proxy + admin routes)
- Semantic cache (similar-request hit → fewer tokens → lower cost)
- Prometheus metrics (see `prometheus/prometheus.yml`)
- SQLite/Postgres via `src/models/database.py`

## Run
```bash
pip install -e .            # or: pip install -r requirements.txt
uvicorn src.main:app --port 8000
# metrics: GET /metrics
```

## Deploy
```bash
docker build -t llm-cost-router .   # if a Dockerfile is present
docker-compose up                    # if a compose file is present
```

## CI
`.github/workflows/ci.yml` — syntax check + `pytest` on every push, with
least-privilege permissions and pinned action versions.

## Author
Nick Yakim — github.com/yakim-nick
