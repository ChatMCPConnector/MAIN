extends Node

const Config := preload("res://scripts/game_config.gd")
const GameModel := preload("res://scripts/game_model.gd")
const SaveManager := preload("res://scripts/save_manager.gd")
const PlayerController := preload("res://scripts/player_controller.gd")
const TrackManager := preload("res://scripts/track_manager.gd")
const AudioManager := preload("res://scripts/audio_manager.gd")

var model := GameModel.new()
var save_data: Dictionary
var player: RunnerPlayerController
var track: RunnerTrackManager
var audio: RunnerAudioManager
var ui_root: Control
var menu_panel: Control
var tutorial_panel: Control
var settings_panel: Control
var credits_panel: Control
var pause_panel: Control
var game_over_panel: Control
var hud: Control
var score_label: Label
var shard_label: Label
var highscore_label: Label
var tutorial_text: Label
var tutorial_progress: Label
var countdown_label: Label
var final_score_label: Label
var final_highscore_label: Label
var final_shards_label: Label
var swipe_start := Vector2.ZERO
var mouse_swipe := false
var tutorial_step := 0
var countdown_active := false

func _ready() -> void:
    process_mode = Node.PROCESS_MODE_ALWAYS
    save_data = SaveManager.load_data()
    _build_world()
    _build_ui()
    audio.configure(save_data)
    if bool(save_data.tutorial_done):
        _show_menu()
    else:
        _start_tutorial()

func _build_world() -> void:
    var environment_node := WorldEnvironment.new()
    var environment := Environment.new()
    environment.background_mode = Environment.BG_COLOR
    environment.background_color = Color("07102d")
    environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
    environment.ambient_light_color = Color("6387c5")
    environment.ambient_light_energy = 0.85
    environment.tonemap_mode = Environment.TONE_MAPPER_FILMIC
    environment.glow_enabled = true
    environment.glow_intensity = 0.75
    environment_node.environment = environment
    add_child(environment_node)
    var light := DirectionalLight3D.new()
    light.rotation_degrees = Vector3(-52.0, -25.0, 0.0)
    light.light_energy = 1.15
    light.shadow_enabled = false
    add_child(light)
    track = TrackManager.new()
    track.name = "TrackManager"
    add_child(track)
    track.obstacle_reached.connect(_on_obstacle_reached)
    track.collectible_reached.connect(_on_collectible_reached)
    player = PlayerController.new()
    player.name = "Player"
    add_child(player)
    var camera := Camera3D.new()
    camera.name = "RunnerCamera"
    camera.position = Vector3(0.0, 5.4, 9.6)
    camera.fov = 66.0
    add_child(camera)
    camera.look_at(Vector3(0.0, 1.1, -10.5), Vector3.UP)
    audio = AudioManager.new()
    add_child(audio)
    _add_star_field()

func _add_star_field() -> void:
    var rng := RandomNumberGenerator.new()
    rng.seed = 8181
    for index in range(70):
        var star := MeshInstance3D.new()
        var mesh := SphereMesh.new()
        mesh.radius = rng.randf_range(0.03, 0.08)
        mesh.height = mesh.radius * 2.0
        mesh.radial_segments = 6
        mesh.rings = 4
        star.mesh = mesh
        var material := StandardMaterial3D.new()
        material.albedo_color = Color("d6ecff")
        material.emission_enabled = true
        material.emission = Color("8edbff")
        material.emission_energy_multiplier = 1.6
        star.material_override = material
        star.position = Vector3(rng.randf_range(-25.0, 25.0), rng.randf_range(5.0, 18.0), rng.randf_range(-100.0, -10.0))
        add_child(star)

func _build_ui() -> void:
    var layer := CanvasLayer.new()
    add_child(layer)
    ui_root = Control.new()
    ui_root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    layer.add_child(ui_root)
    var theme := Theme.new()
    theme.default_font_size = 24
    ui_root.theme = theme
    hud = _build_hud()
    menu_panel = _build_menu()
    tutorial_panel = _build_tutorial()
    settings_panel = _build_settings()
    credits_panel = _build_credits()
    pause_panel = _build_pause()
    game_over_panel = _build_game_over()
    countdown_label = Label.new()
    countdown_label.set_anchors_preset(Control.PRESET_CENTER)
    countdown_label.position = Vector2(-120, -80)
    countdown_label.size = Vector2(240, 160)
    countdown_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    countdown_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
    countdown_label.add_theme_font_size_override("font_size", 92)
    countdown_label.add_theme_color_override("font_color", Color("ffffff"))
    countdown_label.visible = false
    ui_root.add_child(countdown_label)

func _build_hud() -> Control:
    var root := Control.new()
    root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    root.visible = false
    ui_root.add_child(root)
    score_label = _label("PUNKTE 0", 30, Color("d8f7ff"))
    score_label.position = Vector2(28, 20)
    score_label.size = Vector2(360, 50)
    root.add_child(score_label)
    shard_label = _label("STERNSPLITTER 0", 24, Color("ffd84a"))
    shard_label.position = Vector2(28, 70)
    shard_label.size = Vector2(380, 44)
    root.add_child(shard_label)
    var pause_button := _button("Ⅱ  PAUSE")
    pause_button.set_anchors_preset(Control.PRESET_TOP_RIGHT)
    pause_button.position = Vector2(-215, 24)
    pause_button.size = Vector2(185, 54)
    pause_button.pressed.connect(_pause_game)
    root.add_child(pause_button)
    return root

func _build_menu() -> Control:
    var panel := _panel(Vector2(600, 570))
    var box := _vbox(panel)
    box.add_child(_title("NEBULA STRIDE"))
    var subtitle := _label("Fliehe durch die zerfallende Sternenstadt Asterion.", 21, Color("a9c8ff"))
    subtitle.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    box.add_child(subtitle)
    highscore_label = _label("HIGHSCORE 0", 30, Color("ffd84a"))
    highscore_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    box.add_child(highscore_label)
    box.add_child(_spacer(12))
    var play := _button("SPIELEN")
    play.pressed.connect(_begin_run)
    box.add_child(play)
    var tutorial := _button("TUTORIAL")
    tutorial.pressed.connect(_start_tutorial)
    box.add_child(tutorial)
    var settings := _button("EINSTELLUNGEN")
    settings.pressed.connect(_show_settings)
    box.add_child(settings)
    var credits := _button("CREDITS & LIZENZEN")
    credits.pressed.connect(_show_credits)
    box.add_child(credits)
    return panel

func _build_tutorial() -> Control:
    var panel := _panel(Vector2(700, 570))
    var box := _vbox(panel)
    box.add_child(_title("STEUERUNGSTRAINING"))
    tutorial_progress = _label("SCHRITT 1 / 4", 22, Color("ffd84a"))
    tutorial_progress.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    box.add_child(tutorial_progress)
    tutorial_text = _label("Wische nach links, um die Spur zu wechseln.", 29, Color.WHITE)
    tutorial_text.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    tutorial_text.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
    tutorial_text.custom_minimum_size = Vector2(0, 180)
    tutorial_text.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    box.add_child(tutorial_text)
    var hint := _label("Links/rechts: Spurwechsel · Oben: Sprung · Unten: Rutschen\nGelbe Sternsplitter geben Bonuspunkte. Weiche roten und violetten Hindernissen aus.", 19, Color("a9c8ff"))
    hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    box.add_child(hint)
    box.add_child(_spacer(10))
    var skip := _button("ÜBERSPRINGEN")
    skip.pressed.connect(_finish_tutorial)
    box.add_child(skip)
    return panel

func _build_settings() -> Control:
    var panel := _panel(Vector2(620, 590))
    var box := _vbox(panel)
    box.add_child(_title("EINSTELLUNGEN"))
    var music := CheckButton.new()
    music.text = "Musik"
    music.button_pressed = bool(save_data.music)
    music.toggled.connect(func(value: bool): save_data.music = value; _save_settings())
    box.add_child(music)
    var sfx := CheckButton.new()
    sfx.text = "Soundeffekte"
    sfx.button_pressed = bool(save_data.sfx)
    sfx.toggled.connect(func(value: bool): save_data.sfx = value; _save_settings())
    box.add_child(sfx)
    var vibration := CheckButton.new()
    vibration.text = "Vibration"
    vibration.button_pressed = bool(save_data.vibration)
    vibration.toggled.connect(func(value: bool): save_data.vibration = value; _save_settings())
    box.add_child(vibration)
    var volume_label := _label("Lautstärke", 22, Color.WHITE)
    box.add_child(volume_label)
    var slider := HSlider.new()
    slider.min_value = 0.0
    slider.max_value = 1.0
    slider.step = 0.05
    slider.value = float(save_data.volume)
    slider.value_changed.connect(func(value: float): save_data.volume = value; _save_settings())
    box.add_child(slider)
    var reset_tutorial := _button("TUTORIAL ZURÜCKSETZEN")
    reset_tutorial.pressed.connect(func(): save_data.tutorial_done = false; RunnerSaveManager.save_data(save_data); _start_tutorial())
    box.add_child(reset_tutorial)
    var reset_data := _button("SPIELDATEN ZURÜCKSETZEN")
    reset_data.pressed.connect(_reset_data_confirmed)
    box.add_child(reset_data)
    var back := _button("ZURÜCK")
    back.pressed.connect(_show_menu)
    box.add_child(back)
    return panel

func _build_credits() -> Control:
    var panel := _panel(Vector2(760, 600))
    var box := _vbox(panel)
    box.add_child(_title("CREDITS & LIZENZEN"))
    var text := _label("Nebula Stride ist eine eigenständige Produktion.\n\nKonzept, Code, Low-Poly-Geometrie, Farben, Musik und Soundeffekte wurden für dieses Projekt erstellt. Es werden keine externen Laufzeit-Assets, Tracker, Werbung oder Netzwerkdienste verwendet.\n\nEngine: Godot Engine, MIT-Lizenz.", 21, Color("d4e4ff"))
    text.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    text.custom_minimum_size = Vector2(0, 350)
    text.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
    box.add_child(text)
    var back := _button("ZURÜCK")
    back.pressed.connect(_show_menu)
    box.add_child(back)
    return panel

func _build_pause() -> Control:
    var panel := _panel(Vector2(500, 390))
    var box := _vbox(panel)
    box.add_child(_title("PAUSIERT"))
    var resume := _button("WEITERSPIELEN")
    resume.pressed.connect(_resume_game)
    box.add_child(resume)
    var restart := _button("NEU STARTEN")
    restart.pressed.connect(_begin_run)
    box.add_child(restart)
    var menu := _button("HAUPTMENÜ")
    menu.pressed.connect(_show_menu)
    box.add_child(menu)
    return panel

func _build_game_over() -> Control:
    var panel := _panel(Vector2(560, 540))
    var box := _vbox(panel)
    box.add_child(_title("SIGNAL VERLOREN"))
    final_score_label = _label("PUNKTE 0", 32, Color.WHITE)
    final_score_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    box.add_child(final_score_label)
    final_highscore_label = _label("HIGHSCORE 0", 27, Color("ffd84a"))
    final_highscore_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    box.add_child(final_highscore_label)
    final_shards_label = _label("STERNSPLITTER 0", 23, Color("a9c8ff"))
    final_shards_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    box.add_child(final_shards_label)
    var retry := _button("ERNEUT SPIELEN")
    retry.pressed.connect(_begin_run)
    box.add_child(retry)
    var menu := _button("HAUPTMENÜ")
    menu.pressed.connect(_show_menu)
    box.add_child(menu)
    return panel

func _panel(size: Vector2) -> PanelContainer:
    var panel := PanelContainer.new()
    panel.set_anchors_preset(Control.PRESET_CENTER)
    panel.position = -size * 0.5
    panel.size = size
    var style := StyleBoxFlat.new()
    style.bg_color = Color(0.035, 0.06, 0.18, 0.95)
    style.border_color = Color("358bcd")
    style.set_border_width_all(2)
    style.corner_radius_top_left = 24
    style.corner_radius_top_right = 24
    style.corner_radius_bottom_left = 24
    style.corner_radius_bottom_right = 24
    style.content_margin_left = 38
    style.content_margin_right = 38
    style.content_margin_top = 30
    style.content_margin_bottom = 30
    panel.add_theme_stylebox_override("panel", style)
    panel.visible = false
    ui_root.add_child(panel)
    return panel

func _vbox(panel: Control) -> VBoxContainer:
    var box := VBoxContainer.new()
    box.add_theme_constant_override("separation", 13)
    panel.add_child(box)
    return box

func _title(text: String) -> Label:
    var label := _label(text, 43, Color("54dbff"))
    label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    return label

func _label(text: String, size: int, color: Color) -> Label:
    var label := Label.new()
    label.text = text
    label.add_theme_font_size_override("font_size", size)
    label.add_theme_color_override("font_color", color)
    return label

func _button(text: String) -> Button:
    var button := Button.new()
    button.text = text
    button.custom_minimum_size = Vector2(0, 52)
    button.add_theme_font_size_override("font_size", 22)
    button.pressed.connect(func():
        if audio != null:
            audio.play_sfx("button")
    )
    return button

func _spacer(height: float) -> Control:
    var spacer := Control.new()
    spacer.custom_minimum_size = Vector2(0, height)
    return spacer

func _physics_process(delta: float) -> void:
    if model.state != RunnerGameModel.State.PLAYING:
        return
    model.tick(delta)
    player.update_player(delta, model.speed)
    track.update_track(delta, model.speed, model.difficulty)
    score_label.text = "PUNKTE %d" % model.score
    shard_label.text = "STERNSPLITTER %d" % model.collectibles

func _unhandled_input(event: InputEvent) -> void:
    if event is InputEventScreenTouch:
        if event.pressed:
            swipe_start = event.position
        else:
            _process_swipe(event.position - swipe_start)
    elif event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT:
        if event.pressed:
            mouse_swipe = true
            swipe_start = event.position
        elif mouse_swipe:
            mouse_swipe = false
            _process_swipe(event.position - swipe_start)
    if event is InputEventKey and event.pressed and not event.echo:
        match event.physical_keycode:
            KEY_A, KEY_LEFT:
                _perform_action("left")
            KEY_D, KEY_RIGHT:
                _perform_action("right")
            KEY_W, KEY_UP:
                _perform_action("up")
            KEY_S, KEY_DOWN:
                _perform_action("down")
            KEY_ESCAPE:
                _pause_game()
            KEY_G:
                if model.state == RunnerGameModel.State.PLAYING:
                    _game_over()

func _process_swipe(delta: Vector2) -> void:
    var threshold := minf(get_viewport().get_visible_rect().size.x, get_viewport().get_visible_rect().size.y) * Config.SWIPE_THRESHOLD_RATIO
    if delta.length() < threshold:
        return
    if absf(delta.x) > absf(delta.y):
        _perform_action("right" if delta.x > 0.0 else "left")
    else:
        _perform_action("down" if delta.y > 0.0 else "up")

func _perform_action(action: String) -> void:
    if model.state == RunnerGameModel.State.TUTORIAL:
        _advance_tutorial(action)
        return
    if model.state != RunnerGameModel.State.PLAYING:
        return
    match action:
        "left":
            if model.move_lane(-1):
                player.set_lane(model.lane)
                audio.play_sfx("lane")
        "right":
            if model.move_lane(1):
                player.set_lane(model.lane)
                audio.play_sfx("lane")
        "up":
            if player.jump():
                audio.play_sfx("jump")
        "down":
            if player.slide():
                audio.play_sfx("slide")

func _start_tutorial() -> void:
    _hide_all_panels()
    model.state = RunnerGameModel.State.TUTORIAL
    tutorial_step = 0
    tutorial_panel.visible = true
    _update_tutorial_text()

func _advance_tutorial(action: String) -> void:
    var expected := ["left", "right", "up", "down"]
    if action != expected[tutorial_step]:
        return
    tutorial_step += 1
    if tutorial_step >= expected.size():
        tutorial_text.text = "Training abgeschlossen! Die Sternsplitter warten auf dich."
        tutorial_progress.text = "BEREIT"
        await get_tree().create_timer(0.45).timeout
        _finish_tutorial()
    else:
        _update_tutorial_text()

func _update_tutorial_text() -> void:
    var messages := [
        "Wische nach links, um die Spur zu wechseln.",
        "Wische nach rechts, um zurückzuwechseln.",
        "Wische nach oben, um Barrieren zu überspringen.",
        "Wische nach unten, um unter Energiebögen zu rutschen.",
    ]
    tutorial_progress.text = "SCHRITT %d / 4" % (tutorial_step + 1)
    tutorial_text.text = messages[tutorial_step]

func _finish_tutorial() -> void:
    save_data.tutorial_done = true
    SaveManager.save_data(save_data)
    _show_menu()

func _begin_run() -> void:
    if countdown_active:
        return
    countdown_active = true
    _hide_all_panels()
    hud.visible = true
    model.reset(int(Time.get_ticks_msec()) if not OS.has_feature("editor") else 424242)
    player.reset_player()
    track.reset(model.seed_value)
    audio.resume_music()
    countdown_label.visible = true
    for text in ["3", "2", "1", "LOS!"]:
        countdown_label.text = text
        await get_tree().create_timer(0.48).timeout
    countdown_label.visible = false
    model.start_playing()
    countdown_active = false

func _pause_game() -> void:
    if not model.pause():
        return
    pause_panel.visible = true
    audio.pause_music()

func _resume_game() -> void:
    if model.resume():
        pause_panel.visible = false
        audio.resume_music()

func _on_obstacle_reached(kind: String, lane: int) -> void:
    if model.state != RunnerGameModel.State.PLAYING or lane != model.lane:
        return
    if kind == "barrier" and player.is_airborne():
        return
    if kind == "arch" and player.is_sliding():
        return
    _game_over()

func _on_collectible_reached(lane: int) -> void:
    if model.state != RunnerGameModel.State.PLAYING or lane != model.lane:
        return
    model.add_collectible()
    audio.play_sfx("collect")
    if bool(save_data.vibration):
        Input.vibrate_handheld(22)

func _game_over() -> void:
    if model.state == RunnerGameModel.State.GAME_OVER:
        return
    model.game_over()
    audio.play_sfx("hit")
    if bool(save_data.vibration):
        Input.vibrate_handheld(120)
    if model.score > int(save_data.highscore):
        save_data.highscore = model.score
        SaveManager.save_data(save_data)
    hud.visible = false
    final_score_label.text = "PUNKTE %d" % model.score
    final_highscore_label.text = "HIGHSCORE %d" % int(save_data.highscore)
    final_shards_label.text = "STERNSPLITTER %d" % model.collectibles
    game_over_panel.visible = true

func _show_menu() -> void:
    countdown_active = false
    model.state = RunnerGameModel.State.START
    _hide_all_panels()
    highscore_label.text = "HIGHSCORE %d" % int(save_data.highscore)
    menu_panel.visible = true
    audio.resume_music()

func _show_settings() -> void:
    _hide_all_panels()
    settings_panel.visible = true

func _show_credits() -> void:
    _hide_all_panels()
    credits_panel.visible = true

func _hide_all_panels() -> void:
    for panel in [menu_panel, tutorial_panel, settings_panel, credits_panel, pause_panel, game_over_panel]:
        if panel != null:
            panel.visible = false
    if hud != null:
        hud.visible = false
    if countdown_label != null:
        countdown_label.visible = false

func _save_settings() -> void:
    SaveManager.save_data(save_data)
    audio.configure(save_data)

func _reset_data_confirmed() -> void:
    save_data = SaveManager.defaults()
    SaveManager.save_data(save_data)
    audio.configure(save_data)
    _start_tutorial()

func _notification(what: int) -> void:
    if (what == MainLoop.NOTIFICATION_APPLICATION_PAUSED or what == MainLoop.NOTIFICATION_APPLICATION_FOCUS_OUT) and model.state == RunnerGameModel.State.PLAYING:
        call_deferred("_pause_game")
