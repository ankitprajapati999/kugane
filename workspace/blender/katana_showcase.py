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

import bpy
import math
import os

bpy.ops.wm.read_factory_settings(use_empty=True)

# Ensure Cycles render engine for realistic shadows and DOF
bpy.context.scene.render.engine = 'CYCLES'
bpy.context.scene.cycles.samples = 64
bpy.context.scene.render.resolution_x = 1920
bpy.context.scene.render.resolution_y = 1080

# Create World Background
world = bpy.context.scene.world
if not world:
    world = bpy.data.worlds.new("StudioWorld")
    bpy.context.scene.world = world
world.node_tree.nodes.get("Background").inputs[0].default_value = (0.03, 0.03, 0.04, 1.0)

# --- DIRECT MATERIAL CREATION ---
def make_mat(name, color, metallic=0.0, roughness=0.5):
    mat = bpy.data.materials.new(name=name)
    mat.node_tree.nodes.get("Principled BSDF").inputs["Base Color"].default_value = (*color, 1.0)
    mat.node_tree.nodes.get("Principled BSDF").inputs["Metallic"].default_value = metallic
    mat.node_tree.nodes.get("Principled BSDF").inputs["Roughness"].default_value = roughness
    return mat

mat_steel = make_mat("BladeSteel", (0.85, 0.86, 0.88), metallic=0.98, roughness=0.15)
mat_brass = make_mat("FittingsBrass", (0.85, 0.65, 0.2), metallic=0.9, roughness=0.25)
mat_ito = make_mat("SilkWrap", (0.08, 0.08, 0.09), roughness=0.6)
mat_wood = make_mat("ScabbardLacquer", (0.05, 0.05, 0.06), metallic=0.1, roughness=0.2)
mat_stand = make_mat("StandWood", (0.12, 0.08, 0.05), roughness=0.4)

def assign_mat(obj, mat):
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)

# --- PROCEDURAL KATANA MODEL ---

# 1. Blade (Nagasa)
bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.4, 0, 0))
blade = bpy.context.active_object
blade.name = "KatanaBlade"
bpy.ops.object.mode_set(mode='EDIT')
import bmesh
bm = bmesh.from_edit_mesh(blade.data)
for v in bm.verts:
    v.co.x *= 0.75
    v.co.y *= 0.03
    v.co.z *= 0.008
bmesh.update_edit_mesh(blade.data)
bpy.ops.object.mode_set(mode='OBJECT')
assign_mat(blade, mat_steel)

# 2. Tsuba (Guard)
bpy.ops.mesh.primitive_cylinder_add(radius=0.045, depth=0.006, vertices=32, location=(0, 0, 0))
tsuba = bpy.context.active_object
tsuba.name = "KatanaTsuba"
tsuba.rotation_euler = (0, math.radians(90), 0)
assign_mat(tsuba, mat_brass)

# 3. Tsuka (Handle)
bpy.ops.mesh.primitive_cube_add(size=1.0, location=(-0.17, 0, 0))
tsuka = bpy.context.active_object
tsuka.name = "KatanaTsuka"
bpy.ops.object.mode_set(mode='EDIT')
bm = bmesh.from_edit_mesh(tsuka.data)
for v in bm.verts:
    v.co.x *= 0.22
    v.co.y *= 0.028
    v.co.z *= 0.022
bmesh.update_edit_mesh(tsuka.data)
bpy.ops.object.mode_set(mode='OBJECT')
assign_mat(tsuka, mat_ito)

# 4. Saya (Scabbard)
bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.35, -0.06, -0.04))
saya = bpy.context.active_object
saya.name = "KatanaSaya"
bpy.ops.object.mode_set(mode='EDIT')
bm = bmesh.from_edit_mesh(saya.data)
for v in bm.verts:
    v.co.x *= 0.82
    v.co.y *= 0.034
    v.co.z *= 0.025
bmesh.update_edit_mesh(saya.data)
bpy.ops.object.mode_set(mode='OBJECT')
saya.rotation_euler = (0, math.radians(4), 0)
assign_mat(saya, mat_wood)

# 5. Display Stand
bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.2, 0, -0.12))
stand = bpy.context.active_object
stand.name = "DisplayStand"
bpy.ops.object.mode_set(mode='EDIT')
bm = bmesh.from_edit_mesh(stand.data)
for v in bm.verts:
    v.co.x *= 0.7
    v.co.y *= 0.15
    v.co.z *= 0.03
bmesh.update_edit_mesh(stand.data)
bpy.ops.object.mode_set(mode='OBJECT')
assign_mat(stand, mat_stand)


# --- CINEMATIC CAMERA & 3-POINT STUDIO LIGHTING SETUP ---

# Camera
bpy.ops.object.camera_add(location=(0.4, -0.9, 0.35), rotation=(math.radians(65), 0, math.radians(25)))
camera = bpy.context.active_object
camera.name = "CinematicCamera"
bpy.context.scene.camera = camera

# Depth of Field in Blender 5.x / modern API
camera.data.dof.use_dof = True
camera.data.dof.aperture_fstop = 2.8
camera.data.dof.focus_distance = 0.95

# 3-Point Studio Lighting Setup
# 1. Key Light
bpy.ops.object.light_add(type='AREA', location=(0.3, -0.7, 0.8))
key_light = bpy.context.active_object
key_light.name = "KeyLight"
key_light.data.energy = 350.0
key_light.data.size = 0.8
key_light.rotation_euler = (math.radians(45), math.radians(15), math.radians(-30))

# 2. Fill Light
bpy.ops.object.light_add(type='AREA', location=(0.6, 0.5, 0.5))
fill_light = bpy.context.active_object
fill_light.name = "FillLight"
fill_light.data.energy = 120.0
fill_light.data.size = 1.2
fill_light.rotation_euler = (math.radians(60), math.radians(-30), math.radians(140))

# 3. Rim Light
bpy.ops.object.light_add(type='AREA', location=(0.0, 0.8, 0.7))
rim_light = bpy.context.active_object
rim_light.name = "RimLight"
rim_light.data.energy = 500.0
rim_light.data.size = 0.6
rim_light.rotation_euler = (math.radians(-50), math.radians(45), math.radians(180))

# Render showcase image
render_output_path = os.path.abspath("workspace/assets_3d/katana_showcase.png")
bpy.context.scene.render.filepath = render_output_path
bpy.ops.render.render(write_still=True)
print(f"Successfully rendered showcase image to {render_output_path}")
bpy.ops.wm.save_as_mainfile(filepath="E:/kugane/workspace/assets_3d/katana_showcase.blend")
