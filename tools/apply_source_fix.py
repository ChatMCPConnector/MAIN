from pathlib import Path

path = Path("game/main.gd")
text = path.read_text(encoding="utf-8")
old = '\tvar p := get_player(0); if p: perform_attack(p,"special")'
new = '\tvar p = get_player(0)\n\tif p:\n\t\tperform_attack(p,"special")'
if old in text:
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("Applied capture coroutine source fix.")
else:
    print("Capture coroutine source fix already present.")
