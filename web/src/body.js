// ТЕЛО В ВОДЕ — ПОРТ game2/scripts/world/water_physics.gd, ЧИСЛО В ЧИСЛО.
//
// Ничего здесь не выведено заново: константы и формулы взяты из версии для
// телефона как есть. Если развести эти два файла, пешеход в браузере пойдёт по
// воде иначе, чем на телефоне, — и это будет уже другая игра.
//
// Здесь нет ничего про то, как вода ВЫГЛЯДИТ. Только то, что она ДЕЛАЕТ с
// телом: держит его (плотность), тормозит (лобовое сопротивление) и отнимает
// опору (когда веса на ногах не остаётся, оттолкнуться нечем).

export const G = 9.81;
export const RHO = 999.7;        // пресная вода при 10 °C, кг/м³
export const RHO_BODY = 985.0;   // человек с воздухом в лёгких — легче воды
export const CD = 1.1;           // Re ≈ 1.1e5, развитая турбулентность
export const PUSH_FRAC = 0.18;   // удерживаемая горизонтальная реакция опоры
export const BODY_H = 1.75;
export const BODY_M = 70.0;
export const EYE = 1.62;

// высота, м | фронтальная ширина, м | доля объёма ниже этой высоты
const PROF_Y = [0.00, 0.45, 0.85, 1.05, 1.45, 1.62, 1.75];
const PROF_W = [0.30, 0.32, 0.34, 0.36, 0.44, 0.20, 0.16];
const PROF_V = [0.00, 0.14, 0.32, 0.47, 0.87, 0.94, 1.00];

export const bodyVolume = () => BODY_M / RHO_BODY;          // 0.0711 м³

// фронтальная площадь погружённой части — интеграл ширины по высоте
export function frontalArea(h) {
	let s = 0;
	for (let i = 0; i < PROF_Y.length - 1; i++) {
		const y0 = PROF_Y[i], y1 = PROF_Y[i + 1];
		if (h <= y0) break;
		const top = Math.min(h, y1), t = (top - y0) / (y1 - y0);
		s += 0.5 * (PROF_W[i] + (PROF_W[i] + (PROF_W[i + 1] - PROF_W[i]) * t)) * (top - y0);
	}
	return s;
}

export function submergedFrac(h) {
	if (h <= 0) return 0;
	if (h >= BODY_H) return 1;
	for (let i = 0; i < PROF_Y.length - 1; i++) {
		if (h <= PROF_Y[i + 1]) {
			const t = (h - PROF_Y[i]) / (PROF_Y[i + 1] - PROF_Y[i]);
			return PROF_V[i] + (PROF_V[i + 1] - PROF_V[i]) * t;
		}
	}
	return 1;
}

export const buoyancy = (h) => RHO * G * bodyVolume() * submergedFrac(h);

// какая доля веса ещё лежит на ногах; когда мала — сцепления с дном нет
export function footLoad(h) {
	const w = BODY_M * G;
	return Math.min(Math.max((w - buoyancy(h)) / w, 0), 1);
}

// ПРЕДЕЛ БРОДА: установившееся движение, толчок равен сопротивлению
//   F = ½ρ·Cd·A·v²  ->  v = sqrt(2F / (ρ·Cd·A)),
// причём сам толчок падает вместе с нагрузкой на ноги.
export function wadeSpeed(h) {
	const a = frontalArea(h);
	if (a < 1e-4) return Infinity;
	const push = PUSH_FRAC * BODY_M * G * footLoad(h);
	return push <= 0 ? 0 : Math.sqrt(2 * push / (RHO * CD * a));
}

// глубина, где на ногах остаётся меньше пятой части веса — не выбрана, найдена
export function swimDepth() {
	let lo = 0.5, hi = BODY_H;
	for (let i = 0; i < 24; i++) {
		const mid = 0.5 * (lo + hi);
		if (footLoad(mid) > 0.20) lo = mid; else hi = mid;
	}
	return 0.5 * (lo + hi);
}

// ПЕШЕХОД. Тело, а не камера: у него есть вес, и он его чувствует.
//
// Отличие от версии на телефоне названо честно: там CharacterBody3D с капсулой
// и move_and_slide по коллизии рельефа, здесь опора берётся прямо из поля высот.
// На пологом парковом склоне разницы нет; на отвесной стенке будет — тело
// заберётся туда, куда капсула бы не пустила. Стенок в этом срезе нет.
export class Walker {
	constructor(slice) {
		this.slice = slice;
		this.pos = { x: 0, y: 0, z: 0 };      // СТУПНИ, не глаза
		this.vel = { x: 0, y: 0, z: 0 };
		this.yaw = 0; this.pitch = 0;
		this.submersion = 0;
		this.swimming = false;
		this.onGround = true;
		this.speed = 0;
		this._stepAcc = 0;
		this.walkSpeed = 1.6;
		this.runSpeed = 6.5;
	}
	eyeY() { return this.pos.y + EYE; }

	// intent — вектор намерения длиной 0..1 (стик или клавиши)
	// surfaceAt(x,z) — отметка глади или NaN; disturb(x,z,объём) — круги по воде
	update(dt, intent, surfaceAt, disturb) {
		const fwdX = -Math.sin(this.yaw), fwdZ = -Math.cos(this.yaw);
		const rgtX = Math.cos(this.yaw), rgtZ = -Math.sin(this.yaw);
		let mag = Math.hypot(intent.x, intent.y);
		if (mag > 1) { intent = { x: intent.x / mag, y: intent.y / mag }; mag = 1; }
		// шаг переходит в бег не порогом, а плавно от того, как далеко уведён стик
		const t = Math.min(Math.max((mag - 0.35) / 0.65, 0), 1);
		let speed = this.walkSpeed + (this.runSpeed - this.walkSpeed) * t;

		// СКОЛЬКО ТЕЛА В ВОДЕ — от СТУПНЕЙ до глади, а не толща воды: когда тело
		// всплыло, эти числа расходятся, и важно именно погружение.
		const was = this.submersion;
		const surf = surfaceAt(this.pos.x, this.pos.z);
		this.submersion = Number.isNaN(surf) ? 0
			: Math.min(Math.max(surf - this.pos.y, 0), BODY_H);
		this.swimming = this.submersion >= swimDepth();

		if (this.submersion > 0.02) {
			if (!this.swimming) speed = Math.min(speed, wadeSpeed(this.submersion));
			// СЛЕД НА ВОДЕ: круги от шагов. Шаг человека 0.72 м; всплеск тем выше,
			// чем быстрее нога входит в воду. Круги считает НАСТОЯЩИЙ решатель —
			// это те же волны, что от брошенного камня, а не наложенная картинка.
			const vh = Math.hypot(this.vel.x, this.vel.z);
			this._stepAcc += vh * dt;
			if (this._stepAcc > 0.72) {
				this._stepAcc = 0;
				disturb(this.pos.x, this.pos.z, Math.min(0.008 + vh * 0.012, 0.05));
			}
			if (was <= 0.02) disturb(this.pos.x, this.pos.z, 0.06);
		}

		let hx = 0, hz = 0;
		if (mag > 0.03) {
			const wx = rgtX * intent.x + fwdX * (-intent.y);
			const wz = rgtZ * intent.x + fwdZ * (-intent.y);
			const l = Math.hypot(wx, wz) || 1;
			hx = wx / l * speed * mag; hz = wz / l * speed * mag;
		}

		if (this.swimming) {
			// ПЛАВАНИЕ. Опоры нет. Тело ищет равновесие между весом и архимедовой
			// силой, и оно само собой оказывается там, где над водой голова, —
			// никакой заданной «высоты плавания» здесь нет.
			const net = buoyancy(this.submersion) - BODY_M * G;
			const vy = this.vel.y;
			const drag = 0.5 * RHO * CD * 0.16 * vy * Math.abs(vy) / BODY_M;
			this.vel.y += (net / BODY_M - drag) * dt;
			const sw = Math.min(mag * 1.0, 1.0);          // пловец-любитель, м/с
			const l = Math.hypot(hx, hz);
			if (l > 1e-3) { hx = hx / l * sw; hz = hz / l * sw; }
			this.vel.x = hx; this.vel.z = hz;
			this.onGround = false;
		} else {
			this.vel.x = hx; this.vel.z = hz;
			this.vel.y -= G * dt;
		}

		this.pos.x += this.vel.x * dt;
		this.pos.y += this.vel.y * dt;
		this.pos.z += this.vel.z * dt;

		// опора: сквозь землю — никогда
		const g = this.slice.bedAt(this.pos.x, this.pos.z);
		if (this.pos.y <= g) {
			this.pos.y = g;
			if (this.vel.y < 0) this.vel.y = 0;
			this.onGround = true;
		} else if (!this.swimming) {
			this.onGround = false;
		}
		this.speed = Math.hypot(this.vel.x, this.vel.z);
	}
}
