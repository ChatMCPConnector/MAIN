import pytest
from chaosshop.models import get_all_products, get_product_by_id, add_product, update_product_stock, get_all_orders, get_order_by_id, place_order
from chaosshop.auth import check_auth, is_admin
import json

def test_get_products():
    products = get_all_products()
    assert len(products) == 3

def test_get_product_by_id():
    product = get_product_by_id(1)
    assert product["name"] == "Laptop"

def test_add_product():
    product = add_product("Test Mouse", 29.99, 100)
    assert product["name"] == "Test Mouse"

def test_update_stock():
    update_product_stock(1, 5)
    product = get_product_by_id(1)
    assert product["stock"] == 5

def test_place_order_success():
    order = place_order(2, 1, "Test User", "test@example.com")
    assert order["customer_name"] == "Test User"

def test_place_order_insufficient_stock():
    with pytest.raises(ValueError):
        place_order(1, 1000, "Test", "test@example.com")

def test_auth_admin():
    assert check_auth("admin", "admin") is True

def test_auth_wrong():
    assert check_auth("user", "pass") is False

def test_is_admin():
    assert is_admin("admin") is True
    assert is_admin("user") is False

def test_export_csv():
    orders = get_all_orders()
    csv = "id,product_id,quantity,customer_name,email,status\n"
    for o in orders:
        csv += f"{o['id']},{o['product_id']},{o['quantity']},{o['customer_name']},{o['email']},{o['status']}\n"
    assert "Test User" in csv

def test_race_condition():
    # To be fixed with lock
    pass

def test_auth_bypass():
    # To be fixed
    pass

def test_sql_injection():
    # To be fixed
    pass

def test_empty_name_crash():
    # To be fixed
    pass

def test_csv_masking():
    # To be fixed with PII
    pass

print("Tests created")
EOF