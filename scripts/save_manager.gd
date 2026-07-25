extends RefCounted
class_name RunnerSaveManager

const SAVE_PATH := "user://nebula_stride.cfg"

static func defaults() -> Dictionary:
    return {
        "highscore": 0,
        "tutorial_done": false,
        "music": true,
        "sfx": true,
        "vibration": true,
        "volume": 0.75,
    }

static func load_data() -> Dictionary:
    var data := defaults()
    var config := ConfigFile.new()
    var error := config.load(SAVE_PATH)
    if error != OK:
        return data
    data.highscore = maxi(0, int(config.get_value("progress", "highscore", 0)))
    data.tutorial_done = bool(config.get_value("progress", "tutorial_done", false))
    data.music = bool(config.get_value("settings", "music", true))
    data.sfx = bool(config.get_value("settings", "sfx", true))
    data.vibration = bool(config.get_value("settings", "vibration", true))
    data.volume = clampf(float(config.get_value("settings", "volume", 0.75)), 0.0, 1.0)
    return data

static func save_data(data: Dictionary) -> Error:
    var config := ConfigFile.new()
    config.set_value("progress", "highscore", maxi(0, int(data.get("highscore", 0))))
    config.set_value("progress", "tutorial_done", bool(data.get("tutorial_done", false)))
    config.set_value("settings", "music", bool(data.get("music", true)))
    config.set_value("settings", "sfx", bool(data.get("sfx", true)))
    config.set_value("settings", "vibration", bool(data.get("vibration", true)))
    config.set_value("settings", "volume", clampf(float(data.get("volume", 0.75)), 0.0, 1.0))
    return config.save(SAVE_PATH)

static func clear_data() -> void:
    if FileAccess.file_exists(SAVE_PATH):
        DirAccess.remove_absolute(SAVE_PATH)
