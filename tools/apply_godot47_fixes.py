from pathlib import Path

path = Path("game/main.gd")
text = path.read_text(encoding="utf-8")
replacements = [
    ('\t\tvar key := event.keycode', '\t\tvar key: Key = event.keycode'),
    ('\tvar p1 := get_player(0)', '\tvar p1 = get_player(0)'),
    ('\tvar p2 := get_player(1)', '\tvar p2 = get_player(1)'),
    ('\tvar char_idx := {"brawler":1, "runner":0, "ranger":3, "elite":2, "boss":1}.get(kind, 1)', '\tvar char_idx: int = int({"brawler":1, "runner":0, "ranger":3, "elite":2, "boss":1}.get(kind, 1))'),
    ('\tvar target := nearest_target(f)', '\tvar target = nearest_target(f)'),
    ('\tvar damage := 42.0 * f.power', '\tvar damage: float = 42.0 * float(f.power)'),
    ('\tvar params := {', '\tvar params: Array = {'),
    ('draw_style_box(', 'draw_panel('),
    ('func draw_panel(rect: Rect2, fill: Color, border: Color, width := 2.0) -> void:', 'func draw_panel(rect: Rect2, fill: Color, border: Color, width: float = 2.0) -> void:'),
    ('\tvar floor_color := p[1].darkened(0.38)', '\tvar floor_color: Color = p[1].darkened(0.38)'),
    ('var color := {"health":Color("ff657a"),"energy":Color("62dfff"),"weapon":Color("ffd45c")}.get(item.kind,Color.WHITE)', 'var color: Color = {"health":Color("ff657a"),"energy":Color("62dfff"),"weapon":Color("ffd45c")}.get(item.kind,Color.WHITE)'),
    ('\tvar p := get_player(0); var dummy = fighters[1]\n\tvar before: float = dummy.hp\n\tperform_attack(p,"light")\n\tvar ok := screen=="game" and fighters.size()>=2 and dummy.hp < before and p.pos.x >= ARENA.position.x', '\tvar p = get_player(0)\n\tif p == null:\n\t\tget_tree().quit(1)\n\t\treturn\n\tvar dummy: Dictionary = fighters[1]\n\tvar before: float = dummy.hp\n\tperform_attack(p,"light")\n\tvar ok: bool = screen=="game" and fighters.size()>=2 and dummy.hp < before and p.pos.x >= ARENA.position.x'),
]
changed = False
for old, new in replacements:
    if old in text:
        text = text.replace(old, new)
        changed = True
if not changed:
    print("Godot 4.7 source fixes already present.")
else:
    path.write_text(text, encoding="utf-8")
    print("Applied Godot 4.7 parser and typing fixes.")
