from pathlib import Path
import yaml
from typing import Dict, List, Any

# 配置文件路径
CONFIG_DIR = Path(__file__).parent.parent.parent / "assets" / "config"
STAT_FILE = CONFIG_DIR / "entry_stats.yml"

class StatsManager:
    _instance = None
    _stats_data: Dict[str, Any] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(StatsManager, cls).__new__(cls)
            cls._instance._load_data()
        return cls._instance

    def _load_data(self):
        """加载 entry_stats.yml 配置文件"""
        try:
            with open(STAT_FILE, "r", encoding="utf-8") as f:
                self._stats_data = yaml.safe_load(f)
        except Exception as e:
            print(f"Error loading stats file: {e}")
            self._stats_data = {}

    def get_all_stats(self) -> Dict[str, Any]:
        """获取所有属性的统计数据"""
        return self._stats_data

    def get_stat(self, key: str) -> Dict[str, Any]:
        """获取指定属性的统计数据"""
        return self._stats_data.get(key)

    def get_distribution(self, key: str) -> List[Dict[str, float]]:
        """获取指定属性的数值分布"""
        stat = self.get_stat(key)
        return stat.get("distribution", []) if stat else []

    def get_all_keys(self) -> List[str]:
        """获取所有可能的属性键列表"""
        return list(self._stats_data.keys())

    # --- 用户配置管理 ---
    _user_config_file = CONFIG_DIR / "echo_user_config.yml"
    _user_config: Dict[str, Any] = {}

    def load_user_config(self):
        try:
            if self._user_config_file.exists():
                with open(self._user_config_file, "r", encoding="utf-8") as f:
                    self._user_config = yaml.safe_load(f) or {}
        except Exception as e:
            print(f"Error loading user config: {e}")
            self._user_config = {}

    def save_user_config(self):
        try:
            with open(self._user_config_file, "w", encoding="utf-8") as f:
                yaml.dump(self._user_config, f, allow_unicode=True)
        except Exception as e:
            print(f"Error saving user config: {e}")

    def get_user_conf(self, key: str, default: Any = None) -> Any:
        if not self._user_config:
            self.load_user_config()
        return self._user_config.get(key, default)

    def set_user_conf(self, key: str, value: Any):
        self._user_config[key] = value
        self.save_user_config()

# 全局单例
stats_manager = StatsManager()
