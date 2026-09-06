"""ChaosShop — Tests. 5 scheitern anfangs (unterschiedliche Fehlerbilder)."""
import os
import sys
import threading
import sqlite3

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    """Isolierte DB pro Test."""
    import db as dbm
    test_db = str(tmp_path / "test.db")
    monkeypatch.setattr(dbm, "DB_PATH", test_db)
    monkeypatch.setattr(dbm, "_local", threading.local())
    dbm.seed()
    yield


def test_health_endpoint():
    """Server soll antworten (Unit-Ebene: db laedt)."""
    import db as dbm
    assert dbm.get_product(1) is not None


def test_save_and_list_order():
    """Happy Path: eine Bestellung anlegen und listen."""
    import db as dbm
    oid = dbm.save_order("Max Muster", "max@example.com", 1, 2)
    orders = dbm.list_orders()
    assert len(orders) == 1
    assert orders[0][0] == oid
    assert orders[0][5] == 9800  # 2 x 4900


def test_order_with_quotes_in_name():
    """SCHEITERT anfangs: SQL-String-Konkatenation crasht bei Anfuehrungszeichen."""
    import db as dbm
    dbm.save_order("O'Brien", "ob@example.com", 1, 1)
    assert dbm.list_orders()[0][1] == "O'Brien"


def test_race_stock_oversell():
    """SCHEITERT anfangs: Race Condition — Parallelnkäufe überverkaufen
    (mehr erfolgreiche Bestellungen als Anfangsbestand)."""
    import db as dbm

    initial_stock = dbm.get_product(3)[3]  # Monitor: 3 Stück

    def buy():
        try:
            dbm.save_order("Racer", "race@example.com", 3, 1)
        except ValueError:
            pass

    threads = [threading.Thread(target=buy) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    conn = dbm.get_conn()
    sold = conn.execute("SELECT COUNT(*) FROM orders WHERE product_id = 3").fetchone()[0]
    assert sold <= initial_stock, (
        f"Überverkauf! {sold} Bestellungen für {initial_stock} Stück Lager"
    )


def test_is_admin_off_by_one():
    """SCHEITERT anfangs: 'admin' muss Admin sein, 'user' nicht."""
    import auth
    assert auth.is_admin("admin") is True
    assert auth.is_admin("user") is False
    assert auth.is_admin("guest") is False


def test_password_check():
    """Auth-Hash pruefen (feste Erwartung)."""
    import auth
    h = auth.hash_password("geheim")
    assert auth.check_password(h, "geheim") is True
    assert auth.check_password(h, "falsch") is False


def test_quantity_zero_rejected():
    """SCHEITERT anfangs: Menge 0 muss abgelehnt werden (models validate)."""
    import models
    o = models.Order(1, "Zero", "z@example.com", 1, 0, 0, "open")
    with pytest.raises(ValueError):
        o.validate()


def test_validate_empty_email():
    """Ungueltige Email wirft ValueError (besteht schon — Kontroll-Test)."""
    import models
    o = models.Order(2, "NoMail", "no-email", 1, 1, 100, "open")
    with pytest.raises(ValueError):
        o.validate()


def test_pii_fields_marked():
    """PII-Markierung muss die zwei erwarteten Felder nennen."""
    import db as dbm
    assert dbm.PII_FIELDS.get("customer_name") is True
    assert dbm.PII_FIELDS.get("email") is True
