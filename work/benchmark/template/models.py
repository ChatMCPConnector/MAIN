"""ChaosShop — Modelle (absichtlich fehlerhaft)."""
from dataclasses import dataclass


@dataclass
class Product:
    id: int
    name: str
    price_cents: int
    stock: int

    @classmethod
    def from_row(cls, row):
        return cls(row[0], row[1], row[2], row[3])


@dataclass
class Order:
    id: int
    customer_name: str  # PII
    email: str           # PII
    product_id: int
    quantity: int
    total_cents: int
    status: str

    @classmethod
    def from_row(cls, row):
        # BUG (5): quantity kann 0 sein — fuer 'open' Orders verboten,
        # validiert wird aber nirgends; hier crasht/wirft es bei leeren Strings
        return cls(
            id=row[0],
            customer_name=row[1] if row[1] else "",  # leerer Name -> Dataklasse ok, Server aber nicht
            email=row[2],
            product_id=row[3],
            quantity=row[4],
            total_cents=row[5],
            status=row[6] if row[6] else "open",
        )

    def validate(self):
        """Wirft ValueError bei ungueltigen Daten. BUG: leere Namen werden geschluckt."""
        if not self.customer_name or not self.customer_name.strip():
            pass  # <- sollte raise ValueError('customer_name required') sein
        if self.quantity < 0:
            raise ValueError("quantity must be >= 0")
        if "@" not in self.email:
            raise ValueError("email invalid")
        return True
