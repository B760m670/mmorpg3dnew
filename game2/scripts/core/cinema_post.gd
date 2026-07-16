@tool
class_name CinemaPost
extends CompositorEffect
## Кино-пост (Ф0): один compute-проход после тонемапа — лёгкая хроматика,
## виньетка, плёночное зерно. Каноничный минимум для Metal-бэкенда.

@export_range(0.0, 0.1) var grain: float = 0.022
@export_range(0.0, 0.6) var vignette: float = 0.28
@export_range(0.0, 3.0) var chromatic_px: float = 1.2

var rd: RenderingDevice
var shader: RID
var pipeline: RID

func _init() -> void:
	effect_callback_type = EFFECT_CALLBACK_TYPE_POST_TRANSPARENT
	rd = RenderingServer.get_rendering_device()
	if rd:
		RenderingServer.call_on_render_thread(_init_compute)

func _notification(what: int) -> void:
	if what == NOTIFICATION_PREDELETE and shader.is_valid():
		RenderingServer.free_rid(shader)

func _init_compute() -> void:
	var f := load("res://shaders/post/cinema_post.glsl") as RDShaderFile
	if f == null:
		return
	shader = rd.shader_create_from_spirv(f.get_spirv())
	if shader.is_valid():
		pipeline = rd.compute_pipeline_create(shader)

func _render_callback(p_type: int, p_data: RenderData) -> void:
	if not (rd and p_type == EFFECT_CALLBACK_TYPE_POST_TRANSPARENT and pipeline.is_valid()):
		return
	var buffers := p_data.get_render_scene_buffers() as RenderSceneBuffersRD
	if buffers == null:
		return
	var size := buffers.get_internal_size()
	if size.x == 0 or size.y == 0:
		return
	var gx := (size.x - 1) / 8 + 1
	var gy := (size.y - 1) / 8 + 1
	var push := PackedFloat32Array([
		float(size.x), float(size.y),
		float(Time.get_ticks_msec()) / 1000.0,
		grain, vignette, chromatic_px, 0.0, 0.0,
	]).to_byte_array()
	for view in range(buffers.get_view_count()):
		var img := buffers.get_color_layer(view)
		if not img.is_valid():
			continue
		var u := RDUniform.new()
		u.uniform_type = RenderingDevice.UNIFORM_TYPE_IMAGE
		u.binding = 0
		u.add_id(img)
		var uset := UniformSetCacheRD.get_cache(shader, 0, [u])
		var cl := rd.compute_list_begin()
		rd.compute_list_bind_compute_pipeline(cl, pipeline)
		rd.compute_list_bind_uniform_set(cl, uset, 0)
		rd.compute_list_set_push_constant(cl, push, push.size())
		rd.compute_list_dispatch(cl, gx, gy, 1)
		rd.compute_list_end()
