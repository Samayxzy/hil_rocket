// ═══════════════════════════════════════════════════════════════════════════════
// THREE.JS VIEWER
// ═══════════════════════════════════════════════════════════════════════════════
const threeCanvas = document.getElementById('three-canvas');
const viewerDiv   = document.getElementById('viewer');

const renderer = new THREE.WebGLRenderer({ canvas: threeCanvas, antialias: true });
renderer.setClearColor(0x090c10, 1);
renderer.setPixelRatio(window.devicePixelRatio);

const scene  = new THREE.Scene();
scene.fog    = new THREE.Fog(0x090c10, 60, 1400);
const camera = new THREE.PerspectiveCamera(45, 1, 0.001, 2000);
camera.position.set(0.5, 0.2, 2.5);
camera.lookAt(0, 0, 0);

scene.add(new THREE.AmbientLight(0x22d3ee, 0.2));
const dlight = new THREE.DirectionalLight(0xffffff, 0.3);
dlight.position.set(1, 2, 1);
scene.add(dlight);

// World-fixed ground grid — deliberately NOT attached to the rocket or camera.
// The chase camera below fully translates with the rocket (keeping it framed
// near screen-center at all times), so this grid sliding past underneath is
// the primary visual cue that the vehicle is actually moving/drifting, both
// vertically and horizontally. Large + fogged so it reads as an effectively
// endless reference plane rather than a bounded pad marker.
const grid = new THREE.GridHelper(3000, 300, 0x2a3f55, 0x152030); // 10m cells
grid.material.transparent = true;
grid.material.opacity = 0.55;
scene.add(grid);

// Altitude marker rings — thin horizontal circles at regular height
// intervals, giving a visual "ruler" once the rocket is high enough that
// the ground grid alone gives no sense of scale. Rings fade in only once
// the rocket climbs near/above them, and each carries a small altitude
// label sprite so height is readable at a glance, not just implied.
const ALT_RING_SPACING = 50;   // metres between rings
const ALT_RING_COUNT   = 20;   // covers up to 1000m; extend if needed
const altRings = [];

function makeAltLabelSprite(text) {
  const canvas = document.createElement('canvas');
  canvas.width = 128; canvas.height = 32;
  const ctx = canvas.getContext('2d');
  ctx.font = '20px monospace';
  ctx.fillStyle = 'rgba(148,163,184,0.75)';
  ctx.fillText(text, 4, 22);
  const tex = new THREE.CanvasTexture(canvas);
  const mat = new THREE.SpriteMaterial({ map: tex, transparent: true, depthTest: false });
  const sprite = new THREE.Sprite(mat);
  sprite.scale.set(6, 1.5, 1);
  return sprite;
}

for (let i = 1; i <= ALT_RING_COUNT; i++) {
  const alt = i * ALT_RING_SPACING;
  const ringGeo = new THREE.RingGeometry(5.4, 5.5, 48);
  const ringMat = new THREE.MeshBasicMaterial({
    color: 0x1e2d3d, transparent: true, opacity: 0, side: THREE.DoubleSide,
  });
  const ring = new THREE.Mesh(ringGeo, ringMat);
  ring.rotation.x = -Math.PI / 2;
  ring.position.y = alt;
  scene.add(ring);

  const label = makeAltLabelSprite(alt + 'm');
  label.position.set(5.8, alt, 0);
  scene.add(label);

  altRings.push({ ring, label, alt });
}

function updateAltRings(currentAlt) {
  // Fade each ring in as the rocket approaches/passes it, fade out once
  // far below or (optionally) once well above, so only nearby rings
  // clutter the view — keeps the "ruler" readable instead of showing
  // all 20 rings at once regardless of altitude.
  for (const { ring, label, alt } of altRings) {
    const dist = Math.abs(currentAlt - alt);
    const visRange = ALT_RING_SPACING * 3;   // rings within ~150m stay visible
    const opacity = Math.max(0, 1 - dist / visRange) * 0.5;
    ring.material.opacity = opacity;
    label.material.opacity = Math.max(0, 1 - dist / visRange) * 0.85;
  }
}

// Rocket group — nose points in +Y (up in Three.js)
const rocketGroup = new THREE.Group();
scene.add(rocketGroup);

// Trajectory trail
const TRAIL_MAX  = 600;
const trailSimPts = [];
const trailSimGeo = new THREE.BufferGeometry();
const trailSimMat = new THREE.LineBasicMaterial({ color: 0x22d3ee, transparent: true, opacity: 0.7 });
const trailSimLine = new THREE.Line(trailSimGeo, trailSimMat);
scene.add(trailSimLine);

// Exhaust plume particles
const PLUME_COUNT = 80;
const plumeGeo = new THREE.BufferGeometry();
const plumePts = new Float32Array(PLUME_COUNT * 3);
plumeGeo.setAttribute('position', new THREE.BufferAttribute(plumePts, 3));
const plumeMat = new THREE.PointsMaterial({ color: 0xf97316, size: 0.015, transparent: true, opacity: 0.7 });
const plumePoints = new THREE.Points(plumeGeo, plumeMat);
scene.add(plumePoints);
plumePoints.visible = false;

const plumeVels = Array.from({length: PLUME_COUNT}, () => ({
  x: (Math.random()-.5)*.04, y: -(Math.random()*.06+.02), z: (Math.random()-.5)*.04, life: Math.random()
}));

function updatePlume(rocketY, boosting) {
  plumePoints.visible = boosting;
  if (!boosting) return;
  const pos = plumeGeo.attributes.position.array;
  for (let i = 0; i < PLUME_COUNT; i++) {
    const p = plumeVels[i];
    p.life -= 0.04;
    if (p.life <= 0) {
      p.x = (Math.random()-.5)*.01; p.y = 0; p.z = (Math.random()-.5)*.01;
      p.vx = (Math.random()-.5)*.04; p.vy = -(Math.random()*.06+.02); p.vz = (Math.random()-.5)*.04;
      p.life = 1;
    }
    pos[i*3]   = rocketGroup.position.x + (p.x || 0);
    pos[i*3+1] = rocketGroup.position.y + (p.y || 0) - 0.05;
    pos[i*3+2] = rocketGroup.position.z + (p.z || 0);
    if (p.vx) { p.x += p.vx; p.y += p.vy; p.z += p.vz; }
  }
  plumeGeo.attributes.position.needsUpdate = true;
}

// Orbit controls — rotX/rotY set the VIEWING ANGLE around the chase target
// (the rocket), they no longer orbit a fixed world point.
let drag = false, px0 = 0, py0 = 0, rotX = 0.2, rotY = 0.3;
// User-controlled zoom MULTIPLIER (1.0 = default framing), separate from the
// auto chase-distance below — scroll still zooms in/out around whatever
// altitude-appropriate distance the camera has picked.
let userZoom = 1.0;

threeCanvas.addEventListener('mousedown', e => { drag = true; px0 = e.clientX; py0 = e.clientY; });
window.addEventListener('mouseup', () => drag = false);
window.addEventListener('mousemove', e => {
  if (!drag) return;
  rotY += (e.clientX - px0) * 0.008; rotX += (e.clientY - py0) * 0.008;
  px0 = e.clientX; py0 = e.clientY;
});
threeCanvas.addEventListener('wheel', e => { userZoom = Math.max(.15, Math.min(6, userZoom + e.deltaY * 0.001)); });

// Load rocket STL
function parseSTLBuffer(buf) {
  const dv = new DataView(buf);
  const n  = dv.getUint32(80, true);
  if (buf.byteLength === 84 + n * 50) {
    const pos = new Float32Array(n * 9);
    for (let i = 0; i < n; i++) {
      const off = 84 + i*50 + 12;
      for (let j = 0; j < 9; j++) pos[i*9+j] = dv.getFloat32(off+j*4, true);
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    g.computeVertexNormals();
    return g;
  }
  const txt = new TextDecoder().decode(buf);
  const verts = []; const re = /vertex\s+([\d.eE+\-]+)\s+([\d.eE+\-]+)\s+([\d.eE+\-]+)/g; let m;
  while ((m = re.exec(txt))) verts.push(+m[1], +m[2], +m[3]);
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(verts), 3));
  g.computeVertexNormals(); return g;
}

let rocketLoaded  = false;
let rocketLenM    = 0.8;   // real rocket length in metres — updated once /aero resolves

Promise.all([
  fetch('/upload/stl/assembly/file').then(r => r.arrayBuffer()),
  fetch('/aero').then(r => r.json()).catch(() => null),
]).then(([buf, aero]) => {
  const geo = parseSTLBuffer(buf);
  geo.computeBoundingBox();
  const bb  = geo.boundingBox;
  const sz  = new THREE.Vector3(); bb.getSize(sz);
  const ctr = new THREE.Vector3(); bb.getCenter(ctr);

  // TRUE-SCALE fix: previously every rocket was force-normalised to a fixed
  // 1.4 Three.js units regardless of its real size, completely disconnected
  // from the position scale used elsewhere — that's why the rocket looked
  // huge and barely appeared to climb even at real apogees of several
  // hundred metres. Now: 1 Three.js unit = 1 real metre, using the actual
  // Barrowman-derived rocket length (aero.rocket_length, metres) as the
  // ground truth for how many real metres the raw STL's long axis spans.
  if (aero && aero.rocket_length > 0) rocketLenM = aero.rocket_length;
  const rawLength = sz.z;   // STL's long axis extent, in the file's raw units
  const trueScale = rocketLenM / Math.max(rawLength, 1e-6);

  // Centre X/Y (remove any horizontal STL offset) but do NOT centre Z —
  // instead pin the TAIL (bb.min.z, per the Inventor "tail at Z=0" export
  // convention) to the origin, so after rotation the rocket's bottom sits
  // exactly on the grid instead of straddling it at its midpoint.
  geo.translate(-ctr.x, -ctr.y, -bb.min.z);
  geo.scale(trueScale, trueScale, trueScale);

  // Rocket axis is Z in our convention (tail=0, nose=top).
  // Rotate so it points UP in Three.js (+Y). Tail (z=0 pre-rotation) maps
  // to y=0 post-rotation, so it lands exactly on the grid.
  geo.applyMatrix4(new THREE.Matrix4().makeRotationX(-Math.PI / 2));

  const solid = new THREE.Mesh(geo, new THREE.MeshPhongMaterial({
    color: 0x0e7490, transparent: true, opacity: 0.07, side: THREE.DoubleSide
  }));
  const wire = new THREE.LineSegments(
    new THREE.WireframeGeometry(geo),
    new THREE.LineBasicMaterial({ color: 0x22d3ee, transparent: true, opacity: 0.6 })
  );
  rocketGroup.add(solid, wire);
  rocketLoaded = true;
  applyAeroReadout(aero);
}).catch(() => {
  // Fallback: simple true-scale capsule if no STL — same tail-at-origin
  // convention as the real STL path (Three.js cylinders/cones are centred
  // on their own origin by default, so both need an explicit shift to
  // sit base-down on the grid instead of straddling it).
  const bodyLen = rocketLenM * 0.83;
  const noseLen = rocketLenM * 0.17;
  const radius  = rocketLenM * 0.05;
  const cyl  = new THREE.CylinderGeometry(radius, radius, bodyLen, 16);
  cyl.translate(0, bodyLen/2, 0);              // base at y=0, top at y=bodyLen
  const cone = new THREE.ConeGeometry(radius, noseLen, 16);
  cone.translate(0, bodyLen + noseLen/2, 0);    // sits directly on top of the cylinder
  const wire1 = new THREE.LineSegments(new THREE.WireframeGeometry(cyl), new THREE.LineBasicMaterial({color:0x22d3ee, transparent:true, opacity:.6}));
  const wire2 = new THREE.LineSegments(new THREE.WireframeGeometry(cone), new THREE.LineBasicMaterial({color:0x22d3ee, transparent:true, opacity:.6}));
  rocketGroup.add(wire1, wire2);
  rocketLoaded = true;
});

// Resize
function resizeViewer() {
  const w = viewerDiv.clientWidth, h = viewerDiv.clientHeight;
  renderer.setSize(w, h);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}
resizeViewer();
new ResizeObserver(resizeViewer).observe(viewerDiv);

let isBoost = false;

// Chase-camera distance grows with altitude so the rocket stays framed
// across the full flight, but PULLS BACK SLOWLY relative to how fast the
// rocket is actually climbing — a 1:1 pullback rate would just recreate
// the original bug in a different form (camera zooming out exactly as
// fast as the rocket climbs makes the climb look just as static on
// screen). This rate is tuned so the rocket visibly travels a large
// fraction of the frame during a typical flight, with the camera only
// pulling back enough to keep it from leaving frame entirely.
function chaseDistance(altitude) {
  const minDist = Math.max(rocketLenM * 2.2, 1.5);   // close-up framing on the pad
  return minDist + altitude * 0.12;                   // gentle pullback — climb stays dramatic
}

// True chase cam: the camera TARGET (what it orbits/looks at) is the
// rocket's own position, eased for inertia — not a fixed world point. This
// keeps the rocket framed near screen-center for the whole flight, both
// vertically and horizontally. Motion still reads clearly because the grid
// and altitude rings below are fixed in world space and slide past
// underneath as the camera translates to keep up with the rocket.
let smoothedDist = null;
const smoothedTarget = new THREE.Vector3();
const CAMERA_EASE = 0.06;   // lower = smoother/slower to catch up, higher = snappier

function animate3D() {
  requestAnimationFrame(animate3D);

  const rocketPos  = rocketGroup.position;
  const targetDist = chaseDistance(rocketPos.y) * userZoom;

  if (smoothedDist === null) {           // no easing on first frame
    smoothedDist = targetDist;
    smoothedTarget.copy(rocketPos);
  }
  smoothedDist    += (targetDist    - smoothedDist)    * CAMERA_EASE;
  smoothedTarget.x += (rocketPos.x - smoothedTarget.x) * CAMERA_EASE;
  smoothedTarget.y += (rocketPos.y - smoothedTarget.y) * CAMERA_EASE;
  smoothedTarget.z += (rocketPos.z - smoothedTarget.z) * CAMERA_EASE;

  camera.position.x = smoothedTarget.x + Math.sin(rotY) * Math.cos(rotX) * smoothedDist;
  camera.position.y = smoothedTarget.y + Math.sin(rotX) * smoothedDist;
  camera.position.z = smoothedTarget.z + Math.cos(rotY) * Math.cos(rotX) * smoothedDist;
  camera.lookAt(smoothedTarget.x, smoothedTarget.y, smoothedTarget.z);

  updateAltRings(rocketPos.y);
  updatePlume(rocketPos.y, isBoost);
  renderer.render(scene, camera);
}
animate3D();

function updateRocket3D(d) {
  // Position (true 1 Three.js unit = 1 real metre)
  rocketGroup.position.set(d.pos[0], d.pos[2], d.pos[1]);

  // Attitude from quaternion [w, x, y, z]
  // Our convention: quaternion rotates rocket from Z-up to world frame
  // In Three.js Y-up, we need to rotate accordingly
  const q = d.attitude_q; // [w, x, y, z]
  rocketGroup.quaternion.set(q[1], q[3], q[2], q[0]);

  // Trail
  trailSimPts.push(new THREE.Vector3(d.pos[0], d.pos[2], d.pos[1]));
  if (trailSimPts.length > TRAIL_MAX) trailSimPts.shift();
  trailSimGeo.setFromPoints(trailSimPts);

  isBoost = d.phase === 'BOOST';

  // Badge
  document.getElementById('badge-phase').textContent = d.phase;
  document.getElementById('badge-motor').textContent  = d.motor_name;

  updateGroundTrack(d.pos[0], d.pos[1]);
}

// ═══════════════════════════════════════════════════════════════════════════════
// GROUND-TRACK MINIMAP — top-down X(east)/Y(north) trace, since the chase
// camera above always keeps the rocket centered and can no longer show
// absolute horizontal drift by itself.
// ═══════════════════════════════════════════════════════════════════════════════
const groundTrackCanvas = document.getElementById('groundtrack');
const groundTrackCtx    = groundTrackCanvas.getContext('2d');
const groundTrackPts    = [];
const GT_MAX_PTS        = 600;

function updateGroundTrack(x, y) {
  groundTrackPts.push({ x, y });
  if (groundTrackPts.length > GT_MAX_PTS) groundTrackPts.shift();

  const W = groundTrackCanvas.width, H = groundTrackCanvas.height;
  const cx = W / 2, cy = H / 2;
  groundTrackCtx.clearRect(0, 0, W, H);

  let maxR = 10;   // metres — minimum extent so the map isn't hyper-zoomed on the pad
  for (const p of groundTrackPts) maxR = Math.max(maxR, Math.abs(p.x), Math.abs(p.y));
  maxR *= 1.2;
  const s = (W / 2 - 8) / maxR;

  // Axes through the pad
  groundTrackCtx.strokeStyle = 'rgba(30,45,61,0.9)';
  groundTrackCtx.lineWidth = 1;
  groundTrackCtx.beginPath();
  groundTrackCtx.moveTo(cx, 4); groundTrackCtx.lineTo(cx, H - 4);
  groundTrackCtx.moveTo(4, cy); groundTrackCtx.lineTo(W - 4, cy);
  groundTrackCtx.stroke();

  // Pad marker
  groundTrackCtx.fillStyle = 'rgba(148,163,184,0.7)';
  groundTrackCtx.beginPath(); groundTrackCtx.arc(cx, cy, 2, 0, Math.PI * 2); groundTrackCtx.fill();

  // Trail
  if (groundTrackPts.length > 1) {
    groundTrackCtx.strokeStyle = '#22d3ee';
    groundTrackCtx.lineWidth = 1.2;
    groundTrackCtx.beginPath();
    groundTrackPts.forEach((p, i) => {
      const px = cx + p.x * s, py = cy - p.y * s;
      if (i === 0) groundTrackCtx.moveTo(px, py); else groundTrackCtx.lineTo(px, py);
    });
    groundTrackCtx.stroke();
  }

  // Current position
  const last = groundTrackPts[groundTrackPts.length - 1];
  groundTrackCtx.fillStyle = '#f97316';
  groundTrackCtx.beginPath();
  groundTrackCtx.arc(cx + last.x * s, cy - last.y * s, 2.5, 0, Math.PI * 2);
  groundTrackCtx.fill();

  document.getElementById('groundtrack-label').textContent = 'GND TRACK · ±' + maxR.toFixed(0) + 'm';
}

// ═══════════════════════════════════════════════════════════════════════════════
// ADI — Attitude Direction Indicator
// ═══════════════════════════════════════════════════════════════════════════════
const adiCanvas = document.getElementById('adi');
const adiCtx    = adiCanvas.getContext('2d');
const adiR      = 46; // radius

function drawADI(pitchDeg, rollDeg) {
  const W = adiCanvas.width, H = adiCanvas.height;
  const cx = W/2, cy = H/2;

  adiCtx.clearRect(0, 0, W, H);

  // Clip to circle
  adiCtx.save();
  adiCtx.beginPath();
  adiCtx.arc(cx, cy, adiR, 0, Math.PI*2);
  adiCtx.clip();

  // Pitch offset: 1px per degree
  const pitchPx = pitchDeg * 1.2;
  const rollRad  = rollDeg * Math.PI / 180;

  adiCtx.save();
  adiCtx.translate(cx, cy);
  adiCtx.rotate(-rollRad);
  adiCtx.translate(0, pitchPx);

  // Sky
  adiCtx.fillStyle = '#0c2a4a';
  adiCtx.fillRect(-W, -H, W*2, H);

  // Ground
  adiCtx.fillStyle = '#2d1a08';
  adiCtx.fillRect(-W, 0, W*2, H);

  // Horizon line
  adiCtx.strokeStyle = '#e2e8f0';
  adiCtx.lineWidth = 1.5;
  adiCtx.beginPath();
  adiCtx.moveTo(-W, 0); adiCtx.lineTo(W, 0);
  adiCtx.stroke();

  // Pitch ladder (every 10 deg)
  adiCtx.strokeStyle = 'rgba(226,232,240,0.5)';
  adiCtx.fillStyle   = 'rgba(226,232,240,0.5)';
  adiCtx.lineWidth   = 0.8;
  adiCtx.font        = '7px monospace';
  for (let deg = -30; deg <= 30; deg += 10) {
    if (deg === 0) continue;
    const y = -deg * 1.2;
    const hw = deg % 20 === 0 ? 18 : 10;
    adiCtx.beginPath();
    adiCtx.moveTo(-hw, y); adiCtx.lineTo(hw, y);
    adiCtx.stroke();
    adiCtx.fillText(Math.abs(deg), hw+3, y+3);
  }

  adiCtx.restore();

  // Fixed crosshair (does not rotate)
  adiCtx.strokeStyle = '#f97316';
  adiCtx.lineWidth = 1.5;
  // Left wing
  adiCtx.beginPath(); adiCtx.moveTo(cx-30, cy); adiCtx.lineTo(cx-10, cy); adiCtx.stroke();
  // Right wing
  adiCtx.beginPath(); adiCtx.moveTo(cx+10, cy); adiCtx.lineTo(cx+30, cy); adiCtx.stroke();
  // Center dot
  adiCtx.beginPath(); adiCtx.arc(cx, cy, 2, 0, Math.PI*2);
  adiCtx.fillStyle = '#f97316'; adiCtx.fill();

  adiCtx.restore();

  // Circle border
  adiCtx.beginPath();
  adiCtx.arc(cx, cy, adiR, 0, Math.PI*2);
  adiCtx.strokeStyle = '#2a3f55';
  adiCtx.lineWidth   = 2;
  adiCtx.stroke();
}

drawADI(0, 0);

// ═══════════════════════════════════════════════════════════════════════════════
// CHARTS
// ═══════════════════════════════════════════════════════════════════════════════
const CHART_WINDOW = 30; // seconds of data shown
const CHART_BUF    = 1200; // max points buffered

const chartData = {
  alt:   { sim: [], hw: [], color: '#22d3ee', hw_color: '#f97316' },
  pitch: { sim: [], hw: [], color: '#22d3ee', hw_color: '#f97316' },
  roll:  { sim: [], hw: [], color: '#22d3ee', hw_color: '#f97316' },
  gx:    { sim: [],         color: '#22d3ee' },
  sv:    { pitch: [], yaw: [] },
  pid:   { data: [] },
};

let apogeeTime = null, prevVz = 0;

function pushChart(key, t, simVal, hwVal) {
  const d = chartData[key];
  d.sim.push({t, v: simVal});
  if (hwVal !== undefined && d.hw) d.hw.push({t, v: hwVal});
  if (d.sim.length > CHART_BUF) d.sim.shift();
  if (d.hw && d.hw.length > CHART_BUF) d.hw.shift();
}

function drawChart(canvasId, series, opts = {}) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const W = canvas.offsetWidth, H = canvas.offsetHeight;
  if (!W || !H) return;
  canvas.width = W; canvas.height = H;
  const ctx = canvas.getContext('2d');

  ctx.clearRect(0, 0, W, H);

  // Grid
  ctx.strokeStyle = 'rgba(30,45,61,0.8)';
  ctx.lineWidth   = 0.5;
  for (let i = 1; i < 4; i++) {
    ctx.beginPath();
    ctx.moveTo(0, H*i/4); ctx.lineTo(W, H*i/4);
    ctx.stroke();
  }
  for (let i = 1; i < 5; i++) {
    ctx.beginPath();
    ctx.moveTo(W*i/5, 0); ctx.lineTo(W*i/5, H);
    ctx.stroke();
  }

  if (!series.length || !series[0].data.length) return;

  const now   = series[0].data[series[0].data.length - 1].t;
  const tMin  = now - CHART_WINDOW;
  let   yMin  = Infinity, yMax = -Infinity;

  series.forEach(s => {
    s.data.forEach(p => {
      if (p.t < tMin) return;
      if (p.v < yMin) yMin = p.v;
      if (p.v > yMax) yMax = p.v;
    });
  });

  if (!isFinite(yMin)) return;

  const pad = (yMax - yMin) * 0.1 || 1;
  yMin -= pad; yMax += pad;

  const tx = t => (t - tMin) / CHART_WINDOW * W;
  const ty = v => H - (v - yMin) / (yMax - yMin) * H;

  // Time axis labels
  ctx.fillStyle = 'rgba(100,116,139,0.7)';
  ctx.font = '8px monospace';
  for (let dt = 0; dt <= CHART_WINDOW; dt += 10) {
    const x = tx(tMin + dt);
    const label = (tMin + dt).toFixed(0) + 's';
    ctx.fillText(label, x + 2, H - 3);
  }

  // Draw series
  series.forEach(s => {
    if (!s.data.length) return;
    ctx.beginPath();
    ctx.strokeStyle = s.color;
    ctx.lineWidth   = 1.2;
    let started = false;
    s.data.forEach(p => {
      if (p.t < tMin) return;
      const x = tx(p.t), y = ty(p.v);
      if (!started) { ctx.moveTo(x, y); started = true; }
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
  });

  // Apogee marker on altitude chart
  if (opts.apogee && apogeeTime !== null) {
    const ax = tx(apogeeTime);
    if (ax > 0 && ax < W) {
      ctx.strokeStyle = 'rgba(234,179,8,0.6)';
      ctx.lineWidth = 1;
      ctx.setLineDash([3, 3]);
      ctx.beginPath(); ctx.moveTo(ax, 0); ctx.lineTo(ax, H); ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = 'rgba(234,179,8,0.8)';
      ctx.font = '8px monospace';
      ctx.fillText('APOGEE', ax + 2, 12);
    }
  }

  // Y labels
  const maxEl = document.getElementById(opts.ymaxId);
  const minEl = document.getElementById(opts.yminId);
  if (maxEl) maxEl.textContent = yMax.toFixed(1);
  if (minEl) minEl.textContent = yMin.toFixed(1);
}

function redrawAllCharts() {
  drawChart('ch-alt', [
    { data: chartData.alt.sim, color: '#22d3ee' },
    { data: chartData.alt.hw,  color: '#f97316' }
  ], { apogee: true, ymaxId: 'cy-alt-max', yminId: 'cy-alt-min' });

  drawChart('ch-pitch', [
    { data: chartData.pitch.sim, color: '#22d3ee' },
    { data: chartData.pitch.hw,  color: '#f97316' }
  ], { ymaxId: 'cy-pitch-max', yminId: 'cy-pitch-min' });

  drawChart('ch-roll', [
    { data: chartData.roll.sim, color: '#22d3ee' },
    { data: chartData.roll.hw,  color: '#f97316' }
  ], { ymaxId: 'cy-roll-max', yminId: 'cy-roll-min' });

  drawChart('ch-gx', [
    { data: chartData.gx.sim, color: '#22d3ee' }
  ], { ymaxId: 'cy-gx-max', yminId: 'cy-gx-min' });

  drawChart('ch-sv', [
    { data: chartData.sv.pitch, color: '#22d3ee' },
    { data: chartData.sv.yaw,   color: '#f97316' }
  ], { ymaxId: 'cy-sv-max', yminId: 'cy-sv-min' });

  drawChart('ch-pid', [
    { data: chartData.pid.data, color: '#ef4444' }
  ], { ymaxId: 'cy-pid-max', yminId: 'cy-pid-min' });
}

setInterval(redrawAllCharts, 100);

// ═══════════════════════════════════════════════════════════════════════════════
// MISSION TIMELINE + EVENT LOG
// ═══════════════════════════════════════════════════════════════════════════════
const eventTimes = { liftoff: null, burnout: null, apogee: null, touchdown: null };
const eventLog   = [];

function fmtClock(t) {
  const mm = String(Math.floor(t / 60)).padStart(2, '0');
  const ss = (t % 60).toFixed(1).padStart(4, '0');
  return `T+${mm}:${ss}`;
}

function logEvent(t, label, tone) {
  eventLog.unshift({ t, label, tone });
  if (eventLog.length > 40) eventLog.pop();
  const el = document.getElementById('event-log');
  el.innerHTML = eventLog.map(e =>
    `<div class="ev-row"><span class="ev-t">${fmtClock(e.t)}</span><span class="ev-label ${e.tone || ''}">${e.label}</span></div>`
  ).join('');
}

function setChip(id, cls, time) {
  const chip = document.getElementById(id);
  chip.className = 'tl-chip' + (cls ? ' ' + cls : '');
  chip.querySelector('.tl-t').textContent = time != null ? fmtClock(time) : '';
}

function renderTimeline(phase) {
  setChip('tl-pad', phase === 'IDLE' ? 'active' : 'done', phase === 'IDLE' ? null : 0);
  setChip('tl-liftoff',   eventTimes.liftoff   == null ? '' : (phase === 'BOOST'   ? 'active' : 'done'), eventTimes.liftoff);
  setChip('tl-burnout',   eventTimes.burnout   == null ? '' : (phase === 'COAST'   ? 'active' : 'done'), eventTimes.burnout);
  setChip('tl-apogee',    eventTimes.apogee    == null ? '' : (phase === 'DESCENT' ? 'active' : 'done'), eventTimes.apogee);
  setChip('tl-touchdown', eventTimes.touchdown == null ? '' : 'done', eventTimes.touchdown);

  document.getElementById('tl-line-1').className = 'tl-line' + (eventTimes.liftoff   != null ? ' done' : '');
  document.getElementById('tl-line-2').className = 'tl-line' + (eventTimes.burnout   != null ? ' done' : '');
  document.getElementById('tl-line-3').className = 'tl-line' + (eventTimes.apogee    != null ? ' done' : '');
  document.getElementById('tl-line-4').className = 'tl-line' + (eventTimes.touchdown != null ? ' done' : '');
}

// ═══════════════════════════════════════════════════════════════════════════════
// SCRUBBER
// ═══════════════════════════════════════════════════════════════════════════════
let isLive      = true;
let historyBuf  = [];
let scrubbing   = false;

document.getElementById('scrub').addEventListener('mousedown', () => { scrubbing = true; isLive = false; updateLiveBtn(); });
document.getElementById('scrub').addEventListener('mouseup',   () => { scrubbing = false; });
document.getElementById('scrub').addEventListener('input', () => {
  const idx = Math.floor(document.getElementById('scrub').value / 1000 * (historyBuf.length - 1));
  if (historyBuf[idx]) applyState(historyBuf[idx]);
});

function goLive() {
  isLive = true;
  document.getElementById('scrub').value = 1000;
  updateLiveBtn();
  fetch('/resume', { method: 'POST' });
}

function updateLiveBtn() {
  const btn = document.getElementById('btn-live');
  btn.className = isLive ? '' : 'dead';
}

// Sync history from server periodically
setInterval(async () => {
  const res = await fetch('/history');
  historyBuf = await res.json();
}, 5000);

// ═══════════════════════════════════════════════════════════════════════════════
// AERO READOUT (static geometry from the STL/Barrowman pipeline)
// ═══════════════════════════════════════════════════════════════════════════════
function applyAeroReadout(aero) {
  if (!aero) return;
  if (aero.cp_from_nose)    set('st-cp', fmt(aero.cp_from_nose, 3) + ' m');
  if (aero.rocket_length)   set('st-length', fmt(aero.rocket_length, 3) + ' m');
  if (aero.rocket_diameter) set('st-dia', fmt(aero.rocket_diameter, 3) + ' m');
}

// ═══════════════════════════════════════════════════════════════════════════════
// WEBSOCKET + STATE UPDATE
// ═══════════════════════════════════════════════════════════════════════════════
const fmt  = (v, d=2) => typeof v === 'number' ? v.toFixed(d) : '—';
const set  = (id, v)  => { const el = document.getElementById(id); if (el) el.textContent = v; };

let flightStats = { maxAlt: 0, maxSpd: 0, maxG: 0, maxMach: 0, burnEnd: 0 };
let prevPhase   = 'IDLE';

function applyState(d) {
  // Header metrics
  const t = d.t;
  const mm = String(Math.floor(t / 60)).padStart(2, '0');
  const ss = (t % 60).toFixed(1).padStart(4, '0');
  set('clock',   `T+${mm}:${ss}`);
  set('hm-alt',  fmt(d.pos[2], 1));
  set('hm-vz',   fmt(d.vel[2], 1));
  set('hm-spd',  fmt(d.speed, 1));
  set('hm-mach', fmt(d.mach, 3));
  set('hm-g',    fmt(d.g_load, 2));
  set('hm-hz',   fmt(d.hz, 0));

  // Phase pill
  const phaseEl = document.getElementById('pill-phase');
  phaseEl.textContent = d.phase;
  phaseEl.className = 'pill' + (d.phase === 'BOOST' ? ' ok' : d.phase === 'LANDED' ? ' warn' : d.phase === 'COAST' ? ' on' : '');

  // Paused
  document.getElementById('pill-paused').style.display = d.paused ? 'block' : 'none';

  // HW pill
  const hwEl = document.getElementById('pill-hw');
  hwEl.textContent  = d.hw_connected ? 'HW CONNECTED' : 'HW OFFLINE';
  hwEl.className    = 'pill' + (d.hw_connected ? ' ok' : '');

  // ADI
  drawADI(d.euler[0], d.euler[1]);

  // Euler
  set('e-pitch', fmt(d.euler[0], 1) + '°');
  set('e-roll',  fmt(d.euler[1], 1) + '°');
  set('e-yaw',   fmt(d.euler[2], 1) + '°');

  // Angular rates
  set('ar-x', fmt(d.angular_rate[0], 4));
  set('ar-y', fmt(d.angular_rate[1], 4));
  set('ar-z', fmt(d.angular_rate[2], 4));

  // Motor state
  set('ms-thrust', fmt(d.thrust, 1) + ' N');
  set('ms-burn',   d.phase === 'BOOST' ? fmt(d.burn_remaining, 2) + ' s' : '—');
  set('ms-phase',  d.phase);

  // Position
  set('p-x', fmt(d.pos[0])); set('p-y', fmt(d.pos[1])); set('p-z', fmt(d.pos[2]));

  // Velocity
  set('v-x', fmt(d.vel[0])); set('v-y', fmt(d.vel[1])); set('v-z', fmt(d.vel[2]));
  set('v-spd', fmt(d.speed));

  // Acceleration
  set('a-x', fmt(d.accel[0], 3)); set('a-y', fmt(d.accel[1], 3)); set('a-z', fmt(d.accel[2], 3));

  // Aero
  set('aero-q',    fmt(d.dynamic_pressure, 1) + ' Pa');
  set('aero-drag', fmt(d.drag_force, 2) + ' N');
  set('aero-mach', fmt(d.mach, 3));
  set('aero-g',    fmt(d.g_load, 2));
  set('aero-aoa',  fmt(d.aoa, 2) + '°');

  // Sensors
  set('imu-ax', fmt(d.imu_accel[0], 3)); set('imu-ay', fmt(d.imu_accel[1], 3)); set('imu-az', fmt(d.imu_accel[2], 3));
  set('imu-gx', fmt(d.imu_gyro[0], 4));  set('imu-gy', fmt(d.imu_gyro[1], 4));  set('imu-gz', fmt(d.imu_gyro[2], 4));
  set('baro-est',  fmt(d.baro_alt, 1) + ' m');
  set('baro-true', fmt(d.baro_true_alt, 1) + ' m');
  set('baro-err',  (d.baro_error >= 0 ? '+' : '') + fmt(d.baro_error, 2) + ' m');
  set('uart-sent', d.uart_packets_sent);
  set('uart-rate', fmt(d.uart_packet_rate, 1) + ' Hz');
  set('uart-last', d.uart_last_packet || '—');

  // Ground track readout
  const downrange = Math.hypot(d.pos[0], d.pos[1]);
  set('st-downrange', fmt(downrange, 2) + ' m');
  set('st-bearing', downrange > 0.5 ? fmt((Math.atan2(d.pos[0], d.pos[1]) * 180 / Math.PI + 360) % 360, 0) + '°' : '—');

  // HW panel
  const hwOnline = d.hw_connected;
  document.getElementById('hw-offline-msg').style.display  = hwOnline ? 'none' : 'flex';
  document.getElementById('hw-online-content').style.display = hwOnline ? 'block' : 'none';
  if (hwOnline) {
    set('hw-ax', fmt(d.hw_imu_accel[0], 3)); set('hw-ay', fmt(d.hw_imu_accel[1], 3)); set('hw-az', fmt(d.hw_imu_accel[2], 3));
    set('hw-gx', fmt(d.hw_imu_gyro[0], 3));  set('hw-gy', fmt(d.hw_imu_gyro[1], 3));  set('hw-gz', fmt(d.hw_imu_gyro[2], 3));
    set('hw-pitch', fmt(d.hw_attitude[0], 1) + '°');
    set('hw-roll',  fmt(d.hw_attitude[1], 1) + '°');
    set('hw-yaw',   fmt(d.hw_attitude[2], 1) + '°');

    // Servo gauges (assume ±15° max deflection)
    const spct = Math.max(0, Math.min(100, (d.hw_servo_pitch / 15 + 1) / 2 * 100));
    const ypct = Math.max(0, Math.min(100, (d.hw_servo_yaw   / 15 + 1) / 2 * 100));
    document.getElementById('sv-pitch-needle').style.left = spct + '%';
    document.getElementById('sv-yaw-needle').style.left   = ypct + '%';
    const pw = Math.abs(d.hw_servo_pitch) > 10;
    const yw = Math.abs(d.hw_servo_yaw)   > 10;
    document.getElementById('sv-pitch-needle').className = 'servo-needle' + (pw ? ' warn' : '');
    document.getElementById('sv-yaw-needle').className   = 'servo-needle' + (yw ? ' warn' : '');
    set('sv-pitch-val', fmt(d.hw_servo_pitch, 1) + '°');
    set('sv-yaw-val',   fmt(d.hw_servo_yaw,   1) + '°');
    document.getElementById('link-fill').style.width = (d.hw_link_quality * 100) + '%';
  }

  // 3D viewer
  updateRocket3D(d);

  // Chart data
  pushChart('alt',   t, d.pos[2],    d.hw_connected ? d.hw_attitude[0] : undefined);
  pushChart('pitch', t, d.euler[0],  d.hw_connected ? d.hw_attitude[0] : undefined);
  pushChart('roll',  t, d.euler[1],  d.hw_connected ? d.hw_attitude[1] : undefined);
  chartData.gx.sim.push({t, v: d.angular_rate[0]});
  if (chartData.gx.sim.length > CHART_BUF) chartData.gx.sim.shift();
  chartData.sv.pitch.push({t, v: d.hw_servo_pitch});
  chartData.sv.yaw.push({t, v: d.hw_servo_yaw});
  if (chartData.sv.pitch.length > CHART_BUF) chartData.sv.pitch.shift();
  if (chartData.sv.yaw.length   > CHART_BUF) chartData.sv.yaw.shift();
  const pidErr = Math.sqrt(d.hw_pid_error[0]**2 + d.hw_pid_error[1]**2);
  chartData.pid.data.push({t, v: pidErr});
  if (chartData.pid.data.length > CHART_BUF) chartData.pid.data.shift();

  // Apogee detection (chart marker — separate from the phase-transition event below)
  const vz = d.vel[2];
  if (prevPhase === 'BOOST' && vz < 0 && prevVz >= 0 && d.pos[2] > 1) apogeeTime = t;
  prevVz = vz;

  // Flight stats
  flightStats.maxAlt  = Math.max(flightStats.maxAlt,  d.pos[2]);
  flightStats.maxSpd  = Math.max(flightStats.maxSpd,  d.speed);
  flightStats.maxG    = Math.max(flightStats.maxG,    d.g_load);
  flightStats.maxMach = Math.max(flightStats.maxMach, d.mach);
  if (d.phase === 'BOOST') flightStats.burnEnd = t;

  set('rec-alt',  fmt(flightStats.maxAlt, 1) + ' m');
  set('rec-spd',  fmt(flightStats.maxSpd, 1) + ' m/s');
  set('rec-mach', fmt(flightStats.maxMach, 3));
  set('rec-g',    fmt(flightStats.maxG, 2));

  // Mission events + timeline — fires once per phase transition
  if (d.phase !== prevPhase) {
    if (d.phase === 'BOOST'   && eventTimes.liftoff   === null) { eventTimes.liftoff   = t; logEvent(t, 'LIFTOFF', 'ok'); }
    if (d.phase === 'COAST'   && eventTimes.burnout   === null) { eventTimes.burnout   = t; logEvent(t, 'BURNOUT / MECO', 'warn'); }
    if (d.phase === 'DESCENT' && eventTimes.apogee    === null) { eventTimes.apogee    = t; logEvent(t, `APOGEE — ${fmt(d.pos[2], 1)} m`, 'warn'); }
    if (d.phase === 'LANDED'  && eventTimes.touchdown === null) { eventTimes.touchdown = t; logEvent(t, 'TOUCHDOWN', 'red'); }
  }
  renderTimeline(d.phase);

  // Landing detection — show summary once
  if (d.phase === 'LANDED' && prevPhase !== 'LANDED') {
    setTimeout(() => showSummary(d), 800);
  }
  prevPhase = d.phase;

  // Scrubber time display
  set('scrub-time', `T+${mm}:${ss}`);
}

function showSummary(d) {
  set('sum-alt',  fmt(flightStats.maxAlt, 1) + ' m');
  set('sum-spd',  fmt(flightStats.maxSpd, 1) + ' m/s');
  set('sum-g',    fmt(flightStats.maxG, 2) + ' G');
  set('sum-mach', fmt(flightStats.maxMach, 3));
  set('sum-burn', fmt(flightStats.burnEnd, 2) + ' s');
  const mm2 = String(Math.floor(d.t/60)).padStart(2,'0');
  const ss2 = (d.t%60).toFixed(1).padStart(4,'0');
  set('sum-time', `${mm2}:${ss2}`);
  document.getElementById('summary-overlay').classList.add('show');
}

// WebSocket
const ws = new WebSocket(`ws://${location.host}/ws`);
ws.onmessage = e => {
  if (!isLive || scrubbing) return;
  const d = JSON.parse(e.data);
  applyState(d);
};
ws.onclose = () => set('pill-sim', 'SIM OFFLINE');
