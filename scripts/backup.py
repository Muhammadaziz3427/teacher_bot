"""Zaxira nusxa: SQLite baza + Excel eksportlar bitta zip faylda.

Ishlatish (bot ishlab turganda ham xavfsiz — WAL baza uchun `PRAGMA
wal_checkpoint` bilan to'g'ri nusxa olinadi):

    python scripts/backup.py
    python scripts/backup.py --out D:/backups --keep 30

Cron misoli (har kuni 03:30 da):

    30 3 * * * cd /opt/teacher_bot && .venv/bin/python scripts/backup.py --keep 30
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402
from app.utils import now  # noqa: E402


def snapshot_database(source: Path, target: Path) -> None:
    """`sqlite3.Connection.backup` — baza ishlab turganda ham izchil nusxa.

    Eslatma: `with sqlite3.connect(...)` faqat tranzaksiyani yopadi, faylni
    emas — shu sababli ulanishlar qo'lda yopiladi (Windows'da aks holda
    vaqtinchalik fayl o'chmaydi).
    """
    origin = sqlite3.connect(source)
    try:
        copy = sqlite3.connect(target)
        try:
            origin.execute("PRAGMA wal_checkpoint(FULL)")
            origin.backup(copy)
        finally:
            copy.close()
    finally:
        origin.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Teacher Bot zaxira nusxasi")
    parser.add_argument("--out", default="backups", help="papka (default: backups)")
    parser.add_argument("--keep", type=int, default=14,
                        help="nechta arxiv saqlansin (default: 14)")
    args = parser.parse_args()

    database = settings.db_path
    if not database.exists():
        print(f"❌ Baza topilmadi: {database}")
        return 1

    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    stamp = now().strftime("%Y%m%d_%H%M%S")
    archive = out_dir / f"teacher_bot_{stamp}.zip"
    temp_db = out_dir / f".snapshot_{stamp}.db"

    snapshot_database(database, temp_db)
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.write(temp_db, "teacher_bot.db")
        exports = settings.exports_path
        if exports.exists():
            for file in exports.glob("*.xlsx"):
                bundle.write(file, f"exports/{file.name}")
    temp_db.unlink(missing_ok=True)

    size_kb = archive.stat().st_size // 1024
    print(f"✅ Zaxira: {archive} ({size_kb} KB)")

    archives = sorted(out_dir.glob("teacher_bot_*.zip"))
    for old in archives[: max(0, len(archives) - args.keep)]:
        old.unlink()
        print(f"🗑  Eski arxiv o'chirildi: {old.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
