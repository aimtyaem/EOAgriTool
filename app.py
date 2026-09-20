"""
EOAgriTool — Application Entry Point

Usage:
    python -m app          # development
    gunicorn app:app       # production (ASGI via uvicorn worker)
"""

import os
import sys
import logging

from backend.routes import create_app

# --- Logging (before app creation) ---
log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("eoagritool")

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    logger.info("Starting EOAgriTool on port %d (debug=%s)", port, debug)
    app.run(host="0.0.0.0", port=port, debug=debug)