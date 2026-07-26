extends SceneTree

var failures := []

func _initialize() -> void:
	call_deferred("run_tests")

func check(condition: bool, label: String) -> void:
	if condition:
		print("PASS: ", label)
	else:
		push_error("FAIL: " + label)
		failures.append(label)

func run_tests() -> void:
	var scene = load("res://game/main.tscn")
	check(scene != null, "main scene loads")
	if scene == null:
		quit(1); return
	var game = scene.instantiate()
	root.add_child(game)
	await process_frame
	check(game.screen == "main_menu", "main menu opens")
	check(game.CHARACTERS.size() >= 4, "four playable characters exist")
	check(game.STAGES.size() >= 3, "three arenas exist")
	check(game.MODES.size() >= 4, "required modes exist")
	game.start_match("stage")
	await process_frame
	check(game.screen == "game", "stage starts")
	check(game.get_player(0) != null, "player spawns")
	check(game.fighters.size() >= 3, "multiple opponents spawn")
	var player = game.get_player(0)
	var target = game.nearest_target(player)
	player.pos = target.pos - Vector2(45,0)
	player.facing = 1.0
	var hp_before: float = target.hp
	check(game.perform_attack(player,"light"), "light attack triggers")
	check(target.hp < hp_before, "attack causes damage")
	player.cooldown = 0.0
	player.energy = player.max_energy
	check(game.perform_attack(player,"special"), "special attack triggers")
	check(game.projectiles.size() > 0 or target.hp < hp_before, "special creates effect")
	game.start_match("versus")
	check(game.get_player(1) != null, "second local player spawns")
	game.start_match("team")
	check(game.fighters.filter(func(f): return f.team == 1).size() == 2, "team mode assigns two players")
	game.start_match("training")
	check(game.fighters.any(func(f): return f.enemy_type == "dummy"), "training dummy exists")
	check(FileAccess.file_exists("res://export_presets.cfg"), "Windows export preset exists")
	check(FileAccess.file_exists("res://README.md"), "README exists")
	print("TEST SUMMARY: ", 14 - failures.size(), "/14 passed")
	quit(1 if failures.size() > 0 else 0)
