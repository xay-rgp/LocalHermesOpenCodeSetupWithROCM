# Combat, AnimationTree, Enemy AI & 3D Performance

Production architectures for Godot 4.x node-based state machines, hitbox/hurtbox combat, `AnimationTree` + root motion, `NavigationAgent3D` AI coordination, and 3D GPU/CPU profiling.

---

## 1. Node-Based Finite State Machine (FSM)

Keep states as child nodes under `StateMachine` so each behavior is isolated, testable, and cleans up side effects deterministically in `exit()`.

```gdscript
# res://scripts/fsm/state.gd
class_name State
extends Node

signal transition_requested(next_state: StringName, payload: Dictionary)

var actor: CharacterBody3D  # Injected by StateMachine


func enter(_prev_state: StringName, _payload: Dictionary = {}) -> void:
	pass


func exit() -> void:
	pass


func handle_input(_event: InputEvent) -> void:
	pass


func update(_delta: float) -> void:
	pass


func physics_update(_delta: float) -> void:
	pass
```

```gdscript
# res://scripts/fsm/state_machine.gd
class_name StateMachine
extends Node

@export var initial_state: State
@export var actor: CharacterBody3D

var current_state: State
var _states: Dictionary = {}  # StringName -> State


func _ready() -> void:
	assert(actor != null, "StateMachine requires an actor.")
	for child in get_children():
		if child is State:
			var s := child as State
			var key := StringName(s.name)
			_states[key] = s
			s.actor = actor
			s.transition_requested.connect(_on_transition_requested)

	if initial_state != null:
		current_state = initial_state
		current_state.enter(&"", {})


func _unhandled_input(event: InputEvent) -> void:
	if current_state != null:
		current_state.handle_input(event)


func _process(delta: float) -> void:
	if current_state != null:
		current_state.update(delta)


func _physics_process(delta: float) -> void:
	if current_state != null:
		current_state.physics_update(delta)


func force_transition(next_name: StringName, payload: Dictionary = {}) -> void:
	_on_transition_requested(next_name, payload)


func _on_transition_requested(next_name: StringName, payload: Dictionary) -> void:
	if not _states.has(next_name):
		push_warning("StateMachine: unknown state '%s'" % next_name)
		return
	var next_state: State = _states[next_name]
	if next_state == current_state and not payload.get("allow_reenter", false):
		return

	var prev_name := StringName(current_state.name) if current_state != null else &""
	if current_state != null:
		current_state.exit()
	current_state = next_state
	current_state.enter(prev_name, payload)
```

### Canonical Combat States & Invariants
| State | `enter()` Responsibilities | `exit()` Cleanup (Mandatory!) | Allowed Transitions |
|---|---|---|---|
| `Idle` | Zero horizontal target; play locomotion idle | — | `Move`, `Jump`, `Attack`, `Dodge`, `Hurt`, `Dead` |
| `Move` | Feed velocity to locomotion blend | — | `Idle`, `Jump`, `Attack`, `Dodge`, `Hurt`, `Dead` |
| `Jump` | Apply jump impulse (`payload.get("jump", false)`) | Reset coyote/buffer flags | `Idle`, `Move`, `Hurt`, `Dead` |
| `Attack` | Fire combo anim, lock rotation after windup | **Disable `HitboxComponent`**, abort OneShot, reset combo flag | `Idle`, `Move`, `Attack` (next combo), `Dodge` (cancel), `Hurt`, `Dead` |
| `Dodge` | Apply burst velocity, enable **i-frames** | **Disable i-frames**, end dodge anim | `Idle`, `Move`, `Dead` |
| `Hurt` | Play hitstun anim, apply knockback impulse | Clear stagger lock | `Idle`, `Move`, `Dead` |
| `Dead` | Disable hurtbox/collider, play death anim/ragdoll | (Terminal) | None (or respawn reset) |

---

## 2. Combat System: Hitbox, Hurtbox, Combos, I-Frames & Hitstop

### Immutable Payload Resource (`DamageInfo`)
```gdscript
# res://scripts/combat/damage_info.gd
class_name DamageInfo
extends Resource

@export var amount: float = 15.0
@export var stagger_damage: float = 20.0
@export var knockback_force: float = 6.5
@export var hitstop_sec: float = 0.055

var attacker: Node3D
var hit_origin: Vector3
var knockback_dir: Vector3
```

### `HitboxComponent` & `HurtboxComponent`
- **Hitbox**: `Area3D` with `monitoring = false`, `monitorable = false`, `collision_layer = 0`, `collision_mask = EnemyHurtbox` (or `PlayerHurtbox`).
- **Hurtbox**: `Area3D` with `monitoring = false`, `monitorable = true`, `collision_layer = Hurtbox`, `collision_mask = 0`.
- **Active-Frame Toggling**: Call `hitbox.activate(damage_info)` and `hitbox.deactivate()` via **`AnimationPlayer` Call Method Tracks** (`callback_mode_process = PHYSICS`). Always also call `hitbox.deactivate()` in `AttackState.exit()` so getting interrupted mid-swing never leaves an active death-aura hitbox!

```gdscript
# res://scripts/combat/hitbox_component.gd
class_name HitboxComponent
extends Area3D

signal hit_landed(hurtbox: HurtboxComponent, info: DamageInfo)

@export var shape: CollisionShape3D

var _current_damage: DamageInfo
var _hit_ids: Dictionary = {}  # instance_id (int) -> true (per-swing dedup)


func _ready() -> void:
	monitoring = false
	monitorable = false
	if shape != null:
		shape.disabled = true
	area_entered.connect(_on_area_entered)


func activate(info: DamageInfo) -> void:
	_current_damage = info
	_hit_ids.clear()
	if shape != null:
		shape.set_deferred("disabled", false)
	set_deferred("monitoring", true)


func deactivate() -> void:
	set_deferred("monitoring", false)
	if shape != null:
		shape.set_deferred("disabled", true)
	_hit_ids.clear()
	_current_damage = null


func _on_area_entered(area: Area3D) -> void:
	if _current_damage == null or not (area is HurtboxComponent):
		return
	var hurtbox := area as HurtboxComponent
	if hurtbox.owner_node == _current_damage.attacker:
		return  # Never hit self

	# Dedup per target entity (use owner_node id so multi-hurtbox bosses take 1 hit per swing)
	var target_id: int = hurtbox.owner_node.get_instance_id()
	if _hit_ids.has(target_id):
		return
	_hit_ids[target_id] = true

	var payload := _current_damage.duplicate() as DamageInfo
	payload.hit_origin = global_position
	var delta_vec := hurtbox.global_position - global_position
	delta_vec.y = 0.0
	payload.knockback_dir = delta_vec.normalized() if delta_vec.length_squared() > 0.0001 else -global_basis.z

	if hurtbox.receive_hit(payload):
		hit_landed.emit(hurtbox, payload)
```

```gdscript
# res://scripts/combat/hurtbox_component.gd
class_name HurtboxComponent
extends Area3D

signal hit_received(info: DamageInfo)

@export var owner_node: Node3D
var invulnerable: bool = false


func _ready() -> void:
	monitoring = false
	monitorable = true


func set_invulnerable(enabled: bool) -> void:
	invulnerable = enabled
	set_deferred("monitorable", not enabled)


func receive_hit(info: DamageInfo) -> bool:
	if invulnerable:
		return false
	hit_received.emit(info)
	return true
```

### Combo Buffering, Knockback & Hitstop
- **Combo Input Buffering**: During an attack animation, an `AnimationPlayer` method track toggles `_can_buffer_combo = true` (e.g., 40% into swing) and `_can_cancel_recovery = true` (after follow-through). Pressing attack while `_can_buffer_combo` sets `_combo_queued = true`; once `_can_cancel_recovery` fires (or animation finishes), transition directly to `Attack` with `{"combo_index": combo_index + 1}` instead of `Idle`.
- **Knockback Impulse**: In `HurtState.enter()`, assign `actor.velocity = info.knockback_dir * info.knockback_force + Vector3.UP * 1.5`, then decay horizontally in `physics_update` with `move_toward(0.0, knockback_friction * delta)` + gravity.
- **Hitstop (Impact Freeze)**: Avoid freezing the camera or UI via `Engine.time_scale = 0.0` (which breaks timers unless `ignore_time_scale = true` and makes camera laggy). Prefer per-actor pause or brief `Engine.time_scale = 0.05` with an `ignore_time_scale` timer:
  ```gdscript
  func trigger_hitstop(duration: float, anim_tree: AnimationTree) -> void:
      if duration <= 0.0:
          return
      anim_tree.active = false
      await get_tree().create_timer(duration, true, false, true).timeout  # 4th arg = ignore_time_scale
      if is_instance_valid(anim_tree):
          anim_tree.active = true
  ```

---

## 3. `AnimationTree` Blending & Root Motion

### Recommended Graph Topology
```text
AnimationNodeBlendTree (Root)
├── Locomotion (AnimationNodeStateMachine)
│   ├── Idle
│   └── Move (AnimationNodeBlendSpace2D: X=strafe, Y=forward)
├── AttackClip (AnimationNodeAnimation)
└── UpperBodyOneShot (AnimationNodeOneShot)
    ├── filter_enabled = true (check Spine, Chest, Head, Arms, Weapon bones only)
    ├── mix_mode = Mix
    ├── fadein_time = 0.08, fadeout_time = 0.15
    ├── in  ← Locomotion
    └── shot ← AttackClip
```

### Driving Parameters & Root Motion Extraction
```gdscript
# Update BlendSpace2D in local movement space
var local_vel: Vector3 = visual_root.global_basis.inverse() * Vector3(velocity.x, 0.0, velocity.z)
var blend_vec := Vector2(local_vel.x, -local_vel.z) / config.move_speed  # -Z forward -> +Y in BlendSpace2D
anim_tree.set("parameters/Locomotion/Move/blend_position", blend_vec.limit_length(1.0))

# Trigger / Abort upper-body OneShot attack
anim_tree.set("parameters/UpperBodyOneShot/request", AnimationNodeOneShot.ONE_SHOT_REQUEST_FIRE)
# In AttackState.exit() (e.g., if interrupted by Hurt):
anim_tree.set("parameters/UpperBodyOneShot/request", AnimationNodeOneShot.ONE_SHOT_REQUEST_ABORT)
```

**Root Motion Extraction (`_physics_process`):**
- Enable `AnimationTree.root_motion_track` pointing to your `Skeleton3D:Root` bone.
- Extract **delta** motion per physics tick and rotate it into world space via `visual_root.global_basis`:
  ```gdscript
  func apply_root_motion(delta: float) -> void:
      if delta <= 0.0:
          return
      var rm_pos: Vector3 = anim_tree.get_root_motion_position()
      var rm_rot: Quaternion = anim_tree.get_root_motion_rotation()
      visual_root.global_basis = (visual_root.global_basis * Basis(rm_rot)).orthonormalized()

      # Convert local root displacement to world velocity; preserve vertical gravity
      var world_vel: Vector3 = (visual_root.global_basis * rm_pos) / delta
      velocity.x = world_vel.x
      velocity.z = world_vel.z
  ```
- **Gotcha**: Never apply `rm_pos.y` blindly during attacks unless intentionally jumping — let gravity govern Y so characters don't hover off ledges. Also set `AnimationTree.callback_mode_process = ANIMATION_CALLBACK_MODE_PROCESS_PHYSICS` when driving root motion or hitboxes.

---

## 4. Enemy AI: Perception, Navigation & Combat Tokens

### Vision Cone + `PhysicsRayQueryParameters3D` LOS
```gdscript
func can_see_target(target: Node3D, fov_deg: float, max_dist: float, world_mask: int) -> bool:
	var eye_pos := global_position + Vector3.UP * 1.5
	var target_pos := target.global_position + Vector3.UP * 1.2
	var to_target := target_pos - eye_pos
	var dist_sq := to_target.length_squared()
	if dist_sq > max_dist * max_dist or dist_sq < 0.0001:
		return false

	# Flatten onto XZ for horizontal FOV cone check (-Z is forward!)
	var forward_xz := -global_basis.z
	forward_xz.y = 0.0
	var dir_xz := Vector3(to_target.x, 0.0, to_target.z)
	if forward_xz.normalized().dot(dir_xz.normalized()) < cos(deg_to_rad(fov_deg * 0.5)):
		return false

	var query := PhysicsRayQueryParameters3D.create(eye_pos, target_pos, world_mask, [get_rid()])
	query.hit_from_inside = false
	var hit := get_world_3d().direct_space_state.intersect_ray(query)
	# Empty dictionary means unobstructed LOS to target_pos (mask contains World only)
	return hit.is_empty()
```

### `NavigationAgent3D` Async Avoidance & Throttled Repathing
- **Startup Sync**: Never query `get_next_path_position()` on `_ready()` frame 0. Wait for `await get_tree().physics_frame` (or `NavigationServer3D.map_changed`).
- **Throttled Repathing**: Recompute `nav_agent.target_position` on a `0.15s–0.25s` timer AND only if target moved $> 0.4\text{ m}$.
- **RVO2 Avoidance**: Connect `nav_agent.velocity_computed.connect(_on_velocity_computed)`. In `_physics_process`: compute `desired_vel`, pass `nav_agent.set_velocity(desired_vel)`, and call `move_and_slide()` inside `_on_velocity_computed(safe_velocity)`!
  ```gdscript
  func _physics_process(delta: float) -> void:
      _apply_gravity(delta)
      if nav_agent.is_navigation_finished():
          nav_agent.set_velocity(Vector3.ZERO)
          return
      var next_pt := nav_agent.get_next_path_position()
      var dir := next_pt - global_position
      dir.y = 0.0
      var desired := dir.normalized() * move_speed if dir.length_squared() > 0.01 else Vector3.ZERO
      if nav_agent.avoidance_enabled:
          nav_agent.set_velocity(desired)  # Triggers _on_velocity_computed
      else:
          _on_velocity_computed(desired)

  func _on_velocity_computed(safe_velocity: Vector3) -> void:
      velocity.x = safe_velocity.x
      velocity.z = safe_velocity.z
      move_and_slide()
  ```

### Combat Token & Circling Coordination
Prevent 8 enemies from piling onto one point and attacking simultaneously:
- Create a `CombatDirector` managing `max_attack_tokens: int = 2` (Dictionary of active holder IDs).
- Enemies without a token circle at `orbit_radius` (`3.5–4.5 m`) along a personal slot angle (`idx * TAU / num_engagers`) plus soft separation from nearby allies (`dot` tangent strafe).
- **Mandatory invariant**: Release the token in `AttackState.exit()` AND `DeadState.enter()` (plus `tree_exiting`) so killed/stunned enemies never leak tokens!

---

## 5. 3D Performance Optimization & Profiling

### High-Impact Rendering Optimizations
1. **Mesh LOD & Visibility Ranges (HLOD)**: Enable automatic LOD generation on `.glb` imports (`meshes/generate_lods = true`). Set `GeometryInstance3D.visibility_range_begin/end` and `visibility_range_fade_mode = VISIBILITY_RANGE_FADE_SELF` on props/foliage so distant details cull completely before shader invocation.
2. **Occlusion Culling**: Enable `rendering/occlusion_culling/use_occlusion_culling = true`, add `OccluderInstance3D` nodes (bake scene or use simple `BoxOccluder3D` inside walls/buildings). Keep occluders low-poly; occluding behind small trees costs more CPU rasterization than it saves.
3. **`MultiMeshInstance3D`**: Batch grass, rocks, debris, and bullets into one draw call per material (`transform_format = TRANSFORM_3D`, set `visible_instance_count` dynamically for pooling).
4. **Lighting & Shadows**:
   - Use **1 shadow-casting `DirectionalLight3D`** (`PSSM 4 Splits`, tune `directional_shadow_max_distance` to `60–120 m`, avoid unnecessary `250 m`).
   - Disable `shadow_enabled` on small fill `OmniLight3D`s or set `distance_fade_enabled = true` (`distance_fade_begin`, `distance_fade_shadow`).
   - Bake static architecture lighting with `LightmapGI` (`Static` bake mode on meshes) instead of dynamic `SDFGI` when targeting mid/low-end GPUs.
5. **Draw Call Batching & Shader Pre-warming**:
   - Share `StandardMaterial3D`/`ShaderMaterial` instances across meshes; avoid changing uniform flags per instance unless using `instance uniform` (`INSTANCE_CUSTOM`) so pipelines don't multiply.
   - Pre-warm shaders & `GPUParticles3D` during loading screen: instantiate one frame of each unique shader/particle material inside an active off-screen camera pass (`SubViewport` or hidden behind loading curtain with `visible = true` for 2 frames) so Vulkan/OpenGL compiles pipelines before combat begins.

### Profiling Workflow
- **Debugger → Profiler (CPU)**: Separate `_physics_process` time vs `_process` vs `Physics` step vs `Render`. If physics step spikes, check overlapping `Area3D`s, excessive raycasts per frame, or complex trimesh collisions.
- **Debugger → Visual Profiler (GPU)**: Identify whether bottleneck is `Shadow` pass, `Opaque` (draw calls/overdraw), `Transparent` (alpha overdraw from layered particles), or `Post-Process` (SSAO/SSIL/Volumetric Fog).
- **Runtime `Performance` Monitors**:
  ```gdscript
  var fps := Performance.get_monitor(Performance.TIME_FPS)
  var draws := Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME)
  var tris := Performance.get_monitor(Performance.RENDER_TOTAL_PRIMITIVES_IN_FRAME)
  var orphans := Performance.get_monitor(Performance.OBJECT_ORPHAN_NODE_COUNT)
  ```
- **Target Budgets (1080p 60 FPS mid-tier GPU)**: `< 1,500` draw calls, `< 1.5M` visible primitives, `< 2 ms` physics step, `0` orphan nodes on scene reload.
