from app.models import Product

# Fixed IDs so docs and tests stay stable.
# Prices are in paise (100 paise = ₹1).
SEED_PRODUCTS = [
    {"id": 1, "name": "Ceramic Mug", "unit_price_paise": 1299, "inventory": 100},
    {"id": 2, "name": "Notebook", "unit_price_paise": 899, "inventory": 50},
    {"id": 3, "name": "Desk Lamp", "unit_price_paise": 4599, "inventory": 25},
    {"id": 4, "name": "USB-C Cable", "unit_price_paise": 1499, "inventory": 200},
    # Only 2 in stock — used for oversell tests.
    {"id": 5, "name": "Limited Edition Poster", "unit_price_paise": 2999, "inventory": 2},
]


def seed_products(db):
    if db.query(Product).count() > 0:
        return
    for row in SEED_PRODUCTS:
        db.add(Product(**row))
    db.commit()
