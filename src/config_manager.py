import os
import json

DEFAULT_CONFIG = {
    "bill_pdf_dir": "./bills",
    "pdf_password": "",
    "min_amount_filter": 0,
    "categories": {}
}


class ConfigManager:
    def __init__(self, config_path="config.json"):
        self.config_path = config_path
        self.config = self.load_config()

    def load_config(self):
        if not os.path.exists(self.config_path):
            self.save_config(DEFAULT_CONFIG)
            return DEFAULT_CONFIG

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            updated = False
            # Check min_amount_filter validation
            min_amt = data.get("min_amount_filter", 0)
            if not isinstance(min_amt, (int, float)) or min_amt < 0:
                data["min_amount_filter"] = 0
                updated = True

            if "bill_pdf_dir" not in data:
                data["bill_pdf_dir"] = DEFAULT_CONFIG["bill_pdf_dir"]
                updated = True

            if "pdf_password" not in data:
                data["pdf_password"] = DEFAULT_CONFIG["pdf_password"]
                updated = True

            if updated:
                self.save_config(data)

            return data
        except Exception as e:
            print(f"Error reading config.json: {e}")
            return DEFAULT_CONFIG

    def save_config(self, new_config=None):
        if new_config is not None:
            self.config = new_config

        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)

    def get(self, key, default=None):
        val = self.config.get(key, default)
        if key == "min_amount_filter":
            if not isinstance(val, (int, float)) or val < 0:
                return 0
        return val

    def set(self, key, value):
        if key == "min_amount_filter":
            if not isinstance(value, (int, float)) or value < 0:
                value = 0
        self.config[key] = value
        self.save_config()
