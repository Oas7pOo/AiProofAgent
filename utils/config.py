from pathlib import Path
from typing import Any, Dict
import yaml

class ConfigManager:
    def __init__(self, config_path="config.yaml"):
        self.path = Path(config_path)
        self.data: Dict[str, Any] = {}
        self.load()

    def load(self):
        if not self.path.exists():
            self.data = {}
            return
        try:
            with self.path.open("r", encoding="utf-8") as f:
                self.data = yaml.safe_load(f) or {}
        except UnicodeDecodeError:
            with self.path.open("r", encoding="gbk") as f:
                self.data = yaml.safe_load(f) or {}

    def get(self, key: str, default=None):
        keys = key.split(".")
        value = self.data
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value if value is not None else default

    def set(self, key: str, value: Any):
        keys = key.split(".")
        node = self.data
        for k in keys[:-1]:
            node = node.setdefault(k, {})
        node[keys[-1]] = value

    def save(self):
        with self.path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(self.data, f, allow_unicode=True)
