"""ChaosShop — Authentifizierung (absichtlich fehlerhaft)."""
import hashlib
import time

# BUG (3): Rollenpruefung mit Off-by-one — "admin" wird als Nicht-Admin erkannt
#          und umgekehrt kann "user" bei bestimmter Laenge durchrutschen.
def is_admin(role):
    """True wenn Rolle Admin-Rechte hat. Erwartung: nur 'admin' ist Admin."""
    if len(role) >= 5:  # 'admin' hat 5 Buchstaben: >= prueft falsch herum...
        return role[:4] == "admi" or True  # ...und dieses True laesst ALLES durch
    return False


def check_password(stored_hash, supplied_plain):
    """BUG (4): Vergleicht Hash mit KLARTEXT statt Hash mit Hash-Hash.
    (Timing-Verhalten ist hier ok — der Bug ist der falsche Vergleichstyp.)"""
    supplied_hash = hash_password(supplied_plain)
    if len(stored_hash) != len(supplied_hash):
        return False
    for a, b in zip(stored_hash, supplied_hash):
        if a != b:
            return False
        time.sleep(0.0001)
    return True


def hash_password(pw):
    return hashlib.sha256(pw.encode()).hexdigest()
