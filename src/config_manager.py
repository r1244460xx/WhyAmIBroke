import os
import json

DEFAULT_CONFIG = {
    "bill_pdf_dir": "./bills",
    "pdf_passwords": [],
    "min_amount_filter": 0,
    "categories": {},
    "excluded_keywords": []
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

            # Ensure bill_pdf_dir is fixed to ./bills
            if data.get("bill_pdf_dir") != "./bills":
                data["bill_pdf_dir"] = "./bills"
                updated = True

            # Migration & validation for multi-bank pdf_passwords
            if "pdf_passwords" not in data or not isinstance(data["pdf_passwords"], list):
                if "pdf_password" in data and data["pdf_password"]:
                    data["pdf_passwords"] = [{"prefix": "TSB_", "password": str(data["pdf_password"])}]
                else:
                    data["pdf_passwords"] = []
                updated = True
            else:
                # Validate items in pdf_passwords
                valid_passwords = []
                for item in data["pdf_passwords"]:
                    if isinstance(item, dict) and "password" in item:
                        valid_passwords.append({
                            "prefix": str(item.get("prefix", "")),
                            "password": str(item.get("password", ""))
                        })
                if valid_passwords != data["pdf_passwords"]:
                    data["pdf_passwords"] = valid_passwords
                    updated = True

            if "excluded_keywords" not in data or not isinstance(data["excluded_keywords"], list):
                data["excluded_keywords"] = []
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
