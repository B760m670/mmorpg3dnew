@tool
class_name CinemaPost
extends CompositorEffect
## Кино-пост (Ф0): compute-проход после тонемапа — хроматическая аберрация,
## виньетка, плёночное зерно. Вешается на Compositor у WorldEnvironment.

@export_range(0.0, 0.1) var grain: float = 0.022
@export_range(0.0, 0.6) var vignette: float = 0.28
@export_range(0.0, 3.0) var chromatic_px: float = 1.4

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
		push_error("CinemaPost: нет shaders/post/cinema_post.glsl")
		return
	var spirv := f.get_spirv()
	shader = rd.shader_create_from_spirv(spirv)
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
	var groups_x := (size.x - 1) / 8 + 1
	var groups_y := (size.y - 1) / 8 + 1
	var t := float(Time.get_ticks_msec()) / 1000.0
	var push_copy := PackedFloat32Array([
		float(size.x), float(size.y), t,
		grain, vignette, chromatic_px, 0.0, 0.0,
	]).to_byte_array()
	var push_fx := PackedFloat32Array([
		float(size.x), float(size.y), t,
		grain, vignette, chromatic_px, 1.0, 0.0,
	]).to_byte_array()
	# scratch-копия кадра: хроматика читает соседей — из копии, не из себя
	var ctx := StringName("CinemaPost")
	var tex_name := StringName("src_copy")
	if not buffers.has_texture(ctx, tex_name):
		buffers.create_texture(ctx, tex_name,
			RenderingDevice.DATA_FORMAT_R16G16B16A16_SFLOAT,
			RenderingDevice.TEXTURE_USAGE_STORAGE_BIT | RenderingDevice.TEXTURE_USAGE_CAN_COPY_TO_BIT,
			RenderingDevice.TEXTURE_SAMPLES_1, size, buffers.get_view_count(), 1, true, false)
	for view in range(buffers.get_view_count()):
		var img := buffers.get_color_layer(view)
		var src := buffers.get_texture_slice(ctx, tex_name, view, 0, 1, 1)
		var u0 := RDUniform.new()
		u0.uniform_type = RenderingDevice.UNIFORM_TYPE_IMAGE
		u0.binding = 0
		u0.add_id(img)
		var u1 := RDUniform.new()
		u1.uniform_type = RenderingDevice.UNIFORM_TYPE_IMAGE
		u1.binding = 1
		u1.add_id(src)
		var uset := UniformSetCacheRD.get_cache(shader, 0, [u0, u1])
		# проход 1: копия кадра в scratch (поточечно, безопасно)
		var cl := rd.compute_list_begin()
		rd.compute_list_bind_compute_pipeline(cl, pipeline)
		rd.compute_list_bind_uniform_set(cl, uset, 0)
		rd.compute_list_set_push_constant(cl, push_copy, push_copy.size())
		rd.compute_list_dispatch(cl, groups_x, groups_y, 1)
		rd.compute_list_end()
		# проход 2: эффект — соседи читаются из копии, пишем в кадр
		cl = rd.compute_list_begin()
		rd.compute_list_bind_compute_pipeline(cl, pipeline)
		rd.compute_list_bind_uniform_set(cl, uset, 0)
		rd.compute_list_set_push_constant(cl, push_fx, push_fx.size())
		rd.compute_list_dispatch(cl, groups_x, groups_y, 1)
		rd.compute_list_end()
