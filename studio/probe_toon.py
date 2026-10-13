# ПРОВЕРКА №2: настоящий аниме-кадр без видеокарты.
# Grease Pencil Line Art в Cycles закрыл кадр чёрным (проверено: 2 уникальных
# цвета на весь кадр), и разбираться с ним сейчас незачем — есть Freestyle,
# который рисует контур прямо в Cycles и работает на CPU.
# Плоский свет даёт Toon BSDF: у Cycles он есть, и это ровно ступенька
# «свет / тень» с управляемой шириной перехода. Shader to RGB не нужен (он
# только в EEVEE, а EEVEE тут не поднять — видеокарты нет).
import bpy, time, math
S = '/tmp/claude-0/-home-user-mmorpg3dnew/283ce6a4-bcad-5286-9fb2-0f049fba2e1d/scratchpad/'
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)

w = bpy.data.worlds.get('World') or bpy.data.worlds.new('World')
bpy.context.scene.world = w
w.use_nodes = True
w.node_tree.nodes['Background'].inputs[0].default_value = (0.80, 0.87, 0.97, 1)

bpy.ops.mesh.primitive_monkey_add(size=2)
bpy.ops.object.shade_smooth()
bpy.ops.object.modifier_add(type='SUBSURF')
suz = bpy.context.object

mat = bpy.data.materials.new('toon')
mat.use_nodes = True
nt = mat.node_tree
for n in list(nt.nodes):
    if n.type != 'OUTPUT_MATERIAL':
        nt.nodes.remove(n)
toon = nt.nodes.new('ShaderNodeBsdfToon')
toon.component = 'DIFFUSE'
toon.inputs['Color'].default_value = (0.86, 0.62, 0.52, 1)
toon.inputs['Size'].default_value = 0.62      # где проходит граница света и тени
toon.inputs['Smooth'].default_value = 0.02    # почти резкий край — это и есть рисунок
nt.links.new(toon.outputs[0], nt.nodes['Material Output'].inputs['Surface'])
suz.data.materials.append(mat)

cam_d = bpy.data.cameras.new('cam'); cam = bpy.data.objects.new('cam', cam_d)
bpy.context.collection.objects.link(cam)
cam.location = (0, -6, 0.9); cam.rotation_euler = (math.radians(84), 0, 0)
bpy.context.scene.camera = cam
li = bpy.data.lights.new('sun', 'SUN'); li.energy = 4.0; li.angle = 0.0
lo = bpy.data.objects.new('sun', li); bpy.context.collection.objects.link(lo)
lo.rotation_euler = (math.radians(52), 0, math.radians(38))

sc = bpy.context.scene
sc.render.engine = 'CYCLES'
sc.cycles.device = 'CPU'
sc.cycles.samples = 32
sc.render.resolution_x, sc.render.resolution_y = 720, 540
# КОНТУР. Толщина в пикселях, а не «по размеру объекта»: линия в рисунке имеет
# постоянный вес, она не худеет вдали — это одно из главных отличий рисунка от
# фотографии.
sc.render.use_freestyle = True
vl = sc.view_layers[0]
vl.freestyle_settings.crease_angle = math.radians(134)
lineset = vl.freestyle_settings.linesets[0] if vl.freestyle_settings.linesets else vl.freestyle_settings.linesets.new('outline')
lineset.select_silhouette = True
lineset.select_crease = True
lineset.select_border = True
ls = lineset.linestyle
ls.color = (0.06, 0.05, 0.08)
ls.thickness = 2.2
sc.render.line_thickness_mode = 'ABSOLUTE'
sc.render.line_thickness = 2.2

sc.render.filepath = S + 'toon.png'
t = time.time(); bpy.ops.render.render(write_still=True)
print('ТУН+КОНТУР ЗА %.1f с' % (time.time() - t))
