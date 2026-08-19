// УПРАВЛЕНИЕ: ДВА РЕЖИМА, КАК В ВЕРСИИ ДЛЯ ТЕЛЕФОНА.
//
//   СВЕРХУ  — свободная камера над парком (game2/scripts/world/free_camera.gd):
//             один палец — поворот, два — зум («развёл = ближе») и перенос
//             «схвати мир», скорость пропорциональна высоте.
//   ПЕШЕХОД — тело на земле (game2/scripts/world/walker.gd): ЛЕВАЯ половина
//             экрана — стик движения (дальше увёл — быстрее, до бега), ПРАВАЯ —
//             взгляд без инверсии.
//
// ПОЧЕМУ ЕСТЬ КНОПКА, А НЕ ТОЛЬКО ДВОЙНОЙ ТАП. На телефоне режимы переключает
// двойной тап, и это работает, когда знаешь. Открывший ссылку не знает: он
// увидит воду и не найдёт, как в неё войти. Кнопка стоит рядом и называет то,
// куда ведёт. Двойной тап при этом оставлен — привычка не должна ломаться.
//
// БЕЗ ИНВЕРСИЙ. Ни по одной оси, ни в одном режиме. Это правило проекта, и
// нарушать его нельзя даже там, где «привычнее наоборот».
import { Walker, EYE } from './body.js';

const LOOK = 0.0026;        // рад на пиксель — та же чувствительность, что в игре
const STICK_R = 130;        // пикселей до полного отклонения стика (walker.gd)

export class Controls {
	// slice — рельеф; surfaceAt(x,z) — гладь или NaN; disturb(x,z,V) — круги
	constructor(camera, dom, slice, surfaceAt, disturb) {
		this.camera = camera;
		this.dom = dom;
		this.slice = slice;
		this.surfaceAt = surfaceAt;
		this.disturb = disturb;
		this.mode = 'fly';
		this.walker = new Walker(slice);
		this.yaw = 0; this.pitch = 0;
		this.keys = new Set();
		this.onStone = null;       // вызывается при коротком касании
		this._pts = new Map();
		this._two = null;
		this._stickId = -1;
		this._stickO = { x: 0, y: 0 };
		this._stick = { x: 0, y: 0 };
		this._lastTap = -1e9;
		this._bind();
	}

	setLook(dir) {
		this.yaw = Math.atan2(-dir.x, -dir.z);
		this.pitch = Math.asin(Math.min(Math.max(dir.y, -1), 1));
	}

	// --- переход между режимами. Он не мгновенный по смыслу: сверху камера
	// висит в воздухе, у пешехода есть ноги, и надо решить, где именно он встанет.
	toggle() { this.setMode(this.mode === 'fly' ? 'walk' : 'fly'); }

	setMode(m) {
		if (m === this.mode) return;
		if (m === 'walk') {
			// ПЕШЕХОД ВСТАЁТ ТУДА, КУДА СМОТРЕЛИ, А НЕ ПОД КАМЕРУ. С высоты 90 м
			// точка под камерой — это не то место, которое рассматривают; высадка
			// туда ощущается как промах. Луч взгляда до земли даёт то самое место.
			//
			// А «встать на землю» значит НА ЗЕМЛЮ. Первый заход ставил тело прямо в
			// точку луча — а с берега взгляд упирается в дно озера, и игрок
			// оказывался на глубине 3.3 м под водой, всплывая оттуда шесть секунд
			// (замерено: ноги -14.02 при урезе -10.73). Поэтому от точки прицела
			// идём обратно к камере до первой сухой земли.
			const p = this._aimGround(400);
			this.walker.pos.x = p.x; this.walker.pos.z = p.z;
			this.walker.pos.y = this.slice.bedAt(p.x, p.z);
			this.walker.vel = { x: 0, y: 0, z: 0 };
			this.walker.yaw = this.yaw;
			this.walker.pitch = Math.min(this.pitch, 0.1);
			this._stickId = -1; this._stick = { x: 0, y: 0 };
		} else {
			// вверх — на высоту, с которой видно всё озеро, сохранив направление
			this.yaw = this.walker.yaw;
			this.pitch = -0.62;                      // около 35° вниз
			const g = this.slice.bedAt(this.walker.pos.x, this.walker.pos.z);
			this.camera.position.set(
				this.walker.pos.x - Math.sin(this.yaw) * -70,
				g + 90,
				this.walker.pos.z - Math.cos(this.yaw) * -70);
		}
		this.mode = m;
	}

	// точка, куда смотрит камера, опущенная на землю (шагами по лучу), а затем
	// отодвинутая назад до первой СУХОЙ клетки
	_aimGround(maxDist) {
		const c = this.camera;
		const d = { x: -Math.sin(this.yaw) * Math.cos(this.pitch),
			y: Math.sin(this.pitch),
			z: -Math.cos(this.yaw) * Math.cos(this.pitch) };
		const step = maxDist / 160;
		let hit = { x: c.position.x + d.x * 30, z: c.position.z + d.z * 30 }, t = 0;
		for (let i = 0; i < 160; i++) {
			const x = c.position.x + d.x * t, y = c.position.y + d.y * t, z = c.position.z + d.z * t;
			if (y <= this.slice.bedAt(x, z)) { hit = { x, z }; break; }
			t += step;
		}
		const dry = (x, z) => {
			const s = this.surfaceAt(x, z);
			return Number.isNaN(s) || s - this.slice.bedAt(x, z) < 0.20;
		};
		if (dry(hit.x, hit.z)) return hit;
		for (let back = step; back < maxDist; back += step) {
			const x = hit.x - d.x * back, z = hit.z - d.z * back;
			if (dry(x, z)) return { x, z };
		}
		return hit;
	}

	_bind() {
		addEventListener('keydown', e => {
			this.keys.add(e.code);
			if (e.code === 'Tab') { e.preventDefault(); this.toggle(); }
		});
		addEventListener('keyup', e => this.keys.delete(e.code));

		const el = this.dom;
		el.style.touchAction = 'none';
		const pair = () => {
			const a = [...this._pts.values()];
			return {
				d: Math.hypot(a[0].x - a[1].x, a[0].y - a[1].y),
				cx: (a[0].x + a[1].x) / 2, cy: (a[0].y + a[1].y) / 2,
			};
		};
		el.addEventListener('pointerdown', e => {
			try { el.setPointerCapture(e.pointerId); } catch (_) { /* мышь вне окна */ }
			this._pts.set(e.pointerId, { x: e.clientX, y: e.clientY, x0: e.clientX, y0: e.clientY, moved: 0, t: performance.now() });
			if (this.mode === 'walk' && this._stickId < 0 && e.clientX < innerWidth * 0.5) {
				this._stickId = e.pointerId;
				this._stickO = { x: e.clientX, y: e.clientY };
				this._stick = { x: 0, y: 0 };
			}
			if (this.mode === 'fly' && this._pts.size === 2) this._two = pair();
		});
		el.addEventListener('pointermove', e => {
			const p = this._pts.get(e.pointerId);
			if (!p) return;
			const dx = e.clientX - p.x, dy = e.clientY - p.y;
			p.x = e.clientX; p.y = e.clientY; p.moved += Math.abs(dx) + Math.abs(dy);
			if (e.pointerId === this._stickId) {
				this._stick = {
					x: (e.clientX - this._stickO.x) / STICK_R,
					y: (e.clientY - this._stickO.y) / STICK_R,
				};
				const l = Math.hypot(this._stick.x, this._stick.y);
				if (l > 1) { this._stick.x /= l; this._stick.y /= l; }
				return;
			}
			if (this.mode === 'fly' && this._pts.size >= 2 && this._two) {
				const now = pair();
				const gh = this.slice.bedAt(this.camera.position.x, this.camera.position.z);
				const k = 0.004 * (1 + Math.max(0, this.camera.position.y - gh));
				const fx = -Math.sin(this.yaw), fz = -Math.cos(this.yaw);
				const rx = Math.cos(this.yaw), rz = -Math.sin(this.yaw);
				const step = (ax, az, s) => {
					this.camera.position.x += ax * s; this.camera.position.z += az * s;
				};
				step(fx, fz, (now.d - this._two.d) * k);          // развёл = ближе
				step(rx, rz, -(now.cx - this._two.cx) * k);       // схвати мир
				step(fx, fz, (now.cy - this._two.cy) * k);
				this._two = now;
				return;
			}
			this.yaw -= dx * LOOK;
			this.pitch = Math.min(Math.max(this.pitch - dy * LOOK, -1.48), 1.48);
		});
		const end = e => {
			const p = this._pts.get(e.pointerId);
			if (p) {
				const dt = performance.now() - p.t;
				const tap = p.moved < 8 && dt < 300;
				if (tap) {
					// двойной тап — сменить режим (привычка с телефона)
					if (performance.now() - this._lastTap < 380) {
						this._lastTap = -1e9;
						this.toggle();
					} else {
						this._lastTap = performance.now();
						if (this.onStone) this.onStone();
					}
				}
			}
			this._pts.delete(e.pointerId);
			if (e.pointerId === this._stickId) { this._stickId = -1; this._stick = { x: 0, y: 0 }; }
			this._two = this._pts.size === 2 ? pair() : null;
		};
		el.addEventListener('pointerup', end);
		el.addEventListener('pointercancel', end);
	}

	// намерение движения: стик, а на клавиатуре — те же WASD
	_intent() {
		let x = this._stick.x, y = this._stick.y;
		const k = this.keys;
		if (k.has('KeyW')) y -= 1;
		if (k.has('KeyS')) y += 1;
		if (k.has('KeyD')) x += 1;
		if (k.has('KeyA')) x -= 1;
		if ((k.has('ShiftLeft') || k.has('ShiftRight')) && (x || y)) { x *= 1.6; y *= 1.6; }
		return { x, y };
	}

	update(dt) {
		if (this.mode === 'walk') {
			const w = this.walker;
			w.yaw = this.yaw; w.pitch = this.pitch;
			w.update(dt, this._intent(), this.surfaceAt, this.disturb);
			this.camera.position.set(w.pos.x, w.eyeY(), w.pos.z);
		} else {
			// ЛЕТУЧАЯ КАМЕРА: скорость пропорциональна высоте над землёй — у земли
			// шаг мелкий, сверху крупный. Иначе с 90 м озеро не облететь.
			const c = this.camera;
			const gh = this.slice.bedAt(c.position.x, c.position.z);
			const sp = (2.2 + Math.max(0, c.position.y - gh) * 1.1) * dt;
			const i = this._intent();
			const fx = -Math.sin(this.yaw), fz = -Math.cos(this.yaw);
			const rx = Math.cos(this.yaw), rz = -Math.sin(this.yaw);
			c.position.x += (rx * i.x + fx * -i.y) * sp;
			c.position.z += (rz * i.x + fz * -i.y) * sp;
			if (this.keys.has('KeyE')) c.position.y += sp;
			if (this.keys.has('KeyQ')) c.position.y -= sp;
			// сквозь землю не проваливаемся даже в полёте
			c.position.y = Math.max(c.position.y, gh + 1.2);
		}
		this.camera.rotation.set(this.pitch, this.yaw, 0, 'YXZ');
	}

	// куда бросить камень: точка на глади по лучу взгляда
	aimWater(restLevel) {
		const c = this.camera;
		const d = { x: -Math.sin(this.yaw) * Math.cos(this.pitch),
			y: Math.sin(this.pitch),
			z: -Math.cos(this.yaw) * Math.cos(this.pitch) };
		const t = (restLevel - c.position.y) / (d.y < -1e-3 ? d.y : -1e-3);
		const s = Math.min(Math.max(t, 2), 90);
		return { x: c.position.x + d.x * s, z: c.position.z + d.z * s };
	}
}

export { EYE };
