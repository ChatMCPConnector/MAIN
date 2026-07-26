from pathlib import Path

path = Path("game/main.gd")
text = path.read_text(encoding="utf-8")
old = '\tvar dummy: Dictionary = fighters[1]\n\tvar before: float = dummy.hp\n\tperform_attack(p,"light")'
new = '\tvar dummy: Dictionary = fighters[1]\n\tp.pos = dummy.pos - Vector2(45, 0)\n\tp.facing = 1.0\n\tvar before: float = dummy.hp\n\tperform_attack(p,"light")'
if old in text:
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("Placed the smoke-test player inside valid melee range.")
else:
    print("Windows smoke-test position fix already present.")
