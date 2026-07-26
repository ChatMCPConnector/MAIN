extends SceneTree

const GameModel := preload("res://scripts/game_model.gd")
const SaveManager := preload("res://scripts/save_manager.gd")
const Config := preload("res://scripts/game_config.gd")
const AudioManager := preload("res://scripts/audio_manager.gd")

var failures := 0
var checks := 0

func _init() -> void:
    call_deferred("_run")

func _check(condition: bool, message: String) -> void:
    checks += 1
    if not condition:
        failures += 1
        push_error("TEST FAILED: " + message)

func _run() -> void:
    var model := GameModel.new()
    model.reset(777)
    model.start_playing()
    _check(model.lane == 1, "runner starts in center lane")
    _check(model.move_lane(-1) and model.lane == 0, "lane moves left")
    _check(not model.move_lane(-1) and model.lane == 0, "left lane boundary")
    _check(model.move_lane(1) and model.move_lane(1) and model.lane == 2, "lane moves right")
    _check(not model.move_lane(1) and model.lane == 2, "right lane boundary")
    var before := model.speed
    model.tick(20.0)
    _check(model.speed > before, "speed increases")
    for i in range(1000):
        model.tick(0.2)
    _check(model.speed <= Config.MAX_SPEED, "speed is capped")
    _check(model.score > 0 and model.distance > 0.0, "distance creates score")
    var score_before := model.score
    model.add_collectible()
    _check(model.collectibles == 1 and model.score == score_before + Config.COLLECTIBLE_SCORE, "collectible score")
    _check(GameModel.pattern_is_solvable([1, 0, 1]), "open lane pattern is solvable")
    _check(GameModel.pattern_is_solvable([2, 1, 3]), "action lane pattern is solvable")
    _check(not GameModel.pattern_is_solvable([1, 1, 1]), "fully lethal pattern is rejected")
    _check(not GameModel.pattern_is_solvable([0, 1]), "invalid pattern width is rejected")
    _check(model.pause() and model.state == GameModel.State.PAUSED, "pause transition")
    _check(model.resume() and model.state == GameModel.State.PLAYING, "resume transition")
    model.game_over()
    _check(model.state == GameModel.State.GAME_OVER, "game-over transition")
    model.reset(777)
    _check(model.score == 0 and model.collectibles == 0 and model.speed == Config.START_SPEED, "restart resets run")
    var defaults := SaveManager.defaults()
    _check(defaults.highscore == 0 and defaults.tutorial_done == false, "safe save defaults")

    var audio := AudioManager.new()
    var music: AudioStreamWAV = audio._make_music()
    _check(music.format == AudioStreamWAV.FORMAT_16_BITS, "procedural music uses 16-bit PCM")
    _check(music.mix_rate == 22050, "procedural music sample rate")
    _check(not music.stereo, "procedural music is mono")
    _check(music.data.size() == 22050 * 4 * 2, "procedural music buffer size")
    _check(music.loop_mode == AudioStreamWAV.LOOP_DISABLED, "procedural music avoids unsafe PCM loop boundary")
    audio.free()

    print("Nebula Stride tests: %d checks, %d failures" % [checks, failures])
    quit(failures)
