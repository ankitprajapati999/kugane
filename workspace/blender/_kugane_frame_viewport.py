import bpy

def _kugane_frame_gui_viewport():
    scene = bpy.context.scene
    cam = scene.camera
    for win in bpy.context.window_manager.windows:
        for area in win.screen.areas:
            if area.type == "VIEW_3D":
                space = area.spaces.active
                if cam is not None:
                    space.camera = cam
                    space.clip_start = cam.data.clip_start
                    space.clip_end = cam.data.clip_end
                if space.shading.type == "SOLID":
                    space.shading.color_type = "MATERIAL"
                r3d = space.region_3d
                if r3d is not None:
                    r3d.view_perspective = "CAMERA"
                region = next((r for r in area.regions if r.type == "WINDOW"), None)
                if region is not None:
                    try:
                        with bpy.context.temp_override(window=win, area=area, region=region):
                            bpy.ops.view3d.view_center_camera()
                    except Exception:
                        pass
    return None

bpy.app.timers.register(_kugane_frame_gui_viewport, first_interval=0.35)
