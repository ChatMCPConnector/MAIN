extends RefCounted
class_name RunnerGameModel

const Config := preload("res://scripts/game_config.gd")

enum State { START, TUTORIAL, COUNTDOWN, PLAYING, PAUSED, GAME_OVER }

var state: int = State.START
var lane: int = 1
var speed: float = Config.START_SPEED
var distance: float = 0.0
var score: int = 0
var collectibles: int = 0
var difficulty: float = 0.0
var seed_value: int = 1337

func reset(seed: int = 1337) -> void:
    state = State.COUNTDOWN
    lane = 1
    speed = Config.START_SPEED
    distance = 0.0
    score = 0
    collectibles = 0
    difficulty = 0.0
    seed_value = seed

func start_playing() -> void:
    state = State.PLAYING

func tick(delta: float) -> void:
    if state != State.PLAYING:
        return
    speed = minf(Config.MAX_SPEED, speed + Config.SPEED_GAIN * delta)
    distance += speed * delta
    difficulty = clampf(distance / 900.0, 0.0, 1.0)
    score = int(distance * Config.SCORE_PER_METER) + collectibles * Config.COLLECTIBLE_SCORE

func move_lane(direction: int) -> bool:
    if state != State.PLAYING and state != State.TUTORIAL:
        return false
    var previous := lane
    lane = clampi(lane + direction, 0, 2)
    return lane != previous

func add_collectible(amount: int = 1) -> void:
    collectibles += maxi(0, amount)
    score = int(distance * Config.SCORE_PER_METER) + collectibles * Config.COLLECTIBLE_SCORE

func pause() -> bool:
    if state != State.PLAYING:
        return false
    state = State.PAUSED
    return true

func resume() -> bool:
    if state != State.PAUSED:
        return false
    state = State.PLAYING
    return true

func game_over() -> void:
    state = State.GAME_OVER

static func pattern_is_solvable(pattern: Array) -> bool:
    if pattern.size() != 3:
        return false
    for entry in pattern:
        if int(entry) != 1:
            return true
    return false
