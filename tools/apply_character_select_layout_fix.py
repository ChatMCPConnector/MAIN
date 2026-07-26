from pathlib import Path

path = Path("game/main.gd")
text = path.read_text(encoding="utf-8")
old = 'draw_character_portrait(i, rect.position + Vector2(130,145), 1.55)'
new = 'draw_character_portrait(i, rect.position + Vector2(130,145), 1.18)'
if old in text:
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("Reduced character-select portrait scale to preserve text spacing.")
else:
    print("Character-select layout fix already present.")
