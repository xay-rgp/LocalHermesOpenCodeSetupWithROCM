# GDScript 2.0 Architecture & 3D Third-Person Controller

Production patterns for Godot 4.x GDScript 2.0, decoupled scene composition, `CharacterBody3D` third-person movement, `SpringArm3D` camera rig, physics layers/masks, and Jolt Physics notes.

---

## 1. GDScript 2.0 Static Typing, Signals & Exports

Enable strict type warnings in **Project Settings → Debug → GDScript** (`untyped_declaration`, `unsafe_property_access`, `unsafe_method_access`, `unsafe_cast`, `return_value_discarded`) to catch typos at parse time and speed up VM bytecode execution.

```gdscript
@icon("res://assets/icons/player.svg")
class_name PlayerController
extends CharacterBody3D

# Typed signals: emit upward; never reach up with get_parent().get_parent()
signal landed(impact_speed: float)
signal jumped
signal movement_state_changed(is_grounded: bool, speed: float)

@export_category("Dependencies")
@export var config: MovementConfig
@export var visual_root: Node3D
@export var camera_rig: CameraRig

@export_group("Tuning")
@export_range(0.0, 60.0, 0.5, "suffix:m/s") var max_speed: float = 7.0
@export_flags_3d_physics var ground_mask: int = 1

@onready var _coyote_timer: Timer = $CoyoteTimer

# Typed arrays (Godot 4.0+) and typed dicts (Godot 4.4+; use untyped Dictionary in 4.0–4.3)
var _nearby_interactables: Array[Node3D] = []
var _move_input: Vector2 = Vector2.ZERO
```

### Critical GDScript 2.0 Patterns
- **Avoid variant leaks**: `var hit := ray.get_collider()` is inferred as `Object` (safe) vs `Dictionary` lookups `dict["key"]` which return `Variant`. Cast explicitly: `var dmg: float = float(data.get("damage", 0.0))` or `var body := node as CharacterBody3D`.
- **Safe `Callable` bindings & signal cleanup**: Connect in `_ready()` using `some_signal.connect(_on_event)` (prefer method reference over string names). Guard freed references after `await` with `if not is_instance_valid(target): return`.
- **Validate `@export` wiring in-editor** with `@tool` + `_get_configuration_warnings()`:
  ```gdscript
  func _get_configuration_warnings() -> PackedStringArray:
      var warnings: PackedStringArray = []
      if config == null:
          warnings.append("Assign a MovementConfig resource.")
      if visual_root == null:
          warnings.append("Assign visual_root (Node3D) for mesh rotation.")
      return warnings
  ```

---

## 2. Custom `Resource` Data vs Mutable Component Nodes

**Rule:** `Resource` subclasses store **immutable shared configuration/stats**. Component `Node`s hold **mutable per-instance runtime state**.

| Aspect | Custom `Resource` (`extends Resource`) | Component `Node` (`extends Node` / `Area3D`) |
|---|---|---|
| Lifetime & Sharing | Reference-counted; `.tres` instances are **shared by default** across all nodes | Instanced per scene; isolated runtime state |
| Best For | `MovementConfig`, `WeaponData`, `EnemyArchetype`, `DamageInfo` payloads | `HealthComponent`, `HitboxComponent`, `HurtboxComponent`, `StaminaComponent` |
| Mutation Trap | Mutating `stats.hp -= 10` edits the shared `.tres` for **every** enemy | Safe to mutate freely per entity |
| When Mutating Needed | Call `var runtime_data := base_data.duplicate(true)` (`true` = deep-copy subresources) | Store current `hp`, cooldown timers, status effects directly on component |

```gdscript
# res://scripts/resources/movement_config.gd
class_name MovementConfig
extends Resource

@export_group("Ground")
@export var move_speed: float = 6.5
@export var sprint_speed: float = 10.0
@export var ground_accel: float = 42.0
@export var ground_friction: float = 36.0
@export var turn_speed: float = 12.0

@export_group("Jump & Air")
@export var jump_height: float = 2.2
@export var time_to_peak: float = 0.42
@export var time_to_descent: float = 0.34
@export var air_control_factor: float = 0.35
@export var coyote_time: float = 0.12
@export var jump_buffer_time: float = 0.12
@export var jump_cut_multiplier: float = 0.45
@export var max_fall_speed: float = 32.0

# Exact kinematic derivations (h = v0*t - 0.5*g*t^2):
#   jump_velocity = (2 * jump_height) / time_to_peak
#   rise_gravity  = (2 * jump_height) / (time_to_peak^2)
#   fall_gravity  = (2 * jump_height) / (time_to_descent^2)
func get_jump_velocity() -> float:
	return (2.0 * jump_height) / maxf(time_to_peak, 0.01)

func get_rise_gravity() -> float:
	return (2.0 * jump_height) / maxf(time_to_peak * time_to_peak, 0.0001)

func get_fall_gravity() -> float:
	return (2.0 * jump_height) / maxf(time_to_descent * time_to_descent, 0.0001)
```

### Decoupled Scene Composition
- **Call down, signal up**: Parent `Player` calls `health.apply_damage(info)` on child; `HealthComponent` emits `health_depleted`, and `Player` handles death transitions.
- **No brittle path traversal**: Never write `get_node("../../HUD/HealthBar")`. Inject dependencies via `@export` on the scene root, or emit to a small typed SignalBus Autoload (`Events.player_health_changed.emit(hp, max_hp)`).
- **Self-contained scenes (`F6`)**: Every entity scene (`Player.tscn`, `Enemy.tscn`) should instantiate and run cleanly without requiring the full `Main.tscn` world.

---

## 3. Production 3D Third-Person `CharacterBody3D` Controller

### Godot 4 3D Conventions & Physics Rules
- **Coordinate System**: Right-handed Y-up: **`-Z` is forward**, `+X` is right, `+Y` is up.
- **`move_and_slide()` owns `delta`**: `velocity` is in **meters/second**. Multiply accelerations/gravity by `delta`; **never** multiply `velocity` by `delta` before `move_and_slide()`.
- **Slopes**: Configure `CharacterBody3D` properties:
  - `floor_max_angle = deg_to_rad(46.0)`
  - `floor_snap_length = 0.25` (keeps contact running downhill; automatically suppressed by Godot when `velocity.y > 0` or jumping off)
  - `floor_stop_on_slope = true` (prevents sliding down ramps while idle)
  - `floor_constant_speed = true` (prevents slowing down when climbing slopes)
  - `up_direction = Vector3.UP`

```gdscript
# res://scripts/player/third_person_controller.gd
class_name ThirdPersonController
extends CharacterBody3D

signal jumped
signal landed(impact_speed: float)

@export var config: MovementConfig
@export var visual_root: Node3D
@export var camera_rig: CameraRig

var _coyote_timer: float = 0.0
var _jump_buffer_timer: float = 0.0
var _was_on_floor: bool = false
var _last_y_velocity: float = 0.0
var _is_sprinting: bool = false


func _ready() -> void:
	assert(config != null, "MovementConfig must be assigned.")
	floor_stop_on_slope = true
	floor_constant_speed = true
	floor_max_angle = deg_to_rad(46.0)
	floor_snap_length = 0.25


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("jump"):
		_jump_buffer_timer = config.jump_buffer_time
	elif event.is_action_released("jump") and velocity.y > 0.0:
		# Variable jump height on early button release
		velocity.y *= config.jump_cut_multiplier

	_is_sprinting = Input.is_action_pressed("sprint")


func _physics_process(delta: float) -> void:
	_update_timers(delta)
	_apply_gravity(delta)

	var move_dir := _get_camera_relative_direction()
	_apply_horizontal_movement(move_dir, delta)
	_handle_jump()
	_rotate_visual_toward(move_dir, delta)

	_last_y_velocity = velocity.y
	move_and_slide()

	if is_on_floor() and not _was_on_floor:
		landed.emit(absf(_last_y_velocity))
	_was_on_floor = is_on_floor()


func _update_timers(delta: float) -> void:
	if is_on_floor():
		_coyote_timer = config.coyote_time
	else:
		_coyote_timer = maxf(_coyote_timer - delta, 0.0)

	if _jump_buffer_timer > 0.0:
		_jump_buffer_timer = maxf(_jump_buffer_timer - delta, 0.0)


func _apply_gravity(delta: float) -> void:
	if is_on_floor() and velocity.y <= 0.0:
		# Small downward bias stabilizes floor detection on shallow transitions
		velocity.y = -0.1
		return

	var g: float = config.get_rise_gravity() if velocity.y > 0.0 else config.get_fall_gravity()
	velocity.y = maxf(velocity.y - g * delta, -config.max_fall_speed)


func _get_camera_relative_direction() -> Vector3:
	var input_vec := Input.get_vector("move_left", "move_right", "move_forward", "move_backward")
	if input_vec.is_zero_approx():
		return Vector3.ZERO

	var cam_basis: Basis = camera_rig.get_yaw_basis() if camera_rig != null else global_basis
	# Project forward (-Z) and right (+X) onto XZ plane
	var forward := -cam_basis.z
	forward.y = 0.0
	forward = forward.normalized() if forward.length_squared() > 0.0001 else -global_basis.z

	var right := cam_basis.x
	right.y = 0.0
	right = right.normalized() if right.length_squared() > 0.0001 else global_basis.x

	# Note: Input.get_vector().y is negative for "move_forward" (up) and positive for "move_backward" (down)
	return (right * input_vec.x + forward * -input_vec.y).normalized()


func _apply_horizontal_movement(move_dir: Vector3, delta: float) -> void:
	var target_speed := config.sprint_speed if _is_sprinting else config.move_speed
	var target_vel := move_dir * target_speed

	var horiz_vel := Vector3(velocity.x, 0.0, velocity.z)
	var has_input := move_dir.length_squared() > 0.0001
	var rate := config.ground_accel if has_input else config.ground_friction
	if not is_on_floor():
		rate *= config.air_control_factor

	horiz_vel = horiz_vel.move_toward(target_vel, rate * delta)
	velocity.x = horiz_vel.x
	velocity.z = horiz_vel.z


func _handle_jump() -> void:
	if _jump_buffer_timer > 0.0 and _coyote_timer > 0.0:
		velocity.y = config.get_jump_velocity()
		_coyote_timer = 0.0
		_jump_buffer_timer = 0.0
		jumped.emit()


func _rotate_visual_toward(move_dir: Vector3, delta: float) -> void:
	if visual_root == null or move_dir.length_squared() < 0.0001:
		return

	# Option A: Y-axis yaw interpolation (cleanest for upright characters; -Z forward)
	var target_yaw := atan2(-move_dir.x, -move_dir.z)
	visual_root.rotation.y = lerp_angle(visual_root.rotation.y, target_yaw, 1.0 - exp(-config.turn_speed * delta))

	# Option B: Full 3D Basis slerp (use if aligning mesh to slope normals/flying)
	# var target_basis := Basis.looking_at(move_dir, Vector3.UP)
	# visual_root.global_basis = visual_root.global_basis.orthonormalized().slerp(
	#     target_basis, 1.0 - exp(-config.turn_speed * delta)
	# )
```

### Edge Cases in 3D Controllers
- **Stepping onto stairs / uneven curbs**: Capsules glide smoothly over tiny bevels, or pair a forward ankle+knee dual raycast / `test_move()` step-up probe when horizontal speed drops unexpectedly on a step height $\le 0.35\text{ m}$.
- **Frame-rate independent exponential smoothing**: Always use `1.0 - exp(-speed * delta)` instead of bare `speed * delta` inside `lerp`/`slerp`, preventing clamped overshoot (`weight > 1.0`) at low FPS and different turn speeds at 60 vs 144 Hz.
- **Jumping into slopes/ceilings**: Calling `apply_floor_snap()` manually after `velocity.y > 0` breaks jumps; Godot's `move_and_slide()` handles snap suppression automatically when `velocity.y > 0`.

---

## 4. `SpringArm3D` Pitch/Yaw Camera Rig

Recommended scene hierarchy (avoids rotating the `CharacterBody3D` collider with the camera):
```text
Player (CharacterBody3D)
├── CollisionShape3D (CapsuleShape3D)
├── VisualRoot (Node3D) ── Mesh + Skeleton3D
└── CameraRig (Node3D, script: CameraRig)
    └── YawPivot (Node3D)
        └── PitchPivot (Node3D)
            └── SpringArm3D
                └── Camera3D
```

```gdscript
# res://scripts/player/camera_rig.gd
class_name CameraRig
extends Node3D

@export var follow_target: Node3D
@export var mouse_sensitivity: float = 0.0022
@export var min_pitch_deg: float = -70.0
@export var max_pitch_deg: float = 55.0
@export var follow_smoothness: float = 20.0
@export var invert_y: bool = false

@onready var _yaw_pivot: Node3D = $YawPivot
@onready var _pitch_pivot: Node3D = $YawPivot/PitchPivot
@onready var _spring_arm: SpringArm3D = $YawPivot/PitchPivot/SpringArm3D

var _yaw: float = 0.0
var _pitch: float = deg_to_rad(-15.0)


func _ready() -> void:
	# Detach transform inheritance so player mesh/physics tick jitter doesn't shake camera
	top_level = true
	if follow_target != null:
		global_position = follow_target.global_position
		# Exclude player body from SpringArm3D wall collision checks
		if follow_target is CollisionObject3D:
			_spring_arm.add_excluded_object((follow_target as CollisionObject3D).get_rid())

	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("ui_cancel"):
		var captured := Input.mouse_mode == Input.MOUSE_MODE_CAPTURED
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE if captured else Input.MOUSE_MODE_CAPTURED
		return

	if Input.mouse_mode != Input.MOUSE_MODE_CAPTURED:
		return

	if event is InputEventMouseMotion:
		var motion := event as InputEventMouseMotion
		_yaw = wrapf(_yaw - motion.relative.x * mouse_sensitivity, 0.0, TAU)
		var y_sign := 1.0 if invert_y else -1.0
		_pitch = clampf(
			_pitch + motion.relative.y * mouse_sensitivity * y_sign,
			deg_to_rad(min_pitch_deg),
			deg_to_rad(max_pitch_deg)
		)


func _process(delta: float) -> void:
	if follow_target != null:
		# Smooth follow in _process eliminates 60Hz physics vs 144Hz render micro-stutter
		var t := 1.0 - exp(-follow_smoothness * delta)
		global_position = global_position.lerp(follow_target.global_position, t)

	_yaw_pivot.rotation.y = _yaw
	_pitch_pivot.rotation.x = _pitch


func get_yaw_basis() -> Basis:
	return Basis(Vector3.UP, _yaw)
```

### `SpringArm3D` Gotchas
- **Exclude small props / enemies / triggers**: Give `SpringArm3D.collision_mask` ONLY solid world geometry (Layer 1). If it collides with enemies or grass `Area3D`/`StaticBody3D`, the camera violently snaps inward mid-fight.
- **Near-clipping at minimum compression**: Set `SpringArm3D.margin = 0.25` and `Camera3D.near = 0.08` so walls don't show backfaces when the spring compresses behind the player.
- **Physics interpolation (Godot 4.3+)**: Alternatively enable `physics/common/physics_interpolation = true` in Project Settings and keep `CameraRig` as a regular child if you prefer zero follow lag.

---

## 5. Physics Layers, Masks & Jolt Physics Notes

Name layers in **Project Settings → Layer Names → 3D Physics**:

| Layer # | Name | Layer Bit (`1 << (n-1)`) | Typical Mask | Notes |
|---|---|---|---|---|
| 1 | `World` | `1` | — | Static terrain, walls, props; `SpringArm3D` collides only here |
| 2 | `Player` | `2` | `World \| Enemy` | Player `CharacterBody3D` |
| 3 | `Enemy` | `4` | `World \| Player \| Enemy` | Enemy `CharacterBody3D` |
| 4 | `PlayerHitbox` | `8` | `EnemyHurtbox` | `monitoring=true` only during active attack frames; `monitorable=false` |
| 5 | `EnemyHitbox` | `16` | `PlayerHurtbox` | `monitoring=true` only during enemy attack frames; `monitorable=false` |
| 6 | `PlayerHurtbox` | `32` | `0` (none) | Passive target (`monitoring=false`, `monitorable=true`) |
| 7 | `EnemyHurtbox` | `64` | `0` (none) | Passive target (`monitoring=false`, `monitorable=true`) |
| 8 | `Interactable` | `128` | `0` (none) | Scanned by player interaction `Area3D` / `RayCast3D` |

**Remember 1-indexed vs bitmask APIs:**
```gdscript
# 1-indexed layer number:
body.set_collision_layer_value(2, true)   # Layer 2 (Player)
body.set_collision_mask_value(1, true)    # Scans Layer 1 (World)
# Raw bitmask (0-indexed bit shift):
var query := PhysicsRayQueryParameters3D.create(from, to, (1 << 0) | (1 << 2)) # Layers 1 & 3
```

### Jolt Physics Notes (Godot Jolt / Built-in Jolt in 4.4+)
- **Prefer Jolt over GodotPhysics3D** for 3D games: dramatically faster broadphase, stable stacked rigid bodies, reliable `CylinderShape3D` and `ConvexPolygonShape3D` contacts, and significantly fewer trimesh edge-catch glitches in `move_and_slide()`.
- **`Area3D` + `StaticBody3D` sleeping / overlap**: In Jolt, static-vs-area detection works reliably, but toggling `CollisionShape3D.disabled` on a `Hitbox` must either use `set_deferred("disabled", ...)` during physics callbacks or run synchronously inside `AnimationPlayer` physics-synced updates (`callback_mode_process = ANIMATION_CALLBACK_MODE_PROCESS_PHYSICS`).
- **`RayCast3D` / `PhysicsRayQueryParameters3D` flags**:
  - `hit_from_inside = false` (default): rays starting inside a collider ignore it unless explicitly enabled.
  - `hit_back_faces = true`: useful for exiting geometry or validating trimesh containment, disable (`false`) for LOS rays inside thin walls if backfaces interfere.
- **Avoid `ConcavePolygonShape3D` (Trimesh) on moving bodies**: Only use trimesh for `StaticBody3D` level geometry; use `CapsuleShape3D`, `BoxShape3D`, or simplified `ConvexPolygonShape3D` hulls for dynamic bodies and projectiles.

---

## 6. Debugging Checklist

1. **Movement feels 60x too slow or accelerates infinitely**: Check whether `velocity * delta` is wrongly passed or multiplied before `move_and_slide()`.
2. **Character rotates 180° backward**: Model faces `+Z` instead of Godot's `-Z`. Rotate the imported child `MeshInstance3D` by `180°` on Y inside `VisualRoot`, never the root `CharacterBody3D`.
3. **Character stutters on steep stairs or bounces downhill**: Check `floor_snap_length` (increase to `0.25–0.35`) and verify `velocity.y` isn't reset to `0.0` before `move_and_slide()` on slopes (use small `-0.1` bias when grounded).
4. **Camera clips or jitters violently**: Turn on **Debug → Visible Collision Shapes** (`--debug-collisions`) to check if `SpringArm3D` is hitting the player's own collider, an enemy hurtbox, or a trigger `Area3D`.
5. **Orphan node leaks on scene transitions**: Monitor `Performance.get_monitor(Performance.OBJECT_ORPHAN_NODE_COUNT)` in a debug overlay; always `queue_free()` detached nodes rather than only calling `remove_child()`.
