UPPER_BODY_TYPES = {
    "shirts",
    "tshirts",
    "tops",
    "vest top",
    "bodysuit",
    "sweaters",
    "sweatshirts",
    "jackets",
    "blazers",
    "kurtas",
    "tunics",
    "waistcoat",
}
LOWER_BODY_TYPES = {
    "jeans",
    "trousers",
    "shorts",
    "skirts",
    "track pants",
    "leggings",
    "capris",
    "salwar",
}
ONE_PIECE_TYPES = {
    "dresses", "jumpsuit", "rompers", "sarees", "lehenga choli",
    "costumes", "dungarees", "garment set",
}


def classify_garment_zone(article_type: str | None, sub_category: str | None) -> str:
    article = (article_type or "").strip().lower()
    category = (sub_category or "").strip().lower()
    if article in UPPER_BODY_TYPES or category == "topwear":
        return "upper_body"
    if article in LOWER_BODY_TYPES or category == "bottomwear":
        return "lower_body"
    if article in ONE_PIECE_TYPES or category in {"dress", "saree"}:
        return "one_piece"
    if category in {"shoes", "bags", "accessories", "watches", "eyewear"}:
        return "accessory"
    return "other"
