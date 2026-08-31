import bpy, bmesh, math, json, os
from mathutils import Vector

def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)

def mat(name, color, rough, metal=0.0):
    m = bpy.data.materials.new(name); m.use_nodes=True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value=(*color,1)
    b.inputs["Roughness"].default_value=rough
    b.inputs["Metallic"].default_value=metal
    return m

def box(name, cx, cy, z0, sx, sy, h, m):
    bpy.ops.mesh.primitive_cube_add(location=(cx,cy,z0+h/2))
    o=bpy.context.object; o.name=name; o.scale=(sx/2,sy/2,h/2)
    bpy.ops.object.transform_apply(scale=True); o.data.materials.append(m)
    return o

def hip_roof(name, cx, cy, z0, sx, sy, h, m):
    # усечённая 4-скатная кровля: низ = периметр, верх = вжатый гребень
    verts=[(-sx/2,-sy/2,0),(sx/2,-sy/2,0),(sx/2,sy/2,0),(-sx/2,sy/2,0),
           (-sx/2*0.25,0,h),(sx/2*0.25,0,h)]
    faces=[(0,1,5,4),(1,2,5),(2,3,4,5),(3,0,4)]
    me=bpy.data.meshes.new(name); me.from_pydata(verts,[],faces); me.update()
    o=bpy.data.objects.new(name,me); bpy.context.scene.collection.objects.link(o)
    o.location=(cx,cy,z0); o.data.materials.append(m)
    return o

def tower(name, cx, cy, z0, r, h, m, mroof):
    bpy.ops.mesh.primitive_cylinder_add(vertices=5, radius=r, depth=h, location=(cx,cy,z0+h/2))
    o=bpy.context.object; o.name=name; o.data.materials.append(m)
    bpy.ops.mesh.primitive_cone_add(vertices=5, radius1=r*1.15, radius2=0, depth=r*2.2,
        location=(cx,cy,z0+h+r*1.1)); c=bpy.context.object; c.data.materials.append(mroof)
    return o

reset()
sc=bpy.context.scene
stone=mat("stone",(0.80,0.73,0.60),0.75)
roof=mat("roof",(0.14,0.15,0.17),0.55,0.6)

# --- массы дворца (координаты Blender: X восток, Y север, Z вверх), м ---
# центральный корпус (садовая, +Y), скатная кровля
box("corps",0,20,0,120,26,20,stone); hip_roof("corps_roof",0,20,20,120,26,9,roof)
# две пятигранные башни над корпусом
tower("tower_L",-26,22,20,8,14,stone,roof)
tower("tower_R", 26,22,20,8,14,stone,roof)
# концевые каре (Кухонное/Арсенальное) на юж. углах
for sx_ in (-1,1):
    box("care%d"%sx_, sx_*112, -60, 0, 44,44,16, stone)
    hip_roof("care_roof%d"%sx_, sx_*112,-60,16,44,44,7,roof)
# полукруглые галереи, охватывающие плац: дуга сегментов от корпуса к каре
for sx_ in (-1,1):
    for k in range(11):
        t=k/10.0; ang=math.radians(180*t if sx_<0 else 180*(1-t))
        # дуга радиусом ~90 от центра плаца (0,-20)
        gx=sx_* (60 + 52*math.sin(math.pi*t))
        gy=20 - 80*t
        box("gal%d_%d"%(sx_,k), gx, gy, 0, 12, 12, 8, stone)

# --- земля-подложка (трава) для контекста рендера ---
grd=mat("grass",(0.22,0.32,0.12),0.95)
box("ground",0,-20,-0.5,600,600,1,grd)

# --- свет золотого часа + камера с плаца ---
light=bpy.data.lights.new("sun",'SUN'); lo=bpy.data.objects.new("sun",light)
sc.collection.objects.link(lo); light.energy=5; light.angle=0.02
lo.rotation_euler=(math.radians(58),0,math.radians(150))
world=bpy.data.worlds.new("w"); sc.world=world; world.use_nodes=True
world.node_tree.nodes["Background"].inputs[0].default_value=(0.5,0.62,0.8,1)
world.node_tree.nodes["Background"].inputs[1].default_value=1.2
cam=bpy.data.cameras.new("c"); co=bpy.data.objects.new("c",cam); sc.collection.objects.link(co); sc.camera=co
cam.lens=42
co.location=(20,-190,70); co.rotation_euler=(math.radians(74),0,math.radians(6))

sc.render.engine='CYCLES'; sc.cycles.samples=48; sc.cycles.device='CPU'
sc.render.resolution_x=1200; sc.render.resolution_y=620
sc.view_settings.view_transform='AgX'
sc.render.filepath="/tmp/palace_cycles.png"
import time; t=time.time(); bpy.ops.render.render(write_still=True)
print("Cycles рендер дворца за %.1f с"%(time.time()-t))

# --- экспорт glTF в репозиторий (ассет в игру) ---
for o in bpy.data.objects:
    if o.name=="ground": bpy.data.objects.remove(o, do_unlink=True)
os.makedirs("game2/assets/models", exist_ok=True)
bpy.ops.object.select_all(action='SELECT')
bpy.ops.export_scene.gltf(filepath=os.path.abspath("game2/assets/models/palace"),
    export_format='GLB', use_selection=True)
print("glTF → game2/assets/models/palace.glb")
