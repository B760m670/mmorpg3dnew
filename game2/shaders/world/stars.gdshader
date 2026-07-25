shader_type spatial;
// ЗВЁЗДЫ — настоящий каталог точками на небесной сфере. Не текстура-кубмап:
// каждая точка — реальная звезда (RA/Dec J2000), купол крутится матрицей
// экватор→горизонт по звёздному времени (в night_sky.gd). Здесь — вид точки:
//   РАЗМЕР и ЯРКОСТЬ из видимой величины (поток ∝ 2.512^−m);
//   ЦВЕТ из настоящей цвет. температуры (COLOR, посчитан в build_stars.py);
//   ВИДИМОСТЬ ночного неба (night) из высоты Солнца — звёзды проступают в сумерках;
//   ДЫМКА у горизонта гасит низкие светила (атмосферное поглощение).
// Аддитивно поверх неба; глубину не пишем, но тест включён — рельеф/облака
// перекрывают звёзды у горизонта.
render_mode unshaded, blend_add, depth_draw_never, cull_disabled;

uniform float night = 1.0;        // 0 день .. 1 глубокая ночь
uniform float px_scale = 1.0;     // масштаб точки под разрешение экрана

varying vec3 v_col;
varying float v_bright;

void vertex() {
	float mag = UV.x;
	float flux = pow(2.512, -mag);                 // поток от величины
	// высота над горизонтом (для поглощения): нода в центре камеры
	vec3 wdir = normalize((MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz - CAMERA_POSITION_WORLD);
	float ext = smoothstep(-0.04, 0.22, wdir.y);   // гаснет у/за горизонтом
	v_col = COLOR.rgb;
	v_bright = clamp(flux * 0.42, 0.015, 3.5) * ext;
	POINT_SIZE = clamp(3.4 - mag * 0.85, 1.0, 9.0) * px_scale * (0.4 + 0.6 * ext);
}

void fragment() {
	vec2 d = POINT_COORD - vec2(0.5);
	float r = length(d) * 2.0;
	float halo = smoothstep(1.0, 0.0, r);          // мягкий ореол
	float core = smoothstep(0.55, 0.0, r);         // ядро
	ALBEDO = v_col * v_bright * night;
	ALPHA = clamp(halo * 0.5 + core, 0.0, 1.0);
}
