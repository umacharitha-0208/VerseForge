#!/bin/sh
set -e

exec python -m streamlit run frontend/app.py \
    --server.address 0.0.0.0 \
    --server.port 7860 \
    --server.headless true