---
name: godot-development
description: "Build Godot 4 3D games: GDScript, combat, AI, and perf."
version: 1.0.0
author: Xay, Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [godot4, gdscript, gamedev, 3d, physics, combat, animation, ai, navigation]
    related_skills: [software-architecture, debugging-mastery, algorithms-cs, polyglot-programming]
---

# Godot 4 and 3D Game Development

Production Godot 4.x architecture and GDScript 2.0 engineering with special depth in 3D third-person gameplay, character controllers, combat systems, `AnimationTree`, physics, enemy AI, `NavigationServer3D`, and 3D performance optimization.

## When to Use

- Building or debugging Godot 4 projects, GDScript 2.0 scripts, scenes, shaders, or C#/GDExtension nodes
- Designing 3D third-person character controllers, cameras (`SpringArm3D`), combat hitboxes/hurtboxes, state machines, or `AnimationTree` blends
- Implementing 3D enemy AI, `NavigationAgent3D` pathfinding, physics layers/masks, or profiling FPS/frame-time drops
- Don't use for: Unity/Unreal engine specifics or non-game desktop GUIs

## Core Godot 4 Architecture Principles

1. **Call down, signal up.** Parent nodes configure and invoke methods on direct children; child nodes NEVER reach up via `get_parent().get_parent()` — they emit typed `signal`s.
2. **Compose with reusable component nodes, not deep inheritance.** Build `HealthComponent`, `HitboxComponent`, `HurtboxComponent`, `StateMachine`, and `VelocityComponent` as child nodes wired via `@export` references rather than a 1,500-line `CharacterBase.gd`.
3. **Always use static typing in GDScript 2.0.** Annotate variables (`var speed: float = 6.5`), typed arrays (`Array[Enemy]`), parameters, and return types (`-> void`). Enable strict type warnings in Project Settings — typed GDScript catches bugs at parse time and runs measurably faster in the VM.
4. **Separate physics (`_physics_process(delta)`) from rendering/input (`_process(delta)`, `_unhandled_input(event)`).** All `CharacterBody3D.move_and_slide()`, `RayCast3D`, `Area3D` queries, and velocity updates belong in `_physics_process` at fixed tick rate; camera smoothing, UI, and visual effects belong in `_process`.
5. **Respect Godot's 3D coordinate system.** Right-handed Y-up: **-Z is forward**, +X is right, +Y is up. When aligning a character mesh to movement, remember `look_at()` points `-Z` toward the target.

## Quick Reference

| System | Godot 4 Idiom | Critical Detail |
|---|---|---|
| 3D Character | `CharacterBody3D` + `move_and_slide()` | `velocity` is a property; do NOT multiply `velocity` by `delta` before `move_and_slide()` (multiply acceleration/gravity by `delta`) |
| 3D Camera | Pivot `Node3D` → `SpringArm3D` → `Camera3D` | Exclude player collision layer from `SpringArm3D.collision_mask` |
| Combat | `Area3D` Hitbox (layer=off, mask=Hurtbox) + Hurtbox | Disable hitbox `CollisionShape3D` outside active frames; track `hit_targets` per swing to prevent multi-hit |
| Animation | `AnimationPlayer` + `AnimationTree` (`StateMachine` / `BlendTree`) | Drive hitboxes & footstep SFX via Method Call Tracks; use root motion carefully |
| Navigation | `NavigationRegion3D` + `NavigationAgent3D` | Never compute paths every frame; throttle target updates (0.1–0.25s) and await `NavigationServer3D.map_changed` on startup |
| Physics Layers | Named layers in Project Settings (1=World, 2=Player, 3=Enemy, 4=Hitbox, 5=Hurtbox, 6=Interact) | Layer = "what I am"; Mask = "what I scan/collide with" |
| Resource Data | Custom `Resource` subclasses (`WeaponData`, `EnemyStats`) | Call `.duplicate(true)` if mutating per-instance! Resources are shared by default |

## Deep References

Load on demand with `skill_view("godot-development", file_path="...")`:
- `references/gdscript-architecture-and-3d-controller.md` — GDScript 2.0 typing/signals/resources, decoupled scene composition, complete 3D third-person `CharacterBody3D` controller (camera-relative movement, coyote time, jump buffering, slopes, `SpringArm3D` gimbal, physics layers & Jolt).
- `references/combat-animation-ai-and-perf.md` — Finite State Machine & Hierarchical FSM, attack/combo/hitbox/hurtbox/i-frame/hitstop combat architecture, `AnimationTree` blending & root motion, enemy AI (perception cones, LOS raycasts, `NavigationAgent3D`, attack token coordination), and 3D performance optimization (HLOD, `OccluderInstance3D`, `MultiMeshInstance3D`, shader pre-compilation, Profiler).

## Implementation Procedure

1. **Inspect scene tree and project settings first.** Read `project.godot`, `.tscn`, and existing `.gd` scripts (`read_file`, `search_files`) to confirm physics layer names, autoloads, and input actions. Completion criterion: layer bitmasks, autoload singletons, and node paths are verified against actual files.
2. **Design scenes as self-contained units.** Each scene (Player, Enemy, Weapon, Arena) must run cleanly when opened independently (`F6`) with `@export` dependencies rather than hard-coded `/root/...` paths. Completion criterion: zero fragile relative paths like `../../../Player`.
3. **Implement typed GDScript with explicit state transitions.** Drive movement, combat, and AI through clean state machines so impossible overlaps (e.g., attacking while stunned or double-hitting on one swing) cannot occur. Completion criterion: all state enter/exit hooks clean up timers, hitboxes, and animation flags.
4. **Verify via headless Godot check and runtime profiling.** Run `godot --headless --check-only` or scene tests and inspect Monitors (FPS, draw calls, physics time, orphan nodes). Completion criterion: zero script parse errors, zero orphan nodes on scene reload, and stable frame times.

## Common Pitfalls

- **Multiplying `velocity` by `delta` before `move_and_slide()`:** `move_and_slide()` already integrates `delta` internally — multiplying again makes movement 60x too slow and frame-rate dependent!
- **Shared `Resource` mutation bug:** Editing `stats.hp -= 10` on an `@export var stats: EnemyStats` mutates the shared `.tres` resource across ALL enemies of that type. Always duplicate runtime state or separate immutable `EnemyStats` from mutable `HealthComponent`.
- **Freed node references (`Previously freed` crash):** Always check `is_instance_valid(target)` before using cached `Node` references (especially after `await`!).
- **Shadowing built-in `Node` properties (`owner`, `name`, `position`):** Declaring `var owner: Node` in a script extending `Node`/`Area3D` collides with built-in `Node.owner`. Name custom references `target_node`, `health_component`, or `actor`.
- **Headless CLI `class_name` cache trap:** On a fresh repo without `.godot/global_script_class_cache.cfg`, `godot --headless --script test.gd` fails to resolve `class_name` globals. Run `godot --headless --import --quit --path .` first OR use explicit `const Foo = preload("res://foo.gd")`.
- **Memory leaks from orphan nodes:** Nodes created via `.new()` that are removed with `remove_child()` (not `queue_free()`) are NOT garbage collected — they leak permanently. Check `Performance.get_monitor(Performance.OBJECT_ORPHAN_NODE_COUNT)`.
- **Navigation query on frame 0:** `NavigationAgent3D.get_next_path_position()` returns zero/invalid before the first physics frame syncs `NavigationServer3D`. Wait one `await get_tree().physics_frame` before querying paths.
- **Shader compilation stutters in 3D:** First-time material/particle draw causes frame spikes. Pre-warm materials/particles in a loading pass or off-screen camera sweep.
- **`await` re-entrancy bugs:** Calling an async function again while an earlier `await` is pending runs overlapping logic. Guard with state checks or explicit timers (`SceneTreeTimer` / `Timer` node) instead of unguarded `await`.

## Verification

- Headless syntax & script check: `terminal(command="godot --headless --quit --path <project_dir>")` (confirm 0 script/parse errors in stderr).
- Run GUT / GdUnit4 tests if installed: `terminal(command="godot --headless -s addons/gut/gut_cmdln.gd")` (or project test runner).
- Verify zero orphan nodes, zero unfreed timers/signals, and clean hitbox disable on interrupted attacks.
