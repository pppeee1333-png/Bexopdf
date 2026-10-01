"""
user_stats.py - تتبع وإحصائيات المستخدمين
"""

import json
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from utils import logger

STATS_FILE = Path(os.path.dirname(__file__)) / "user_stats.json"

class UserStats:
    """نظام تتبع المستخدمين والإحصائيات"""
    
    @staticmethod
    def _load_stats() -> dict:
        try:
            if STATS_FILE.exists():
                with open(STATS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {
                "users": {},
                "total_users": 0,
                "total_interactions": 0,
                "daily_users": {},
                "monthly_users": {},
                "last_updated": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"❌ فشل تحميل الإحصائيات: {e}")
            return {
                "users": {},
                "total_users": 0,
                "total_interactions": 0,
                "daily_users": {},
                "monthly_users": {},
                "last_updated": datetime.now().isoformat()
            }
    
    @staticmethod
    def _save_stats(stats: dict) -> bool:
        try:
            with open(STATS_FILE, 'w', encoding='utf-8') as f:
                json.dump(stats, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"❌ فشل حفظ الإحصائيات: {e}")
            return False
    
    @staticmethod
    def track_user(user_id: int, username: str = None, first_name: str = None):
        try:
            stats = UserStats._load_stats()
            user_id_str = str(user_id)
            now = datetime.now()
            today = now.strftime("%Y-%m-%d")
            month = now.strftime("%Y-%m")
            
            if user_id_str not in stats["users"]:
                stats["users"][user_id_str] = {
                    "first_seen": now.isoformat(),
                    "last_seen": now.isoformat(),
                    "username": username or "",
                    "first_name": first_name or "",
                    "interactions": 1
                }
                stats["total_users"] += 1
            else:
                stats["users"][user_id_str]["last_seen"] = now.isoformat()
                stats["users"][user_id_str]["interactions"] += 1
                if username:
                    stats["users"][user_id_str]["username"] = username
                if first_name:
                    stats["users"][user_id_str]["first_name"] = first_name
            
            stats["total_interactions"] += 1
            
            if today not in stats["daily_users"]:
                stats["daily_users"][today] = []
            if user_id_str not in stats["daily_users"][today]:
                stats["daily_users"][today].append(user_id_str)
            
            if month not in stats["monthly_users"]:
                stats["monthly_users"][month] = []
            if user_id_str not in stats["monthly_users"][month]:
                stats["monthly_users"][month].append(user_id_str)
            
            stats["last_updated"] = now.isoformat()
            
            UserStats._save_stats(stats)
            return True
        except Exception as e:
            logger.error(f"❌ فشل تتبع المستخدم: {e}")
            return False
    
    @staticmethod
    def get_stats() -> dict:
        try:
            stats = UserStats._load_stats()
            now = datetime.now()
            today = now.strftime("%Y-%m-%d")
            week_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d")
            
            total_users = stats.get("total_users", 0)
            total_interactions = stats.get("total_interactions", 0)
            
            daily_users = stats.get("daily_users", {})
            today_users = len(daily_users.get(today, []))
            
            weekly_users = set()
            for date, users in daily_users.items():
                if date >= week_ago:
                    weekly_users.update(users)
            
            monthly_users = stats.get("monthly_users", {})
            this_month_users = len(monthly_users.get(now.strftime("%Y-%m"), []))
            
            active_users = len(weekly_users)
            
            return {
                "total_users": total_users,
                "total_interactions": total_interactions,
                "today_users": today_users,
                "weekly_active": active_users,
                "monthly_active": this_month_users,
                "last_updated": stats.get("last_updated", now.isoformat())
            }
        except Exception as e:
            logger.error(f"❌ فشل جلب الإحصائيات: {e}")
            return {"error": str(e)}
    
    @staticmethod
    def get_top_users(limit: int = 10) -> List[dict]:
        try:
            stats = UserStats._load_stats()
            users = stats.get("users", {})
            
            sorted_users = sorted(
                users.items(),
                key=lambda x: x[1].get("interactions", 0),
                reverse=True
            )[:limit]
            
            result = []
            for user_id, data in sorted_users:
                result.append({
                    "user_id": user_id,
                    "username": data.get("username", "مجهول"),
                    "first_name": data.get("first_name", ""),
                    "interactions": data.get("interactions", 0),
                    "first_seen": data.get("first_seen", ""),
                    "last_seen": data.get("last_seen", "")
                })
            
            return result
        except Exception as e:
            logger.error(f"❌ فشل جلب المستخدمين الأكثر تفاعلاً: {e}")
            return []

user_stats = UserStats()
