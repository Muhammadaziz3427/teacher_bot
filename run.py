"""Entry point — run the bot with:  python run.py"""

from __future__ import annotations

import asyncio
import sys

# Windows consoles use cp1252/cp1254 by default; log lines and bot output
# contain characters (→ ✅ …) those encodings cannot represent.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from app.main import main

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit) as exc:
        if str(exc):
            print(exc)
