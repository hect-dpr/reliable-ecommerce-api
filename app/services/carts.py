from sqlalchemy.orm import joinedload

from app import errors
from app.models import Cart, CartItem, CartStatus, Product
from app.serializers import cart_out


def _get_open_cart(db, cart_id):
    cart = (
        db.query(Cart)
        .options(joinedload(Cart.items))
        .filter(Cart.id == cart_id)
        .one_or_none()
    )
    if cart is None:
        raise errors.not_found("cart_not_found", "Cart {} does not exist".format(cart_id))
    if cart.status != CartStatus.open:
        raise errors.conflict(
            "cart_checked_out",
            "Cart {} has already been checked out".format(cart_id),
        )
    return cart


def _products_map(db, product_ids):
    if not product_ids:
        return {}
    products = db.query(Product).filter(Product.id.in_(product_ids)).all()
    return {p.id: p for p in products}


def create_cart(db):
    cart = Cart(status=CartStatus.open)
    db.add(cart)
    db.commit()
    db.refresh(cart)
    return cart_out(cart, {})


def get_cart(db, cart_id):
    cart = (
        db.query(Cart)
        .options(joinedload(Cart.items))
        .filter(Cart.id == cart_id)
        .one_or_none()
    )
    if cart is None:
        raise errors.not_found("cart_not_found", "Cart {} does not exist".format(cart_id))
    products = _products_map(db, [i.product_id for i in cart.items])
    return cart_out(cart, products)


def add_item(db, cart_id, product_id, quantity):
    cart = _get_open_cart(db, cart_id)
    product = db.query(Product).filter(Product.id == product_id).one_or_none()
    if product is None:
        raise errors.bad_request(
            "invalid_product",
            "Product {} does not exist".format(product_id),
        )
    if quantity <= 0:
        raise errors.bad_request("invalid_quantity", "Quantity must be greater than zero")
    if quantity > product.inventory:
        raise errors.bad_request(
            "insufficient_inventory",
            "Product {} has only {} in stock".format(product_id, product.inventory),
        )

    existing = (
        db.query(CartItem)
        .filter(CartItem.cart_id == cart.id, CartItem.product_id == product_id)
        .one_or_none()
    )
    if existing is not None:
        new_qty = existing.quantity + quantity
        if new_qty > product.inventory:
            raise errors.bad_request(
                "insufficient_inventory",
                "Product {} has only {} in stock".format(product_id, product.inventory),
            )
        existing.quantity = new_qty
    else:
        db.add(CartItem(cart_id=cart.id, product_id=product_id, quantity=quantity))

    db.commit()
    return get_cart(db, cart_id)


def update_item(db, cart_id, product_id, quantity):
    cart = _get_open_cart(db, cart_id)
    item = (
        db.query(CartItem)
        .filter(CartItem.cart_id == cart.id, CartItem.product_id == product_id)
        .one_or_none()
    )
    if item is None:
        raise errors.not_found(
            "cart_item_not_found",
            "Product {} is not in cart {}".format(product_id, cart_id),
        )
    product = db.query(Product).filter(Product.id == product_id).one_or_none()
    if product is None:
        raise errors.bad_request(
            "invalid_product",
            "Product {} does not exist".format(product_id),
        )
    if quantity > product.inventory:
        raise errors.bad_request(
            "insufficient_inventory",
            "Product {} has only {} in stock".format(product_id, product.inventory),
        )
    item.quantity = quantity
    db.commit()
    return get_cart(db, cart_id)


def remove_item(db, cart_id, product_id):
    cart = _get_open_cart(db, cart_id)
    item = (
        db.query(CartItem)
        .filter(CartItem.cart_id == cart.id, CartItem.product_id == product_id)
        .one_or_none()
    )
    if item is None:
        raise errors.not_found(
            "cart_item_not_found",
            "Product {} is not in cart {}".format(product_id, cart_id),
        )
    db.delete(item)
    db.commit()
    return get_cart(db, cart_id)
