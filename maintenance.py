import json
from pathlib import Path

from config import Config
from utils import logger

MAINTENANCE_FILE = Path(Config.BASE_DIR) / "maintenance.json"


class MaintenanceSystem:

    @staticmethod
    def is_enabled() -> bool:
        try:
            if not MAINTENANCE_FILE.exists():
                return False

            with open(MAINTENANCE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            return bool(data.get("enabled", False))

        except Exception as e:
            logger.error(f"خطأ في قراءة حالة الصيانة: {e}")
            return False

    @staticmethod
    def set_enabled(enabled: bool) -> bool:
        try:
            with open(MAINTENANCE_FILE, "w", encoding="utf-8") as f:
                json.dump(
                    {"enabled": bool(enabled)},
                    f,
                    ensure_ascii=False,
                    indent=2
                )

            return True

        except Exception as e:
            logger.error(f"خطأ في حفظ حالة الصيانة: {e}")
            return False
