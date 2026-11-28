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
import bmesh
import math

# Clear scene
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# Helper: Create realistic material
def make_material(name, base_color, roughness=0.3, metallic=0.0, clearcoat=0.0):
    mat = bpy.data.materials.new(name=name)
    mat.node_tree.nodes.clear()
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    
    shader = nodes.new(type='ShaderNodeBsdfPrincipled')
    shader.location = (0, 0)
    shader.inputs['Base Color'].default_value = base_color
    shader.inputs['Roughness'].default_value = roughness
    shader.inputs['Metallic'].default_value = metallic
    if 'Clearcoat' in shader.inputs:
        shader.inputs['Clearcoat'].default_value = clearcoat
        
    out = nodes.new(type='ShaderNodeOutputMaterial')
    out.location = (300, 0)
    links.new(shader.outputs['BSDF'], out.inputs['Surface'])
    return mat

# Materials
mat_steel = make_material("Steel", (0.85, 0.87, 0.9, 1.0), roughness=0.15, metallic=1.0)
mat_brass = make_material("BrassTsuba", (0.85, 0.65, 0.2, 1.0), roughness=0.25, metallic=0.9)
mat_ito = make_material("ItoBlack", (0.05, 0.05, 0.05, 1.0), roughness=0.8, metallic=0.0)
mat_gold = make_material("GoldAccents", (0.9, 0.75, 0.2, 1.0), roughness=0.2, metallic=0.95)
mat_saya = make_material("SayaRedLacquer", (0.35, 0.02, 0.02, 1.0), roughness=0.2, metallic=0.1, clearcoat=0.5)

# 1. BLADE (Toshin) - Curved geometry
mesh = bpy.data.meshes.new("KatanaMesh")
blade = bpy.data.objects.new("Katana_Blade", mesh)
bpy.context.collection.objects.link(blade)

bm = bmesh.new()
steps = 50
for i in range(steps):
    y = (i / (steps - 1)) * 0.75
    curv = 0.03 * ((y / 0.75) ** 1.5)
    
    w = 0.032 * (1.0 - 0.3 * (y / 0.75))
    if y > 0.68:
        w *= (1.0 - (y - 0.68) / 0.07)
        
    th = 0.007 * (1.0 - 0.2 * (y / 0.75))
    
    bm.verts.new((curv, y, th))
    bm.verts.new((curv - w, y, -th * 0.8))
    bm.verts.new((curv - w * 0.35, y, 0))

bm.verts.ensure_lookup_table()

for i in range(steps - 1):
    row1_0 = bm.verts[i*3 + 0]
    row1_1 = bm.verts[i*3 + 1]
    row1_2 = bm.verts[i*3 + 2]
    
    row2_0 = bm.verts[(i+1)*3 + 0]
    row2_1 = bm.verts[(i+1)*3 + 1]
    row2_2 = bm.verts[(i+1)*3 + 2]
    
    bm.faces.new((row1_0, row1_2, row2_2, row2_0))
    bm.faces.new((row1_2, row1_1, row2_1, row2_2))

bm.to_mesh(mesh)
bm.free()

blade.data.materials.append(mat_steel)
bpy.ops.object.select_all(action='DESELECT')
blade.select_set(True)
bpy.context.view_layer.objects.active = blade
bpy.ops.object.shade_smooth()

# 2. HABAKI
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0.02, 0))
habaki = bpy.context.active_object
habaki.name = "Katana_Habaki"
habaki.scale = (0.028, 0.04, 0.012)
bpy.ops.object.transform_apply(scale=True)
habaki.data.materials.append(mat_brass)

# 3. TSUBA
bpy.ops.mesh.primitive_cylinder_add(radius=0.042, depth=0.006, vertices=32, location=(0, -0.015, 0))
tsuba = bpy.context.active_object
tsuba.name = "Katana_Tsuba"
tsuba.rotation_euler = (math.radians(90), 0, 0)
bpy.ops.object.transform_apply(rotation=True)
tsuba.data.materials.append(mat_brass)

# 4. TSUKA
bpy.ops.mesh.primitive_cylinder_add(radius=0.016, depth=0.19, vertices=24, location=(0, -0.125, 0))
tsuka = bpy.context.active_object
tsuka.name = "Katana_Tsuka"
tsuka.rotation_euler = (math.radians(90), 0, 0)
bpy.ops.object.transform_apply(rotation=True)
tsuka.data.materials.append(mat_ito)

# Menuki
bpy.ops.mesh.primitive_uv_sphere_add(radius=0.006, location=(-0.012, -0.10, 0))
menuki1 = bpy.context.active_object
menuki1.name = "Katana_Menuki_L"
menuki1.scale = (0.5, 2.0, 0.8)
bpy.ops.object.transform_apply(scale=True)
menuki1.data.materials.append(mat_gold)

bpy.ops.mesh.primitive_uv_sphere_add(radius=0.006, location=(0.012, -0.14, 0))
menuki2 = bpy.context.active_object
menuki2.name = "Katana_Menuki_R"
menuki2.scale = (0.5, 2.0, 0.8)
bpy.ops.object.transform_apply(scale=True)
menuki2.data.materials.append(mat_gold)

# 5. KASHIRA
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, -0.225, 0))
kashira = bpy.context.active_object
kashira.name = "Katana_Kashira"
kashira.scale = (0.022, 0.015, 0.014)
bpy.ops.object.transform_apply(scale=True)
kashira.rotation_euler = (math.radians(90), 0, 0)
bpy.ops.object.transform_apply(rotation=True)
kashira.data.materials.append(mat_brass)

# 6. SAYA (Scabbard - perfectly aligned along the blade curve path)
bpy.ops.mesh.primitive_cube_add(size=1, location=(0.015, 0.38, 0))
saya = bpy.context.active_object
saya.name = "Katana_Saya"
saya.scale = (0.038, 0.78, 0.022)
bpy.ops.object.transform_apply(scale=True)
saya.data.materials.append(mat_saya)
bpy.ops.object.shade_smooth()

# Export to GLB
export_path = "workspace/assets_3d/katana.glb"
bpy.ops.export_scene.gltf(filepath=export_path, export_format='GLB', use_selection=False)
print("Successfully exported katana to:", export_path)
bpy.ops.wm.save_as_mainfile(filepath="E:/kugane/workspace/assets_3d/katana.blend")
