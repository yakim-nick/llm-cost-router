# llm-cost-router

LLM API Gateway / cost router. FastAPI-сервис, который маршрутизирует запросы
к разным LLM-провiders (OpenAI, Anthropic), кэширует семантически похожие
запросы, собирает метрики стоимости/латентности (Prometheus) и отдаёт
админку для анализа расходов.

## Стек
- FastAPI (proxy + admin routes)
- Semantic cache (сходство запросов → меньше токенов = дешевле)
- Prometheus-метрики (см. `prometheus/prometheus.yml`)
- SQLite/Postgres через `src/models/database.py`

## Запуск
```bash
pip install -e .            # или: pip install -r requirements.txt
uvicorn src.main:app --port 8000
# метрики: GET /metrics
```

## Деплой
```bash
docker build -t llm-cost-router .   # если есть Dockerfile
docker-compose up                    # если есть compose
```

## CI
`.github/workflows/ci.yml` — синтаксис-проверка + pytest на каждый push.

## Автор
Nick Yakim — github.com/yakim-nick
