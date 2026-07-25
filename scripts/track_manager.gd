extends Node3D
class_name RunnerTrackManager

signal obstacle_reached(kind: String, lane: int)
signal collectible_reached(lane: int)

const Config := preload("res://scripts/game_config.gd")

var rng := RandomNumberGenerator.new()
var segments: Array[Node3D] = []
var obstacle_pool: Array[Dictionary] = []
var collectible_pool: Array[Dictionary] = []
var spawn_distance := 10.0
var pattern_counter := 0

func _ready() -> void:
    _build_segments()
    _build_pools()

func reset(seed: int) -> void:
    rng.seed = seed
    spawn_distance = 14.0
    pattern_counter = 0
    for i in range(segments.size()):
        segments[i].position.z = -float(i) * Config.TRACK_SEGMENT_LENGTH
    for item in obstacle_pool:
        item.active = false
        item.node.visible = false
    for item in collectible_pool:
        item.active = false
        item.node.visible = false

func update_track(delta: float, speed: float, difficulty: float) -> void:
    var movement := speed * delta
    for segment in segments:
        segment.position.z += movement
        if segment.position.z > Config.TRACK_SEGMENT_LENGTH:
            segment.position.z -= Config.TRACK_SEGMENT_LENGTH * Config.TRACK_SEGMENT_COUNT
            _refresh_segment(segment)
    spawn_distance -= movement
    if spawn_distance <= 0.0:
        _spawn_pattern(difficulty)
        spawn_distance = lerpf(18.0, 11.5, difficulty) + rng.randf_range(-1.5, 2.0)
    for item in obstacle_pool:
        if not item.active:
            continue
        item.node.position.z += movement
        if item.node.position.z >= -0.25 and not item.triggered:
            item.triggered = true
            obstacle_reached.emit(item.kind, item.lane)
        if item.node.position.z > 8.0:
            item.active = false
            item.node.visible = false
    for item in collectible_pool:
        if not item.active:
            continue
        item.node.position.z += movement
        item.node.rotation.y += delta * 3.2
        if item.node.position.z >= -0.2 and not item.triggered:
            item.triggered = true
            collectible_reached.emit(item.lane)
        if item.node.position.z > 7.0:
            item.active = false
            item.node.visible = false

func _spawn_pattern(difficulty: float) -> void:
    pattern_counter += 1
    var safe_lane := rng.randi_range(0, 2)
    var blocked_count := 1 if difficulty < 0.24 or pattern_counter % 3 == 0 else 2
    var lanes := [0, 1, 2]
    lanes.erase(safe_lane)
    lanes.shuffle()
    for i in range(blocked_count):
        var kind_options := ["barrier", "arch", "pillar"]
        if difficulty < 0.18:
            kind_options = ["barrier", "arch"]
        _activate_obstacle(lanes[i], kind_options[rng.randi_range(0, kind_options.size() - 1)], -68.0 - i * 0.5)
    _spawn_collectible_line(safe_lane, -60.0)
    if blocked_count == 1 and rng.randf() < 0.45:
        var second_safe := lanes[1]
        _spawn_collectible_line(second_safe, -64.0)

func _activate_obstacle(lane: int, kind: String, z_pos: float) -> void:
    for item in obstacle_pool:
        if item.active:
            continue
        item.active = true
        item.triggered = false
        item.kind = kind
        item.lane = lane
        item.node.visible = true
        item.node.position = Vector3(Config.LANE_X[lane], 0.0, z_pos)
        _style_obstacle(item.node, kind)
        return

func _spawn_collectible_line(lane: int, start_z: float) -> void:
    for index in range(4):
        for item in collectible_pool:
            if item.active:
                continue
            item.active = true
            item.triggered = false
            item.lane = lane
            item.node.visible = true
            item.node.position = Vector3(Config.LANE_X[lane], 1.25, start_z - index * 2.5)
            break

func _build_segments() -> void:
    for index in range(Config.TRACK_SEGMENT_COUNT):
        var segment := Node3D.new()
        segment.name = "TrackSegment%d" % index
        segment.position.z = -float(index) * Config.TRACK_SEGMENT_LENGTH
        add_child(segment)
        segments.append(segment)
        var floor_mesh := BoxMesh.new()
        floor_mesh.size = Vector3(11.5, 0.45, Config.TRACK_SEGMENT_LENGTH - 0.15)
        var floor := MeshInstance3D.new()
        floor.mesh = floor_mesh
        floor.position.y = -0.32
        floor.material_override = _material(Color("111a42"), 0.15)
        segment.add_child(floor)
        for lane_x in [-1.6, 1.6]:
            var strip_mesh := BoxMesh.new()
            strip_mesh.size = Vector3(0.08, 0.03, Config.TRACK_SEGMENT_LENGTH - 0.6)
            var strip := MeshInstance3D.new()
            strip.mesh = strip_mesh
            strip.position = Vector3(lane_x, -0.08, 0.0)
            strip.material_override = _emissive(Color("32c8ff"))
            segment.add_child(strip)
        for side in [-1.0, 1.0]:
            for local_z in [-8.0, 0.0, 8.0]:
                var tower := _tower(Color("532b83") if index % 2 == 0 else Color("1d5f80"))
                tower.position = Vector3(side * rng.randf_range(7.5, 10.5), 1.7, local_z)
                tower.scale.y = rng.randf_range(0.7, 1.6)
                segment.add_child(tower)

func _refresh_segment(segment: Node3D) -> void:
    segment.rotation.y = 0.0

func _build_pools() -> void:
    for index in range(Config.MAX_OBSTACLES):
        var node := Node3D.new()
        node.name = "Obstacle%d" % index
        node.visible = false
        add_child(node)
        obstacle_pool.append({"node": node, "active": false, "triggered": false, "kind": "barrier", "lane": 0})
    for index in range(Config.MAX_COLLECTIBLES):
        var node := MeshInstance3D.new()
        node.name = "Shard%d" % index
        var mesh := PrismMesh.new()
        mesh.size = Vector3(0.72, 1.15, 0.42)
        node.mesh = mesh
        node.material_override = _emissive(Color("ffcc33"))
        node.visible = false
        add_child(node)
        collectible_pool.append({"node": node, "active": false, "triggered": false, "lane": 0})

func _style_obstacle(node: Node3D, kind: String) -> void:
    for child in node.get_children():
        child.queue_free()
    if kind == "barrier":
        var block := _box(Vector3(2.5, 1.15, 0.8), Color("ff5b57"))
        block.position.y = 0.5
        node.add_child(block)
    elif kind == "arch":
        var top := _box(Vector3(2.6, 0.55, 0.9), Color("8c5cff"))
        top.position.y = 2.0
        node.add_child(top)
        for x in [-1.05, 1.05]:
            var leg := _box(Vector3(0.35, 3.0, 0.7), Color("5a3bb5"))
            leg.position = Vector3(x, 1.25, 0.0)
            node.add_child(leg)
    else:
        var pillar := _box(Vector3(2.25, 3.4, 1.1), Color("f43f8f"))
        pillar.position.y = 1.5
        node.add_child(pillar)

func _tower(color: Color) -> MeshInstance3D:
    return _box(Vector3(1.8, 4.2, 1.8), color)

func _box(size: Vector3, color: Color) -> MeshInstance3D:
    var mesh := BoxMesh.new()
    mesh.size = size
    var instance := MeshInstance3D.new()
    instance.mesh = mesh
    instance.material_override = _material(color, 0.25)
    return instance

func _material(color: Color, metallic: float = 0.0) -> StandardMaterial3D:
    var material := StandardMaterial3D.new()
    material.albedo_color = color
    material.metallic = metallic
    material.roughness = 0.62
    return material

func _emissive(color: Color) -> StandardMaterial3D:
    var material := _material(color, 0.25)
    material.emission_enabled = true
    material.emission = color
    material.emission_energy_multiplier = 2.0
    return material
