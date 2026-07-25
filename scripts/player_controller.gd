extends Node3D
class_name RunnerPlayerController

const Config := preload("res://scripts/game_config.gd")

var target_lane := 1
var vertical_velocity := 0.0
var jump_height := 0.0
var slide_timer := 0.0
var body_root: Node3D
var left_arm: MeshInstance3D
var right_arm: MeshInstance3D
var left_leg: MeshInstance3D
var right_leg: MeshInstance3D

func _ready() -> void:
    _build_character()
    reset_player()

func reset_player() -> void:
    target_lane = 1
    position = Vector3(Config.LANE_X[1], 0.0, 0.0)
    vertical_velocity = 0.0
    jump_height = 0.0
    slide_timer = 0.0
    scale = Vector3.ONE

func set_lane(lane: int) -> void:
    target_lane = clampi(lane, 0, 2)

func jump() -> bool:
    if jump_height > 0.04 or vertical_velocity > 0.0 or slide_timer > 0.0:
        return false
    vertical_velocity = Config.JUMP_VELOCITY
    return true

func slide() -> bool:
    if jump_height > 0.08 or slide_timer > 0.0:
        return false
    slide_timer = Config.SLIDE_DURATION
    return true

func is_airborne() -> bool:
    return jump_height > 0.72

func is_sliding() -> bool:
    return slide_timer > 0.15

func update_player(delta: float, speed: float) -> void:
    position.x = move_toward(position.x, Config.LANE_X[target_lane], Config.LANE_CHANGE_SPEED * delta)
    if vertical_velocity != 0.0 or jump_height > 0.0:
        vertical_velocity -= Config.GRAVITY * delta
        jump_height = maxf(0.0, jump_height + vertical_velocity * delta)
        if jump_height <= 0.0 and vertical_velocity < 0.0:
            vertical_velocity = 0.0
    var base_height := 0.95
    if slide_timer > 0.0:
        slide_timer = maxf(0.0, slide_timer - delta)
        body_root.scale.y = 0.48
        base_height = 0.48
    else:
        body_root.scale.y = move_toward(body_root.scale.y, 1.0, delta * 8.0)
    body_root.position.y = base_height + jump_height
    var phase := Time.get_ticks_msec() * 0.001 * clampf(speed * 0.75, 6.0, 18.0)
    var swing := sin(phase) * (0.75 if not is_airborne() else 0.2)
    left_arm.rotation.x = swing
    right_arm.rotation.x = -swing
    left_leg.rotation.x = -swing
    right_leg.rotation.x = swing
    body_root.rotation.z = move_toward(body_root.rotation.z, (Config.LANE_X[target_lane] - position.x) * -0.07, delta * 4.0)

func _build_character() -> void:
    body_root = Node3D.new()
    body_root.name = "AstraRunner"
    add_child(body_root)
    body_root.position.y = 0.95
    var suit := Color("42d9ff")
    var accent := Color("ff4fd8")
    var dark := Color("18204a")
    var torso := _box(Vector3(1.0, 1.45, 0.62), suit)
    torso.position.y = 1.1
    body_root.add_child(torso)
    var head := _sphere(0.48, Color("ffe3c2"))
    head.position.y = 2.15
    body_root.add_child(head)
    var visor := _box(Vector3(0.72, 0.22, 0.12), accent)
    visor.position = Vector3(0.0, 2.2, -0.43)
    body_root.add_child(visor)
    left_arm = _box(Vector3(0.26, 1.15, 0.26), dark)
    right_arm = _box(Vector3(0.26, 1.15, 0.26), dark)
    left_arm.position = Vector3(-0.68, 1.15, 0.0)
    right_arm.position = Vector3(0.68, 1.15, 0.0)
    body_root.add_child(left_arm)
    body_root.add_child(right_arm)
    left_leg = _box(Vector3(0.34, 1.15, 0.38), dark)
    right_leg = _box(Vector3(0.34, 1.15, 0.38), dark)
    left_leg.position = Vector3(-0.28, 0.0, 0.0)
    right_leg.position = Vector3(0.28, 0.0, 0.0)
    body_root.add_child(left_leg)
    body_root.add_child(right_leg)
    var pack := _box(Vector3(0.72, 0.8, 0.25), accent)
    pack.position = Vector3(0.0, 1.1, 0.45)
    body_root.add_child(pack)

func _box(size: Vector3, color: Color) -> MeshInstance3D:
    var mesh := BoxMesh.new()
    mesh.size = size
    var instance := MeshInstance3D.new()
    instance.mesh = mesh
    instance.material_override = _material(color)
    return instance

func _sphere(radius: float, color: Color) -> MeshInstance3D:
    var mesh := SphereMesh.new()
    mesh.radius = radius
    mesh.height = radius * 2.0
    mesh.radial_segments = 12
    mesh.rings = 6
    var instance := MeshInstance3D.new()
    instance.mesh = mesh
    instance.material_override = _material(color)
    return instance

func _material(color: Color) -> StandardMaterial3D:
    var material := StandardMaterial3D.new()
    material.albedo_color = color
    material.metallic = 0.15
    material.roughness = 0.55
    return material
