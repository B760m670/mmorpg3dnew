// ФИНАЛЬНЫЙ ПРОХОД: ОДИН тонмаппинг на весь кадр, плюс ореол.
//
// ЗАЧЕМ ОТДЕЛЬНЫМ ПРОХОДОМ. Сперва я тонмаппил в каждом шейдере отдельно, и
// вода вышла белой: небо писало линейную яркость, отражение попадало в воду уже
// как экранное значение, а вода умножала его на экспозицию ЕЩЁ РАЗ. Ошибка не в
// числах, а в том, что у кадра не было одного места, где линейный свет
// становится картинкой. Теперь оно есть: сцена целиком линейная (в буфере
// половинной точности), а кривая тона применяется здесь и только здесь.
//
// ЗАЧЕМ ОРЕОЛ. Солнечная дорожка на воде по расчёту доходит до сотен единиц
// линейной яркости — это честно, у настоящего блика контраст к траве около
// 10 000:1. Экран отдаёт 100:1. Без ореола вся дорожка просто упирается в белое
// и превращается в лист бумаги. Ореол — не украшение: это единственный способ
// показать, что за белым пятном стоит очень много света, он выносит переизбыток
// В СОСЕДНИЕ ПИКСЕЛИ, как это делает объектив.
//
// Кривая ФИЛЬМИЧЕСКАЯ, не ACES: измерено, что фит ACES на почти чёрном уводит
// нейтральный серый в зелень (G выше остальных на 1.67 из 255).
import * as THREE from 'three';

const QUAD_VS = `varying vec2 vUv; void main(){ vUv=uv; gl_Position=vec4(position.xy,0.0,1.0); }`;

// Яркая часть кадра. Порог берётся ВЫШЕ единицы: всё, что ниже, кривая тона и
// так покажет, и размывать его значит просто мылить кадр.
const BRIGHT_FS = `precision highp float;
	varying vec2 vUv; uniform sampler2D tSrc; uniform float thresh, exposure;
	void main(){
		vec3 c = texture2D(tSrc, vUv).rgb * exposure;
		float l = max(max(c.r, c.g), c.b);
		float k = max(l - thresh, 0.0) / max(l, 1e-4);
		gl_FragColor = vec4(c * k, 1.0);
	}`;

// Тент 3x3 — стандартный фильтр цепочки уменьшений: он даёт гладкий ореол без
// квадратов, которые оставляет простая выборка соседей.
const BLUR_FS = `precision highp float;
	varying vec2 vUv; uniform sampler2D tSrc; uniform vec2 texel; uniform float scale;
	void main(){
		vec2 d = texel * scale;
		vec3 s = texture2D(tSrc, vUv).rgb * 4.0;
		s += (texture2D(tSrc, vUv + vec2( d.x, 0.0)).rgb
		    + texture2D(tSrc, vUv + vec2(-d.x, 0.0)).rgb
		    + texture2D(tSrc, vUv + vec2(0.0,  d.y)).rgb
		    + texture2D(tSrc, vUv + vec2(0.0, -d.y)).rgb) * 2.0;
		s += texture2D(tSrc, vUv + d).rgb
		   + texture2D(tSrc, vUv - d).rgb
		   + texture2D(tSrc, vUv + vec2( d.x, -d.y)).rgb
		   + texture2D(tSrc, vUv + vec2(-d.x,  d.y)).rgb;
		gl_FragColor = vec4(s / 16.0, 1.0);
	}`;

const TONE_FS = `precision highp float;
	varying vec2 vUv;
	uniform sampler2D tScene, tBloom;
	uniform float exposure, vignette, grain, bloom, t;
	// целочисленный хеш: fract(sin(dot())) на решётке пикселей коррелирует
	float hash(vec2 p){
		uvec2 q = uvec2(ivec2(p)) * uvec2(1597334673u, 3812015801u);
		uint n = (q.x ^ q.y) * 1597334673u;
		n = (n ^ (n >> 15u)) * 2246822519u;
		n = (n ^ (n >> 13u)) * 3266489917u;
		return float(n ^ (n >> 16u)) * (1.0/4294967295.0);
	}
	void main(){
		vec3 c = texture2D(tScene, vUv).rgb * exposure;
		c += texture2D(tBloom, vUv).rgb * bloom;
		c = max(c - 0.004, 0.0);
		c = (c*(6.2*c+0.5))/(c*(6.2*c+1.7)+0.06);   // фильмическая кривая
		vec2 d = vUv - 0.5;
		c *= 1.0 - vignette * smoothstep(0.10, 0.55, dot(d,d));
		// зерно растёт в тенях, как на настоящей матрице
		float lum = dot(c, vec3(0.299,0.587,0.114));
		float n = hash(gl_FragCoord.xy + vec2(floor(t*61.0), floor(t*37.0))) - 0.5;
		c += n * grain * (0.010 + 0.030 * (1.0 - smoothstep(0.0, 0.26, lum)));
		gl_FragColor = vec4(max(c, 0.0), 1.0);
	}`;

function rt(w, h) {
	return new THREE.WebGLRenderTarget(Math.max(1, w | 0), Math.max(1, h | 0), {
		type: THREE.HalfFloatType, depthBuffer: false, stencilBuffer: false,
		minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter,
	});
}

export class Post {
	constructor(renderer, w, h) {
		this.renderer = renderer;
		this.rt = new THREE.WebGLRenderTarget(w, h, {
			type: THREE.HalfFloatType, depthBuffer: true, stencilBuffer: false,
			minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter,
		});
		this.cam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
		this.quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), null);
		this.scene = new THREE.Scene();
		this.scene.add(this.quad);

		const plain = (fs, uni) => new THREE.ShaderMaterial({
			uniforms: uni, vertexShader: QUAD_VS, fragmentShader: fs,
			depthTest: false, depthWrite: false,
		});
		this.exposure = 3.0;
		this.mBright = plain(BRIGHT_FS, {
			tSrc: { value: null }, thresh: { value: 1.0 },
			exposure: { value: this.exposure },
		});
		this.mBlur = plain(BLUR_FS, {
			tSrc: { value: null }, texel: { value: new THREE.Vector2() }, scale: { value: 1.0 },
		});
		// подъём обратно складывается, а не заменяет: иначе крупный уровень стёр бы
		// мелкий и от ореола осталось бы одно широкое пятно без ядра
		this.mUp = plain(BLUR_FS, {
			tSrc: { value: null }, texel: { value: new THREE.Vector2() }, scale: { value: 1.0 },
		});
		this.mUp.blending = THREE.AdditiveBlending;
		this.mTone = plain(TONE_FS, {
			tScene: { value: this.rt.texture }, tBloom: { value: null },
			exposure: { value: this.exposure }, vignette: { value: 0.22 },
			grain: { value: 1.0 }, bloom: { value: 0.05 }, t: { value: 0 },
		});
		// ЧЕТЫРЕ УРОВНЯ, А НЕ ОДНО РАЗМЫТИЕ. Ореол объектива спадает не по Гауссу,
		// а гораздо длиннее: у него есть и плотное ядро в пару пикселей, и шлейф
		// на четверть кадра. Сумма уровней разного масштаба это и даёт.
		this.levels = [];
		this.resize(w, h);
	}
	resize(w, h) {
		this.rt.setSize(w, h);
		for (const l of this.levels) { l.a.dispose(); l.b.dispose(); }
		this.levels = [];
		let lw = w >> 1, lh = h >> 1;
		for (let i = 0; i < 4; i++) {
			this.levels.push({ a: rt(lw, lh), b: rt(lw, lh), w: lw, h: lh });
			lw = Math.max(1, lw >> 1); lh = Math.max(1, lh >> 1);
		}
	}
	_pass(mat, target) {
		this.quad.material = mat;
		this.renderer.setRenderTarget(target);
		this.renderer.clear();
		this.renderer.render(this.scene, this.cam);
	}
	render(scene, camera, t) {
		this.mTone.uniforms.t.value = t;
		this.renderer.setRenderTarget(this.rt);
		this.renderer.clear();
		this.renderer.render(scene, camera);

		// яркая часть -> цепочка уменьшений, каждый уровень размывается по себе
		this.mBright.uniforms.tSrc.value = this.rt.texture;
		this.mBright.uniforms.exposure.value = this.exposure;
		this._pass(this.mBright, this.levels[0].a);
		for (let i = 0; i < this.levels.length; i++) {
			const L = this.levels[i];
			if (i > 0) {
				this.mBlur.uniforms.tSrc.value = this.levels[i - 1].b.texture;
				this.mBlur.uniforms.texel.value.set(1 / this.levels[i - 1].w, 1 / this.levels[i - 1].h);
				this.mBlur.uniforms.scale.value = 1.0;
				this._pass(this.mBlur, L.a);
			}
			this.mBlur.uniforms.tSrc.value = L.a.texture;
			this.mBlur.uniforms.texel.value.set(1 / L.w, 1 / L.h);
			this.mBlur.uniforms.scale.value = 2.0;
			this._pass(this.mBlur, L.b);
		}
		// собираем обратно снизу вверх аддитивно
		for (let i = this.levels.length - 1; i > 0; i--) {
			this.mUp.uniforms.tSrc.value = this.levels[i].b.texture;
			this.mUp.uniforms.texel.value.set(1 / this.levels[i].w, 1 / this.levels[i].h);
			this.quad.material = this.mUp;
			this.renderer.setRenderTarget(this.levels[i - 1].b);
			this.renderer.autoClear = false;
			this.renderer.render(this.scene, this.cam);
			this.renderer.autoClear = true;
		}
		this.mTone.uniforms.tBloom.value = this.levels[0].b.texture;
		this.mTone.uniforms.exposure.value = this.exposure;
		this._pass(this.mTone, null);
	}
}
