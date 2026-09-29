"""Entry point — run the bot with:  python run.py"""

from __future__ import annotations

import asyncio
import signal
import sys

# Windows consoles use cp1252/cp1254 by default; log lines and bot output
# contain characters (→ ✅ …) those encodings cannot represent.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# PaaS hosts (Render) stop a service with SIGTERM. Turn it into SystemExit so
# the shutdown hook in app/main.py runs: worker stops, DB is saved to GitHub.
if hasattr(signal, "SIGTERM"):
    def _sigterm(_signum, _frame):
        raise SystemExit(143)

    try:
        signal.signal(signal.SIGTERM, _sigterm)
    except (ValueError, OSError):          # not on the main thread / unsupported
        pass

from app.main import main

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit) as exc:
        if str(exc):
            print(exc)
