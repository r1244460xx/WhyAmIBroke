class CategoryClassifier:
    def __init__(self, categories_dict):
        """
        categories_dict: dict mapping category_name -> list of keywords
        """
        self.categories_dict = categories_dict or {}

    def update_categories(self, categories_dict):
        self.categories_dict = categories_dict or {}

    def classify(self, description):
        if not description or not isinstance(description, str):
            return "其他"

        desc_upper = description.upper()

        # Check each category and its keywords
        for category, keywords in self.categories_dict.items():
            for kw in keywords:
                if kw and kw.upper() in desc_upper:
                    return category

        return "其他"
