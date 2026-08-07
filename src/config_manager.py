import os
import json

DEFAULT_CONFIG = {
    "bill_pdf_dir": "./bills",
    "pdf_password": "",
    "categories": {
        "餐飲與食品": [
            "全聯", "7-ELEVEN", "7-11", "統一超商", "全家", "萊爾富", "OK超商", "美廉社",
            "麥當勞", "摩斯", "肯德基", "UberEats", "Foodpanda", "星巴克", "路易莎", "得正",
            "春山茶水", "壽司", "火鍋", "餐廳", "食堂", "咖啡", "便當", "麵館", "麵包",
            "茶", "飲料", "酸菜魚", "心樸市集", "大排檔", "壹穴"
        ],
        "交通與出行": [
            "Uber", "台灣大車隊", "和欣客運", "高鐵", "台鐵", "捷運", "悠遊卡", "一卡通",
            "加油站", "中油", "台亞", "停車", "iRent", "GoShare", "WeMo", "ETC",
            "BEIJING METRO", "DIDI", "北京地鐵", "滴滴"
        ],
        "電信與固定開銷": [
            "中華電信", "台灣大哥大", "遠傳", "大安文山", "有線電視", "水費", "電費", "瓦斯"
        ],
        "數位訂閱與服務": [
            "Netflix", "Spotify", "YouTube", "Apple", "Google", "iCloud", "ChatGPT",
            "Midjourney", "Microsoft", "OpenAI", "國外交易服務費"
        ],
        "購物與網購": [
            "MOMO", "蝦皮", "PChome", "酷朋", "Coupang", "博客來", "誠品", "露天", "Yahoo",
            "百貨", "新光三越", "SOGO", "微風", "遠東", "UNIQLO", "GU", "ZARA", "Amazon",
            "昇恒昌", "免稅", "金興發", "LINEPAY"
        ],
        "娛樂與休閒": [
            "威秀", "國賓", "秀泰", "KTV", "錢櫃", "好樂迪", "蒸氣", "Steam", "PlayStation",
            "Nintendo", "桌遊", "夏洛克", "預售票", "Klook", "KKday", "體育客"
        ],
        "生活與醫藥": [
            "屈臣氏", "康是美", "寶雅", "大樹藥局", "柏愛藥局", "診所", "醫院", "藥局"
        ],
        "信用卡繳款": [
            "網路銀行繳款", "自動扣繳", "ATM繳款", "臨櫃繳款"
        ]
    }
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

            # Ensure all required keys exist
            updated = False
            for key, val in DEFAULT_CONFIG.items():
                if key not in data:
                    data[key] = val
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
        return self.config.get(key, default)

    def set(self, key, value):
        self.config[key] = value
        self.save_config()

    def get_categories(self):
        return self.config.get("categories", DEFAULT_CONFIG["categories"])

    def add_keyword_to_category(self, category_name, keyword):
        categories = self.get_categories()
        if category_name not in categories:
            categories[category_name] = []
        if keyword not in categories[category_name]:
            categories[category_name].append(keyword)
            self.config["categories"] = categories
            self.save_config()
