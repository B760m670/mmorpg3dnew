#!/usr/bin/env python3
# Студия предпросмотра (Blender Cycles) — настоящий путь-трейсер, физические
# материалы и свет. Мои «настоящие глаза»: импортирует GLB, ставит небо Nishita,
# солнце, землю, снимает объект с нескольких ракурсов в контактный лист.
import bpy, sys, os, math
import numpy as np

A = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
GLB = A[0]
OUT = A[1] if len(A) > 1 else "/tmp/studio.png"
SAMPLES = int(A[2]) if len(A) > 2 else 48
RES = int(A[3]) if len(A) > 3 else 640

# чистая сцена
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = 'CYCLES'
sc.cycles.device = 'CPU'
sc.cycles.samples = SAMPLES
sc.cycles.use_denoising = True
try: sc.cycles.denoiser = 'OPENIMAGEDENOISE'
except Exception: pass
sc.render.resolution_x = RES
sc.render.resolution_y = RES
sc.render.film_transparent = False
sc.view_settings.view_transform = 'AgX'   # современный кинематографичный тонмаппинг
sc.view_settings.look = 'AgX - Medium High Contrast'

# небо Nishita + солнце
world = bpy.data.worlds.new("W"); sc.world = world
world.use_nodes = True
nt = world.node_tree; nt.nodes.clear()
bg = nt.nodes.new("ShaderNodeBackground")
sky = nt.nodes.new("ShaderNodeTexSky")
sky.sky_type = 'MULTIPLE_SCATTERING'
sky.sun_elevation = math.radians(38)
sky.sun_rotation = math.radians(50)
sky.air_density = 1.2
out = nt.nodes.new("ShaderNodeOutputWorld")
nt.links.new(sky.outputs[0], bg.inputs[0])
nt.links.new(bg.outputs[0], out.inputs[0])
bg.inputs[1].default_value = 1.0

sun = bpy.data.lights.new("Sun", 'SUN'); sun.energy = 3.2; sun.angle = math.radians(1.5)
sun_o = bpy.data.objects.new("Sun", sun); sc.collection.objects.link(sun_o)
sun_o.rotation_euler = (math.radians(52), 0, math.radians(-50))

# импорт GLB
bpy.ops.import_scene.gltf(filepath=GLB)
objs = [o for o in sc.objects if o.type == 'MESH']

# общий bbox
mins = np.array([1e9]*3); maxs = np.array([-1e9]*3)
for o in objs:
    for c in o.bound_box:
        w = o.matrix_world @ __import__("mathutils").Vector(c)
        mins = np.minimum(mins, [w.x, w.y, w.z]); maxs = np.maximum(maxs, [w.x, w.y, w.z])
center = (mins+maxs)/2; size = float(np.linalg.norm(maxs-mins))
ground_z = mins[2]

# земля
gm = bpy.data.meshes.new("g"); go = bpy.data.objects.new("g", gm)
sc.collection.objects.link(go)
import bmesh
bm = bmesh.new(); bmesh.ops.create_grid(bm, size=size*6, x_segments=1, y_segments=1)
bm.to_mesh(gm); bm.free()
go.location = (center[0], center[1], ground_z)
gmat = bpy.data.materials.new("ground"); gmat.use_nodes = True
gb = gmat.node_tree.nodes.get("Principled BSDF")
gb.inputs["Base Color"].default_value = (0.21, 0.26, 0.14, 1)
gb.inputs["Roughness"].default_value = 0.95
gm.materials.append(gmat)

# камера
cam_d = bpy.data.cameras.new("C"); cam_d.lens = 50
cam = bpy.data.objects.new("C", cam_d); sc.collection.objects.link(cam)
sc.camera = cam
mathutils = __import__("mathutils")

def shoot(az_deg, el_deg, dist_k, path):
    az = math.radians(az_deg); el = math.radians(el_deg)
    d = size*dist_k
    cam.location = (center[0]+d*math.cos(el)*math.cos(az),
                    center[1]+d*math.cos(el)*math.sin(az),
                    center[2]+d*math.sin(el))
    look = mathutils.Vector((center[0], center[1], center[2]))
    dirv = (mathutils.Vector(cam.location) - look)
    cam.rotation_euler = dirv.to_track_quat('Z', 'Y').to_euler()
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)

angles = [(-55, 22), (30, 16), (135, 28), (200, 14)]
tiles = []
for i, (az, el) in enumerate(angles):
    p = f"/tmp/_st_{i}.png"; shoot(az, el, 0.95, p); tiles.append(p)

# контактный лист 2x2
def load(p):
    im = bpy.data.images.load(p)
    w, h = im.size
    a = np.empty(w*h*4, np.float32); im.pixels.foreach_get(a)
    bpy.data.images.remove(im); return a.reshape(h, w, 4)
rows = [np.concatenate([load(tiles[0]), load(tiles[1])], 1),
        np.concatenate([load(tiles[2]), load(tiles[3])], 1)]
sheet = np.ascontiguousarray(np.concatenate(rows, 0), np.float32)
H, W = sheet.shape[:2]
im = bpy.data.images.new("sheet", width=W, height=H, alpha=True)
im.pixels.foreach_set(sheet.reshape(-1))
im.file_format = 'PNG'; im.filepath_raw = OUT; im.save()
print("[studio] ->", OUT, "size", size)
