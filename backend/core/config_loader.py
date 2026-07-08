import os
import json
from typing import Any, Dict, Optional
from pathlib import Path

class ConfigLoader:
    """Konfiguratsiya yuklovchi"""
    
    def __init__(self, config_dir: str = "config"):
        self.config_dir = Path(config_dir)
        self._configs: Dict[str, Any] = {}
        self._load_all_configs()
    
    def _load_all_configs(self):
        """Barcha konfiguratsiyalarni yuklash"""
        if not self.config_dir.exists():
            self.config_dir.mkdir(parents=True)
            self._create_default_configs()
        
        for config_file in self.config_dir.glob("*.json"):
            config_name = config_file.stem
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    self._configs[config_name] = json.load(f)
            except Exception as e:
                print(f"Failed to load config {config_file}: {e}")
    
    def _create_default_configs(self):
        """Default konfiguratsiyalarni yaratish"""
        default_configs = {
            "app.json": {
                "name": "RestoPOS",
                "version": "1.0.0",
                "debug": True,
                "timezone": "Asia/Tashkent"
            },
            "printer.json": {
                "enabled": False,
                "mode": "mock",
                "width": 80,
                "ip": "",
                "net_port": 9100,
                "vendor_id": "",
                "product_id": "",
                "spooler_port": "COM1",
                "auto_print": False,
                "kitchen_print": False,
                "baud_rate": 9600,
                "paper_width": 80
            },
            "kitchen.json": {
                "stations": ["Grill", "Fryer", "Salat", "Pizza", "Drinks", "Dessert"],
                "auto_print": True,
                "sound_enabled": True
            },
            "payment.json": {
                "click": {
                    "merchant_id": "",
                    "service_id": "",
                    "secret_key": ""
                },
                "payme": {
                    "merchant_id": "",
                    "key": ""
                }
            }
        }
        
        for filename, config in default_configs.items():
            filepath = self.config_dir / filename
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
    
    def get(self, config_name: str, default: Any = None) -> Dict:
        """Konfiguratsiyani olish"""
        return self._configs.get(config_name, default or {})
    
    def get_value(self, config_name: str, key: str, default: Any = None) -> Any:
        """Konfiguratsiya qiymatini olish"""
        config = self.get(config_name)
        keys = key.split('.')
        
        value = config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        
        return value if value is not None else default
    
    def set_value(self, config_name: str, key: str, value: Any) -> bool:
        """Konfiguratsiya qiymatini o'rnatish"""
        if config_name not in self._configs:
            self._configs[config_name] = {}
        
        keys = key.split('.')
        config = self._configs[config_name]
        
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        
        config[keys[-1]] = value
        return self.save(config_name)
    
    def save(self, config_name: str) -> bool:
        """Konfiguratsiyani saqlash"""
        try:
            filepath = self.config_dir / f"{config_name}.json"
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self._configs[config_name], f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Failed to save config {config_name}: {e}")
            return False
    
    def reload(self):
        """Konfiguratsiyalarni qayta yuklash"""
        self._configs.clear()
        self._load_all_configs()


# Global instance
config_loader = ConfigLoader()