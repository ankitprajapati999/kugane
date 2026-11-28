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

    # Subtle micro-roughness & micro-bump for realistic non-plastic surfaces
    if noise_roughness > 0 and "Roughness" in bsdf.inputs:
        tex_coord = nodes.new("ShaderNodeTexCoord")
        noise = nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = 18.0
        noise.inputs["Detail"].default_value = 6.0
        ramp = nodes.new("ShaderNodeMapRange")
        ramp.inputs["To Min"].default_value = max(0.02, roughness - noise_roughness)
        ramp.inputs["To Max"].default_value = min(0.98, roughness + noise_roughness)
        links.new(tex_coord.outputs["Object"], noise.inputs["Vector"])
        links.new(noise.outputs["Fac"], ramp.inputs["Value"])
        links.new(ramp.outputs["Result"], bsdf.inputs["Roughness"])
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
import bmesh
import math
import mathutils

# 1. Clear scene properly
bpy.ops.wm.read_factory_settings(use_empty=True)

if "Cube" in bpy.data.objects:
    bpy.data.objects.remove(bpy.data.objects["Cube"], do_unlink=True)

# 2. Materials
def make_mat(name, color, roughness, metallic=0.0):
    mat = bpy.data.materials.new(name=name)
    mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = color
    mat.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = roughness
    mat.node_tree.nodes["Principled BSDF"].inputs["Metallic"].default_value = metallic
    return mat

mat_steel = make_mat("KatanaSteel", (0.85, 0.86, 0.88, 1.0), 0.15, 0.95)
mat_habaki = make_mat("HabakiBrass", (0.85, 0.70, 0.25, 1.0), 0.25, 0.90)
mat_tsuka_wrap = make_mat("TsukaWrap", (0.08, 0.08, 0.10, 1.0), 0.7, 0.0)
mat_same = make_mat("SameSkin", (0.92, 0.90, 0.85, 1.0), 0.6, 0.0)
mat_wood = make_mat("ScabbardWood", (0.05, 0.05, 0.05, 1.0), 0.4, 0.0)
mat_metal_fittings = make_mat("FittingsDark", (0.12, 0.12, 0.12, 1.0), 0.3, 0.85)
mat_gold_accent = make_mat("GoldAccent", (0.9, 0.75, 0.2, 1.0), 0.3, 0.85)

def assign_mat(obj, mat):
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)

# --- BLADE ---
num_blade_steps = 60
blade_length = 0.75
curv_max = 0.035

bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, blade_length/2))
blade_obj = bpy.context.active_object
blade_obj.name = "KatanaBlade"
assign_mat(blade_obj, mat_steel)

mesh = blade_obj.data
bm = bmesh.new()
bm.from_mesh(mesh)

for v in bm.verts:
    z_norm = v.co.z + 0.5
    v.co.z = z_norm * blade_length
    v.co.y += curv_max * (z_norm ** 2.0)
    taper = (1.0 - z_norm * 0.65)
    v.co.x *= taper * 0.8
    if z_norm > 0.85:
        tip_t = (z_norm - 0.85) / 0.15
        v.co.y *= (1.0 - tip_t * 0.5)
        v.co.x *= (1.0 - tip_t * 0.8)

bm.to_mesh(mesh)
bm.free()

sub = blade_obj.modifiers.new(name="Subsurf", type='SUBSURF')
sub.levels = 2
sub.render_levels = 2
bev = blade_obj.modifiers.new(name="Bevel", type='BEVEL')
bev.width = 0.0008
bev.segments = 2

for poly in blade_obj.data.polygons:
    poly.use_smooth = True


# --- HABAKI ---
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, curv_max * (0.02 ** 2), 0.01))
habaki = bpy.context.active_object
habaki.name = "Habaki"
habaki.scale = (0.012, 0.032, 0.025)
bpy.ops.object.transform_apply(scale=True)
assign_mat(habaki, mat_habaki)
bev_h = habaki.modifiers.new(name="Bevel", type='BEVEL')
bev_h.width = 0.001
bev_h.segments = 2
for poly in habaki.data.polygons:
    poly.use_smooth = True


# --- TSUKA CORE & SAME-GAWA ---
tsuka_len = 0.20
tsuka_z_start = -tsuka_len/2 - 0.01
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, curv_max * (0.05 ** 2), tsuka_z_start + tsuka_len/2))
tsuka_core = bpy.context.active_object
tsuka_core.name = "TsukaCore"
tsuka_core.scale = (0.016, 0.028, tsuka_len)
bpy.ops.object.transform_apply(scale=True)
assign_mat(tsuka_core, mat_same)
for poly in tsuka_core.data.polygons:
    poly.use_smooth = True


# --- CRISP TSUKA-ITO (HANDLE WRAP) VIA CURVES WITH BEVEL ---
num_turns = 7
wrap_z_start = tsuka_z_start + 0.01
wrap_z_end = tsuka_z_start + tsuka_len - 0.01
wrap_total_len = wrap_z_end - wrap_z_start

def add_crisp_tsuka_ito_helix(sign, layer_z):
    curve_data = bpy.data.curves.new(f'TsukaHelix_{sign}', type='CURVE')
    curve_data.dimensions = '3D'
    curve_data.resolution_u = 12
    
    spline = curve_data.splines.new(type='POLY')
    steps = 120
    spline.points.add(steps - 1)
    
    for i in range(steps):
        t = i / (steps - 1)
        z = wrap_z_start + t * wrap_total_len
        angle = t * num_turns * 2 * math.pi * sign
        
        rx = 0.0175 + layer_z
        ry = 0.0295 + layer_z
        cy = curv_max * (((z - tsuka_z_start)/blade_length) ** 2.0)
        
        x = math.cos(angle) * rx
        y = cy + math.sin(angle) * ry
        spline.points[i].co = (x, y, z, 1.0)
        
    helix_obj = bpy.data.objects.new(f'TsukaWrapStrand_{sign}', curve_data)
    bpy.context.collection.objects.link(helix_obj)
    
    # Flat-topped diamond cross section bevel
    bev_data = bpy.data.curves.new(f'CordProfile_{sign}', type='CURVE')
    bev_data.dimensions = '2D'
    bev_spline = bev_data.splines.new(type='POLY')
    bev_spline.points.add(3)
    bev_spline.points[0].co = ( 0.0055,  0.0,    0, 1)
    bev_spline.points[1].co = ( 0.0,     0.0022, 0, 1)
    bev_spline.points[2].co = (-0.0055,  0.0,    0, 1)
    bev_spline.points[3].co = ( 0.0,    -0.0022, 0, 1)
    bev_spline.use_cyclic_u = True
    
    bev_obj = bpy.data.objects.new(f'CordBev_{sign}', bev_data)
    bpy.context.collection.objects.link(bev_obj)
    bev_obj.hide_viewport = True
    bev_obj.hide_render = True
    
    curve_data.bevel_object = bev_obj
    curve_data.use_fill_caps = True
    
    assign_mat(helix_obj, mat_tsuka_wrap)
    return helix_obj

wrap1 = add_crisp_tsuka_ito_helix(1.0, 0.0)
wrap2 = add_crisp_tsuka_ito_helix(-1.0, 0.0015)


# --- FUCHI & KASHIRA ---
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, curv_max * ((tsuka_z_start)/blade_length)**2, tsuka_z_start))
fuchi = bpy.context.active_object
fuchi.name = "Fuchi"
fuchi.scale = (0.019, 0.031, 0.015)
bpy.ops.object.transform_apply(scale=True)
assign_mat(fuchi, mat_metal_fittings)
bev_f = fuchi.modifiers.new(name="Bevel", type='BEVEL')
bev_f.width = 0.001
bev_f.segments = 2
for poly in fuchi.data.polygons:
    poly.use_smooth = True

bpy.ops.mesh.primitive_cube_add(size=1, location=(0, curv_max * ((tsuka_z_start + tsuka_len)/blade_length)**2, tsuka_z_start + tsuka_len))
kashira = bpy.context.active_object
kashira.name = "Kashira"
kashira.scale = (0.018, 0.030, 0.014)
bpy.ops.object.transform_apply(scale=True)
assign_mat(kashira, mat_metal_fittings)
bev_k = kashira.modifiers.new(name="Bevel", type='BEVEL')
bev_k.width = 0.001
bev_k.segments = 2
for poly in kashira.data.polygons:
    poly.use_smooth = True


# --- MENUKI ---
for side_sign in [-1, 1]:
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.005, location=(side_sign * 0.015, curv_max * 0.15, tsuka_z_start + tsuka_len * 0.45))
    menuki = bpy.context.active_object
    menuki.name = f"Menuki_{side_sign}"
    menuki.scale = (0.5, 1.0, 0.4)
    bpy.ops.object.transform_apply(scale=True)
    assign_mat(menuki, mat_gold_accent)
    for poly in menuki.data.polygons:
        poly.use_smooth = True


# --- TSUBA ---
tsuba_z = tsuka_z_start
bpy.ops.mesh.primitive_cylinder_add(radius=0.042, depth=0.005, location=(0, curv_max * ((tsuba_z)/blade_length)**2, tsuba_z))
tsuba = bpy.context.active_object
tsuba.name = "Tsuba"
tsuba.scale = (1.0, 0.85, 1.0)
bpy.ops.object.transform_apply(scale=True)
assign_mat(tsuba, mat_metal_fittings)
bev_t = tsuba.modifiers.new(name="Bevel", type='BEVEL')
bev_t.width = 0.0008
bev_t.segments = 2
for poly in tsuba.data.polygons:
    poly.use_smooth = True


# --- SAYA ---
saya_len = 0.82
saya_z_start = 0.01
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0))
saya = bpy.context.active_object
saya.name = "Saya"

mesh_s = saya.data
bm_s = bmesh.new()
bm_s.from_mesh(mesh_s)
for v in bm_s.verts:
    z_norm = (v.co.z + 0.5)
    z = saya_z_start + z_norm * saya_len
    v.co.z = z
    v.co.y += curv_max * ((z / blade_length) ** 2.0)
    taper = (1.0 - z_norm * 0.25)
    v.co.x *= 0.018 * taper
    v.co.y += 0.032 * taper * (1.0 - z_norm*0.1)
bm_s.to_mesh(mesh_s)
bm_s.free()

assign_mat(saya, mat_wood)
sub_s = saya.modifiers.new(name="Subsurf", type='SUBSURF')
sub_s.levels = 2
sub_s.render_levels = 2
bev_s = saya.modifiers.new(name="Bevel", type='BEVEL')
bev_s.width = 0.001
bev_s.segments = 2
for poly in saya.data.polygons:
    poly.use_smooth = True


# --- CLOSE-UP CAMERA SHOT FOCUSED ON HANDLE WRAP ---
bpy.ops.object.camera_add(location=(0.10, 0.06, tsuka_z_start + tsuka_len/2))
cam = bpy.context.active_object
cam.name = "HandleWrapCloseUpCamera"

target_loc = mathutils.Vector((0.0, curv_max * (0.05**2), tsuka_z_start + tsuka_len/2))
direction = target_loc - cam.location
rot_quat = direction.to_track_quat('-Z', 'Y')
cam.rotation_euler = rot_quat.to_euler()
bpy.context.scene.camera = cam


# --- EXPORT TO GLB ---
output_path = r"E:\kugane\workspace\assets_3d\japanese_katana.glb"
bpy.ops.export_scene.gltf(filepath=output_path, export_format='GLB', use_selection=False)
print("Successfully generated and exported refined katana handle wrap to:", output_path)
bpy.ops.wm.save_as_mainfile(filepath="E:/kugane/workspace/assets_3d/japanese_katana.blend")
