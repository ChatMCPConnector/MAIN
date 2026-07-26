extends Node2D

const W := 1280.0
const H := 720.0
const ARENA := Rect2(95, 285, 1090, 315)
const VERSION := "1.0.0"

const CHARACTERS := [
	{"name":"Kira Volt", "tag":"Storm Runner", "speed":285.0, "hp":920.0, "energy":120.0, "power":0.92, "color":Color("39d6ff"), "accent":Color("fff06a"), "specials":"Arc Bolt / Thunder Step"},
	{"name":"Brakk Forge", "tag":"Iron Vanguard", "speed":205.0, "hp":1280.0, "energy":90.0, "power":1.28, "color":Color("ff7448"), "accent":Color("ffd0a8"), "specials":"Furnace Spin / Meteor Fist"},
	{"name":"Mira Bloom", "tag":"Aether Warden", "speed":235.0, "hp":1040.0, "energy":145.0, "power":0.90, "color":Color("74f0a7"), "accent":Color("f0fff6"), "specials":"Renewal Pulse / Vine Guard"},
	{"name":"Nyx Shade", "tag":"Void Duelist", "speed":310.0, "hp":850.0, "energy":130.0, "power":1.05, "color":Color("b67aff"), "accent":Color("ff79c6"), "specials":"Rift Wave / Phase Strike"}
]

const STAGES := [
	{"name":"Skyline Foundry", "subtitle":"Conveyor lanes and molten vents", "palette":[Color("0b1638"), Color("1e4670"), Color("ff7a45")]},
	{"name":"Verdant Metro", "subtitle":"An abandoned station reclaimed by nature", "palette":[Color("071f28"), Color("1c6b55"), Color("8df095")]},
	{"name":"Null Observatory", "subtitle":"Low gravity above a fractured moon", "palette":[Color("170d35"), Color("4d2d7f"), Color("e49cff")]}
]

const MODES := [
	{"id":"stage", "name":"STAGE RUN", "desc":"Three escalating waves and a boss"},
	{"id":"versus", "name":"LOCAL VERSUS", "desc":"Player 1 versus Player 2"},
	{"id":"team", "name":"TEAM BATTLE", "desc":"Two local players against a squad"},
	{"id":"training", "name":"TRAINING", "desc":"Practice combos against a durable dummy"},
	{"id":"survival", "name":"SURVIVAL", "desc":"Endless waves for a high score"}
]

var screen := "main_menu"
var menu_index := 0
var selected_mode := "stage"
var p1_character := 0
var p2_character := 1
var selected_stage := 0
var fighters: Array = []
var projectiles: Array = []
var pickups: Array = []
var objects: Array = []
var particles: Array = []
var next_fighter_id := 1
var wave := 0
var score := 0
var game_time := 0.0
var result_text := ""
var message := ""
var message_timer := 0.0
var shake := 0.0
var slow_motion := 0.0
var sfx_volume := 0.75
var music_volume := 0.32
var fullscreen := false
var music_clock := 0.0
var music_step := 0
var sfx_player: AudioStreamPlayer
var music_player: AudioStreamPlayer
var tone_cache := {}
var rng := RandomNumberGenerator.new()
var capture_mode := false
var joy_prev := {}

func _ready() -> void:
	rng.seed = 4132026
	process_mode = Node.PROCESS_MODE_ALWAYS
	set_process(true)
	set_physics_process(true)
	sfx_player = AudioStreamPlayer.new()
	music_player = AudioStreamPlayer.new()
	add_child(sfx_player)
	add_child(music_player)
	load_settings()
	var args := OS.get_cmdline_user_args()
	if "--smoke-test" in args:
		call_deferred("run_smoke_test")
	elif "--capture-ci" in args:
		capture_mode = true
		call_deferred("capture_ci_gallery")
	queue_redraw()

func _physics_process(delta: float) -> void:
	if message_timer > 0.0:
		message_timer -= delta
	if shake > 0.0:
		shake = max(0.0, shake - delta * 20.0)
	if screen == "game" and not get_tree().paused:
		process_gamepad_buttons()
	if screen != "game" or get_tree().paused:
		update_music(delta)
		queue_redraw()
		return
	var step := delta * (0.32 if slow_motion > 0.0 else 1.0)
	if slow_motion > 0.0:
		slow_motion -= delta
	game_time += step
	update_music(delta)
	update_fighters(step)
	update_projectiles(step)
	update_pickups(step)
	update_particles(step)
	check_match_state()
	queue_redraw()

func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
		handle_mouse_click(event.position)
		queue_redraw()
		return
	if event is InputEventKey and event.pressed and not event.echo:
		var key: Key = event.keycode
		if key == KEY_F11:
			fullscreen = not fullscreen
			DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_FULLSCREEN if fullscreen else DisplayServer.WINDOW_MODE_WINDOWED)
			save_settings()
			return
		if key == KEY_ESCAPE:
			handle_escape()
			return
		match screen:
			"main_menu": handle_main_menu_key(key)
			"mode_select": handle_mode_key(key)
			"character_select": handle_character_key(key)
			"stage_select": handle_stage_key(key)
			"options": handle_options_key(key)
			"controls":
				if key in [KEY_ENTER, KEY_SPACE, KEY_BACKSPACE]: screen = "main_menu"
			"game": handle_game_key(key)
			"result":
				if key in [KEY_ENTER, KEY_SPACE]: screen = "main_menu"; get_tree().paused = false
	queue_redraw()

func handle_mouse_click(pos: Vector2) -> void:
	match screen:
		"main_menu":
			for i in 4:
				if Rect2(430, 285 + i * 72, 420, 54).has_point(pos):
					menu_index = i; handle_main_menu_key(KEY_ENTER); return
		"mode_select":
			for i in MODES.size():
				if Rect2(175, 145 + i * 92, 930, 72).has_point(pos):
					menu_index = i; handle_mode_key(KEY_ENTER); return
		"character_select":
			for i in CHARACTERS.size():
				if Rect2(82 + i * 300, 155, 260, 440).has_point(pos): p1_character = i; return
		"stage_select":
			if Rect2(175,150,930,500).has_point(pos): handle_stage_key(KEY_ENTER)
		"options":
			for i in 3:
				if Rect2(320,190+i*105,640,72).has_point(pos): menu_index=i; change_option(1); return
		"controls", "result": screen = "main_menu"

func process_gamepad_buttons() -> void:
	var pads := Input.get_connected_joypads()
	for player_index in mini(2, pads.size()):
		var device: int = pads[player_index]
		var f = get_player(player_index)
		if not f: continue
		var mapping := {JOY_BUTTON_A:"light", JOY_BUTTON_X:"heavy", JOY_BUTTON_Y:"special", JOY_BUTTON_B:"jump", JOY_BUTTON_LEFT_SHOULDER:"dash"}
		for button in mapping:
			var key := "%d:%d" % [device, button]
			var pressed := Input.is_joy_button_pressed(device, button)
			if pressed and not joy_prev.get(key, false):
				match mapping[button]:
					"light", "heavy", "special": perform_attack(f, mapping[button])
					"jump": jump_fighter(f)
					"dash": dash_fighter(f)
			joy_prev[key] = pressed

func handle_escape() -> void:
	if screen == "game":
		get_tree().paused = not get_tree().paused
		message = "PAUSED — Enter: Resume   R: Restart   Esc: Resume   Q: Main Menu" if get_tree().paused else ""
	elif screen in ["mode_select", "options", "controls"]:
		screen = "main_menu"
	elif screen in ["character_select", "stage_select"]:
		screen = "mode_select"
	elif screen == "result":
		screen = "main_menu"

func handle_main_menu_key(key: Key) -> void:
	var count := 4
	if key in [KEY_UP, KEY_W]: menu_index = wrapi(menu_index - 1, 0, count)
	elif key in [KEY_DOWN, KEY_S]: menu_index = wrapi(menu_index + 1, 0, count)
	elif key in [KEY_ENTER, KEY_SPACE]:
		play_sound("menu")
		match menu_index:
			0: screen = "mode_select"; menu_index = 0
			1: screen = "controls"
			2: screen = "options"; menu_index = 0
			3: get_tree().quit()

func handle_mode_key(key: Key) -> void:
	if key in [KEY_UP, KEY_W]: menu_index = wrapi(menu_index - 1, 0, MODES.size())
	elif key in [KEY_DOWN, KEY_S]: menu_index = wrapi(menu_index + 1, 0, MODES.size())
	elif key in [KEY_ENTER, KEY_SPACE]:
		selected_mode = MODES[menu_index].id
		screen = "character_select"
		play_sound("menu")

func handle_character_key(key: Key) -> void:
	if key in [KEY_LEFT, KEY_A]: p1_character = wrapi(p1_character - 1, 0, CHARACTERS.size())
	elif key in [KEY_RIGHT, KEY_D]: p1_character = wrapi(p1_character + 1, 0, CHARACTERS.size())
	elif key == KEY_Q: p2_character = wrapi(p2_character - 1, 0, CHARACTERS.size())
	elif key == KEY_E: p2_character = wrapi(p2_character + 1, 0, CHARACTERS.size())
	elif key in [KEY_ENTER, KEY_SPACE]: screen = "stage_select"; play_sound("menu")

func handle_stage_key(key: Key) -> void:
	if key in [KEY_LEFT, KEY_A, KEY_UP, KEY_W]: selected_stage = wrapi(selected_stage - 1, 0, STAGES.size())
	elif key in [KEY_RIGHT, KEY_D, KEY_DOWN, KEY_S]: selected_stage = wrapi(selected_stage + 1, 0, STAGES.size())
	elif key in [KEY_ENTER, KEY_SPACE]: start_match(selected_mode)

func handle_options_key(key: Key) -> void:
	if key in [KEY_UP, KEY_W]: menu_index = wrapi(menu_index - 1, 0, 3)
	elif key in [KEY_DOWN, KEY_S]: menu_index = wrapi(menu_index + 1, 0, 3)
	elif key in [KEY_LEFT, KEY_A]: change_option(-1)
	elif key in [KEY_RIGHT, KEY_D, KEY_ENTER, KEY_SPACE]: change_option(1)

func change_option(direction: int) -> void:
	match menu_index:
		0: music_volume = clamp(music_volume + direction * 0.1, 0.0, 1.0)
		1: sfx_volume = clamp(sfx_volume + direction * 0.1, 0.0, 1.0)
		2:
			fullscreen = not fullscreen
			DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_FULLSCREEN if fullscreen else DisplayServer.WINDOW_MODE_WINDOWED)
	save_settings()
	play_sound("menu")

func handle_game_key(key: Key) -> void:
	if get_tree().paused:
		if key == KEY_ENTER: get_tree().paused = false; message = ""
		elif key == KEY_R: get_tree().paused = false; start_match(selected_mode)
		elif key == KEY_Q: get_tree().paused = false; screen = "main_menu"; message = ""
		return
	var p1 = get_player(0)
	var p2 = get_player(1)
	if p1:
		if key == KEY_Z: perform_attack(p1, "light")
		elif key == KEY_X: perform_attack(p1, "heavy")
		elif key == KEY_C: perform_attack(p1, "special")
		elif key == KEY_V: jump_fighter(p1)
		elif key == KEY_B: dash_fighter(p1)
	if p2:
		if key == KEY_F: perform_attack(p2, "light")
		elif key == KEY_G: perform_attack(p2, "heavy")
		elif key == KEY_H: perform_attack(p2, "special")
		elif key == KEY_R: jump_fighter(p2)
		elif key == KEY_T: dash_fighter(p2)

func start_match(mode: String) -> void:
	selected_mode = mode
	screen = "game"
	get_tree().paused = false
	fighters.clear(); projectiles.clear(); pickups.clear(); particles.clear(); objects.clear()
	next_fighter_id = 1; wave = 0; score = 0; game_time = 0.0; result_text = ""; message = ""
	spawn_arena_objects()
	match mode:
		"versus":
			fighters.append(make_fighter(p1_character, Vector2(315, 455), 1, 0))
			fighters.append(make_fighter(p2_character, Vector2(965, 455), 2, 1))
		"team":
			fighters.append(make_fighter(p1_character, Vector2(300, 430), 1, 0))
			fighters.append(make_fighter(p2_character, Vector2(300, 505), 1, 1))
			spawn_enemy("brawler", Vector2(900, 400)); spawn_enemy("runner", Vector2(980, 490)); spawn_enemy("ranger", Vector2(1040, 550)); spawn_enemy("elite", Vector2(1030, 350))
		"training":
			fighters.append(make_fighter(p1_character, Vector2(380, 455), 1, 0))
			var dummy := make_fighter(1, Vector2(820, 455), 2, -1, "dummy")
			dummy.hp = 99999.0; dummy.max_hp = 99999.0; fighters.append(dummy)
		"survival":
			fighters.append(make_fighter(p1_character, Vector2(320, 455), 1, 0))
			spawn_next_wave()
		_:
			fighters.append(make_fighter(p1_character, Vector2(320, 455), 1, 0))
			spawn_next_wave()
	play_sound("start")

func make_fighter(char_idx: int, pos: Vector2, team: int, player: int, enemy_type := "") -> Dictionary:
	var data = CHARACTERS[char_idx]
	var f := {
		"id": next_fighter_id, "char": char_idx, "name": data.name, "pos": pos, "z": 0.0, "vz": 0.0,
		"team": team, "player": player, "enemy_type": enemy_type, "hp": data.hp, "max_hp": data.hp,
		"energy": data.energy, "max_energy": data.energy, "speed": data.speed, "power": data.power,
		"color": data.color, "accent": data.accent, "facing": 1.0 if team == 1 else -1.0,
		"cooldown": 0.0, "attack_timer": 0.0, "attack_kind": "", "stun": 0.0, "invuln": 0.0,
		"block": false, "dash": 0.0, "combo": 0, "combo_timer": 0.0, "dead": false,
		"ai_state": "search", "ai_clock": rng.randf_range(0.0, 0.3), "weapon": 0, "hit_flash": 0.0
	}
	next_fighter_id += 1
	return f

func spawn_enemy(kind: String, pos: Vector2) -> void:
	var char_idx: int = int({"brawler":1, "runner":0, "ranger":3, "elite":2, "boss":1}.get(kind, 1))
	var f := make_fighter(char_idx, pos, 2, -1, kind)
	match kind:
		"runner": f.speed *= 1.18; f.hp *= 0.72; f.max_hp = f.hp; f.name = "Flux Raider"
		"ranger": f.speed *= 0.86; f.hp *= 0.82; f.max_hp = f.hp; f.name = "Null Slinger"
		"elite": f.hp *= 1.55; f.max_hp = f.hp; f.power *= 1.18; f.name = "Aegis Captain"
		"boss": f.hp *= 3.1; f.max_hp = f.hp; f.power *= 1.35; f.speed *= 0.90; f.name = "THE IRON ECLIPSE"
		_: f.name = "Forge Grunt"
	fighters.append(f)

func spawn_next_wave() -> void:
	wave += 1
	message = "WAVE %d" % wave; message_timer = 1.8
	if selected_mode == "stage":
		if wave == 1:
			spawn_enemy("brawler", Vector2(920, 410)); spawn_enemy("runner", Vector2(1010, 500))
		elif wave == 2:
			spawn_enemy("brawler", Vector2(880, 380)); spawn_enemy("ranger", Vector2(1030, 470)); spawn_enemy("elite", Vector2(980, 545))
		else:
			spawn_enemy("boss", Vector2(970, 450)); spawn_enemy("runner", Vector2(850, 535))
	else:
		var count := mini(2 + wave, 7)
		for i in count:
			var kinds := ["brawler", "runner", "ranger", "elite"]
			spawn_enemy(kinds[(wave + i) % kinds.size()], Vector2(850 + (i % 3) * 100, 345 + (i % 4) * 65))

func spawn_arena_objects() -> void:
	objects = [
		{"pos":Vector2(575, 390), "hp":120.0, "kind":"crate"},
		{"pos":Vector2(700, 535), "hp":120.0, "kind":"crate"},
		{"pos":Vector2(1010, 575), "hp":160.0, "kind":"reactor"}
	]

func update_fighters(delta: float) -> void:
	for f in fighters:
		if f.dead: continue
		f.cooldown = max(0.0, f.cooldown - delta)
		f.attack_timer = max(0.0, f.attack_timer - delta)
		f.stun = max(0.0, f.stun - delta)
		f.invuln = max(0.0, f.invuln - delta)
		f.hit_flash = max(0.0, f.hit_flash - delta)
		f.combo_timer -= delta
		if f.combo_timer <= 0.0: f.combo = 0
		if f.z > 0.0 or f.vz != 0.0:
			f.z += f.vz * delta; f.vz -= 1250.0 * delta
			if f.z <= 0.0: f.z = 0.0; f.vz = 0.0
		if f.dash > 0.0:
			f.dash -= delta
			f.pos.x += f.facing * 650.0 * delta
			f.invuln = 0.08
		if f.stun > 0.0: continue
		f.block = false
		if f.player >= 0:
			update_player_control(f, delta)
		elif f.enemy_type != "dummy":
			update_ai(f, delta)
		f.pos.x = clamp(f.pos.x, ARENA.position.x + 25.0, ARENA.end.x - 25.0)
		f.pos.y = clamp(f.pos.y, ARENA.position.y + 35.0, ARENA.end.y - 18.0)
	fighters = fighters.filter(func(x): return not (x.dead and x.player < 0 and x.enemy_type != "dummy"))

func update_player_control(f: Dictionary, delta: float) -> void:
	var dir := Vector2.ZERO
	if f.player == 0:
		dir.x = Input.get_axis("ui_left", "ui_right")
		dir.y = Input.get_axis("ui_up", "ui_down")
		f.block = Input.is_key_pressed(KEY_B) and f.dash <= 0.0
		if Input.get_connected_joypads().size() > 0:
			dir += Vector2(Input.get_joy_axis(0, JOY_AXIS_LEFT_X), Input.get_joy_axis(0, JOY_AXIS_LEFT_Y))
	else:
		dir.x = float(Input.is_key_pressed(KEY_D)) - float(Input.is_key_pressed(KEY_A))
		dir.y = float(Input.is_key_pressed(KEY_S)) - float(Input.is_key_pressed(KEY_W))
		f.block = Input.is_key_pressed(KEY_T) and f.dash <= 0.0
		if Input.get_connected_joypads().size() > 1:
			dir += Vector2(Input.get_joy_axis(1, JOY_AXIS_LEFT_X), Input.get_joy_axis(1, JOY_AXIS_LEFT_Y))
	if dir.length() > 0.15 and f.attack_timer <= 0.05:
		dir = dir.normalized(); f.pos += dir * f.speed * delta
		if abs(dir.x) > 0.1: f.facing = sign(dir.x)

func update_ai(f: Dictionary, delta: float) -> void:
	f.ai_clock -= delta
	var target = nearest_target(f)
	if not target: f.ai_state = "search"; return
	var offset: Vector2 = target.pos - f.pos
	var distance := offset.length()
	var kind: String = f.enemy_type
	if f.hp < f.max_hp * 0.22 and rng.randf() < 0.012:
		f.ai_state = "retreat"
	elif distance > (250.0 if kind == "ranger" else 105.0):
		f.ai_state = "pursue"
	else:
		f.ai_state = "attack"
	if kind == "ranger" and distance < 190.0: f.ai_state = "retreat"
	match f.ai_state:
		"pursue":
			var move := offset.normalized(); f.pos += move * f.speed * delta
			if abs(move.x) > 0.1: f.facing = sign(move.x)
		"retreat":
			var move := -offset.normalized(); f.pos += move * f.speed * 0.72 * delta
			f.block = rng.randf() < 0.35
		"attack":
			f.facing = sign(offset.x) if abs(offset.x) > 2.0 else f.facing
			if f.ai_clock <= 0.0:
				f.ai_clock = rng.randf_range(0.22, 0.62)
				if kind == "ranger": perform_attack(f, "special")
				elif kind == "boss" and f.energy >= 25.0 and rng.randf() < 0.58: perform_attack(f, "special")
				elif kind == "elite" and rng.randf() < 0.30: f.block = true
				else: perform_attack(f, "heavy" if rng.randf() < 0.28 else "light")

func nearest_target(f: Dictionary):
	var best = null; var best_d := INF
	for other in fighters:
		if other.dead or other.team == f.team: continue
		var d: float = f.pos.distance_squared_to(other.pos)
		if d < best_d: best_d = d; best = other
	return best

func get_player(index: int):
	for f in fighters:
		if f.player == index and not f.dead: return f
	return null

func perform_attack(f: Dictionary, kind: String) -> bool:
	if f.dead or f.stun > 0.0 or f.cooldown > 0.0: return false
	var damage: float = 42.0 * float(f.power)
	var range_x := 92.0; var range_y := 48.0; var cost := 0.0; var knock := 105.0
	match kind:
		"light": f.cooldown = 0.26; f.attack_timer = 0.18; damage *= 0.74
		"heavy": f.cooldown = 0.62; f.attack_timer = 0.36; damage *= 1.62; range_x = 118.0; knock = 220.0
		"special":
			cost = 24.0
			if f.energy < cost: message = "Not enough energy"; message_timer = 0.7; return false
			f.energy -= cost; f.cooldown = 0.88; f.attack_timer = 0.55; damage *= 1.90; range_x = 165.0; range_y = 92.0; knock = 290.0
			activate_special(f, damage)
			play_sound("special")
			return true
	f.attack_kind = kind
	play_sound("attack")
	var hit_any := false
	for target in fighters:
		if target.dead or target.team == f.team or target.invuln > 0.0: continue
		var dx: float = (target.pos.x - f.pos.x) * f.facing
		var dy: float = abs(target.pos.y - f.pos.y)
		if dx > -18.0 and dx < range_x and dy < range_y and abs(target.z - f.z) < 75.0:
			apply_damage(target, damage, f, knock); hit_any = true
	if hit_any:
		f.combo += 1; f.combo_timer = 1.15; f.energy = min(f.max_energy, f.energy + 8.0)
	for obj in objects.duplicate():
		var dx: float = abs(obj.pos.x - f.pos.x); var dy: float = abs(obj.pos.y - f.pos.y)
		if dx < range_x and dy < range_y: damage_object(obj, damage)
	return true

func activate_special(f: Dictionary, damage: float) -> void:
	match int(f.char):
		0:
			projectiles.append({"pos":f.pos + Vector2(f.facing * 50.0, -f.z), "vel":Vector2(f.facing * 620.0, 0), "team":f.team, "damage":damage, "life":1.6, "color":f.accent, "radius":18.0, "owner":f})
		1:
			for target in fighters:
				if target.team != f.team and not target.dead and target.pos.distance_to(f.pos) < 185.0: apply_damage(target, damage * 0.78, f, 340.0)
			shake = 12.0
		2:
			f.hp = min(f.max_hp, f.hp + 130.0); f.invuln = 0.65
			for ally in fighters:
				if ally.team == f.team and ally.pos.distance_to(f.pos) < 210.0: ally.hp = min(ally.max_hp, ally.hp + 65.0)
		3:
			for i in 3:
				projectiles.append({"pos":f.pos + Vector2(0, (i - 1) * 38), "vel":Vector2(f.facing * (500.0 + i * 60.0), 0), "team":f.team, "damage":damage * 0.72, "life":1.35, "color":f.accent, "radius":14.0 + i * 3.0, "owner":f})
	particles.append({"pos":f.pos, "life":0.55, "max":0.55, "color":f.accent, "size":120.0})

func apply_damage(target: Dictionary, amount: float, source: Dictionary, knock: float) -> void:
	if target.dead: return
	var actual := amount * (0.22 if target.block else 1.0)
	if target.block: play_sound("block")
	else: play_sound("hit")
	target.hp -= actual; target.stun = 0.08 if target.block else 0.22; target.hit_flash = 0.14
	target.pos.x += source.facing * knock * (0.16 if target.block else 0.32)
	target.invuln = 0.08; shake = max(shake, 5.0 if actual < 80 else 10.0)
	particles.append({"pos":target.pos - Vector2(0, target.z + 55), "life":0.35, "max":0.35, "color":Color.WHITE, "size":45.0 + actual * 0.3})
	if target.hp <= 0.0:
		if target.enemy_type == "dummy":
			target.hp = target.max_hp; target.pos = Vector2(820, 455); message = "Training dummy reset"; message_timer = 0.7
		else:
			target.dead = true; target.hp = 0.0; score += 100 if target.player < 0 else 0; slow_motion = 0.18
			play_sound("ko")

func jump_fighter(f: Dictionary) -> void:
	if f.z <= 0.0 and f.stun <= 0.0: f.vz = 560.0; play_sound("jump")

func dash_fighter(f: Dictionary) -> void:
	if f.dash <= 0.0 and f.cooldown <= 0.0: f.dash = 0.16; f.cooldown = 0.32; play_sound("dash")

func update_projectiles(delta: float) -> void:
	for p in projectiles:
		p.pos += p.vel * delta; p.life -= delta
		for f in fighters:
			if f.dead or f.team == p.team or f.invuln > 0.0: continue
			if f.pos.distance_to(p.pos) < p.radius + 32.0:
				apply_damage(f, p.damage, p.owner, 240.0); p.life = 0.0; break
	projectiles = projectiles.filter(func(p): return p.life > 0.0 and p.pos.x > 40 and p.pos.x < W - 40)

func update_pickups(delta: float) -> void:
	for item in pickups:
		item.life -= delta; item.bob += delta * 4.0
		for f in fighters:
			if f.dead or f.pos.distance_to(item.pos) > 42.0: continue
			match item.kind:
				"health": f.hp = min(f.max_hp, f.hp + 180.0)
				"energy": f.energy = min(f.max_energy, f.energy + 50.0)
				"weapon": f.weapon += 1; f.power += 0.12
			item.life = 0.0; play_sound("pickup"); break
	pickups = pickups.filter(func(i): return i.life > 0.0)

func damage_object(obj: Dictionary, amount: float) -> void:
	obj.hp -= amount
	if obj.hp <= 0.0:
		var kinds := ["health", "energy", "weapon"]
		pickups.append({"pos":obj.pos, "kind":kinds[rng.randi_range(0, kinds.size() - 1)], "life":12.0, "bob":0.0})
		objects.erase(obj); shake = 8.0

func update_particles(delta: float) -> void:
	for p in particles: p.life -= delta
	particles = particles.filter(func(p): return p.life > 0.0)

func check_match_state() -> void:
	var team1_alive := fighters.any(func(f): return f.team == 1 and not f.dead)
	var team2_alive := fighters.any(func(f): return f.team == 2 and not f.dead)
	if not team1_alive:
		finish_match("DEFEAT")
		return
	if selected_mode == "training": return
	if not team2_alive:
		if selected_mode in ["stage", "survival"]:
			if selected_mode == "stage" and wave >= 3: finish_match("STAGE CLEARED")
			else:
				spawn_next_wave(); spawn_arena_objects()
		else:
			finish_match("TEAM 1 WINS" if selected_mode == "team" else "VICTORY")

func finish_match(text: String) -> void:
	result_text = text; screen = "result"; play_sound("victory" if text != "DEFEAT" else "ko")

func update_music(delta: float) -> void:
	music_clock -= delta
	if music_volume <= 0.01 or music_clock > 0.0: return
	music_clock = 0.48 if screen == "game" else 0.78
	var notes := [110.0, 146.83, 164.81, 220.0, 196.0, 146.83]
	var freq: float = notes[music_step % notes.size()] * (1.0 + selected_stage * 0.08)
	music_step += 1
	music_player.volume_db = linear_to_db(max(0.001, music_volume * 0.22))
	music_player.stream = make_tone(freq, 0.18, 0.15)
	music_player.play()

func play_sound(kind: String) -> void:
	if sfx_volume <= 0.01: return
	var params: Array = {
		"menu":[520.0,0.06], "start":[330.0,0.18], "attack":[190.0,0.05], "hit":[82.0,0.09],
		"block":[720.0,0.05], "special":[880.0,0.16], "jump":[420.0,0.08], "dash":[260.0,0.06],
		"pickup":[660.0,0.12], "ko":[70.0,0.28], "victory":[990.0,0.30]
	}.get(kind, [440.0,0.08])
	sfx_player.volume_db = linear_to_db(max(0.001, sfx_volume * 0.55))
	sfx_player.stream = make_tone(params[0], params[1], 0.28)
	sfx_player.play()

func make_tone(freq: float, duration: float, amp: float) -> AudioStreamWAV:
	var key := "%d_%d" % [int(freq), int(duration * 1000)]
	if tone_cache.has(key): return tone_cache[key]
	var rate := 22050; var samples := int(rate * duration); var data := PackedByteArray(); data.resize(samples * 2)
	for i in samples:
		var env := 1.0 - float(i) / samples
		var value := int(sin(TAU * freq * float(i) / rate) * env * amp * 32767.0)
		data.encode_s16(i * 2, value)
	var wav := AudioStreamWAV.new(); wav.format = AudioStreamWAV.FORMAT_16_BITS; wav.mix_rate = rate; wav.stereo = false; wav.data = data
	tone_cache[key] = wav
	return wav

func settings_path() -> String:
	if OS.has_feature("editor"): return "user://neon_rift_settings.cfg"
	return OS.get_executable_path().get_base_dir().path_join("settings.cfg")

func load_settings() -> void:
	var cfg := ConfigFile.new()
	if cfg.load(settings_path()) == OK:
		music_volume = float(cfg.get_value("audio", "music", music_volume))
		sfx_volume = float(cfg.get_value("audio", "sfx", sfx_volume))
		fullscreen = bool(cfg.get_value("video", "fullscreen", false))

func save_settings() -> void:
	var cfg := ConfigFile.new(); cfg.set_value("audio", "music", music_volume); cfg.set_value("audio", "sfx", sfx_volume); cfg.set_value("video", "fullscreen", fullscreen); cfg.save(settings_path())

func _draw() -> void:
	var offset := Vector2(rng.randf_range(-shake, shake), rng.randf_range(-shake, shake)) if shake > 0.0 else Vector2.ZERO
	draw_set_transform(offset)
	match screen:
		"main_menu": draw_main_menu()
		"mode_select": draw_mode_select()
		"character_select": draw_character_select()
		"stage_select": draw_stage_select()
		"options": draw_options()
		"controls": draw_controls()
		"game": draw_game()
		"result": draw_result()
	draw_set_transform(Vector2.ZERO)

func draw_background(palette: Array) -> void:
	draw_rect(Rect2(0,0,W,H), palette[0])
	for i in 9:
		var t := float(i) / 8.0
		draw_rect(Rect2(0, t * H, W, H / 8.0 + 1), palette[0].lerp(palette[1], t * 0.78))
	for i in 18:
		var x := float((i * 173 + 41) % 1280); var y := float((i * 97 + 31) % 260)
		draw_circle(Vector2(x,y), 1.5 + (i % 3), Color(1,1,1,0.35))

func title(text: String, y: float, size := 54) -> void:
	draw_string(ThemeDB.fallback_font, Vector2(W * 0.5 - ThemeDB.fallback_font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, size).x * 0.5, y), text, HORIZONTAL_ALIGNMENT_LEFT, -1, size, Color.WHITE)

func draw_main_menu() -> void:
	draw_background([Color("050817"), Color("172c5c"), Color("ff4f9b")])
	draw_circle(Vector2(1045,145), 130, Color("5ce7ff"), false, 7)
	draw_circle(Vector2(1045,145), 82, Color(0.8,0.3,1,0.45), false, 3)
	title("NEON RIFT", 128, 76)
	title("ARENA BREAKERS", 178, 30)
	draw_string(ThemeDB.fallback_font, Vector2(442,220), "A portable 2.5D arena brawler", HORIZONTAL_ALIGNMENT_LEFT, -1, 20, Color("9ed7ff"))
	var entries := ["PLAY", "CONTROLS", "OPTIONS", "QUIT"]
	for i in entries.size():
		draw_menu_button(entries[i], Rect2(430, 285 + i * 72, 420, 54), i == menu_index)
	draw_string(ThemeDB.fallback_font, Vector2(34,690), "v%s  •  Arrow keys + Enter  •  F11 Fullscreen" % VERSION, HORIZONTAL_ALIGNMENT_LEFT, -1, 16, Color(1,1,1,0.55))

func draw_menu_button(label: String, rect: Rect2, active: bool) -> void:
	draw_panel(rect, Color("4c2d78") if active else Color(0.05,0.08,0.16,0.82), Color("6ff2ff") if active else Color(1,1,1,0.16), 3.0)
	draw_string(ThemeDB.fallback_font, rect.position + Vector2(26,36), ("▶  " if active else "   ") + label, HORIZONTAL_ALIGNMENT_LEFT, -1, 23, Color.WHITE if active else Color(1,1,1,0.72))

func draw_panel(rect: Rect2, fill: Color, border: Color, width: float = 2.0) -> void:
	draw_rect(rect, fill, true); draw_rect(rect, border, false, width)

func draw_mode_select() -> void:
	draw_background([Color("080b20"), Color("243b70"), Color("6f5cff")]); title("SELECT MODE", 92, 46)
	for i in MODES.size():
		var rect := Rect2(175, 145 + i * 92, 930, 72); var active := i == menu_index
		draw_panel(rect, Color(0.19,0.10,0.36,0.95) if active else Color(0.03,0.05,0.12,0.82), Color("63eaff") if active else Color(1,1,1,0.12), 3)
		draw_string(ThemeDB.fallback_font, rect.position + Vector2(26,30), MODES[i].name, HORIZONTAL_ALIGNMENT_LEFT, -1, 23, Color.WHITE)
		draw_string(ThemeDB.fallback_font, rect.position + Vector2(26,56), MODES[i].desc, HORIZONTAL_ALIGNMENT_LEFT, -1, 16, Color("a9c8ef"))

func draw_character_select() -> void:
	draw_background([Color("0b0d1d"), Color("2a2754"), Color("d449a7")]); title("CHOOSE YOUR BREAKER", 85, 44)
	for i in CHARACTERS.size():
		var rect := Rect2(82 + i * 300, 155, 260, 440); var active := i == p1_character; var p2 := i == p2_character and selected_mode in ["versus","team"]
		draw_panel(rect, Color(0.05,0.06,0.13,0.93), CHARACTERS[i].color if active else (Color("ffcf62") if p2 else Color(1,1,1,0.12)), 5 if active or p2 else 2)
		draw_character_portrait(i, rect.position + Vector2(130,145), 1.18)
		draw_string(ThemeDB.fallback_font, rect.position + Vector2(18,278), CHARACTERS[i].name, HORIZONTAL_ALIGNMENT_LEFT, -1, 25, Color.WHITE)
		draw_string(ThemeDB.fallback_font, rect.position + Vector2(18,308), CHARACTERS[i].tag, HORIZONTAL_ALIGNMENT_LEFT, -1, 17, CHARACTERS[i].color)
		draw_string(ThemeDB.fallback_font, rect.position + Vector2(18,344), "HP %d   SPD %d" % [CHARACTERS[i].hp, CHARACTERS[i].speed], HORIZONTAL_ALIGNMENT_LEFT, -1, 15, Color("bdd0e8"))
		draw_string(ThemeDB.fallback_font, rect.position + Vector2(18,374), CHARACTERS[i].specials, HORIZONTAL_ALIGNMENT_LEFT, 220, 14, Color("e7d7ff"))
		if active: draw_string(ThemeDB.fallback_font, rect.position + Vector2(18,420), "PLAYER 1", HORIZONTAL_ALIGNMENT_LEFT, -1, 18, Color("63eaff"))
		if p2: draw_string(ThemeDB.fallback_font, rect.position + Vector2(145,420), "PLAYER 2", HORIZONTAL_ALIGNMENT_LEFT, -1, 18, Color("ffcf62"))
	draw_string(ThemeDB.fallback_font, Vector2(270,655), "P1: ← →     P2: Q E     Enter: Continue", HORIZONTAL_ALIGNMENT_LEFT, -1, 20, Color.WHITE)

func draw_character_portrait(idx: int, center: Vector2, scale := 1.0) -> void:
	var c: Color = CHARACTERS[idx].color; var a: Color = CHARACTERS[idx].accent
	draw_circle(center + Vector2(0,38)*scale, 44*scale, Color(0,0,0,0.35))
	draw_rect(Rect2(center + Vector2(-34,-10)*scale, Vector2(68,112)*scale), c, true)
	draw_circle(center + Vector2(0,-32)*scale, 31*scale, a)
	if idx == 0:
		draw_polyline(PackedVector2Array([center+Vector2(-30,-56)*scale,center+Vector2(0,-83)*scale,center+Vector2(30,-56)*scale]), c, 9*scale)
	elif idx == 1:
		draw_rect(Rect2(center+Vector2(-50,10)*scale,Vector2(100,22)*scale),a,true)
	elif idx == 2:
		draw_circle(center+Vector2(0,38)*scale,58*scale,Color(c,0.18),false,5*scale)
	else:
		draw_polygon(PackedVector2Array([center+Vector2(-42,-22)*scale,center+Vector2(42,-22)*scale,center+Vector2(0,35)*scale]),PackedColorArray([Color(a,0.5)]))

func draw_stage_select() -> void:
	draw_background([Color("050716"), Color("1e3156"), Color("5de6ff")]); title("SELECT ARENA", 95, 46)
	var stage = STAGES[selected_stage]
	draw_stage_preview(selected_stage, Rect2(175,150,930,400))
	draw_panel(Rect2(175,565,930,85), Color(0.02,0.04,0.1,0.93), stage.palette[2], 3)
	draw_string(ThemeDB.fallback_font, Vector2(205,602), "◀  %s  ▶" % stage.name, HORIZONTAL_ALIGNMENT_LEFT, -1, 28, Color.WHITE)
	draw_string(ThemeDB.fallback_font, Vector2(205,630), stage.subtitle, HORIZONTAL_ALIGNMENT_LEFT, -1, 17, Color("b8d9f4"))

func draw_stage_preview(idx: int, rect: Rect2) -> void:
	var p = STAGES[idx].palette; draw_rect(rect,p[0]);
	for i in 6: draw_rect(Rect2(rect.position + Vector2(0,i*rect.size.y/6),Vector2(rect.size.x,rect.size.y/6+1)),p[0].lerp(p[1],float(i)/7.0))
	if idx == 0:
		for i in 7: draw_rect(Rect2(rect.position+Vector2(55+i*130,80+(i%2)*45),Vector2(80,190)),Color(0.08,0.11,0.18),true)
		draw_circle(rect.position+Vector2(720,270),70,p[2])
	elif idx == 1:
		for i in 9: draw_circle(rect.position+Vector2(60+i*105,130+(i%3)*45),55,Color(p[2],0.35))
		draw_rect(Rect2(rect.position+Vector2(0,305),Vector2(rect.size.x,55)),Color("18232c"))
	else:
		draw_circle(rect.position+Vector2(730,120),85,Color("d8ddff")); draw_circle(rect.position+Vector2(755,105),70,p[0])
		for i in 5: draw_circle(rect.position+Vector2(90+i*190,285-(i%2)*40),28,p[2],false,5)

func draw_options() -> void:
	draw_background([Color("070a18"), Color("24345e"), Color("40d7bc")]); title("OPTIONS", 105, 50)
	var labels := ["Music Volume", "Effects Volume", "Fullscreen"]
	var values := ["%d%%" % int(music_volume*100), "%d%%" % int(sfx_volume*100), "ON" if fullscreen else "OFF"]
	for i in 3:
		var rect := Rect2(320,190+i*105,640,72); draw_panel(rect,Color(0.03,0.05,0.13,0.9),Color("63eaff") if i==menu_index else Color(1,1,1,0.14),3)
		draw_string(ThemeDB.fallback_font,rect.position+Vector2(24,44),labels[i],HORIZONTAL_ALIGNMENT_LEFT,-1,22,Color.WHITE)
		draw_string(ThemeDB.fallback_font,rect.position+Vector2(480,44),values[i],HORIZONTAL_ALIGNMENT_LEFT,-1,22,Color("83f7dd"))
	draw_string(ThemeDB.fallback_font,Vector2(350,580),"Arrow keys adjust • Esc returns • Settings save beside the portable EXE",HORIZONTAL_ALIGNMENT_LEFT,-1,17,Color("b8d9f4"))

func draw_controls() -> void:
	draw_background([Color("080a19"),Color("222f58"),Color("ef4b8f")]); title("CONTROLS", 90, 48)
	draw_panel(Rect2(90,135,520,475),Color(0.03,0.05,0.12,0.9),Color("63eaff"),3)
	draw_panel(Rect2(670,135,520,475),Color(0.03,0.05,0.12,0.9),Color("ffcf62"),3)
	draw_string(ThemeDB.fallback_font,Vector2(125,185),"PLAYER 1",HORIZONTAL_ALIGNMENT_LEFT,-1,28,Color("63eaff"))
	draw_string(ThemeDB.fallback_font,Vector2(705,185),"PLAYER 2",HORIZONTAL_ALIGNMENT_LEFT,-1,28,Color("ffcf62"))
	var p1 := ["Move: Arrow keys","Light: Z","Heavy: X","Special: C","Jump: V","Dash / Guard: B","Pause: Esc"]
	var p2 := ["Move: W A S D","Light: F","Heavy: G","Special: H","Jump: R","Dash / Guard: T","Gamepads: 1 and 2"]
	for i in p1.size():
		draw_string(ThemeDB.fallback_font,Vector2(125,235+i*48),p1[i],HORIZONTAL_ALIGNMENT_LEFT,-1,21,Color.WHITE)
		draw_string(ThemeDB.fallback_font,Vector2(705,235+i*48),p2[i],HORIZONTAL_ALIGNMENT_LEFT,-1,21,Color.WHITE)
	draw_string(ThemeDB.fallback_font,Vector2(390,665),"Enter / Space / Backspace: Return",HORIZONTAL_ALIGNMENT_LEFT,-1,19,Color("c5daf0"))

func draw_game() -> void:
	draw_arena()
	for obj in objects: draw_object(obj)
	for item in pickups: draw_pickup(item)
	var sorted := fighters.duplicate(); sorted.sort_custom(func(a,b): return a.pos.y < b.pos.y)
	for f in sorted: draw_fighter(f)
	for p in projectiles: draw_projectile(p)
	for p in particles: draw_particle(p)
	draw_hud()
	if message_timer > 0.0: title(message, 215, 34)
	if get_tree().paused:
		draw_rect(Rect2(0,0,W,H),Color(0,0,0,0.70)); title("PAUSED", 300, 64); title("Enter: Resume   R: Restart   Q: Main Menu", 370, 22)

func draw_arena() -> void:
	var p = STAGES[selected_stage].palette; draw_background(p)
	if selected_stage == 0:
		for i in 11: draw_rect(Rect2(i*130,150-(i%3)*35,85,190+(i%3)*35),Color(0.03,0.05,0.10,0.92))
		draw_circle(Vector2(1030,190),85,p[2],false,8)
	elif selected_stage == 1:
		for i in 12: draw_circle(Vector2(i*115,210+(i%3)*22),70,Color(p[2],0.26))
		draw_rect(Rect2(0,235,W,55),Color("172b31"))
	else:
		draw_circle(Vector2(1010,145),105,Color("d9e4ff")); draw_circle(Vector2(1042,125),88,p[0])
		for i in 8: draw_circle(Vector2(110+i*155,235-(i%2)*40),18,p[2],false,4)
	var floor_color: Color = p[1].darkened(0.38)
	draw_polygon(PackedVector2Array([Vector2(50,265),Vector2(1230,265),Vector2(1190,630),Vector2(90,630)]),PackedColorArray([floor_color]))
	for y in range(300,630,55): draw_line(Vector2(75,y),Vector2(1205,y),Color(1,1,1,0.08),2)
	for x in range(100,1200,100): draw_line(Vector2(x,285),Vector2(640+(x-640)*0.92,630),Color(1,1,1,0.06),2)
	draw_polyline(PackedVector2Array([Vector2(50,265),Vector2(1230,265),Vector2(1190,630),Vector2(90,630),Vector2(50,265)]),p[2],4)

func draw_object(obj: Dictionary) -> void:
	var pos: Vector2 = obj.pos
	draw_ellipse_shadow(pos, 34, 12)
	if obj.kind == "reactor":
		draw_circle(pos-Vector2(0,34),28,Color("3d4862")); draw_circle(pos-Vector2(0,34),17,Color("66edff"),false,5)
	else:
		draw_rect(Rect2(pos-Vector2(28,54),Vector2(56,54)),Color("75513d")); draw_rect(Rect2(pos-Vector2(28,54),Vector2(56,54)),Color("d49a62"),false,4); draw_line(pos-Vector2(24,50),pos+Vector2(24,-4),Color("d49a62"),4)

func draw_pickup(item: Dictionary) -> void:
	var pos: Vector2 = item.pos + Vector2(0, sin(item.bob)*8-28); var color: Color = {"health":Color("ff657a"),"energy":Color("62dfff"),"weapon":Color("ffd45c")}.get(item.kind,Color.WHITE)
	draw_circle(pos,18,Color(0,0,0,0.35)); draw_circle(pos,14,color); draw_circle(pos,14,Color.WHITE,false,3)

func draw_fighter(f: Dictionary) -> void:
	var pos: Vector2 = f.pos; draw_ellipse_shadow(pos, 36, 12)
	if f.dead:
		draw_line(pos-Vector2(38,10),pos+Vector2(38,5),Color(f.color,0.45),18); return
	var body_pos := pos - Vector2(0,f.z+58)
	var c: Color = Color.WHITE if f.hit_flash > 0.0 else f.color; var a: Color = f.accent
	if f.block: draw_arc(body_pos,54,0,TAU,32,Color(a,0.55),6)
	if f.dash > 0.0:
		for i in 3: draw_line(body_pos-Vector2(f.facing*(25+i*18),0),body_pos-Vector2(f.facing*(70+i*25),0),Color(c,0.25),12-i*2)
	draw_line(body_pos+Vector2(-18,30),body_pos+Vector2(-22,70),c.darkened(0.25),14)
	draw_line(body_pos+Vector2(18,30),body_pos+Vector2(22,70),c.darkened(0.25),14)
	draw_rect(Rect2(body_pos-Vector2(27,20),Vector2(54,72)),c,true)
	draw_circle(body_pos-Vector2(0,43),24,a)
	var arm_y := -3.0 if f.attack_timer <= 0.0 else -18.0
	draw_line(body_pos+Vector2(0,arm_y),body_pos+Vector2(f.facing*(48 if f.attack_timer>0 else 35),arm_y-8),c,15)
	if f.attack_timer > 0.0:
		draw_arc(body_pos+Vector2(f.facing*50,-10),40,-1.2 if f.facing>0 else 1.9,1.2 if f.facing>0 else 4.3,20,Color(a,0.8),7)
	if int(f.char)==0: draw_polyline(PackedVector2Array([body_pos+Vector2(-20,-60),body_pos+Vector2(0,-84),body_pos+Vector2(20,-60)]),c,6)
	elif int(f.char)==1: draw_rect(Rect2(body_pos+Vector2(-38,-5),Vector2(76,16)),a,true)
	elif int(f.char)==2: draw_arc(body_pos,43,0,TAU,24,Color(a,0.45),4)
	else: draw_polygon(PackedVector2Array([body_pos+Vector2(-34,-23),body_pos+Vector2(34,-23),body_pos+Vector2(0,18)]),PackedColorArray([Color(a,0.3)]))
	if f.enemy_type == "boss": draw_arc(body_pos-Vector2(0,48),34,PI,TAU,16,Color("ffdf63"),7)
	var bar_w := 76.0; draw_rect(Rect2(pos+Vector2(-38,-f.z-120),Vector2(bar_w,7)),Color(0,0,0,0.6)); draw_rect(Rect2(pos+Vector2(-38,-f.z-120),Vector2(bar_w*clamp(f.hp/f.max_hp,0,1),7)),Color("53ef8d") if f.team==1 else Color("ff596e"))

func draw_ellipse_shadow(center: Vector2, rx: float, ry: float) -> void:
	var points := PackedVector2Array()
	for i in 24: points.append(center+Vector2(cos(TAU*i/24.0)*rx,sin(TAU*i/24.0)*ry))
	draw_polygon(points,PackedColorArray([Color(0,0,0,0.36)]))

func draw_projectile(p: Dictionary) -> void:
	draw_circle(p.pos,p.radius*1.7,Color(p.color,0.18)); draw_circle(p.pos,p.radius,p.color); draw_circle(p.pos,p.radius,Color.WHITE,false,3)

func draw_particle(p: Dictionary) -> void:
	var t: float = p.life/p.max; draw_circle(p.pos,p.size*(1.0-t),Color(p.color,t),false,5)

func draw_hud() -> void:
	var players := fighters.filter(func(f): return f.player >= 0)
	for i in players.size():
		var f = players[i]; var x := 35.0 if i==0 else 765.0
		draw_panel(Rect2(x,24,480,82),Color(0.02,0.03,0.08,0.88),f.color,3)
		draw_string(ThemeDB.fallback_font,Vector2(x+18,50),"P%d  %s"%[i+1,f.name],HORIZONTAL_ALIGNMENT_LEFT,-1,19,Color.WHITE)
		draw_rect(Rect2(x+18,62,440,15),Color("251d2d")); draw_rect(Rect2(x+18,62,440*clamp(f.hp/f.max_hp,0,1),15),Color("ff5b75"))
		draw_rect(Rect2(x+18,82,440,9),Color("16243c")); draw_rect(Rect2(x+18,82,440*clamp(f.energy/f.max_energy,0,1),9),Color("55dfff"))
		if f.combo>1: draw_string(ThemeDB.fallback_font,Vector2(x+370,50),"%d HIT"%f.combo,HORIZONTAL_ALIGNMENT_LEFT,-1,18,Color("fff06a"))
	draw_string(ThemeDB.fallback_font,Vector2(560,44),"WAVE %d"%wave if selected_mode in ["stage","survival"] else selected_mode.to_upper(),HORIZONTAL_ALIGNMENT_LEFT,-1,19,Color.WHITE)
	draw_string(ThemeDB.fallback_font,Vector2(568,72),"SCORE %06d"%score,HORIZONTAL_ALIGNMENT_LEFT,-1,16,Color("a7c9e8"))

func draw_result() -> void:
	draw_background([Color("050817"),Color("2c235d"),Color("ff4f9b")]); title(result_text,250,66)
	title("Score %06d   •   Time %02d:%02d"%[score,int(game_time)/60,int(game_time)%60],330,24)
	draw_menu_button("RETURN TO MAIN MENU",Rect2(400,405,480,62),true)

func run_smoke_test() -> void:
	start_match("training")
	var p = get_player(0)
	if p == null:
		get_tree().quit(1)
		return
	var dummy: Dictionary = fighters[1]
	var before: float = dummy.hp
	perform_attack(p,"light")
	var ok: bool = screen=="game" and fighters.size()>=2 and dummy.hp < before and p.pos.x >= ARENA.position.x
	var log_path := OS.get_executable_path().get_base_dir().path_join("smoke-test.log") if not OS.has_feature("editor") else "user://smoke-test.log"
	var file := FileAccess.open(log_path,FileAccess.WRITE)
	if file: file.store_line("Neon Rift smoke test: %s"%("PASS" if ok else "FAIL")); file.store_line("fighters=%d damage=%s"%[fighters.size(),str(dummy.hp<before)])
	get_tree().quit(0 if ok else 1)

func capture_ci_gallery() -> void:
	var dir := "res://artifacts/screenshots"
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(dir))
	await get_tree().process_frame; await get_tree().process_frame
	await save_capture(dir.path_join("01-main-menu.png"))
	screen="character_select"; await save_capture(dir.path_join("02-character-select.png"))
	screen="stage_select"; await save_capture(dir.path_join("03-stage-select.png"))
	start_match("stage"); await get_tree().process_frame; await save_capture(dir.path_join("04-stage-combat.png"))
	var p = get_player(0)
	if p:
		perform_attack(p,"special")
	await get_tree().process_frame; await save_capture(dir.path_join("05-special-attack.png"))
	selected_stage=2; start_match("stage"); wave=2; fighters = fighters.filter(func(f): return f.player>=0); spawn_enemy("boss",Vector2(900,455)); await save_capture(dir.path_join("06-boss-fight.png"))
	get_tree().paused=true; await save_capture(dir.path_join("07-pause-menu.png")); get_tree().paused=false
	result_text="STAGE CLEARED"; screen="result"; await save_capture(dir.path_join("08-result.png"))
	get_tree().quit()

func save_capture(path: String) -> void:
	queue_redraw(); await get_tree().process_frame; await RenderingServer.frame_post_draw
	get_viewport().get_texture().get_image().save_png(path)
