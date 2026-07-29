import threading
import json
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
import webbrowser

HTML = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>MONK HIL Console</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{
  --bg:     #0f1520;
  --bg1:    #141d2b;
  --bg2:    #1a2538;
  --border: #243044;
  --orange: #fb923c;
  --orange2:#7c3a0e;
  --green:  #34d399;
  --cyan:   #38bdf8;
  --amber:  #fcd34d;
  --red:    #f87171;
  --dim:    #4b5a6e;
  --text:   #e2eaf4;
  --muted:  #6b7f96;
  --mono:   'Courier New', monospace;
}
body{background:var(--bg);color:var(--text);font-family:var(--mono);overflow:hidden;height:100vh;width:100vw}

#launch-screen{
  position:absolute;inset:0;background:var(--bg);
  display:flex;flex-direction:column;align-items:center;justify-content:center;
  z-index:100;gap:0
}
.ls-logo{
  font-size:42px;font-weight:900;color:var(--orange);
  letter-spacing:8px;margin-bottom:4px;
  border-bottom:2px solid var(--orange);padding-bottom:10px
}
.ls-sub{font-size:11px;color:var(--muted);letter-spacing:4px;margin-bottom:36px}
.ls-card{
  background:var(--bg1);border:1px solid var(--border);
  border-top:2px solid var(--orange);
  padding:28px 36px;width:580px
}
.ls-section{font-size:10px;color:var(--orange);letter-spacing:2px;margin-bottom:14px}
.ls-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:24px}
.ls-field{display:flex;flex-direction:column;gap:5px}
.ls-label{font-size:10px;color:var(--muted);letter-spacing:1px}
.ls-input{
  background:var(--bg2);border:1px solid var(--border);color:var(--text);
  font-family:var(--mono);font-size:13px;padding:7px 10px;
  outline:none;transition:border-color .2s
}
.ls-input:focus{border-color:var(--orange)}
.ls-select{
  background:var(--bg2);border:1px solid var(--border);color:var(--text);
  font-family:var(--mono);font-size:13px;padding:7px 10px;
  outline:none;cursor:pointer;width:100%
}
.ls-motor-row{margin-bottom:20px}
.ls-motor-info{
  display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:10px
}
.ls-mi{background:var(--bg2);border:1px solid var(--border);padding:8px 10px;text-align:center}
.ls-mi-v{font-size:15px;font-weight:700;color:var(--orange)}
.ls-mi-l{font-size:9px;color:var(--muted);letter-spacing:1px;margin-top:2px}
.ls-divider{border:none;border-top:1px solid var(--border);margin:20px 0}
.ls-launch-btn{
  width:100%;padding:14px;background:var(--orange);color:#0f1520;
  font-family:var(--mono);font-size:14px;font-weight:700;letter-spacing:3px;
  border:none;cursor:pointer;transition:background .2s
}
.ls-launch-btn:hover{background:#fdba74}
.ls-warning{font-size:9px;color:var(--muted);text-align:center;margin-top:10px;letter-spacing:1px}

#dashboard{display:none;flex-direction:column;height:100vh}

#hdr{
  height:50px;background:var(--bg1);border-bottom:2px solid var(--orange2);
  display:flex;align-items:center;padding:0 18px;gap:16px;flex-shrink:0
}
.logo{
  font-size:22px;font-weight:900;color:var(--orange);
  letter-spacing:5px;margin-right:6px;
  border-right:2px solid var(--orange2);padding-right:16px
}
.pill{font-size:10px;padding:3px 9px;border-radius:2px;border:1px solid;letter-spacing:1px;white-space:nowrap}
.pill-sim{border-color:#34d39940;background:#34d39910;color:var(--green)}
.pill-paused{border-color:#fcd34d40;background:#fcd34d10;color:var(--amber);animation:blink 1.2s infinite}
.pill-hw-on{border-color:#38bdf840;background:#38bdf810;color:var(--cyan);animation:blink 2s infinite}
.pill-hw-off{border-color:#4b5a6e40;background:#4b5a6e08;color:var(--muted)}
.pill-phase{border-color:#fb923c40;background:#fb923c10;color:var(--orange)}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.4}}
.mtime{font-size:24px;font-weight:700;color:#fff;letter-spacing:2px;margin-left:4px}
.hstats{margin-left:auto;display:flex;gap:24px}
.hs{text-align:right}
.hs-v{font-size:20px;font-weight:700;color:var(--orange);line-height:1}
.hs-l{font-size:9px;color:var(--muted);letter-spacing:1px;margin-top:2px}

#timeline{
  height:40px;background:var(--bg1);border-bottom:1px solid var(--border);
  display:flex;align-items:center;padding:0 18px;gap:14px;flex-shrink:0
}
.tl-btn{
  font-family:var(--mono);font-size:10px;letter-spacing:1px;font-weight:700;
  padding:5px 12px;border-radius:2px;border:1px solid;cursor:pointer;
  background:transparent;transition:all .15s;white-space:nowrap
}
.tl-btn.live-on{border-color:var(--green);color:var(--green);background:#34d39912}
.tl-btn.live-off{border-color:var(--muted);color:var(--muted)}
.tl-btn:hover{filter:brightness(1.3)}
#tl-track-wrap{flex:1;position:relative;height:18px;display:flex;align-items:center}
#tl-track{
  width:100%;height:4px;background:var(--border);border-radius:2px;position:relative;cursor:pointer
}
#tl-fill{position:absolute;left:0;top:0;height:4px;background:var(--orange);border-radius:2px;width:0%}
#tl-handle{
  position:absolute;top:50%;width:13px;height:13px;border-radius:50%;
  background:var(--orange);border:2px solid #fff;transform:translate(-50%,-50%);
  cursor:grab;left:0%;box-shadow:0 0 6px #fb923c80
}
#tl-handle:active{cursor:grabbing}
.tl-time{font-size:11px;color:var(--muted);white-space:nowrap;min-width:140px;text-align:right}
.tl-time .now{color:var(--text);font-weight:700}

#main{
  display:grid;
  grid-template-columns:1fr 1fr 280px 1fr 1fr;
  gap:1px;background:var(--border);
  flex:1;min-height:0
}

.panel{background:var(--bg1);overflow-y:auto;display:flex;flex-direction:column}
.phead{
  font-size:10px;letter-spacing:2px;color:var(--orange);
  padding:9px 14px 7px;border-bottom:1px solid var(--border);
  flex-shrink:0;display:flex;align-items:center;gap:7px
}
.phead-dot{width:6px;height:6px;border-radius:50%;background:var(--orange);flex-shrink:0}
.phead-c{color:var(--cyan)}
.phead-dot-c{background:var(--cyan)}
.psec{padding:10px 14px;border-bottom:1px solid var(--border)}
.psec-title{font-size:10px;color:var(--muted);letter-spacing:1px;margin-bottom:8px}
.dr{display:flex;justify-content:space-between;align-items:center;padding:3px 0;border-bottom:1px solid #1a253810}
.dr:last-child{border:none}
.dk{font-size:11px;color:var(--muted)}
.dv{font-size:13px;font-weight:600}
.dv-g{color:var(--green)}
.dv-c{color:var(--cyan)}
.dv-o{color:var(--orange)}
.dv-a{color:var(--amber)}
.dv-r{color:var(--red)}
.dv-d{color:var(--dim)}

.sg{margin-bottom:10px}
.sg-lbl{font-size:10px;color:var(--muted);letter-spacing:1px;display:flex;justify-content:space-between;margin-bottom:4px}
.sg-bg{height:6px;background:var(--border);border-radius:3px;overflow:hidden}
.sg-bar{height:6px;border-radius:3px;transition:width .1s,background .2s}
.sg-val{font-size:15px;font-weight:700;color:var(--text);margin-top:4px}

#adi-wrap{display:flex;justify-content:center;padding:10px 0 6px}
#adi{width:130px;height:130px}
.att-row{display:grid;grid-template-columns:1fr 1fr 1fr;gap:5px;margin-top:6px}
.att-cell{background:var(--bg);border:1px solid var(--border);border-radius:2px;padding:6px 5px;text-align:center}
.att-v{font-size:16px;font-weight:700;line-height:1}
.att-l{font-size:8px;color:var(--muted);letter-spacing:1px;margin-top:3px}

#hw-offline{
  display:flex;flex-direction:column;align-items:center;justify-content:center;
  height:100%;padding:24px;text-align:center;gap:10px
}
.hw-off-icon{font-size:32px;color:var(--border)}
.hw-off-title{font-size:12px;color:var(--muted);letter-spacing:1px}
.hw-off-sub{font-size:10px;color:var(--dim);line-height:1.7;max-width:170px}

.lq-bg{height:4px;background:var(--border);border-radius:2px;overflow:hidden;margin-top:4px}
.lq-bar{height:4px;border-radius:2px;transition:width .3s,background .3s}

#view{background:var(--bg);position:relative;overflow:hidden}
#c3{width:100%;height:100%;display:block}
.v-lbl{position:absolute;top:10px;left:12px;font-size:9px;color:#fb923c50;letter-spacing:2px;pointer-events:none}
.v-hint{position:absolute;bottom:10px;left:12px;font-size:9px;color:#ffffff18;pointer-events:none}
.v-phase{
  position:absolute;top:10px;right:12px;font-size:10px;color:var(--orange);
  letter-spacing:1px;background:#fb923c12;border:1px solid #fb923c35;
  padding:3px 9px;border-radius:2px;pointer-events:none
}
.v-legend{
  position:absolute;bottom:10px;right:12px;font-size:9px;
  display:flex;flex-direction:column;gap:4px;pointer-events:none
}
.v-leg-row{display:flex;align-items:center;gap:5px}
.v-leg-dot{width:10px;height:2px;border-radius:1px}

.motor-badge{
  position:absolute;bottom:36px;left:12px;
  font-size:10px;color:var(--orange);letter-spacing:1px;
  background:#fb923c12;border:1px solid #fb923c35;padding:3px 9px;border-radius:2px
}

#btm{
  height:340px;display:grid;
  grid-template-columns:repeat(6,1fr);
  gap:1px;background:var(--border);flex-shrink:0
}
.cp{background:var(--bg1);padding:10px 13px 6px;overflow:hidden;display:flex;flex-direction:column;min-height:0}
.ch-legend{display:flex;gap:12px;margin-bottom:4px;flex-shrink:0}
.ch-leg{display:flex;align-items:center;gap:4px;font-size:9px}
.ch-leg-dot{width:12px;height:2px;border-radius:1px}
.ct{font-size:10px;color:var(--muted);letter-spacing:1.5px;margin-bottom:5px;display:flex;justify-content:space-between;flex-shrink:0}
.ct-val{color:var(--orange);font-size:11px}
.ch-wrap{flex:1;position:relative;min-height:0;display:flex}
canvas.ch{width:100%;height:100%;display:block}
</style>
</head>
<body>

<div id="launch-screen">
  <div class="ls-logo">MONK·HIL</div>
  <div class="ls-sub">HARDWARE-IN-THE-LOOP GROUND STATION</div>
  <div class="ls-card">
    <div class="ls-section">MOTOR SELECTION</div>
    <div class="ls-motor-row">
      <select class="ls-select" id="motor-select" onchange="onMotorSelect()">
        <option value="">— Select Estes motor —</option>
        <optgroup label="Mini (13mm)">
          <option value="1/4A3-3T">Estes 1/4A3-3T</option>
          <option value="1/2A3-4T">Estes 1/2A3-4T</option>
          <option value="A3-4T">Estes A3-4T</option>
        </optgroup>
        <optgroup label="Standard (18mm)">
          <option value="A8-3">Estes A8-3</option>
          <option value="B4-4">Estes B4-4</option>
          <option value="B6-4">Estes B6-4</option>
          <option value="C6-3">Estes C6-3</option>
          <option value="C6-5">Estes C6-5</option>
        </optgroup>
        <optgroup label="24mm">
          <option value="D12-3">Estes D12-3</option>
          <option value="D12-5">Estes D12-5</option>
          <option value="E12-4">Estes E12-4</option>
          <option value="E12-6">Estes E12-6</option>
        </optgroup>
        <optgroup label="29mm (High Power)">
          <option value="F15-0" selected>Estes F15-0 ★</option>
          <option value="F15-4">Estes F15-4</option>
          <option value="F15-6">Estes F15-6</option>
          <option value="F15-8">Estes F15-8</option>
        </optgroup>
      </select>
      <div class="ls-motor-info" id="motor-info">
        <div class="ls-mi"><div class="ls-mi-v" id="mi-thrust">14.4 N</div><div class="ls-mi-l">AVG THRUST</div></div>
        <div class="ls-mi"><div class="ls-mi-v" id="mi-max">25.3 N</div><div class="ls-mi-l">MAX THRUST</div></div>
        <div class="ls-mi"><div class="ls-mi-v" id="mi-burn">3.5 s</div><div class="ls-mi-l">BURN TIME</div></div>
        <div class="ls-mi"><div class="ls-mi-v" id="mi-imp">49.6 Ns</div><div class="ls-mi-l">TOTAL IMPULSE</div></div>
      </div>
    </div>

    <hr class="ls-divider">
    <div class="ls-section">ROCKET PARAMETERS</div>
    <div class="ls-grid">
      <div class="ls-field">
        <div class="ls-label">MASS (kg)</div>
        <input class="ls-input" id="cfg-mass" type="number" value="2.5" step="0.1">
      </div>
      <div class="ls-field">
        <div class="ls-label">MOMENT ARM (m)</div>
        <input class="ls-input" id="cfg-arm" type="number" value="0.3" step="0.01">
      </div>
      <div class="ls-field">
        <div class="ls-label">DRAG COEFF (Cd)</div>
        <input class="ls-input" id="cfg-cd" type="number" value="0.4" step="0.01">
      </div>
      <div class="ls-field">
        <div class="ls-label">CROSS SECTION (m²)</div>
        <input class="ls-input" id="cfg-area" type="number" value="0.007" step="0.001">
      </div>
      <div class="ls-field">
        <div class="ls-label">SIM DURATION (s)</div>
        <input class="ls-input" id="cfg-dur" type="number" value="12" step="1">
      </div>
      <div class="ls-field">
        <div class="ls-label">COM PORT</div>
        <input class="ls-input" id="cfg-port" type="text" value="COM3">
      </div>
    </div>

    <button class="ls-launch-btn" onclick="launchSim()">▶  LAUNCH SIMULATION</button>
    <div class="ls-warning">Parameters are sent to the Python simulation on launch</div>
  </div>
</div>

<div id="dashboard">
  <div id="hdr">
    <span class="logo">MONK·HIL</span>
    <span class="pill pill-sim" id="sim-pill">● SIM ACTIVE</span>
    <span class="pill pill-hw-off" id="hw-pill">○ HW OFFLINE</span>
    <span class="pill pill-phase" id="phase-pill">BOOST</span>
    <span class="mtime" id="mtime">T+00:00.0</span>
    <div class="hstats">
      <div class="hs"><div class="hs-v" id="h-alt">0</div><div class="hs-l">ALT m</div></div>
      <div class="hs"><div class="hs-v" id="h-vz">0.0</div><div class="hs-l">Vz m/s</div></div>
      <div class="hs"><div class="hs-v" id="h-spd">0.0</div><div class="hs-l">SPD m/s</div></div>
      <div class="hs"><div class="hs-v" id="h-mach">0.000</div><div class="hs-l">MACH</div></div>
      <div class="hs"><div class="hs-v" id="h-gee">1.00</div><div class="hs-l">G-LOAD</div></div>
      <div class="hs"><div class="hs-v" id="h-hz">—</div><div class="hs-l">LOOP Hz</div></div>
    </div>
  </div>

  <div id="timeline">
    <button class="tl-btn live-on" id="tl-live-btn" onclick="goLive()">● LIVE</button>
    <div id="tl-track-wrap">
      <div id="tl-track">
        <div id="tl-fill"></div>
        <div id="tl-handle"></div>
      </div>
    </div>
    <div class="tl-time"><span class="now" id="tl-now">T+00:00.0</span> / <span id="tl-end">T+00:00.0</span></div>
  </div>

  <div id="main">
    <div class="panel">
      <div class="phead"><div class="phead-dot"></div>SIM TRUTH · ATTITUDE</div>
      <div class="psec">
        <div class="psec-title">ATTITUDE INDICATOR</div>
        <div id="adi-wrap"><canvas id="adi" width="130" height="130"></canvas></div>
        <div class="att-row">
          <div class="att-cell"><div class="att-v dv-g" id="s-pitch">0.0°</div><div class="att-l">PITCH</div></div>
          <div class="att-cell"><div class="att-v dv-g" id="s-roll">0.0°</div><div class="att-l">ROLL</div></div>
          <div class="att-cell"><div class="att-v dv-g" id="s-yaw">0.0°</div><div class="att-l">YAW</div></div>
        </div>
      </div>
      <div class="psec">
        <div class="psec-title">ANGULAR RATE · rad/s (TRUE)</div>
        <div class="dr"><span class="dk">ωx (pitch)</span><span class="dv dv-g" id="s-wx">0.0000</span></div>
        <div class="dr"><span class="dk">ωy (roll)</span><span class="dv dv-g" id="s-wy">0.0000</span></div>
        <div class="dr"><span class="dk">ωz (yaw)</span><span class="dv dv-g" id="s-wz">0.0000</span></div>
      </div>
      <div class="psec">
        <div class="psec-title">MOTOR STATE</div>
        <div class="dr"><span class="dk">Thrust</span><span class="dv dv-o" id="s-thrust">0.0 N</span></div>
        <div class="dr"><span class="dk">Burn remaining</span><span class="dv dv-a" id="s-burn">—</span></div>
        <div class="dr"><span class="dk">Phase</span><span class="dv dv-o" id="s-phase">BOOST</span></div>
      </div>
    </div>

    <div class="panel">
      <div class="phead"><div class="phead-dot"></div>SIM TRUTH · DYNAMICS</div>
      <div class="psec">
        <div class="psec-title">POSITION · m (XYZ)</div>
        <div class="dr"><span class="dk">X (east)</span><span class="dv dv-g" id="s-px">0.00</span></div>
        <div class="dr"><span class="dk">Y (north)</span><span class="dv dv-g" id="s-py">0.00</span></div>
        <div class="dr"><span class="dk">Z (up)</span><span class="dv dv-g" id="s-pz">0.00</span></div>
      </div>
      <div class="psec">
        <div class="psec-title">VELOCITY · m/s</div>
        <div class="dr"><span class="dk">Vx</span><span class="dv dv-g" id="s-vx">0.00</span></div>
        <div class="dr"><span class="dk">Vy</span><span class="dv dv-g" id="s-vy">0.00</span></div>
        <div class="dr"><span class="dk">Vz</span><span class="dv dv-g" id="s-vz">0.00</span></div>
        <div class="dr"><span class="dk">|V| speed</span><span class="dv dv-o" id="s-vmag">0.00</span></div>
      </div>
      <div class="psec">
        <div class="psec-title">TRUE ACCELERATION · m/s²</div>
        <div class="dr"><span class="dk">Ax</span><span class="dv dv-g" id="s-ax">0.000</span></div>
        <div class="dr"><span class="dk">Ay</span><span class="dv dv-g" id="s-ay">0.000</span></div>
        <div class="dr"><span class="dk">Az</span><span class="dv dv-g" id="s-az">-9.810</span></div>
      </div>
      <div class="psec">
        <div class="psec-title">AERODYNAMICS</div>
        <div class="dr"><span class="dk">Dynamic pressure</span><span class="dv dv-g" id="s-q">0.0 Pa</span></div>
        <div class="dr"><span class="dk">Drag force</span><span class="dv dv-g" id="s-drag">0.0 N</span></div>
        <div class="dr"><span class="dk">Mach</span><span class="dv dv-g" id="s-mach">0.000</span></div>
        <div class="dr"><span class="dk">G-load</span><span class="dv dv-o" id="s-gee">1.00</span></div>
      </div>
    </div>

    <div id="view">
      <canvas id="c3"></canvas>
      <div class="v-lbl">3D · TVC ROCKET</div>
      <div class="v-hint">DRAG · SCROLL</div>
      <div class="v-phase" id="v-phase">BOOST</div>
      <div class="motor-badge" id="motor-badge">F15-0</div>
      <div class="v-legend">
        <div class="v-leg-row"><div class="v-leg-dot" style="background:#34d399"></div><span style="font-size:9px;color:#6b7f96">SIM</span></div>
        <div class="v-leg-row"><div class="v-leg-dot" style="background:#38bdf8"></div><span style="font-size:9px;color:#6b7f96">HW</span></div>
      </div>
    </div>

    <div class="panel">
      <div class="phead"><div class="phead-dot"></div>SENSOR DATA · IMU / BARO</div>
      <div class="psec">
        <div class="psec-title">SYNTHETIC IMU · SENT TO HW</div>
        <div class="dr"><span class="dk">Ax (w/ noise)</span><span class="dv dv-g" id="imu-ax">0.000</span></div>
        <div class="dr"><span class="dk">Ay (w/ noise)</span><span class="dv dv-g" id="imu-ay">0.000</span></div>
        <div class="dr"><span class="dk">Az (w/ noise)</span><span class="dv dv-g" id="imu-az">9.810</span></div>
        <div class="dr"><span class="dk">Gx (w/ noise)</span><span class="dv dv-g" id="imu-gx">0.0000</span></div>
        <div class="dr"><span class="dk">Gy (w/ noise)</span><span class="dv dv-g" id="imu-gy">0.0000</span></div>
        <div class="dr"><span class="dk">Gz (w/ noise)</span><span class="dv dv-g" id="imu-gz">0.0000</span></div>
      </div>
      <div class="psec">
        <div class="psec-title">BAROMETER · SYNTHETIC</div>
        <div class="dr"><span class="dk">Baro altitude</span><span class="dv dv-g" id="imu-baro">0.0 m</span></div>
        <div class="dr"><span class="dk">True altitude</span><span class="dv dv-o" id="imu-true">0.0 m</span></div>
        <div class="dr"><span class="dk">Δ baro error</span><span class="dv dv-a" id="imu-derr">0.00 m</span></div>
      </div>
      <div class="psec">
        <div class="psec-title">UART OUTGOING</div>
        <div class="dr"><span class="dk">Packets sent</span><span class="dv dv-g" id="u-sent">0</span></div>
        <div class="dr"><span class="dk">Packet rate</span><span class="dv dv-g" id="u-rate">— Hz</span></div>
        <div class="dr"><span class="dk">Last packet</span><span class="dv dv-g" id="u-last">—</span></div>
      </div>
    </div>

    <div class="panel">
      <div class="phead phead-c"><div class="phead-dot phead-dot-c"></div>HW TELEMETRY · MONK</div>
      <div id="hw-offline-msg">
        <div id="hw-offline">
          <div class="hw-off-icon">⬡</div>
          <div class="hw-off-title">FLIGHT COMPUTER OFFLINE</div>
          <div class="hw-off-sub">Connect the MONK board via UART to view hardware telemetry</div>
        </div>
      </div>
      <div id="hw-data" style="display:none;flex-direction:column">
        <div class="psec">
          <div class="psec-title">ONBOARD IMU READINGS</div>
          <div class="dr"><span class="dk">Ax (hw raw)</span><span class="dv dv-c" id="h-ax">—</span></div>
          <div class="dr"><span class="dk">Ay (hw raw)</span><span class="dv dv-c" id="h-ay">—</span></div>
          <div class="dr"><span class="dk">Az (hw raw)</span><span class="dv dv-c" id="h-az">—</span></div>
          <div class="dr"><span class="dk">Gx (hw raw)</span><span class="dv dv-c" id="h-gx">—</span></div>
          <div class="dr"><span class="dk">Gy (hw raw)</span><span class="dv dv-c" id="h-gy">—</span></div>
          <div class="dr"><span class="dk">Gz (hw raw)</span><span class="dv dv-c" id="h-gz">—</span></div>
        </div>
        <div class="psec">
          <div class="psec-title">ONBOARD ESTIMATES</div>
          <div class="dr"><span class="dk">Pitch (est.)</span><span class="dv dv-c" id="h-epitch">—</span></div>
          <div class="dr"><span class="dk">Roll (est.)</span><span class="dv dv-c" id="h-eroll">—</span></div>
          <div class="dr"><span class="dk">Baro alt (est.)</span><span class="dv dv-c" id="h-baro">—</span></div>
          <div class="dr"><span class="dk">Δ pitch (sim−hw)</span><span class="dv dv-a" id="h-dpitch">—</span></div>
          <div class="dr"><span class="dk">Δ roll (sim−hw)</span><span class="dv dv-a" id="h-droll">—</span></div>
          <div class="dr"><span class="dk">Δ alt (sim−hw)</span><span class="dv dv-a" id="h-dalt">—</span></div>
        </div>
        <div class="psec">
          <div class="psec-title">TVC SERVO OUTPUT</div>
          <div class="sg">
            <div class="sg-lbl"><span>PITCH SERVO</span><span id="sg-l-deg">90°</span></div>
            <div class="sg-bg"><div class="sg-bar" id="sg-l" style="width:50%"></div></div>
            <div class="sg-val" id="sg-l-off">±0°</div>
          </div>
          <div class="sg">
            <div class="sg-lbl"><span>YAW SERVO</span><span id="sg-r-deg">90°</span></div>
            <div class="sg-bg"><div class="sg-bar" id="sg-r" style="width:50%"></div></div>
            <div class="sg-val" id="sg-r-off">±0°</div>
          </div>
        </div>
        <div class="psec">
          <div class="psec-title">UART LINK HEALTH</div>
          <div class="dr"><span class="dk">Packets recv</span><span class="dv dv-c" id="h-recv">0</span></div>
          <div class="dr"><span class="dk">Dropped</span><span class="dv" id="h-drop">0</span></div>
          <div class="dr"><span class="dk">Link quality</span><span class="dv dv-c" id="h-lq">—</span></div>
          <div class="lq-bg"><div class="lq-bar" id="lq-bar" style="width:0%"></div></div>
          <div class="dr" style="margin-top:5px"><span class="dk">HW loop Hz</span><span class="dv dv-o" id="h-hwHz">—</span></div>
        </div>
      </div>
    </div>
  </div>

  <div id="btm">
    <div class="cp">
      <div class="ch-legend">
        <div class="ch-leg"><div class="ch-leg-dot" style="background:#34d399"></div><span style="color:#34d399">SIM</span></div>
        <div class="ch-leg"><div class="ch-leg-dot" style="background:#38bdf8"></div><span style="color:#38bdf8">HW</span></div>
      </div>
      <div class="ct">ALTITUDE · m<span class="ct-val" id="cv-alt">0</span></div>
      <div class="ch-wrap"><canvas class="ch" id="ch-alt"></canvas></div>
    </div>
    <div class="cp">
      <div class="ch-legend">
        <div class="ch-leg"><div class="ch-leg-dot" style="background:#34d399"></div><span style="color:#34d399">SIM</span></div>
        <div class="ch-leg"><div class="ch-leg-dot" style="background:#38bdf8"></div><span style="color:#38bdf8">HW</span></div>
      </div>
      <div class="ct">PITCH · deg<span class="ct-val" id="cv-pitch">0.0</span></div>
      <div class="ch-wrap"><canvas class="ch" id="ch-pitch"></canvas></div>
    </div>
    <div class="cp">
      <div class="ch-legend">
        <div class="ch-leg"><div class="ch-leg-dot" style="background:#34d399"></div><span style="color:#34d399">SIM</span></div>
        <div class="ch-leg"><div class="ch-leg-dot" style="background:#38bdf8"></div><span style="color:#38bdf8">HW</span></div>
      </div>
      <div class="ct">ROLL · deg<span class="ct-val" id="cv-roll">0.0</span></div>
      <div class="ch-wrap"><canvas class="ch" id="ch-roll"></canvas></div>
    </div>
    <div class="cp">
      <div class="ch-legend">
        <div class="ch-leg"><div class="ch-leg-dot" style="background:#34d399"></div><span style="color:#34d399">SIM</span></div>
        <div class="ch-leg"><div class="ch-leg-dot" style="background:#38bdf8"></div><span style="color:#38bdf8">HW</span></div>
      </div>
      <div class="ct">GYRO X · rad/s<span class="ct-val" id="cv-gx">0.000</span></div>
      <div class="ch-wrap"><canvas class="ch" id="ch-gx"></canvas></div>
    </div>
    <div class="cp">
      <div class="ch-legend">
        <div class="ch-leg"><div class="ch-leg-dot" style="background:#fb923c"></div><span style="color:#fb923c">PITCH</span></div>
        <div class="ch-leg"><div class="ch-leg-dot" style="background:#fcd34d"></div><span style="color:#fcd34d">YAW</span></div>
      </div>
      <div class="ct">SERVO · deg offset<span class="ct-val" id="cv-srv">0</span></div>
      <div class="ch-wrap"><canvas class="ch" id="ch-srv"></canvas></div>
    </div>
    <div class="cp">
      <div class="ch-legend">
        <div class="ch-leg"><div class="ch-leg-dot" style="background:#fb923c"></div><span style="color:#fb923c">ERROR</span></div>
      </div>
      <div class="ct">PID ERROR · deg<span class="ct-val" id="cv-pid">0.0</span></div>
      <div class="ch-wrap"><canvas class="ch" id="ch-pid"></canvas></div>
    </div>
  </div>
</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
<script>
const $=id=>document.getElementById(id);

const MOTORS={
  '1/4A3-3T':{avg:3.0,max:8.5,burn:0.5,imp:0.6,dia:'13mm'},
  '1/2A3-4T':{avg:3.0,max:9.4,burn:0.9,imp:1.25,dia:'13mm'},
  'A3-4T':{avg:3.0,max:9.8,burn:0.5,imp:1.25,dia:'13mm'},
  'A8-3':{avg:8.0,max:15.6,burn:0.5,imp:2.5,dia:'18mm'},
  'B4-4':{avg:4.2,max:13.5,burn:1.1,imp:5.0,dia:'18mm'},
  'B6-4':{avg:6.0,max:12.6,burn:0.85,imp:5.0,dia:'18mm'},
  'C6-3':{avg:6.0,max:14.1,burn:1.9,imp:10.0,dia:'18mm'},
  'C6-5':{avg:6.0,max:14.1,burn:1.9,imp:10.0,dia:'18mm'},
  'D12-3':{avg:12.0,max:29.7,burn:1.6,imp:20.0,dia:'24mm'},
  'D12-5':{avg:12.0,max:29.7,burn:1.6,imp:20.0,dia:'24mm'},
  'E12-4':{avg:11.2,max:33.3,burn:2.4,imp:27.2,dia:'24mm'},
  'E12-6':{avg:11.2,max:33.3,burn:2.4,imp:27.2,dia:'24mm'},
  'F15-0':{avg:14.4,max:25.3,burn:3.5,imp:49.6,dia:'29mm'},
  'F15-4':{avg:14.4,max:25.3,burn:3.5,imp:49.6,dia:'29mm'},
  'F15-6':{avg:14.4,max:25.3,burn:3.5,imp:49.6,dia:'29mm'},
  'F15-8':{avg:14.4,max:25.3,burn:3.5,imp:49.6,dia:'29mm'},
};

let selectedMotor='F15-0';
onMotorSelect();

function onMotorSelect(){
  const sel=$('motor-select').value||'F15-0';
  selectedMotor=sel;
  const m=MOTORS[sel];
  if(!m)return;
  $('mi-thrust').textContent=m.avg+' N';
  $('mi-max').textContent=m.max+' N';
  $('mi-burn').textContent=m.burn+' s';
  $('mi-imp').textContent=m.imp+' Ns';
}

function launchSim(){
  const m=MOTORS[selectedMotor]||MOTORS['F15-0'];
  const cfg={
    motor:selectedMotor,
    thrust:m.avg,
    burn_time:m.burn,
    mass:parseFloat($('cfg-mass').value)||2.5,
    thrust_moment_arm:parseFloat($('cfg-arm').value)||0.3,
    Cd:parseFloat($('cfg-cd').value)||0.4,
    A:parseFloat($('cfg-area').value)||0.007,
    max_time:parseFloat($('cfg-dur').value)||12,
    uart_port:$('cfg-port').value||'COM3',
  };
  fetch('/launch',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(cfg)})
    .then(()=>{
      $('launch-screen').style.display='none';
      $('dashboard').style.display='flex';
      $('motor-badge').textContent=selectedMotor;
      startSSE();
    });
}

let renderer,scene,camera,rocket,simLine,hwLine,eGlow,eGlow2,glowMat,plumeMat;
const simPos=[],hwPos=[];
let camTh=0.55,camPh=0.38,camDist=18,isDrag=false,lmx=0,lmy=0;
const camTgt=new THREE.Vector3(0,5,0);

function initThree(){
  const canvas3=$('c3');
  renderer=new THREE.WebGLRenderer({canvas:canvas3,antialias:true});
  renderer.setPixelRatio(devicePixelRatio);
  scene=new THREE.Scene();
  scene.background=new THREE.Color(0x0f1520);
  scene.fog=new THREE.Fog(0x0f1520,100,400);
  camera=new THREE.PerspectiveCamera(45,1,0.1,1000);
  scene.add(new THREE.AmbientLight(0x0a1830,4));
  const sun=new THREE.DirectionalLight(0x3355aa,2.5);
  sun.position.set(10,30,10);sun.castShadow=true;scene.add(sun);
  eGlow=new THREE.PointLight(0xff6020,0,10);scene.add(eGlow);
  eGlow2=new THREE.PointLight(0xff9040,0,5);scene.add(eGlow2);
  scene.add(new THREE.GridHelper(80,40,0x1a2538,0x141d2b));
  const gnd=new THREE.Mesh(new THREE.PlaneGeometry(80,80),
    new THREE.MeshStandardMaterial({color:0x0a1018,roughness:1}));
  gnd.rotation.x=-Math.PI/2;gnd.position.y=-0.01;gnd.receiveShadow=true;scene.add(gnd);

  rocket=mkRocket();rocket.position.set(0,1,0);scene.add(rocket);

  const simGeo=new THREE.BufferGeometry();
  simLine=new THREE.Line(simGeo,new THREE.LineBasicMaterial({color:0x34d399,opacity:.6,transparent:true}));
  scene.add(simLine);
  const hwGeo=new THREE.BufferGeometry();
  hwLine=new THREE.Line(hwGeo,new THREE.LineBasicMaterial({color:0x38bdf8,opacity:.4,transparent:true}));
  scene.add(hwLine);

  const canvas3el=$('c3');
  canvas3el.addEventListener('mousedown',e=>{isDrag=true;lmx=e.clientX;lmy=e.clientY});
  window.addEventListener('mouseup',()=>isDrag=false);
  window.addEventListener('mousemove',e=>{
    if(!isDrag)return;
    camTh-=(e.clientX-lmx)*.007;camPh-=(e.clientY-lmy)*.005;
    camPh=Math.max(.05,Math.min(1.38,camPh));lmx=e.clientX;lmy=e.clientY;
  });
  canvas3el.addEventListener('wheel',e=>{camDist=Math.max(4,Math.min(100,camDist+e.deltaY*.06));},{passive:true});
  renderLoop();
}

function mkRocket(){
  const r=new THREE.Group();
  const bMat=new THREE.MeshStandardMaterial({color:0xc8d4e0,metalness:.65,roughness:.25});
  const nMat=new THREE.MeshStandardMaterial({color:0xfb923c,metalness:.3,roughness:.4});
  const fMat=new THREE.MeshStandardMaterial({color:0x374151,metalness:.6,roughness:.3});
  const blMat=new THREE.MeshStandardMaterial({color:0x999,metalness:.9,roughness:.15});
  const rMat=new THREE.MeshStandardMaterial({color:0xfb923c,metalness:.7,roughness:.2,emissive:0xfb923c,emissiveIntensity:.25});
  const body=new THREE.Mesh(new THREE.CylinderGeometry(.18,.21,2.4,20),bMat);
  body.castShadow=true;r.add(body);
  const nose=new THREE.Mesh(new THREE.ConeGeometry(.18,1.0,20),nMat);
  nose.position.y=1.7;nose.castShadow=true;r.add(nose);
  const ring1=new THREE.Mesh(new THREE.TorusGeometry(.2,.015,8,24),
    new THREE.MeshStandardMaterial({color:0xfb923c,metalness:.8,emissive:0xfb923c,emissiveIntensity:.15}));
  ring1.position.y=1.1;ring1.rotation.x=Math.PI/2;r.add(ring1);
  for(let i=0;i<4;i++){
    const fin=new THREE.Mesh(new THREE.BoxGeometry(.035,.55,.45),fMat);
    const a=(i/4)*Math.PI*2;
    fin.position.set(Math.cos(a)*.21,-0.9,Math.sin(a)*.21);
    fin.rotation.y=a;fin.castShadow=true;r.add(fin);
  }
  const bell=new THREE.Mesh(new THREE.CylinderGeometry(.13,.21,.26,16),blMat);
  bell.position.y=-1.33;r.add(bell);
  const gimbal=new THREE.Mesh(new THREE.TorusGeometry(.23,.022,10,24),rMat);
  gimbal.position.y=-1.1;gimbal.rotation.x=Math.PI/2;r.add(gimbal);
  glowMat=new THREE.MeshBasicMaterial({color:0xff6020,transparent:true,opacity:0});
  plumeMat=new THREE.MeshBasicMaterial({color:0xff9040,transparent:true,opacity:0});
  const glowM=new THREE.Mesh(new THREE.SphereGeometry(.32,8,8),glowMat);
  glowM.position.y=-1.55;r.add(glowM);
  const plumeM=new THREE.Mesh(new THREE.ConeGeometry(.16,.9,8),plumeMat);
  plumeM.position.y=-2.0;plumeM.rotation.x=Math.PI;r.add(plumeM);
  return r;
}

function resz(){
  const el=$('view');
  const w=el.clientWidth,h=el.clientHeight;
  const c=$('c3');
  if(c.width!==w||c.height!==h){
    renderer.setSize(w,h,false);
    camera.aspect=w/h;camera.updateProjectionMatrix();
  }
}

function drawADI(pitch,roll){
  const c=$('adi'),ctx=c.getContext('2d');
  const cx=65,cy=65,r=60;
  ctx.clearRect(0,0,130,130);
  ctx.save();
  ctx.beginPath();ctx.arc(cx,cy,r,0,Math.PI*2);ctx.clip();
  ctx.save();
  ctx.translate(cx,cy);ctx.rotate(-roll*Math.PI/180);
  const pp=pitch*1.6;
  ctx.fillStyle='#0c2550';ctx.fillRect(-r,-r+pp,r*2,r*2);
  ctx.fillStyle='#1a3a18';ctx.fillRect(-r,pp,r*2,r);
  ctx.strokeStyle='#ffffff35';ctx.lineWidth=1;
  ctx.beginPath();ctx.moveTo(-r,pp);ctx.lineTo(r,pp);ctx.stroke();
  for(let p=-20;p<=20;p+=10){
    if(p===0)continue;
    const y=pp+p*1.6;
    ctx.strokeStyle='#ffffff18';ctx.lineWidth=.5;
    ctx.beginPath();ctx.moveTo(-14,y);ctx.lineTo(14,y);ctx.stroke();
  }
  ctx.restore();
  ctx.strokeStyle='#fb923c60';ctx.lineWidth=2;
  ctx.beginPath();ctx.arc(cx,cy,r,0,Math.PI*2);ctx.stroke();
  ctx.restore();
  ctx.strokeStyle='#fb923c';ctx.lineWidth=2;ctx.lineCap='round';
  ctx.beginPath();ctx.moveTo(cx-22,cy);ctx.lineTo(cx-9,cy);ctx.stroke();
  ctx.beginPath();ctx.moveTo(cx+9,cy);ctx.lineTo(cx+22,cy);ctx.stroke();
  ctx.beginPath();ctx.moveTo(cx,cy-7);ctx.lineTo(cx,cy+7);ctx.stroke();
  ctx.fillStyle='#fb923c';ctx.beginPath();ctx.arc(cx,cy,2.5,0,Math.PI*2);ctx.fill();
}

const FULL_HISTORY=[];
const HIST_SAMPLE_EVERY=0.05;
let lastHistT=-1;

const HLEN=300;
const H={simAlt:[],hwAlt:[],simPitch:[],hwPitch:[],simRoll:[],hwRoll:[],simGx:[],hwGx:[],srvL:[],srvR:[],pid:[]};
function pushH(k,v){H[k].push(v);if(H[k].length>HLEN)H[k].shift();}

function rebuildRollingFromHistory(uptoIndex){
  for(const k of Object.keys(H)) H[k]=[];
  const start=Math.max(0,uptoIndex-HLEN+1);
  for(let i=start;i<=uptoIndex;i++){
    const d=FULL_HISTORY[i];
    if(!d)continue;
    pushH('simAlt',d.alt);pushH('simPitch',d.pitch);pushH('simRoll',d.roll);pushH('simGx',d.omega_x);
    pushH('srvL',d.servo_l-90);pushH('srvR',d.servo_r-90);pushH('pid',d.pid_err);
    if(d.hw_connected){pushH('hwAlt',d.baro);pushH('hwPitch',d.est_pitch);pushH('hwRoll',d.est_roll);pushH('hwGx',d.imu_gx);}
  }
}

function drawChart(id,series,colors,unitFmt){
  const c=$(id);if(!c)return;
  const wrap=c.parentElement;
  const W=wrap.clientWidth||200,H2=wrap.clientHeight||220;
  c.width=W;c.height=H2;
  const ctx=c.getContext('2d');
  ctx.fillStyle='#0f1520';ctx.fillRect(0,0,W,H2);

  const LABEL_W=40;
  const plotW=W-LABEL_W;

  const valid=series.filter(s=>s&&s.length>1);
  let mn=0,mx=1;
  if(valid.length){
    const all=valid.flat().filter(v=>isFinite(v));
    if(all.length){
      mn=Math.min(...all);mx=Math.max(...all);
      if(mx-mn<.01){mn-=.5;mx+=.5;}
      const pad=(mx-mn)*.1;mn-=pad;mx+=pad;
    }
  }

  ctx.strokeStyle='#1a2538';ctx.lineWidth=.5;
  ctx.fillStyle='#4b5a6e';ctx.font='9px Courier New';ctx.textAlign='right';
  const steps=4;
  for(let i=0;i<=steps;i++){
    const y=H2*i/steps;
    ctx.beginPath();ctx.moveTo(LABEL_W,y);ctx.lineTo(W,y);ctx.stroke();
    const val=mx-(mx-mn)*(i/steps);
    const txt=unitFmt?unitFmt(val):val.toFixed(1);
    ctx.fillText(txt,LABEL_W-5,y+3);
  }

  if(!valid.length)return;
  series.forEach((data,di)=>{
    if(!data||data.length<2)return;
    ctx.beginPath();ctx.strokeStyle=colors[di];ctx.lineWidth=1.5;
    data.forEach((v,i)=>{
      const x=LABEL_W+(i/(HLEN-1))*plotW,y=H2-((v-mn)/(mx-mn))*H2;
      i===0?ctx.moveTo(x,y):ctx.lineTo(x,y);
    });
    ctx.stroke();
  });
}

let D=null,hwConnected=false;
let isLive=true,scrubIndex=-1,maxT=0;
function startSSE(){
  const es=new EventSource('/data');
  es.onmessage=e=>{
    const d=JSON.parse(e.data);
    D=d;
    if(d.t - lastHistT >= HIST_SAMPLE_EVERY || FULL_HISTORY.length===0){
      FULL_HISTORY.push(d);
      lastHistT=d.t;
    }
    maxT=Math.max(maxT,d.t);
    if(isLive) renderFrame(d);
    updateTimelineUI();
  };
}

function fmtT(t){
  const s=Math.floor(t),ms=Math.floor((t%1)*10);
  const mm=Math.floor(s/60),ss=s%60;
  return `T+${String(mm).padStart(2,'0')}:${String(ss).padStart(2,'0')}.${ms}`;
}

function updateTimelineUI(){
  const curT = isLive ? maxT : (FULL_HISTORY[scrubIndex]?FULL_HISTORY[scrubIndex].t:0);
  $('tl-now').textContent=fmtT(curT);
  $('tl-end').textContent=fmtT(maxT);
  const pct = maxT>0 ? (curT/maxT)*100 : 0;
  $('tl-fill').style.width=pct+'%';
  $('tl-handle').style.left=pct+'%';
}

function goLive(){
  isLive=true;
  scrubIndex=-1;
  $('tl-live-btn').textContent='● LIVE';
  $('tl-live-btn').className='tl-btn live-on';
  $('sim-pill').textContent='● SIM ACTIVE';
  $('sim-pill').className='pill pill-sim';
  fetch('/resume',{method:'POST'}).catch(()=>{});
  if(D) renderFrame(D);
}

function scrubTo(clientX){
  const track=$('tl-track');
  const rect=track.getBoundingClientRect();
  let pct=(clientX-rect.left)/rect.width;
  pct=Math.max(0,Math.min(1,pct));
  const targetT=pct*maxT;

  let idx=0,best=Infinity;
  for(let i=0;i<FULL_HISTORY.length;i++){
    const diff=Math.abs(FULL_HISTORY[i].t-targetT);
    if(diff<best){best=diff;idx=i;}
  }
  scrubIndex=idx;
  isLive=false;
  $('tl-live-btn').textContent='▶ RESUME';
  $('tl-live-btn').className='tl-btn live-off';
  $('sim-pill').textContent='⏸ PAUSED';
  $('sim-pill').className='pill pill-paused';
  fetch('/pause',{method:'POST'}).catch(()=>{});

  const d=FULL_HISTORY[idx];
  if(d){
    rebuildRollingFromHistory(idx);
    renderFrame(d,true);
  }
  updateTimelineUI();
}

let scrubbing=false;
window.addEventListener('load',()=>{
  $('tl-track').addEventListener('mousedown',e=>{scrubbing=true;scrubTo(e.clientX);});
  window.addEventListener('mousemove',e=>{if(scrubbing)scrubTo(e.clientX);});
  window.addEventListener('mouseup',()=>scrubbing=false);
});

function setVal(id,v,cls){
  const el=$(id);if(!el)return;
  el.textContent=v;
  if(cls)el.className='dv '+cls;
}

function updateDOM(d){
  $('mtime').textContent=fmtT(d.t);
  $('h-alt').textContent=d.alt.toFixed(0);
  $('h-vz').textContent=d.vz.toFixed(1);
  $('h-spd').textContent=d.spd.toFixed(1);
  $('h-mach').textContent=(d.spd/343).toFixed(3);
  $('h-gee').textContent=(Math.abs(d.az)/9.81).toFixed(2);
  $('h-hz').textContent=d.loop_hz||'—';
  $('v-phase').textContent=d.phase;
  $('phase-pill').textContent=d.phase;

  const pc=Math.abs(d.pitch)>15?'dv-r':Math.abs(d.pitch)>7?'dv-a':'dv-g';
  $('s-pitch').textContent=d.pitch.toFixed(1)+'°';$('s-pitch').className='att-v '+pc;
  $('s-roll').textContent=d.roll.toFixed(1)+'°';
  $('s-yaw').textContent=d.yaw.toFixed(1)+'°';
  setVal('s-wx',d.omega_x.toFixed(4),'dv-g');
  setVal('s-wy',d.omega_y.toFixed(4),'dv-g');
  setVal('s-wz',d.omega_z.toFixed(4),'dv-g');
  setVal('s-thrust',d.thrust.toFixed(1)+' N','dv-o');
  $('s-burn').textContent=d.burning?d.burn_rem.toFixed(2)+'s':'BURNOUT';
  $('s-burn').className='dv '+(d.burning?'dv-a':'dv-d');
  setVal('s-phase',d.phase,'dv-o');
  setVal('s-px',d.pos_x.toFixed(2),'dv-g');
  setVal('s-py',d.pos_y.toFixed(2),'dv-g');
  setVal('s-pz',d.pos_z.toFixed(2),'dv-g');
  setVal('s-vx',d.vx.toFixed(2),'dv-g');
  setVal('s-vy',d.vy.toFixed(2),'dv-g');
  setVal('s-vz',d.vz.toFixed(2),'dv-g');
  setVal('s-vmag',d.spd.toFixed(2),'dv-o');
  setVal('s-ax',d.ax.toFixed(3),'dv-g');
  setVal('s-ay',d.ay.toFixed(3),'dv-g');
  setVal('s-az',d.az.toFixed(3),'dv-g');
  setVal('s-q',d.q.toFixed(1)+' Pa','dv-g');
  setVal('s-drag',d.drag.toFixed(1)+' N','dv-g');
  setVal('s-mach',(d.spd/343).toFixed(3),'dv-g');
  setVal('s-gee',(Math.abs(d.az)/9.81).toFixed(2),'dv-o');
  setVal('imu-ax',d.ax.toFixed(3),'dv-g');
  setVal('imu-ay',d.ay.toFixed(3),'dv-g');
  setVal('imu-az',d.az.toFixed(3),'dv-g');
  setVal('imu-gx',d.omega_x.toFixed(4),'dv-g');
  setVal('imu-gy',d.omega_y.toFixed(4),'dv-g');
  setVal('imu-gz',d.omega_z.toFixed(4),'dv-g');
  setVal('imu-baro',d.baro.toFixed(1)+' m','dv-g');
  setVal('imu-true',d.alt.toFixed(1)+' m','dv-o');
  const derr=d.alt-d.baro;
  $('imu-derr').textContent=(derr>=0?'+':'')+derr.toFixed(2)+' m';
  $('imu-derr').className='dv '+(Math.abs(derr)>2?'dv-a':'dv-g');
  setVal('u-sent',d.uart_sent,'dv-g');
  $('u-rate').textContent=(d.loop_hz||'—')+' Hz';
  $('u-last').textContent='$S,'+d.ax.toFixed(2)+','+d.ay.toFixed(2)+'...';

  const hwNow=d.hw_connected;
  if(hwNow!==hwConnected){
    hwConnected=hwNow;
    $('hw-pill').textContent=hwNow?'● HW CONNECTED':'○ HW OFFLINE';
    $('hw-pill').className='pill '+(hwNow?'pill-hw-on':'pill-hw-off');
    $('hw-offline-msg').style.display=hwNow?'none':'block';
    $('hw-data').style.display=hwNow?'flex':'none';
  }
  if(hwNow){
    setVal('h-ax',d.imu_ax.toFixed(3),'dv-c');
    setVal('h-ay',d.imu_ay.toFixed(3),'dv-c');
    setVal('h-az',d.imu_az.toFixed(3),'dv-c');
    setVal('h-gx',d.imu_gx.toFixed(4),'dv-c');
    setVal('h-gy',d.imu_gy.toFixed(4),'dv-c');
    setVal('h-gz',d.imu_gz.toFixed(4),'dv-c');
    setVal('h-epitch',d.est_pitch.toFixed(1)+'°','dv-c');
    setVal('h-eroll',d.est_roll.toFixed(1)+'°','dv-c');
    setVal('h-baro',d.baro.toFixed(1)+' m','dv-c');
    const dp=d.pitch-d.est_pitch,dr=d.roll-d.est_roll,da=d.alt-d.baro;
    $('h-dpitch').textContent=(dp>=0?'+':'')+dp.toFixed(2)+'°';
    $('h-dpitch').className='dv '+(Math.abs(dp)>2?'dv-a':'dv-c');
    $('h-droll').textContent=(dr>=0?'+':'')+dr.toFixed(2)+'°';
    $('h-droll').className='dv '+(Math.abs(dr)>2?'dv-a':'dv-c');
    $('h-dalt').textContent=(da>=0?'+':'')+da.toFixed(2)+' m';
    $('h-dalt').className='dv '+(Math.abs(da)>2?'dv-a':'dv-c');
    const slOff=d.servo_l-90,srOff=d.servo_r-90;
    $('sg-l-deg').textContent=d.servo_l+'°';
    $('sg-r-deg').textContent=d.servo_r+'°';
    $('sg-l').style.width=(d.servo_l/180*100)+'%';
    $('sg-r').style.width=(d.servo_r/180*100)+'%';
    $('sg-l').style.background=Math.abs(slOff)>7?'#f87171':'#fb923c';
    $('sg-r').style.background=Math.abs(srOff)>7?'#f87171':'#fb923c';
    $('sg-l-off').textContent=(slOff>=0?'+':'')+slOff+'°';
    $('sg-r-off').textContent=(srOff>=0?'+':'')+srOff+'°';
    const total=d.uart_sent||1;
    const lq=Math.round(((total-d.uart_dropped)/total)*100);
    setVal('h-recv',d.uart_recv,'dv-c');
    $('h-drop').textContent=d.uart_dropped;
    $('h-drop').className='dv '+(d.uart_dropped>5?'dv-a':'dv-c');
    $('h-lq').textContent=lq+'%';
    $('lq-bar').style.width=lq+'%';
    $('lq-bar').style.background=lq>85?'#38bdf8':lq>60?'#fcd34d':'#f87171';
    setVal('h-hwHz',d.hw_loop_hz||'—','dv-o');
  }

  $('cv-alt').textContent=d.alt.toFixed(0);
  $('cv-pitch').textContent=d.pitch.toFixed(1);
  $('cv-roll').textContent=d.roll.toFixed(1);
  $('cv-gx').textContent=d.omega_x.toFixed(3);
  $('cv-srv').textContent=(d.servo_l-90).toFixed(0);
  $('cv-pid').textContent=d.pid_err.toFixed(1);
  drawChart('ch-alt',[H.simAlt,hwNow?H.hwAlt:[]],['#34d399','#38bdf8'],v=>v.toFixed(0));
  drawChart('ch-pitch',[H.simPitch,hwNow?H.hwPitch:[]],['#34d399','#38bdf8'],v=>v.toFixed(1));
  drawChart('ch-roll',[H.simRoll,hwNow?H.hwRoll:[]],['#34d399','#38bdf8'],v=>v.toFixed(1));
  drawChart('ch-gx',[H.simGx,hwNow?H.hwGx:[]],['#34d399','#38bdf8'],v=>v.toFixed(2));
  drawChart('ch-srv',[H.srvL,H.srvR],['#fb923c','#fcd34d'],v=>v.toFixed(0));
  drawChart('ch-pid',[H.pid],['#fb923c'],v=>v.toFixed(1));
}

function renderFrame(d, fromScrub){
  const S=0.05;
  const vx=d.pos_x*S,vy=d.pos_z*S+1,vz=d.pos_y*S;
  rocket.position.set(vx,vy,vz);
  rocket.rotation.x=d.pitch*Math.PI/180;
  rocket.rotation.z=-d.roll*Math.PI/180;
  rocket.rotation.y=d.yaw*Math.PI/180;

  if(!fromScrub){
    simPos.push(vx,vy,vz);
    if(simPos.length>900)simPos.splice(0,3);
    simLine.geometry.setAttribute('position',new THREE.Float32BufferAttribute([...simPos],3));
    simLine.geometry.setDrawRange(0,simPos.length/3);
    if(d.hw_connected){
      hwPos.push(vx,vy+.02,vz);
      if(hwPos.length>900)hwPos.splice(0,3);
      hwLine.geometry.setAttribute('position',new THREE.Float32BufferAttribute([...hwPos],3));
      hwLine.geometry.setDrawRange(0,hwPos.length/3);
    }
    pushH('simAlt',d.alt);pushH('simPitch',d.pitch);pushH('simRoll',d.roll);pushH('simGx',d.omega_x);
    pushH('srvL',d.servo_l-90);pushH('srvR',d.servo_r-90);pushH('pid',d.pid_err);
    if(d.hw_connected){pushH('hwAlt',d.baro);pushH('hwPitch',d.est_pitch);pushH('hwRoll',d.est_roll);pushH('hwGx',d.imu_gx);}
  }

  const fl=d.burning?(0.55+Math.random()*.45):0;
  glowMat.opacity=fl*.85;plumeMat.opacity=fl*.65;
  eGlow.intensity=fl*7;eGlow2.intensity=fl*3;
  eGlow.position.copy(rocket.position);eGlow.position.y-=.35;
  eGlow2.position.copy(rocket.position);eGlow2.position.y-=.6;
  const tx=rocket.position.x,ty=rocket.position.y+2,tz=rocket.position.z;
  camTgt.lerp(new THREE.Vector3(tx,ty,tz),fromScrub?1:.04);

  updateDOM(d);
}

function renderLoop(){
  requestAnimationFrame(renderLoop);
  resz();
  camera.position.set(
    camTgt.x+camDist*Math.sin(camPh)*Math.sin(camTh),
    camTgt.y+camDist*Math.cos(camPh),
    camTgt.z+camDist*Math.sin(camPh)*Math.cos(camTh)
  );
  camera.lookAt(camTgt);
  renderer.render(scene,camera);
}

window.addEventListener('load',()=>{
  initThree();
  onMotorSelect();
  $('motor-select').value='F15-0';
  onMotorSelect();
});
</script>
</body>
</html>"""

class _State:
    def __init__(self):
        self._d={}
        self._cfg=None
        self._lock=threading.Lock()
        self._launched=threading.Event()
        self._paused=threading.Event()

    def set(self,d):
        with self._lock: self._d=d
    def get(self):
        with self._lock: return dict(self._d)
    def set_cfg(self,c):
        with self._lock: self._cfg=c
        self._launched.set()
    def get_cfg(self):
        with self._lock: return self._cfg
    def wait_for_launch(self,timeout=300):
        return self._launched.wait(timeout)
    def pause(self):
        self._paused.set()
    def resume(self):
        self._paused.clear()
    def is_paused(self):
        return self._paused.is_set()

_state=_State()

class _ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

class _Handler(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def do_GET(self):
        if self.path=='/':
            self.send_response(200)
            self.send_header('Content-Type','text/html')
            self.end_headers()
            self.wfile.write(HTML.encode())
        elif self.path=='/data':
            self.send_response(200)
            self.send_header('Content-Type','text/event-stream')
            self.send_header('Cache-Control','no-cache')
            self.send_header('Access-Control-Allow-Origin','*')
            self.end_headers()
            try:
                while True:
                    d=_state.get()
                    if d:
                        self.wfile.write(f"data:{json.dumps(d)}\n\n".encode())
                        self.wfile.flush()
                    time.sleep(0.033)
            except: pass
        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        if self.path=='/launch':
            length=int(self.headers.get('Content-Length',0))
            body=self.rfile.read(length)
            cfg=json.loads(body)
            _state.set_cfg(cfg)
            self.send_response(200)
            self.send_header('Content-Type','application/json')
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
        elif self.path=='/pause':
            _state.pause()
            self.send_response(200)
            self.send_header('Content-Type','application/json')
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
        elif self.path=='/resume':
            _state.resume()
            self.send_response(200)
            self.send_header('Content-Type','application/json')
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
        else:
            self.send_response(404); self.end_headers()

class Dashboard:
    def __init__(self,port=8765):
        self.port=port
        self._loop_times=[]
        self._server=_ThreadingHTTPServer(('localhost',port),_Handler)
        threading.Thread(target=self._server.serve_forever,daemon=True).start()

    def start(self):
        url=f'http://localhost:{self.port}'
        print(f'[Dashboard] Running at {url}')
        print(f'[Dashboard] Waiting for launch...')
        webbrowser.open(url)

    def wait_for_launch(self):
        _state.wait_for_launch()
        return _state.get_cfg()

    def is_paused(self):
        """Call this every loop iteration in main.py. While True, main.py
        should skip stepping physics/UART/time, but keep calling this
        (and ideally sleep briefly) so the loop can resume promptly."""
        return _state.is_paused()

    def update(self,t,physics,servo_left,servo_right,
               accel,gyro,altitude,
               sent,received,dropped,
               hw_connected=False,
               est_pitch=0.0,est_roll=0.0,
               hw_loop_hz=0):
        import numpy as np
        roll,pitch,yaw=physics.get_attitude()
        spd=float(np.linalg.norm(physics.vel))
        vx,vy,vz=physics.vel
        self._loop_times.append(time.time())
        if len(self._loop_times)>50: self._loop_times.pop(0)
        if len(self._loop_times)>1:
            dts=[self._loop_times[i]-self._loop_times[i-1] for i in range(1,len(self._loop_times))]
            avg=sum(dts)/len(dts)
            hz=round(1/avg) if avg>0 else 0
        else: hz=0
        from config import CONFIG
        burn_time=CONFIG.get('burn_time',3.5)
        burning=t<burn_time
        burn_rem=max(0,burn_time-t)
        if burning:       phase='BOOST'
        elif vy>0:        phase='COAST'
        elif physics.pos[2]>1: phase='DESCENT'
        else:             phase='LANDED'
        thrust_now=CONFIG.get('thrust',14.4) if burning else 0.0
        rho=1.225; Cd=CONFIG.get('Cd',.4); A=CONFIG.get('A',.007)
        drag=0.5*rho*Cd*A*spd**2
        q=0.5*rho*spd**2
        pid_err=float(-pitch*0.8)
        _state.set({
            't':round(t,2),'alt':float(physics.pos[2]),
            'pos_x':float(physics.pos[0]),'pos_y':float(physics.pos[1]),'pos_z':float(physics.pos[2]),
            'vx':float(vx),'vy':float(vy),'vz':float(vz),'spd':spd,
            'pitch':float(pitch),'roll':float(roll),'yaw':float(yaw),
            'ax':float(accel[0]),'ay':float(accel[1]),'az':float(accel[2]),
            'omega_x':float(physics.omega[0]),'omega_y':float(physics.omega[1]),'omega_z':float(physics.omega[2]),
            'thrust':thrust_now,'burning':burning,'burn_rem':burn_rem,
            'q':float(q),'drag':float(drag),'phase':phase,
            'servo_l':int(servo_left),'servo_r':int(servo_right),
            'imu_ax':float(accel[0]),'imu_ay':float(accel[1]),'imu_az':float(accel[2]),
            'imu_gx':float(gyro[0]),'imu_gy':float(gyro[1]),'imu_gz':float(gyro[2]),
            'baro':float(altitude),'est_pitch':float(est_pitch),'est_roll':float(est_roll),
            'uart_sent':sent,'uart_recv':received,'uart_dropped':dropped,
            'hw_connected':hw_connected,'hw_loop_hz':hw_loop_hz,'loop_hz':hz,'pid_err':pid_err,
        })

    def save(self,path='logs/last_flight.png'):
        print(f'[Dashboard] Session ended.')
