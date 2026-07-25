extends Node
class_name RunnerAudioManager

var music_player: AudioStreamPlayer
var sfx_player: AudioStreamPlayer
var music_enabled := true
var sfx_enabled := true
var volume := 0.75

func _ready() -> void:
    music_player = AudioStreamPlayer.new()
    sfx_player = AudioStreamPlayer.new()
    add_child(music_player)
    add_child(sfx_player)
    music_player.stream = _make_music()
    music_player.finished.connect(_restart_music)

func configure(data: Dictionary) -> void:
    music_enabled = bool(data.get("music", true))
    sfx_enabled = bool(data.get("sfx", true))
    volume = clampf(float(data.get("volume", 0.75)), 0.0, 1.0)
    music_player.volume_db = linear_to_db(maxf(0.01, volume * 0.45))
    sfx_player.volume_db = linear_to_db(maxf(0.01, volume))
    if music_enabled and not music_player.playing:
        music_player.play()
    elif not music_enabled:
        music_player.stop()

func play_sfx(kind: String) -> void:
    if not sfx_enabled:
        return
    var frequency := 520.0
    var duration := 0.10
    match kind:
        "collect":
            frequency = 960.0
            duration = 0.12
        "jump":
            frequency = 620.0
        "slide":
            frequency = 390.0
        "lane":
            frequency = 460.0
            duration = 0.06
        "hit":
            frequency = 120.0
            duration = 0.32
        "button":
            frequency = 720.0
            duration = 0.05
    sfx_player.stream = _make_tone(frequency, duration, 0.32)
    sfx_player.play()

func pause_music() -> void:
    if music_player.playing:
        music_player.stream_paused = true

func resume_music() -> void:
    if music_enabled:
        if not music_player.playing:
            music_player.play()
        music_player.stream_paused = false

func _restart_music() -> void:
    if music_enabled:
        music_player.play()

func _make_music() -> AudioStreamWAV:
    var sample_rate := 22050
    var duration := 4.0
    var frames := int(sample_rate * duration)
    var bytes := PackedByteArray()
    bytes.resize(frames * 2)
    var notes := PackedFloat32Array([220.0, 277.18, 329.63, 440.0, 329.63, 277.18, 246.94, 329.63])
    for i in range(frames):
        var beat := int(float(i) / sample_rate / 0.5) % notes.size()
        var t := float(i) / sample_rate
        var value := sin(TAU * notes[beat] * t) * 0.10 + sin(TAU * notes[beat] * 0.5 * t) * 0.05
        _write_sample(bytes, i, value)
    var stream := AudioStreamWAV.new()
    stream.format = AudioStreamWAV.FORMAT_16_BITS
    stream.mix_rate = sample_rate
    stream.stereo = false
    stream.data = bytes
    stream.loop_mode = AudioStreamWAV.LOOP_FORWARD
    stream.loop_begin = 0
    stream.loop_end = frames
    return stream

func _make_tone(frequency: float, duration: float, strength: float) -> AudioStreamWAV:
    var sample_rate := 22050
    var frames := int(sample_rate * duration)
    var bytes := PackedByteArray()
    bytes.resize(frames * 2)
    for i in range(frames):
        var t := float(i) / sample_rate
        var envelope := 1.0 - float(i) / frames
        _write_sample(bytes, i, sin(TAU * frequency * t) * strength * envelope)
    var stream := AudioStreamWAV.new()
    stream.format = AudioStreamWAV.FORMAT_16_BITS
    stream.mix_rate = sample_rate
    stream.stereo = false
    stream.data = bytes
    return stream

func _write_sample(bytes: PackedByteArray, frame: int, value: float) -> void:
    var sample := int(clampf(value, -1.0, 1.0) * 32767.0)
    if sample < 0:
        sample += 65536
    bytes[frame * 2] = sample & 0xff
    bytes[frame * 2 + 1] = (sample >> 8) & 0xff
