#!/usr/bin/env python3
# Большой Гатчинский дворец — детальная модель с настоящими PBR-материалами.
# Рустованный цоколь, ашларовые этажи, тяги, наличники, карниз, балюстрада,
# две пятигранные башни (Часовая/Сигнальная), центральный портик. Экспорт GLB
# + предпросмотр в Cycles.
import bpy, bmesh, math, os, sys
import numpy as np
from mathutils import Vector

A = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
ROOT = A[0] if A else "/home/user/mmorpg3dnew"
PREVIEW = A[1] if len(A) > 1 else ""
TEX = os.path.join(ROOT, "game/world/textures")
OUT = os.path.join(ROOT, "game/world/buildings")

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene

# ---------- материалы с текстурами ----------
def img(name):
    p = os.path.join(TEX, name)
    im = bpy.data.images.load(p, check_existing=True)
    return im

def tex_mat(name, alb, nrm, rgh, color=(1,1,1), metal=0.0, rough_mul=1.0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs[0], out.inputs[0])
    bsdf.inputs["Metallic"].default_value = metal
    if alb:
        ta = nt.nodes.new("ShaderNodeTexImage"); ta.image = img(alb); ta.image.colorspace_settings.name='sRGB'
        if color != (1,1,1):
            mix = nt.nodes.new("ShaderNodeMixRGB"); mix.blend_type='MULTIPLY'; mix.inputs[0].default_value=1.0
            mix.inputs[2].default_value=(*color,1)
            nt.links.new(ta.outputs[0], mix.inputs[1]); nt.links.new(mix.outputs[0], bsdf.inputs["Base Color"])
        else:
            nt.links.new(ta.outputs[0], bsdf.inputs["Base Color"])
    else:
        bsdf.inputs["Base Color"].default_value = (*color,1)
    if nrm:
        tn = nt.nodes.new("ShaderNodeTexImage"); tn.image = img(nrm); tn.image.colorspace_settings.name='Non-Color'
        nm = nt.nodes.new("ShaderNodeNormalMap"); nm.inputs["Strength"].default_value=1.0
        nt.links.new(tn.outputs[0], nm.inputs["Color"]); nt.links.new(nm.outputs[0], bsdf.inputs["Normal"])
    if rgh:
        tr = nt.nodes.new("ShaderNodeTexImage"); tr.image = img(rgh); tr.image.colorspace_settings.name='Non-Color'
        if rough_mul != 1.0:
            mr = nt.nodes.new("ShaderNodeMath"); mr.operation='MULTIPLY'; mr.inputs[1].default_value=rough_mul
            nt.links.new(tr.outputs[0], mr.inputs[0]); nt.links.new(mr.outputs[0], bsdf.inputs["Roughness"])
        else:
            nt.links.new(tr.outputs[0], bsdf.inputs["Roughness"])
    return m

STONE = tex_mat("stone", "stone_albedo.png", "stone_normal.png", "stone_rough.png")
RUSTIC = tex_mat("rustic", "rustic_albedo.png", "rustic_normal.png", "rustic_rough.png")
ROOF = tex_mat("roof", None, None, None, color=(0.17, 0.30, 0.27), metal=0.0)
ROOF.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.6
TRIM = tex_mat("trim", None, None, None, color=(0.80,0.77,0.70))          # окрашенные наличники
GLASS = tex_mat("glass", None, None, None, color=(0.06,0.09,0.12), metal=0.0)
GLASS.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.08
GOLD = tex_mat("gold", None, None, None, color=(0.78,0.60,0.20), metal=1.0)
GOLD.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.28

OBJS = []
def cube_uv(obj, scale):
    me = obj.data
    bm = bmesh.new(); bm.from_mesh(me)
    uv = bm.loops.layers.uv.verify()
    mw = obj.matrix_world
    for f in bm.faces:
        n = f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))   # доминантная ось
        for l in f.loops:
            co = mw @ l.vert.co
            if ax == 0: u,v = co.y, co.z
            elif ax == 1: u,v = co.x, co.z
            else: u,v = co.x, co.y
            l[uv].uv = (u/scale, v/scale)
    bm.to_mesh(me); bm.free()

def box(x0,x1, y0,y1, z0,z1, mat, uv=2.0, name="box"):
    me = bpy.data.meshes.new(name); o = bpy.data.objects.new(name, me)
    sc.collection.objects.link(o)
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces); bm.to_mesh(me); bm.free()
    o.scale = ((x1-x0)/1, (y1-y0)/1, (z1-z0)/1)
    o.location = ((x0+x1)/2,(y0+y1)/2,(z0+z1)/2)
    bpy.context.view_layer.update()
    o.data.materials.append(mat)
    cube_uv(o, uv)
    OBJS.append(o); return o

def roof_hip(x0, x1, y0, y1, z0, zr, mat, ins=8.0, uv=3.0, name="roof"):
    yc = (y0+y1)/2
    v = [(x0,y0,z0),(x1,y0,z0),(x1,y1,z0),(x0,y1,z0),(x0+ins,yc,zr),(x1-ins,yc,zr)]
    faces = [(0,1,5,4),(2,3,4,5),(1,2,5),(3,0,4)]
    me = bpy.data.meshes.new(name); o = bpy.data.objects.new(name, me)
    sc.collection.objects.link(o)
    bm = bmesh.new()
    bv = [bm.verts.new(p) for p in v]
    for f in faces: bm.faces.new([bv[i] for i in f])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=6, use_grid_fill=True)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.normal_update()
    bm.to_mesh(me); bm.free()
    o.data.materials.append(mat); cube_uv(o, uv); OBJS.append(o); return o

def prism(cx, cy, z0, z1, radius, sides, mat, rot=0.0, uv=2.0, name="prism"):
    me = bpy.data.meshes.new(name); o = bpy.data.objects.new(name, me)
    sc.collection.objects.link(o)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=sides, radius1=radius, radius2=radius, depth=z1-z0)
    bm.to_mesh(me); bm.free()
    o.location = (cx, cy, (z0+z1)/2); o.rotation_euler=(0,0,rot)
    bpy.context.view_layer.update()
    o.data.materials.append(mat); cube_uv(o, uv); OBJS.append(o); return o

# ================= ГЕОМЕТРИЯ =================
HALF = 60.0          # половина длины главного корпуса (корпус 120 м)
DEP = 22.0           # глубина
FY = DEP/2           # южный фасад (+Y)
Zg, Z2, Z3, Zc = 0.0, 5.2, 10.8, 15.4     # низ этажей и карниза
Ztop = 16.6
# --- корпус по этажам ---
box(-HALF, HALF, -FY, FY, Zg, Z2, RUSTIC, uv=2.6, name="ground")       # рустованный цоколь
box(-HALF, HALF, -FY, FY, Z2, Z3, STONE, uv=2.2, name="floor2")         # бельэтаж
box(-HALF, HALF, -FY, FY, Z3, Zc, STONE, uv=2.2, name="floor3")         # верхний этаж
# --- тяги/карнизы (протяжённые пояски) ---
def band(z0, z1, over, mat=TRIM):
    box(-HALF-over, HALF+over, -FY-over, FY+over, z0, z1, mat, uv=2.0, name="band")
band(Z2-0.15, Z2+0.15, 0.25)                     # межэтажная тяга
band(Z3-0.12, Z3+0.12, 0.18)
band(Zc, Zc+0.7, 0.6)                            # главный карниз
# --- балюстрада-парапет ---
box(-HALF-0.3, HALF+0.3, -FY-0.3, FY+0.3, Zc+0.7, Zc+0.8, TRIM, name="parapet_base")
nb = int((HALF*2)/1.6)
for i in range(nb+1):
    x = -HALF + i*(HALF*2)/nb
    box(x-0.12, x+0.12, FY+0.05, FY+0.3, Zc+0.8, Ztop-0.15, TRIM, uv=1.0, name="baluster")
    box(x-0.12, x+0.12, -FY-0.3, -FY-0.05, Zc+0.8, Ztop-0.15, TRIM, uv=1.0, name="baluster")
box(-HALF-0.3, HALF+0.3, FY+0.0, FY+0.35, Ztop-0.15, Ztop, TRIM, name="railcap_s")
box(-HALF-0.3, HALF+0.3, -FY-0.35, -FY-0.0, Ztop-0.15, Ztop, TRIM, name="railcap_n")
# вальмовая кровля (низкая, за балюстрадой)
roof_hip(-HALF+0.5, HALF-0.5, -FY+0.5, FY-0.5, Zc+0.7, Zc+3.2, ROOF, ins=9.0, name="roof")

# --- окна с наличниками (на южном и северном фасадах) ---
def window(x, z, w, h, y_face, tall=False):
    d = 0.35
    yf = y_face
    s = 1 if yf > 0 else -1
    # проём (тёмное стекло, утоплено)
    box(x-w/2, x+w/2, yf - s*d, yf - s*(d-0.25), z, z+h, GLASS, uv=1.0, name="pane")
    # рама-наличник
    fr = 0.22
    box(x-w/2-fr, x-w/2, yf-s*0.05, yf+s*0.12, z-fr, z+h+fr, TRIM, uv=1.0, name="jamb")
    box(x+w/2, x+w/2+fr, yf-s*0.05, yf+s*0.12, z-fr, z+h+fr, TRIM, uv=1.0, name="jamb")
    box(x-w/2-fr, x+w/2+fr, yf-s*0.05, yf+s*0.12, z+h, z+h+fr, TRIM, uv=1.0, name="lintel")
    # подоконник
    box(x-w/2-fr-0.1, x+w/2+fr+0.1, yf-s*0.05, yf+s*0.28, z-fr-0.12, z-fr, TRIM, uv=1.0, name="sill")
    # сандрик (карниз над окном бельэтажа)
    if tall:
        box(x-w/2-fr-0.2, x+w/2+fr+0.2, yf-s*0.05, yf+s*0.40, z+h+fr, z+h+fr+0.28, TRIM, name="pediment")

def window_row(z, h, tall, faces=(FY,-FY), step=4.0, skip_center=6.0):
    n = int((HALF*2-4)/step)
    for i in range(n+1):
        x = -HALF+2 + i*(HALF*2-4)/n
        if abs(x) < skip_center:   # оставить место центральному портику
            continue
        for yf in faces:
            window(x, z, 1.5 if not tall else 1.7, h, yf, tall)

window_row(Zg+1.4, 2.6, False)          # цоколь: арочные заменим прямоуг.
window_row(Z2+0.9, 3.4, True)           # бельэтаж — высокие окна с сандриками
window_row(Z3+0.7, 2.6, False)          # верх

# --- центральный портик ---
box(-8.5, 8.5, FY-0.2, FY+2.6, Zg, Z3+0.6, STONE, uv=2.2, name="portico")
for cx in (-6.5,-3.2,3.2,6.5):          # 4 колонны
    prism(cx, FY+2.2, Zg, Z2+0.2, 0.55, 16, TRIM, uv=1.5, name="column")
box(-8.5, 8.5, FY+1.6, FY+2.8, Z2+0.2, Z2+0.9, TRIM, name="portico_arch")   # антаблемент
box(-7, 7, FY+0.4, FY+2.6, Z3+0.6, Z3+0.9, TRIM, name="balcony")            # балкон
# фронтон над портиком
prism(0, FY+1.5, Z3+0.9, Z3+3.4, 9.0, 3, STONE, rot=math.radians(90), uv=2.0, name="ped")

# --- две пятигранные башни на концах (Часовая и Сигнальная) ---
for sx, clock in ((-HALF+3, True), (HALF-3, False)):
    prism(sx, FY-3.0, Zg, Zc+3.0, 6.2, 5, STONE, rot=math.radians(36), uv=2.2, name="tower")
    band(Zc+3.0-0.4, Zc+3.0+0.3, 0.0)  # (no-op width) -> use explicit ring
    prism(sx, FY-3.0, Zc+3.0, Zc+3.6, 6.6, 5, TRIM, rot=math.radians(36), uv=1.0, name="tower_cornice")
    # низкий купол-фонарик
    prism(sx, FY-3.0, Zc+3.6, Zc+5.4, 3.0, 8, ROOF, uv=2.0, name="tower_dome")
    prism(sx, FY-3.0, Zc+5.4, Zc+7.2, 0.25, 8, GOLD, rot=0, uv=1.0, name="finial")
    if clock:
        box(sx-1.2, sx+1.2, FY+3.0, FY+3.3, Z3+1.5, Z3+3.9, GOLD, uv=1.0, name="clock")
    # окна башни
    for tz,th in ((Z2+0.9,3.0),(Z3+0.7,2.4)):
        window(sx, tz, 1.4, th, FY+2.9, False)

print("[palace] parts:", len(OBJS))
# диагностика крыши
for o in OBJS:
    if o.name.startswith("roof"):
        mw = o.matrix_world
        me = o.data
        tf = max(me.polygons, key=lambda p: (mw @ p.center).z)
        wn = (mw.to_3x3() @ tf.normal).normalized()
        print("[dbg] roof top-face world normal:", round(wn.x,2), round(wn.y,2), round(wn.z,2),
              "mats:", [m.name for m in me.materials])

# ================= ЭКСПОРТ =================
for o in bpy.context.selected_objects: o.select_set(False)
for o in OBJS: o.select_set(True)
bpy.context.view_layer.objects.active = OBJS[0]
bpy.ops.export_scene.gltf(filepath=os.path.join(OUT,"palace.glb"), use_selection=True,
    export_format='GLB', export_yup=True, export_apply=True)
print("[palace] exported ->", os.path.join(OUT,"palace.glb"))

# ================= CYCLES-ПРЕДПРОСМОТР =================
if PREVIEW:
    sc.render.engine='CYCLES'; sc.cycles.device='CPU'; sc.cycles.samples=40
    sc.cycles.use_denoising=True
    try: sc.cycles.denoiser='OPENIMAGEDENOISE'
    except Exception: pass
    sc.render.resolution_x=760; sc.render.resolution_y=560
    sc.view_settings.view_transform='AgX'
    world=bpy.data.worlds.new("W"); sc.world=world; world.use_nodes=True
    nt=world.node_tree; nt.nodes.clear()
    bg=nt.nodes.new("ShaderNodeBackground"); sky=nt.nodes.new("ShaderNodeTexSky")
    sky.sky_type='MULTIPLE_SCATTERING'; sky.sun_elevation=math.radians(40); sky.sun_rotation=math.radians(60)
    wout=nt.nodes.new("ShaderNodeOutputWorld")
    nt.links.new(sky.outputs[0],bg.inputs[0]); nt.links.new(bg.outputs[0],wout.inputs[0])
    sun=bpy.data.lights.new("S",'SUN'); sun.energy=3.0; sun.angle=math.radians(1.5)
    so=bpy.data.objects.new("S",sun); sc.collection.objects.link(so)
    so.rotation_euler=(math.radians(54),0,math.radians(-60))
    # земля
    gm=bpy.data.meshes.new("g"); go=bpy.data.objects.new("g",gm); sc.collection.objects.link(go)
    bm=bmesh.new(); bmesh.ops.create_grid(bm,size=600,x_segments=1,y_segments=1); bm.to_mesh(gm); bm.free()
    gmat=bpy.data.materials.new("gr"); gmat.use_nodes=True
    gmat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value=(0.20,0.25,0.13,1)
    gmat.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value=0.95
    gm.materials.append(gmat)
    cam_d=bpy.data.cameras.new("C"); cam_d.lens=52; cam=bpy.data.objects.new("C",cam_d)
    sc.collection.objects.link(cam); sc.camera=cam
    center=Vector((0,0,8));
    def shoot(az,el,dist,path):
        a=math.radians(az); e=math.radians(el)
        cam.location=center+Vector((dist*math.cos(e)*math.cos(a),dist*math.cos(e)*math.sin(a),dist*math.sin(e)))
        cam.rotation_euler=(Vector(cam.location)-center).to_track_quat('Z','Y').to_euler()
        sc.render.filepath=path; bpy.ops.render.render(write_still=True)
    views=[(-62,10,120),(-30,4,95),(20,18,120),(-90,3,90)]
    tiles=[]
    for i,(az,el,d) in enumerate(views):
        p=f"/tmp/_pl_{i}.png"; shoot(az,el,d,p); tiles.append(p)
    def load(p):
        im=bpy.data.images.load(p); w,h=im.size; a=np.empty(w*h*4,np.float32); im.pixels.foreach_get(a)
        bpy.data.images.remove(im); return a.reshape(h,w,4)
    sheet=np.ascontiguousarray(np.concatenate([np.concatenate([load(tiles[0]),load(tiles[1])],1),
        np.concatenate([load(tiles[2]),load(tiles[3])],1)],0),np.float32)
    H,W=sheet.shape[:2]; im=bpy.data.images.new("s",width=W,height=H,alpha=True)
    im.pixels.foreach_set(sheet.reshape(-1)); im.file_format='PNG'; im.filepath_raw=PREVIEW; im.save()
    print("[palace] preview ->", PREVIEW)
