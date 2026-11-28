# -*- coding: utf-8 -*-
"""
core/agents/tools/blender_tools.py — Realistic Blender 3D Modeling, Verification,
2-Model Retention & Launch Tools.

Pipeline:
  1. create_blender_model_script -> injects Blender 3.x/4.x/5.x-safe realism helpers
  2. run_blender_script(open_gui=False) -> builds & verifies 0 errors in background
  3. verify_blender_model_against_requirements -> audits mesh stats, renders preview,
     and compares against user requirements via VLM before opening Blender
  4. open_blender_model_gui -> opens the verified .blend in Blender on the system
"""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool

from config.settings import BLENDER_PATH, GENERATED_WORKSPACE

_BLENDER_SCRIPTS_DIR = GENERATED_WORKSPACE / "blender"
_ASSETS_3D_DIR = GENERATED_WORKSPACE / "assets_3d"
_MANIFEST_PATH = _ASSETS_3D_DIR / ".kugane_models.json"
MAX_UNPINNED_MODELS = 2

_BLENDER_MODEL_GETTER: Optional[Callable[[], Optional[BaseChatModel]]] = None


def set_blender_model_getter(getter: Callable[[], Optional[BaseChatModel]]) -> None:
    """Register the active chat/VLM model getter used by model verification."""
    global _BLENDER_MODEL_GETTER
    _BLENDER_MODEL_GETTER = getter


# ── Blender 3.x / 4.x / 5.x Safe Realism Helper Library ───────────────────────
_REALISM_HELPERS = '''
# ── Kugane Realistic Blender Helpers (Blender 3.x / 4.x / 5.x safe) ──────────
import bpy
import bmesh
import math
from mathutils import Vector

def kugane_clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)

def kugane_set_smooth(obj):
    if obj is None or obj.type != "MESH":
        return
    mesh = obj.data
    if len(mesh.polygons) > 0:
        mesh.polygons.foreach_set("use_smooth", [True] * len(mesh.polygons))
    mesh.update()

def kugane_add_bevel(obj, width=0.015, segments=3):
    if obj is None or obj.type != "MESH":
        return
    mod = obj.modifiers.new(name="KuganeBevel", type="BEVEL")
    mod.width = width
    mod.segments = segments
    mod.limit_method = "ANGLE"
    mod.angle_limit = math.radians(30.0)
    mod.harden_normals = False
    return mod

def kugane_add_subsurf(obj, levels=2):
    if obj is None or obj.type != "MESH":
        return
    mod = obj.modifiers.new(name="KuganeSubsurf", type="SUBSURF")
    mod.levels = levels
    mod.render_levels = levels
    return mod

def kugane_add_solidify(obj, thickness=0.02, offset=0.0):
    if obj is None or obj.type != "MESH":
        return
    mod = obj.modifiers.new(name="KuganeSolidify", type="SOLIDIFY")
    mod.thickness = thickness
    mod.offset = offset
    return mod

def kugane_boolean_cut(target_obj, cutter_obj, operation="DIFFERENCE", apply_mod=True):
    if target_obj is None or cutter_obj is None:
        return
    mod = target_obj.modifiers.new(name="KuganeBoolean", type="BOOLEAN")
    mod.operation = operation
    mod.object = cutter_obj
    mod.solver = "EXACT"
    if apply_mod:
        bpy.context.view_layer.objects.active = target_obj
        try:
            bpy.ops.object.modifier_apply(modifier=mod.name)
            bpy.data.objects.remove(cutter_obj, do_unlink=True)
        except Exception:
            cutter_obj.hide_set(True)
            cutter_obj.hide_render = True

def kugane_create_lathe_profile(name, profile_points, steps=36):
    """Create a smooth revolved 3D mesh from [(radius, z), ...] points."""
    mesh = bpy.data.meshes.new(name + "_Mesh")
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    bm = bmesh.new()
    verts = [bm.verts.new((float(r), 0.0, float(z))) for r, z in profile_points]
    edges = [bm.edges.new((verts[i], verts[i + 1])) for i in range(len(verts) - 1)]
    bmesh.ops.spin(
        bm,
        geom=verts + edges,
        cent=(0.0, 0.0, 0.0),
        axis=(0.0, 0.0, 1.0),
        angle=math.tau,
        steps=max(8, int(steps)),
        use_merge=True,
    )
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()
    kugane_set_smooth(obj)
    return obj

def kugane_make_material(
    name,
    base_color=(0.5, 0.5, 0.5, 1.0),
    metallic=0.0,
    roughness=0.4,
    ior=1.45,
    transmission=0.0,
    emission=None,
    emission_strength=0.0,
    noise_roughness=0.08,
    bump_strength=0.12,
):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = next((n for n in nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None:
        bsdf = nodes.new("ShaderNodeBsdfPrincipled")

    if len(base_color) == 3:
        base_color = (*base_color, 1.0)
    bsdf.inputs["Base Color"].default_value = base_color
    if "Metallic" in bsdf.inputs:
        bsdf.inputs["Metallic"].default_value = float(metallic)
    if "Roughness" in bsdf.inputs:
        bsdf.inputs["Roughness"].default_value = float(roughness)
    if "IOR" in bsdf.inputs:
        bsdf.inputs["IOR"].default_value = float(ior)
    for key in ("Transmission Weight", "Transmission"):
        if key in bsdf.inputs:
            bsdf.inputs[key].default_value = float(transmission)
            break
    if emission is not None:
        if len(emission) == 3:
            emission = (*emission, 1.0)
        for key in ("Emission Color", "Emission"):
            if key in bsdf.inputs:
                bsdf.inputs[key].default_value = emission
                break
        if "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = float(emission_strength)

    if (noise_roughness > 0 or bump_strength > 0) and "Roughness" in bsdf.inputs:
        tex_coord = nodes.new("ShaderNodeTexCoord")
        noise = nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = 20.0
        noise.inputs["Detail"].default_value = 6.0
        links.new(tex_coord.outputs["Object"], noise.inputs["Vector"])

        if noise_roughness > 0:
            ramp = nodes.new("ShaderNodeMapRange")
            ramp.inputs["To Min"].default_value = max(0.02, roughness - noise_roughness)
            ramp.inputs["To Max"].default_value = min(0.98, roughness + noise_roughness)
            links.new(noise.outputs["Fac"], ramp.inputs["Value"])
            links.new(ramp.outputs["Result"], bsdf.inputs["Roughness"])

        if bump_strength > 0 and "Normal" in bsdf.inputs:
            bump = nodes.new("ShaderNodeBump")
            bump.inputs["Strength"].default_value = float(bump_strength)
            bump.inputs["Distance"].default_value = 0.005
            links.new(noise.outputs["Fac"], bump.inputs["Height"])
            links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat

def kugane_assign_material(obj, mat):
    if obj is None or obj.type != "MESH" or mat is None:
        return
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)

def kugane_world_bounds(obj):
    bpy.context.view_layer.update()
    pts = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    min_v = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    max_v = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return min_v, max_v

def kugane_place_on_ground(obj, z=0.0):
    min_v, _ = kugane_world_bounds(obj)
    obj.location.z += (z - min_v.z)

def kugane_snap_on_top(obj, base_obj, gap=0.0):
    _, base_max = kugane_world_bounds(base_obj)
    obj_min, _ = kugane_world_bounds(obj)
    obj.location.z += (base_max.z + gap - obj_min.z)

def kugane_ensure_studio_lights():
    scene = bpy.context.scene
    if any(o.type == "LIGHT" for o in scene.objects):
        return
    sun_d = bpy.data.lights.new("KuganeSun", type="SUN")
    sun_d.energy = 2.8
    sun_o = bpy.data.objects.new("KuganeSun", sun_d)
    scene.collection.objects.link(sun_o)
    sun_o.rotation_euler = (math.radians(52), math.radians(12), math.radians(38))

    fill_d = bpy.data.lights.new("KuganeFill", type="AREA")
    fill_d.energy = 160.0
    fill_d.size = 4.0
    fill_o = bpy.data.objects.new("KuganeFill", fill_d)
    scene.collection.objects.link(fill_o)
    fill_o.location = (-3.5, -3.5, 3.0)
    fill_o.rotation_euler = (Vector((0, 0, 0.5)) - fill_o.location).to_track_quat("-Z", "Y").to_euler()
'''

_VERIFY_INSPECT_SCRIPT = '''
import json
import math
import sys
import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
blend_path, out_png, out_json = argv[0], argv[1], argv[2]

bpy.ops.wm.open_mainfile(filepath=blend_path)
scene = bpy.context.scene
bpy.context.view_layer.update()

geom_objs = [
    o for o in scene.objects
    if o.type in {"MESH", "CURVE", "SURFACE", "META", "FONT"} and not o.hide_get()
]

objects_info = []
all_corners = []
total_verts = 0
total_faces = 0
unmaterialed = []

for obj in geom_objs:
    pts = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    all_corners.extend(pts)
    min_v = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    max_v = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    dims = max_v - min_v
    verts = len(obj.data.vertices) if obj.type == "MESH" else 0
    faces = len(obj.data.polygons) if obj.type == "MESH" else 0
    total_verts += verts
    total_faces += faces
    mats = [m.name for m in obj.data.materials if m] if hasattr(obj.data, "materials") else []
    if obj.type == "MESH" and not mats:
        unmaterialed.append(obj.name)
    objects_info.append({
        "name": obj.name,
        "type": obj.type,
        "verts": verts,
        "faces": faces,
        "materials": mats,
        "modifiers": [m.type for m in obj.modifiers],
        "bounds_min": [round(min_v.x, 3), round(min_v.y, 3), round(min_v.z, 3)],
        "bounds_max": [round(max_v.x, 3), round(max_v.y, 3), round(max_v.z, 3)],
        "size": [round(dims.x, 3), round(dims.y, 3), round(dims.z, 3)],
    })

rendered = False
if all_corners:
    g_min = Vector((min(p.x for p in all_corners), min(p.y for p in all_corners), min(p.z for p in all_corners)))
    g_max = Vector((max(p.x for p in all_corners), max(p.y for p in all_corners), max(p.z for p in all_corners)))
    center = (g_min + g_max) * 0.5
    size = g_max - g_min
    max_dim = max(size.x, size.y, size.z, 0.5)

    # Render fast temporary preview without modifying the .blend file on disk
    cam_data = bpy.data.cameras.new("_KuganeVerifyCam")
    cam = bpy.data.objects.new("_KuganeVerifyCam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam_data.lens = 35.0
    cam_data.sensor_width = 36.0
    view_dir = Vector((1.0, -1.2, 0.75)).normalized()
    dist = max_dim * 2.1
    cam.location = center + view_dir * dist
    cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam_data.clip_start = max(0.01, dist * 0.005)
    cam_data.clip_end = max(2000.0, dist * 15.0)

    available_engines = [e.identifier for e in scene.render.bl_rna.properties["engine"].enum_items]
    for eng in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "BLENDER_WORKBENCH", "CYCLES"):
        if eng in available_engines:
            scene.render.engine = eng
            break

    scene.render.resolution_x = 640
    scene.render.resolution_y = 480
    scene.render.resolution_percentage = 100
    scene.render.filepath = out_png
    scene.render.image_settings.file_format = "PNG"
    try:
        bpy.ops.render.render(write_still=True)
        rendered = True
    except Exception:
        rendered = False

report = {
    "object_count": len(geom_objs),
    "total_verts": total_verts,
    "total_faces": total_faces,
    "unmaterialed_objects": unmaterialed,
    "objects": objects_info[:40],
    "rendered_preview": rendered,
}
with open(out_json, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2)
'''


def find_blender_executable() -> str | None:
    """Locate blender.exe from BLENDER_PATH, PATH, or standard Windows install paths."""
    if BLENDER_PATH and Path(BLENDER_PATH).is_file():
        return BLENDER_PATH
    which = shutil.which("blender")
    if which:
        return which

    candidates: list[Path] = []
    pf = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Blender Foundation"
    if pf.exists():
        candidates.extend(sorted(pf.glob("Blender*/blender.exe"), reverse=True))
    local_app = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Blender Foundation"
    if local_app.exists():
        candidates.extend(sorted(local_app.glob("Blender*/blender.exe"), reverse=True))

    for c in candidates:
        if c.is_file():
            return str(c)
    return None


def _load_manifest() -> dict[str, dict[str, Any]]:
    _ASSETS_3D_DIR.mkdir(parents=True, exist_ok=True)
    if not _MANIFEST_PATH.is_file():
        return {}
    try:
        data = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_manifest(data: dict[str, dict[str, Any]]) -> None:
    _ASSETS_3D_DIR.mkdir(parents=True, exist_ok=True)
    _MANIFEST_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _sync_manifest_with_disk(manifest: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    _BLENDER_SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    _ASSETS_3D_DIR.mkdir(parents=True, exist_ok=True)

    for p in list(_BLENDER_SCRIPTS_DIR.glob("*.py")) + list(_ASSETS_3D_DIR.glob("*")):
        if p.name.startswith(".") or p.name.startswith("_"):
            continue
        stem = p.stem
        if stem not in manifest:
            manifest[stem] = {
                "name": stem,
                "created_at": p.stat().st_mtime,
                "pinned": False,
            }
    return manifest


def _delete_model_files(stem: str) -> list[str]:
    deleted: list[str] = []
    for folder in (_BLENDER_SCRIPTS_DIR, _ASSETS_3D_DIR):
        if not folder.exists():
            continue
        for p in folder.glob(f"{stem}.*"):
            if p.is_file():
                try:
                    p.unlink()
                    deleted.append(str(p))
                except OSError:
                    pass
    return deleted


def _prune_old_models(manifest: dict[str, dict[str, Any]], keep_stem: str | None = None) -> list[str]:
    """Keep at most MAX_UNPINNED_MODELS (2) most recent unpinned models."""
    unpinned = [
        (stem, info)
        for stem, info in manifest.items()
        if not info.get("pinned", False)
    ]
    unpinned.sort(
        key=lambda item: (
            1 if item[0] == keep_stem else 0,
            float(item[1].get("created_at", 0.0)),
        ),
        reverse=True,
    )

    pruned_stems: list[str] = []
    for stem, _info in unpinned[MAX_UNPINNED_MODELS:]:
        _delete_model_files(stem)
        manifest.pop(stem, None)
        pruned_stems.append(stem)

    return pruned_stems


def register_and_prune_model(model_stem: str, pinned: bool = False) -> list[str]:
    manifest = _sync_manifest_with_disk(_load_manifest())
    existing = manifest.get(model_stem, {})
    manifest[model_stem] = {
        "name": model_stem,
        "created_at": time.time(),
        "pinned": bool(existing.get("pinned", False) or pinned),
    }
    pruned = _prune_old_models(manifest, keep_stem=model_stem)
    _save_manifest(manifest)
    return pruned


@tool
def detect_blender() -> str:
    """Check whether Blender is installed on this Windows PC and return its executable path."""
    exe = find_blender_executable()
    if exe:
        return json.dumps({"installed": True, "blender_executable": exe}, indent=2)
    return json.dumps(
        {
            "installed": False,
            "blender_executable": None,
            "hint": "Blender executable not found on PATH or C:\\Program Files\\Blender Foundation. "
            "Install Blender or set BLENDER_PATH in .env. Scripts can still be generated.",
        },
        indent=2,
    )


@tool
def save_blender_model_keep_safe(model_name: str) -> str:
    """
    Mark a generated Blender model as saved/pinned so it will NOT be deleted
    by the 2-recent-models auto-cleanup rule. Call ONLY when the user asks to
    keep or save a model safely.
    """
    clean_name = re.sub(r"[^A-Za-z0-9_-]+", "_", model_name).strip("_")
    manifest = _sync_manifest_with_disk(_load_manifest())
    if clean_name not in manifest:
        return json.dumps(
            {
                "status": "not_found",
                "model_name": clean_name,
                "available_models": list(manifest.keys()),
            },
            indent=2,
        )
    manifest[clean_name]["pinned"] = True
    _save_manifest(manifest)
    return json.dumps(
        {"status": "saved_keep_safe", "model_name": clean_name, "pinned": True},
        indent=2,
    )


@tool
def list_stored_blender_models() -> str:
    """List currently retained Blender models (max 2 recent unpinned + any user-saved pinned models)."""
    manifest = _sync_manifest_with_disk(_load_manifest())
    _save_manifest(manifest)
    return json.dumps({"models": list(manifest.values())}, indent=2)


@tool
def create_blender_model_script(
    model_name: str,
    bpy_script_code: str,
    export_format: str = "fbx",
    keep_safe: bool = False,
) -> str:
    """
    Save a procedural Blender Python (bpy) script to workspace/blender/<model_name>.py,
    inject Blender-version-safe realism helpers (kugane_make_material, kugane_add_bevel,
    kugane_add_subsurf, kugane_add_solidify, kugane_boolean_cut, kugane_create_lathe_profile,
    kugane_set_smooth, kugane_snap_on_top, kugane_ensure_studio_lights), and export
    to workspace/assets_3d/<model_name>.blend + .<export_format>.
    """
    _BLENDER_SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    _ASSETS_3D_DIR.mkdir(parents=True, exist_ok=True)

    clean_name = re.sub(r"[^A-Za-z0-9_-]+", "_", model_name).strip("_") or "kugane_model"
    fmt = export_format.lower().strip(".")
    if fmt not in {"fbx", "glb", "gltf", "blend"}:
        fmt = "fbx"

    pruned_models = register_and_prune_model(clean_name, pinned=keep_safe)

    script_path = _BLENDER_SCRIPTS_DIR / f"{clean_name}.py"
    export_path = _ASSETS_3D_DIR / f"{clean_name}.{fmt}"
    blend_path = _ASSETS_3D_DIR / f"{clean_name}.blend"

    code = bpy_script_code.strip()
    if "kugane_make_material" not in code:
        code = _REALISM_HELPERS.strip() + "\n\n" + code

    if "kugane_ensure_studio_lights()" not in code:
        m_save = re.search(
            r"^[ \t]*bpy\.ops\.(?:wm\.save_as_mainfile|export_scene\.\w+)\(",
            code,
            flags=re.MULTILINE,
        )
        if m_save:
            idx = m_save.start()
            code = code[:idx] + "kugane_ensure_studio_lights()\n\n" + code[idx:]
        else:
            code += "\n\nkugane_ensure_studio_lights()\n"

    blend_posix = blend_path.as_posix()
    export_posix = export_path.as_posix()

    if str(export_path).replace("\\", "/") not in code.replace("\\", "/") and (
        "export_scene" not in code and "save_as_mainfile" not in code
    ):
        if fmt == "fbx":
            export_block = (
                f'bpy.ops.wm.save_as_mainfile(filepath="{blend_posix}")\n'
                f'bpy.ops.export_scene.fbx(filepath="{export_posix}", use_selection=False)\n'
            )
        elif fmt in {"glb", "gltf"}:
            export_block = (
                f'bpy.ops.wm.save_as_mainfile(filepath="{blend_posix}")\n'
                f'bpy.ops.export_scene.gltf(filepath="{export_posix}", export_format="GLB")\n'
            )
        else:
            export_block = f'bpy.ops.wm.save_as_mainfile(filepath="{blend_posix}")\n'
        code += "\n" + export_block
    elif "save_as_mainfile" not in code:
        code += f'\nbpy.ops.wm.save_as_mainfile(filepath="{blend_posix}")\n'

    script_path.write_text(code, encoding="utf-8")
    return json.dumps(
        {
            "status": "script_saved",
            "model_name": clean_name,
            "script_path": str(script_path),
            "expected_export_path": str(export_path),
            "blend_path": str(blend_path),
            "pruned_old_models": pruned_models,
        },
        indent=2,
    )


@tool
def run_blender_script(script_path: str, open_gui: bool = False) -> str:
    """
    Build and verify the 3D model in headless Blender first (returncode == 0,
    no Python tracebacks, .blend file exists).
    Keep open_gui=False while building & running verify_blender_model_against_requirements,
    then call open_blender_model_gui(model_name) (or open_gui=True) once verified!
    """
    s_path = Path(script_path)
    if not s_path.is_file():
        return json.dumps({"status": "error", "error": f"Script not found: {script_path}"})

    exe = find_blender_executable()
    if not exe:
        return json.dumps(
            {
                "status": "blender_not_installed",
                "script_path": str(s_path),
                "message": (
                    "Blender executable was not found, so the script was saved but not executed. "
                    "Install Blender or set BLENDER_PATH in .env."
                ),
            },
            indent=2,
        )

    res = subprocess.run(
        [exe, "--background", "--python", str(s_path)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    exported = [
        str(p)
        for p in _ASSETS_3D_DIR.glob("*")
        if p.is_file() and p.stem == s_path.stem and not p.name.endswith(".blend1")
    ]
    blend_file = _ASSETS_3D_DIR / f"{s_path.stem}.blend"

    has_py_error = (
        res.returncode != 0
        or "Traceback (most recent call last):" in (res.stderr or "")
        or "Traceback (most recent call last):" in (res.stdout or "")
    )
    if has_py_error or not blend_file.is_file():
        return json.dumps(
            {
                "status": "failed",
                "returncode": res.returncode,
                "blend_exists": blend_file.is_file(),
                "exported_files": exported,
                "stdout_tail": (res.stdout or "")[-1200:],
                "stderr_tail": (res.stderr or "")[-1200:],
                "action_required": "Fix the Python/bpy error in the script and re-run before verification.",
            },
            indent=2,
        )

    pruned_models = register_and_prune_model(s_path.stem)

    gui_pid = None
    if open_gui:
        proc = subprocess.Popen(
            [exe, str(blend_file)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0),
        )
        gui_pid = proc.pid

    return json.dumps(
        {
            "status": "completed_and_opened_in_blender" if gui_pid else "completed_ready_for_verification",
            "returncode": res.returncode,
            "model_name": s_path.stem,
            "blend_file": str(blend_file),
            "exported_files": exported,
            "blender_gui_pid": gui_pid,
            "pruned_old_models": pruned_models,
            "stdout_tail": (res.stdout or "")[-800:],
        },
        indent=2,
    )


@tool
def verify_blender_model_against_requirements(
    model_name: str,
    user_requirements: str,
) -> str:
    """
    Inspect the built Blender model (<model_name>.blend) structurally and visually
    against the user's requirements before opening Blender:
      1) Audits geometry counts, materials, modifiers, and part bounds.
      2) Renders a temporary preview PNG in headless Blender.
      3) Passes the preview + structural audit + user_requirements to the active
         VLM/LLM to verify accuracy & realism and suggest exact fixes if needed.
    """
    clean_name = re.sub(r"[^A-Za-z0-9_-]+", "_", model_name).strip("_")
    blend_file = _ASSETS_3D_DIR / f"{clean_name}.blend"
    if not blend_file.is_file():
        return json.dumps(
            {"passed": False, "error": f"Built .blend not found for {clean_name}."}
        )

    exe = find_blender_executable()
    if not exe:
        return json.dumps(
            {
                "passed": False,
                "error": "Blender executable not found; cannot run structural & visual verification.",
            }
        )

    _BLENDER_SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    inspect_py = _BLENDER_SCRIPTS_DIR / f"_verify_{clean_name}.py"
    preview_png = _ASSETS_3D_DIR / f".verify_{clean_name}.png"
    audit_json = _ASSETS_3D_DIR / f".verify_{clean_name}.json"

    inspect_py.write_text(_VERIFY_INSPECT_SCRIPT.strip() + "\n", encoding="utf-8")

    try:
        res = subprocess.run(
            [
                exe,
                "--background",
                "--python",
                str(inspect_py),
                "--",
                str(blend_file),
                str(preview_png),
                str(audit_json),
            ],
            capture_output=True,
            text=True,
            timeout=180,
        )
        if res.returncode != 0 or not audit_json.is_file():
            return json.dumps(
                {
                    "passed": False,
                    "error": "Verification inspection failed in Blender.",
                    "stderr_tail": (res.stderr or "")[-800:],
                }
            )

        audit = json.loads(audit_json.read_text(encoding="utf-8"))
        structural_issues: list[str] = []
        if audit.get("object_count", 0) == 0:
            structural_issues.append("Scene contains 0 geometry objects.")
        if audit.get("total_faces", 0) < 12:
            structural_issues.append(
                f"Geometry is too primitive (only {audit.get('total_faces', 0)} faces)."
            )
        if audit.get("unmaterialed_objects"):
            structural_issues.append(
                f"Meshes missing materials: {audit['unmaterialed_objects']}"
            )

        model = _BLENDER_MODEL_GETTER() if _BLENDER_MODEL_GETTER is not None else None
        if model is None:
            passed = not structural_issues
            return json.dumps(
                {
                    "passed": passed,
                    "accuracy_score": 8 if passed else 3,
                    "structural_audit": audit,
                    "geometry_or_realism_issues": structural_issues,
                    "refinement_instructions": "" if passed else "; ".join(structural_issues),
                },
                indent=2,
            )

        blocks: list[dict[str, Any]] = []
        if preview_png.is_file():
            b64 = base64.b64encode(preview_png.read_bytes()).decode("ascii")
            blocks.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{b64}"},
                }
            )

        blocks.append(
            {
                "type": "text",
                "text": (
                    "You are a strict 3D Quality & Requirements Verifier.\n"
                    f"User Requirements:\n{user_requirements}\n\n"
                    f"Blender Structural Audit:\n{json.dumps(audit, indent=2)}\n\n"
                    f"Pre-detected Structural Issues: {structural_issues}\n\n"
                    "Evaluate the rendered 3D model preview + structural audit against the user's "
                    "requirements. Reply ONLY with valid JSON matching:\n"
                    '{"passed": true/false, "accuracy_score": 1-10, '
                    '"missing_features": [...], "geometry_or_realism_issues": [...], '
                    '"refinement_instructions": "specific bpy fixes if not passed"}'
                ),
            }
        )
        resp = model.invoke([HumanMessage(content=blocks)])
        raw = resp.content if isinstance(resp.content, str) else str(resp.content)

        verdict: dict[str, Any] = {}
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            try:
                verdict = json.loads(m.group(0))
            except Exception:
                verdict = {}

        if not verdict:
            verdict = {
                "passed": not structural_issues,
                "accuracy_score": 7 if not structural_issues else 3,
                "missing_features": [],
                "geometry_or_realism_issues": structural_issues,
                "refinement_instructions": raw[:500],
            }

        if structural_issues:
            verdict["passed"] = False
            existing_issues = list(verdict.get("geometry_or_realism_issues") or [])
            verdict["geometry_or_realism_issues"] = structural_issues + existing_issues

        verdict["structural_audit"] = {
            "object_count": audit.get("object_count"),
            "total_verts": audit.get("total_verts"),
            "total_faces": audit.get("total_faces"),
            "rendered_preview": audit.get("rendered_preview"),
        }
        return json.dumps(verdict, indent=2)
    finally:
        for tmp_file in (inspect_py, preview_png, audit_json):
            try:
                tmp_file.unlink(missing_ok=True)
            except OSError:
                pass


@tool
def open_blender_model_gui(model_name: str) -> str:
    """
    Open the completed and verified <model_name>.blend file inside Blender GUI
    on the user's system. Call AFTER verify_blender_model_against_requirements passes.
    """
    clean_name = re.sub(r"[^A-Za-z0-9_-]+", "_", model_name).strip("_")
    blend_file = _ASSETS_3D_DIR / f"{clean_name}.blend"
    if not blend_file.is_file():
        return json.dumps({"status": "error", "error": f".blend file not found: {blend_file}"})

    exe = find_blender_executable()
    if not exe:
        return json.dumps({"status": "blender_not_installed", "blend_file": str(blend_file)})

    proc = subprocess.Popen(
        [exe, str(blend_file)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "DETACHED_PROCESS", 0),
    )
    return json.dumps(
        {
            "status": "opened_in_blender",
            "model_name": clean_name,
            "blend_file": str(blend_file),
            "blender_gui_pid": proc.pid,
        },
        indent=2,
    )
