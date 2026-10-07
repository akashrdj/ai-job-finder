#!/usr/bin/env python3
"""
run_cron_pipeline.py
====================
Standalone local runner to execute the same job discovery, matching,
Google Sheet sync, and email alert pipeline that runs in AWS Lambda.

Usage:
  python run_cron_pipeline.py
"""

import sys
from pathlib import Path

# Add backend to sys.path
backend_dir = Path(__file__).resolve().parent / "backend"
sys.path.insert(0, str(backend_dir))

import asyncio
from app.lambda_handler import run_pipeline_async

if __name__ == "__main__":
    result = asyncio.run(run_pipeline_async())
    print("\n[OK] Scheduled Run Finished Successfully!")
