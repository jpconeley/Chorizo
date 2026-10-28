#!/bin/sh
# Container entrypoint: migrate, optionally load demo data, then serve the API.
set -e

alembic upgrade head
chorizo seed-reference
if [ "$CHORIZO_SEED_DEMO" = "1" ]; then
  chorizo seed-demo
  chorizo refresh-estimates
fi

exec uvicorn chorizo.api.main:app --host 0.0.0.0 --port 8000
