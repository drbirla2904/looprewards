/* OFFLet v2 core: DOM helper, API client, state, router, layout, auth, shared components, account, counter screen. */
(function (FX) {
  'use strict';
  const t = FX.t;
  const S = FX.S = { token: localStorage.t || '', role: localStorage.r || '', user: null, shops: [], biz: null, sub: null, nav: 0, unread: 0, pending: 0 };
  FX.routes = { customer: {}, owner: {}, staff: {}, vendor: {} };

  /* ---------------- DOM ---------------- */
  function put(el, kids) {
    for (const k of kids) {
      if (k == null || k === false || k === true) continue;
      if (Array.isArray(k)) put(el, k);
      else if (k.nodeType) el.appendChild(k);
      else el.appendChild(document.createTextNode(String(k)));
    }
  }
  function h(tag, props, ...kids) {
    if (props != null && (typeof props !== 'object' || props.nodeType || Array.isArray(props))) { kids.unshift(props); props = null; }
    const parts = String(tag).split(/(?=[.#])/);
    const name = parts[0] && !/^[.#]/.test(parts[0]) ? parts.shift() : 'div';
    const el = document.createElement(name);
    for (const p of parts) { if (p[0] === '.') el.classList.add(p.slice(1)); else el.id = p.slice(1); }
    let late = null;
    if (props) for (const [k, v] of Object.entries(props)) {
      if (v == null || v === false) continue;
      if (k === 'class') el.classList.add(...String(v).split(' ').filter(Boolean));
      else if (k === 'style') { if (typeof v === 'string') el.style.cssText = v; else for (const [a, b] of Object.entries(v)) a.startsWith('--') ? el.style.setProperty(a, b) : (el.style[a] = b); }
      else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2).toLowerCase(), v);
      else if (k === 'value') late = v;
      else if (k === 'checked' || k === 'disabled' || k === 'selected' || k === 'hidden') el[k] = v;
      else el.setAttribute(k, v === true ? '' : v);
    }
    put(el, kids);
    if (late != null) el.value = late;
    return el;
  }
  FX.h = h;
  const $ = s => document.querySelector(s);
  const ICONS = {
    home: '<path d="m3 11 9-7 9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>',
    users: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c.6-3.6 3-5.5 6.5-5.5s5.9 1.9 6.5 5.5M16 4.8a3.5 3.5 0 0 1 0 6.4M18 14.8c2 .6 3.2 2.3 3.5 5.2"/>',
    gift: '<rect x="3" y="8" width="18" height="4" rx="1"/><path d="M12 8v13M5 12v8h14v-8M12 8c-1-4-6-4-5-1 .5 1.500 3 1 5 1zm0 0c1-4 6-4 5-1-.5 1.500-3 1-5 1z"/>',
    cal: '<rect x="3.5" y="5" width="17" height="15" rx="2"/><path d="M8 3v4M16 3v4M3.500 10h17"/>',
    mega: '<path d="M3 11v2a1 1 0 0 0 1 1h3l8 4V6L7 10H4a1 1 0 0 0-1 1zM18.500 9a4 4 0 0 1 0 6"/>',
    chart: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
    shop: '<path d="M3 10v10h18V10M2.500 10 4.500 4h15l2 6M9 20v-6h6v6M2.500 10a3 3 0 0 0 6 0 3 3 0 0 0 6 0 3 3 0 0 0 6 0"/>',
    card: '<rect x="2.500" y="5" width="19" height="14" rx="2"/><path d="M2.500 10h19M6 15h4"/>',
    user: '<circle cx="12" cy="8" r="4"/><path d="M4 21c.8-4.200 4-6 8-6s7.200 1.800 8 6"/>',
    bell: '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 8-3 9.500h18C21 16 18 15 18 8M10 21h4"/>',
    check: '<path d="m5 12.500 4.500 4.500L19 7"/>',
    more: '<circle cx="5" cy="12" r="1.500"/><circle cx="12" cy="12" r="1.500"/><circle cx="19" cy="12" r="1.500"/>',
    star: '<path d="m12 3 2.700 5.600 6.100.8-4.500 4.200 1.100 6.100L12 16.800 6.600 19.700l1.100-6.100L3.200 9.400l6.100-.8z"/>',
    scan: '<path d="M4 8V5a1 1 0 0 1 1-1h3M16 4h3a1 1 0 0 1 1 1v3M20 16v3a1 1 0 0 1-1 1h-3M8 20H5a1 1 0 0 1-1-1v-3M4 12h16"/>',
    pie: '<path d="M12 3v9h9a9 9 0 1 1-9-9z"/>',
    out: '<path d="M10 4H5a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1h5M15 8l4 4-4 4M19 12H9"/>'
  };
  const ico = n => { const s = h('span'); s.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true">' + (ICONS[n] || '') + '</svg>'; return s.firstChild; };
  FX.ico = ico;

  /* ---------------- formatting ---------------- */
  const loc = () => (FX.lang === 'hi' ? 'hi-IN' : 'en-IN');
  const rupee = n => '₹' + Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 });
  const fmtDate = d => (d ? new Date(d).toLocaleDateString(loc(), { day: 'numeric', month: 'short' }) : '');
  const fmtDT = d => (d ? new Date(d).toLocaleString(loc(), { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' }) : '');
  const num = v => { const n = Number(v); return Number.isInteger(n) ? String(n) : String(+n.toFixed(2)); };
  function ago(d) {
    if (!d) return t('Never');
    const days = Math.floor((Date.now() - new Date(d).getTime()) / 864e5);
    if (days <= 0) return t('Today');
    if (days === 1) return t('Yesterday');
    if (days < 14) return t('{n} days ago', { n: days });
    if (days < 60) return t('{n} weeks ago', { n: Math.floor(days / 7) });
    return t('{n} months ago', { n: Math.floor(days / 30) });
  }
  const until = d => { const days = Math.ceil((new Date(d).getTime() - Date.now()) / 864e5); return days <= 0 ? t('Expires today') : days === 1 ? t('Expires tomorrow') : t('Expires in {n} days', { n: days }); };
  const fmtVal = (type, v) => (type === 'amount' ? rupee(v) : num(v));
  const isLight = hex => { const m = /^#?([0-9a-f]{6})$/i.exec(hex || ''); if (!m) return false; const n = parseInt(m[1], 16); return (0.299 * (n >> 16) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255)) / 255 > 0.62; };
  const shopVars = c => ({ '--shop': c || '#5e35b1', '--shop-ink': isLight(c) ? '#15192b' : '#fff' });
  const initial = s => (String(s || '?').trim()[0] || '?').toUpperCase();
  Object.assign(FX, { rupee, fmtDate, fmtDT, num, ago, until, fmtVal, shopVars, initial });

  /* ---------------- API ---------------- */
  function errText(j) {
    if (!j) return '';
    if (typeof j === 'string') return j;
    if (Array.isArray(j)) return j.map(errText).join(' ');
    if (j.detail) return errText(j.detail);
    return Object.entries(j).map(([k, v]) => (k === 'non_field_errors' ? '' : k + ': ') + errText(v)).join(' ');
  }
  async function api(path, method, body) {
    const headers = {};
    if (S.token) headers.Authorization = 'Token ' + S.token;
    let data;
    if (body instanceof FormData) data = body;
    else if (body !== undefined) { headers['Content-Type'] = 'application/json'; data = JSON.stringify(body); }
    const requestMethod = method || 'GET';
    const url = new URL('/api/' + path, location.origin);
    if (requestMethod.toUpperCase() === 'GET') url.searchParams.set('_offlet', Date.now().toString());
    let r;
    try { r = await fetch(url, { method: requestMethod, headers, body: data, cache: 'no-store' }); }
    catch (e) { throw new Error(t('No internet connection. Please try again.')); }
    if (r.status === 204) return null;
    let j = null;
    try { j = await r.json(); } catch (e) { /* non-JSON */ }
    if (r.status === 401 && S.token) { FX.signOut(); throw new Error(t('Please log in again.')); }
    if (!r.ok) throw new Error(FX.tr(errText(j)) || t('Something went wrong. Please try again.'));
    return j;
  }
  FX.api = api;

  let razorpayLoad = null;
  FX.loadRazorpay = function () {
    if (window.Razorpay) return Promise.resolve();
    if (!razorpayLoad) {
      razorpayLoad = new Promise((resolve, reject) => {
        const fail = () => {
          razorpayLoad = null;
          reject(new Error(t('Could not load the payment window. Check your connection.')));
        };
        const script = h('script', {
          src: 'https://checkout.razorpay.com/v1/checkout.js',
          onload: () => window.Razorpay ? resolve() : fail(),
          onerror: fail
        });
        document.head.appendChild(script);
      });
    }
    return razorpayLoad;
  };

  /* ---------------- overlays ---------------- */
  function toast(msg, bad, action) {
    const el = h('div.toast' + (bad ? '.bad' : ''), { role: bad ? 'alert' : 'status' },
      h('span.toast-mark', { 'aria-hidden': 'true' }, bad ? '!' : '✓'),
      h('span.toast-message', msg),
      action ? h('button.toast-action', { onclick: () => { el.remove(); action.fn(); } }, action.label) : null);
    $('#toasts').appendChild(el);
    setTimeout(() => el.remove(), action ? 6500 : 4200);
    return el;
  }
  function modal(title, body, opts) {
    opts = opts || {};
    const d = h('dialog' + (opts.drawer ? '.drawer' : '') + (opts.cls ? '.' + opts.cls : ''), { 'aria-label': title, style: opts.style || null });
    const close = () => { if (d.open) d.close(); d.remove(); };
    d.addEventListener('close', () => d.remove());
    d.addEventListener('click', e => { if (e.target === d) close(); });
    d.appendChild(h('div.in', h('div.hd', h('h2', title), h('button.iconbtn', { type: 'button', 'aria-label': t('Close'), onclick: close }, '✕')), body));
    document.body.appendChild(d);
    d.showModal();
    return { el: d, close };
  }
  function shopQRTarget(raw) {
    const value = String(raw || '').trim();
    let code, params = new URLSearchParams();
    if (/^[a-z0-9]{6}$/i.test(value)) {
      code = value.toLowerCase();
    } else {
      let url;
      try { url = new URL(value, location.origin); } catch (e) { return null; }
      const match = /^\/b\/([a-z0-9]{6})\/?$/i.exec(url.pathname);
      if (!match) return null;
      code = match[1].toLowerCase();
      for (const key of ['c', 'ref', 'tab']) {
        const param = url.searchParams.get(key);
        if (param && (key !== 'tab' || ['earn', 'rewards', 'book', 'history', 'invite', 'spin'].includes(param))) {
          params.set(key, param);
        }
      }
    }
    return '/b/' + encodeURIComponent(code) + '/' + (params.size ? '?' + params.toString() : '');
  }
  function scanShopQR() {
    const video = h('video.scan-video', { autoplay: true, playsinline: true, muted: true, 'aria-label': t('Camera view') });
    const camera = h('div.scan-camera', video);
    const status = h('p.scan-status', { role: 'status' }, t('Starting camera…'));
    const code = h('input', { type: 'text', inputmode: 'text', maxlength: 6, autocomplete: 'off', autocapitalize: 'characters', placeholder: t('6-character shop code'), 'aria-label': t('6-character shop code') });
    const codeError = h('p.scan-error', { role: 'alert', hidden: true });
    const openCode = () => {
      const target = shopQRTarget(code.value);
      if (!target) {
        codeError.textContent = t('Enter a valid 6-character shop code.');
        codeError.hidden = false;
        return;
      }
      stopCamera();
      location.href = target;
    };
    const manual = h('form.scan-manual', { onsubmit: e => { e.preventDefault(); openCode(); } },
      h('label', t('Or enter shop code'), code), codeError,
      h('button.btn.block', { type: 'submit' }, t('Open shop')));
    const m = modal(t('Scan shop QR'), h('div.stack', camera, status, manual), { cls: 'scan-modal' });
    let stream = null, frame = 0, checking = false, stopped = false;
    function stopCamera() {
      stopped = true;
      if (frame) cancelAnimationFrame(frame);
      if (stream) stream.getTracks().forEach(track => track.stop());
      video.srcObject = null;
    }
    m.el.addEventListener('close', stopCamera, { once: true });
    const Detector = window.BarcodeDetector;
    if (!window.isSecureContext || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      camera.hidden = true;
      status.textContent = t('Camera scanning is unavailable here. Enter the shop code instead.');
      return;
    }
    if (!Detector) {
      camera.hidden = true;
      status.textContent = t('QR scanning is not supported in this browser. Enter the shop code instead.');
      return;
    }
    let detector;
    try { detector = new Detector({ formats: ['qr_code'] }); }
    catch (e) {
      camera.hidden = true;
      status.textContent = t('QR scanning is not supported in this browser. Enter the shop code instead.');
      return;
    }
    navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' } }, audio: false })
      .then(async cameraStream => {
        if (stopped) { cameraStream.getTracks().forEach(track => track.stop()); return; }
        stream = cameraStream;
        video.srcObject = stream;
        await video.play();
        status.textContent = t('Point your camera at a shop QR code.');
        const scanFrame = async () => {
          if (stopped || checking || !m.el.open) return;
          checking = true;
          try {
            const results = await detector.detect(video);
            for (const result of results) {
              const target = shopQRTarget(result.rawValue);
              if (!target) {
                status.textContent = t('That QR code is not a shop QR code. Keep scanning or enter the shop code.');
                continue;
              }
              stopCamera();
              m.close();
              location.href = target;
              return;
            }
          } catch (e) {
            stopCamera();
            status.textContent = t('Could not read the QR code. Enter the shop code instead.');
            return;
          } finally {
            checking = false;
          }
          if (!stopped && m.el.open) frame = requestAnimationFrame(scanFrame);
        };
        frame = requestAnimationFrame(scanFrame);
      })
      .catch(() => {
        stopCamera();
        camera.hidden = true;
        status.textContent = t('Camera access was unavailable. Check permission or enter the shop code.');
      });
  }
  FX.scanShopQR = scanShopQR;
  function confirmBox(msg, okLabel, danger) {
    return new Promise(res => {
      const m = modal(t('Please confirm'), h('div.stack', h('p', msg), h('div.row', { style: 'justify-content:flex-end' },
        h('button.btn.ghost', { onclick: () => { m.close(); res(false); } }, t('Cancel')),
        h('button.btn' + (danger ? '.danger' : ''), { onclick: () => { m.close(); res(true); } }, okLabel || t('Confirm')))));
      m.el.addEventListener('close', () => res(false));
    });
  }
  async function busy(btn, fn) {
    if (btn.disabled) return;
    btn.disabled = true;
    try { return await fn(); } catch (e) { toast(e.message, true); } finally { btn.disabled = false; }
  }
  Object.assign(FX, { toast, modal, confirmBox, busy });

  /* ---------------- components ---------------- */
  const field = (label, input, hint) => h('label.field', h('span', t(label)), input, hint ? h('small', t(hint)) : null);
  const inp = (props) => h('input', Object.assign({ placeholder: props && props.ph ? t(props.ph) : null }, props, { ph: null }));
  const sel = (opts, value, props) => h('select', Object.assign({ value }, props), opts.map(o => h('option', { value: o[0], selected: String(o[0]) === String(value) }, t(o[1]))));
  const pill = (txt, kind) => h('span.pill' + (kind ? '.' + kind : ''), txt);
  const empty = (title, sub, action) => h('div.empty', h('b', t(title)), sub ? h('p', t(sub)) : null, action || null);
  const kpi = (label, value, note) => h('div.kpi', h('div.l', t(label)), h('div.v', value), note ? h('div.d', note) : null);
  const avatar = (name, img) => h('div.avatar', img ? h('img', { src: img, alt: '' }) : initial(name));
  const chips = (items, current, onPick) => h('div.chips', items.map(([k, label, n]) => h('button.chip', { type: 'button', 'aria-pressed': String(k === current), onclick: () => onPick(k) }, t(label), n != null ? h('b', n) : null)));
  const tierPill = tier => pill(t(tier === 'gold' ? 'Gold' : tier === 'silver' ? 'Silver' : 'Member'), tier === 'gold' || tier === 'silver' ? tier : '');
  const stars = (n, onPick) => {
    if (!onPick) return h('span.stars.ro', '★'.repeat(Math.round(n)) + '☆'.repeat(5 - Math.round(n)));
    const wrap = h('div.stars'); let v = 0;
    const paint = () => [...wrap.children].forEach((b, i) => b.classList.toggle('on', i < v));
    for (let i = 1; i <= 5; i++) wrap.appendChild(h('button', { type: 'button', 'aria-label': i + ' / 5', onclick: () => { v = i; paint(); onPick(i); } }, '★'));
    return wrap;
  };
  function stampRow(cur, target, type, fresh) {
    const n = Math.floor(Number(target));
    if (type === 'amount' || n > 12 || n < 1) return null;
    const have = Math.min(n, Math.floor(Number(cur)));
    const row = h('div.stamps', { role: 'img', 'aria-label': have + ' / ' + n });
    for (let i = 0; i < n; i++) {
      const last = i === n - 1;
      row.appendChild(h('div.stamp' + (i < have ? '.on' : '') + (last ? '.gift' : '') + (fresh && i === have - 1 ? '.pop' : ''), last && i >= have ? h('span', '🎁') : i < have ? h('span', '✓') : null));
    }
    return row;
  }
  function barChart(series, key, altKey) {
    const w = 600, hh = 150, max = Math.max(1, ...series.map(s => s[key])), bw = w / series.length;
    const ns = 'http://www.w3.org/2000/svg', svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', `0 0 ${w} ${hh + 16}`); svg.setAttribute('class', 'chart'); svg.setAttribute('preserveAspectRatio', 'none'); svg.setAttribute('role', 'img');
    series.forEach((s, i) => {
      const bh = Math.max(s[key] ? 3 : 0, (s[key] / max) * hh);
      const r = document.createElementNS(ns, 'rect');
      r.setAttribute('x', i * bw + 1); r.setAttribute('width', Math.max(1, bw - 3)); r.setAttribute('y', hh - bh); r.setAttribute('height', bh);
      const ti = document.createElementNS(ns, 'title'); ti.textContent = fmtDate(s.date) + ': ' + s[key]; r.appendChild(ti);
      svg.appendChild(r);
      if (i % Math.ceil(series.length / 6) === 0) { const tx = document.createElementNS(ns, 'text'); tx.setAttribute('x', i * bw); tx.setAttribute('y', hh + 13); tx.textContent = fmtDate(s.date); svg.appendChild(tx); }
    });
    return svg;
  }
  const hbars = (rows) => { const max = Math.max(1, ...rows.map(r => r[1])); return h('div', rows.map(([l, v]) => h('div.hbar', h('span', l), h('div.t', h('i', { style: { width: (100 * v / max) + '%' } })), h('b.num', v)))); };
  const copy = async (txt) => { try { await navigator.clipboard.writeText(txt); } catch (e) { const a = h('textarea', { value: txt }); document.body.appendChild(a); a.select(); document.execCommand('copy'); a.remove(); } toast(t('Copied')); };
  const share = (text, url) => { if (navigator.share) navigator.share({ text, url }).catch(() => {}); else window.open('https://wa.me/?text=' + encodeURIComponent(text + ' ' + url), '_blank', 'noopener'); };
  const locate = (options = {}) => new Promise((resolve, reject) => {
    if (!window.isSecureContext) return reject(new Error(t('Location detection requires a secure HTTPS connection.')));
    if (!navigator.geolocation) return reject(new Error(t('This device or browser does not support location detection.')));
    navigator.geolocation.getCurrentPosition(resolve, error => {
      const message = error.code === 1 ? 'Location access was denied. Allow it in your browser settings and try again.' :
        error.code === 2 ? 'Your device could not determine the location. Check its location services and try again.' :
          error.code === 3 ? 'Location request timed out. Check that device location is enabled and try again.' :
            'Could not detect your location. Please try again.';
      reject(new Error(t(message)));
    }, Object.assign({ enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }, options));
  });
  const getPos = () => locate({ enableHighAccuracy: false, timeout: 4000, maximumAge: 60000 }).then(p => p.coords).catch(() => null);
  Object.assign(FX, { field, inp, sel, pill, empty, kpi, avatar, chips, tierPill, stars, stampRow, barChart, hbars, copy, share, getPos, locate });

  /* ---------------- motion + delight ---------------- */
  FX.haptic = p => { try { if (navigator.vibrate) navigator.vibrate(p || 12); } catch (e) { /* unsupported */ } };
  const calm = () => window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
  FX.confetti = function (n) {
    if (calm()) return;
    const c = h('canvas.confetti', { 'aria-hidden': 'true' }); document.body.appendChild(c);
    const ctx = c.getContext('2d'), dpr = Math.min(2, window.devicePixelRatio || 1);
    c.width = innerWidth * dpr; c.height = innerHeight * dpr;
    const cols = ['#ffb020', '#5e35b1', '#3b5bdb', '#d3443b', '#1b8a5a', '#ffffff'];
    const ps = Array.from({ length: n || 100 }, () => ({ x: innerWidth / 2, y: innerHeight * 0.42, vx: (Math.random() - 0.5) * 15, vy: -Math.random() * 13 - 4,
      s: Math.random() * 7 + 4, r: Math.random() * 6, vr: (Math.random() - 0.5) * 0.4, c: cols[(Math.random() * cols.length) | 0] }));
    let f = 0;
    (function tick() {
      ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, c.width, c.height); ctx.scale(dpr, dpr);
      ps.forEach(p => { p.vy += 0.35; p.x += p.vx; p.y += p.vy; p.r += p.vr; ctx.save(); ctx.translate(p.x, p.y); ctx.rotate(p.r); ctx.fillStyle = p.c; ctx.fillRect(-p.s / 2, -p.s / 2, p.s, p.s * 0.6); ctx.restore(); });
      if (++f < 160) requestAnimationFrame(tick); else c.remove();
    })();
  };
  /* Compact, non-blocking reward moment. actions = [[label, fn, 'ghost'?]] */
  FX.celebrate = function (o) {
    FX.haptic([18, 40, 18]); FX.confetti(o.big ? 160 : 90);
    const previousFocus = document.activeElement;
    const close = () => {
      document.removeEventListener('keydown', onKeydown);
      el.remove();
      if (previousFocus && previousFocus.isConnected && typeof previousFocus.focus === 'function') previousFocus.focus();
    };
    const onKeydown = event => { if (event.key === 'Escape') close(); };
    const el = h('div.celebrate', { role: 'dialog', 'aria-label': o.title, tabindex: '-1' },
      h('div.box', h('div.badge' + (o.ok ? '.ok' : ''), o.icon || '🎉'), h('h2', o.title), o.text ? h('p', o.text) : null, o.body || null,
        (o.actions || []).map(([label, fn, kind]) => h('button.btn.block' + (kind ? '.' + kind : ''), { onclick: () => { close(); if (fn) fn(); } }, label)),
        h('button.btn.ghost.block', { onclick: close }, t('Close'))));
    document.body.appendChild(el);
    el.focus();
    document.addEventListener('keydown', onKeydown);
    return { close };
  };
  FX.ring = function (pct, mid, sub, size) {
    const r = 40, C = 2 * Math.PI * r, wrap = h('div.ring-wrap', { style: { '--sz': (size || 92) + 'px' }, role: 'img', 'aria-label': Math.round(pct) + '%' });
    wrap.innerHTML = '<svg viewBox="0 0 100 100" aria-hidden="true"><circle class="bg" cx="50" cy="50" r="' + r + '"/><circle class="fg" cx="50" cy="50" r="' + r + '" stroke-dasharray="' + C + '" stroke-dashoffset="' + C + '"/></svg>';
    wrap.appendChild(h('div.mid', h('span', mid), sub ? h('small', sub) : null));
    requestAnimationFrame(() => requestAnimationFrame(() => { wrap.querySelector('.fg').style.strokeDashoffset = String(C * (1 - Math.max(0, Math.min(100, pct)) / 100)); }));
    return wrap;
  };
  /* icon tiles: [emoji, label, href | function, badge?] */
  FX.tiles = items => h('div.tiles', items.map(([em, label, go, badge]) => {
    const inner = [h('span.ti', em, badge ? h('span.dot', badge) : null), h('span', t(label))];
    return typeof go === 'function' ? h('button.tile', { type: 'button', onclick: go }, ...inner) : h('a.tile', { href: go }, ...inner);
  }));
  const TEXT_SIZES = [
    { id: 'very-small', scale: 0.8, label: 'Very small' },
    { id: 'small', scale: 0.9, label: 'Small' },
    { id: 'medium', scale: 1, label: 'Medium' },
    { id: 'large', scale: 1.1, label: 'Large' }
  ];
  const applyTextSize = id => {
    const size = TEXT_SIZES.find(x => x.id === id) || TEXT_SIZES[2];
    document.documentElement.style.setProperty('--font-scale', size.scale);
    return size;
  };
  let textSize = applyTextSize(localStorage.fx_font_size || 'medium');
  FX.cycleTextSize = () => {
    const current = TEXT_SIZES.indexOf(textSize);
    const next = TEXT_SIZES[(current + 1) % TEXT_SIZES.length];
    localStorage.fx_font_size = next.id;
    textSize = applyTextSize(next.id);
    FX.toast(t('Text size: {size}', { size: t(next.label) }));
  };
  FX.skel = () => h('div.skels', h('div.skel.title'), h('div.skel.card'), h('div.skel.card'), h('div.skel.line', { style: 'width:70%' }));
  FX.ripple = (btn, e) => { const r = btn.getBoundingClientRect(), d = Math.max(r.width, r.height); btn.appendChild(h('span.rip', { style: { width: d + 'px', height: d + 'px', left: (e.clientX - r.left - d / 2) + 'px', top: (e.clientY - r.top - d / 2) + 'px' } })); setTimeout(() => { const x = btn.querySelector('.rip'); if (x) x.remove(); }, 650); };
  const strip = h('div.offline', { role: 'status', hidden: true }, t('You are offline. Changes will work again when you reconnect.'));
  document.body.insertBefore(strip, document.body.firstChild);
  const net = () => { strip.hidden = navigator.onLine; };
  window.addEventListener('online', net); window.addEventListener('offline', net); net();

  /* ---------------- layout + nav ---------------- */
  const NAV = {
    customer: [['', 'Home', 'home'], ['rewards', 'Rewards', 'gift'], ['scan', 'Scan', 'scan'], ['bookings', 'Bookings', 'cal'], ['account', 'Account', 'user']],
    staff: [['', 'Queue', 'check'], ['bookings', 'Bookings', 'cal'], ['counter', 'Counter code', 'scan'], ['account', 'Account', 'user']],
    vendor: [['', 'Dashboard', 'home'], ['kit', 'Marketing kit', 'mega'], ['statements', 'Earnings', 'card'], ['account', 'Account', 'user']],
    owner: [['', 'Today', 'home'], ['customers', 'Customers', 'users'], ['rewards', 'Rewards', 'gift'], ['bookings', 'Bookings', 'cal'],
      ['spin', 'Spin & Win', 'pie'], ['campaigns', 'Offers', 'mega'], ['insights', 'Insights', 'chart'], ['shop', 'My shop', 'shop'], ['refer', 'Refer & Earn', 'gift'], ['billing', 'Billing', 'card'], ['account', 'Account', 'user']]
  };
  function navItems() {
    let items = NAV[S.role] || [];
    if (S.role === 'owner' && S.biz && !S.biz.bookings_enabled) items = items.filter(i => i[0] !== 'bookings');
    return items;
  }
  const curPath = () => (location.hash.replace(/^#\/?/, '').split('/')[0] || '');
  function navLink(i, cls) {
    if (S.role === 'customer' && i[0] === 'scan') {
      return h('button.nav.scan-action', { type: 'button', 'aria-label': t('Scan shop QR'), onclick: scanShopQR },
        h('span.scan-bubble', ico('scan')), h('span.scan-label', t(i[1])));
    }
    const badge = (i[0] === '' && S.pending && (S.role === 'owner' || S.role === 'staff')) || (i[0] === 'rewards' && false) ? h('span.dot', S.pending) : null;
    return h('a.nav', { href: '#/' + i[0], 'aria-current': curPath() === i[0] ? 'page' : null, onclick: () => { const d = document.querySelector('dialog.more'); if (d) d.remove(); } }, ico(i[2]), t(i[1]), badge);
  }
  function drawNav() {
    const items = navItems();
    const side = $('.side nav'), tabs = $('.tabs');
    if (!side) return;
    side.replaceChildren(...items.filter(i => !(S.role === 'customer' && i[0] === 'scan')).map(i => navLink(i)));
    const main = items.slice(0, items.length > 5 ? 4 : 5), rest = items.length > 5 ? items.slice(4) : [];
    tabs.replaceChildren(...main.map(i => navLink(i)));
    if (rest.length) tabs.appendChild(h('button.nav', { onclick: () => { const m = modal(t('More'), h('div.stack.s', rest.map(i => navLink(i)))); m.el.classList.add('more'); } }, ico('more'), t('More')));
    const bell = $('#bellDot'); if (bell) { bell.textContent = S.unread > 9 ? '9+' : S.unread; bell.hidden = !S.unread; }
  }
  function layout() {
    const root = $('#root');
    const shopSwitch = S.role === 'owner' && S.shops.length > 1 ? sel(S.shops.map(s => [s.shop_code, s.name]), S.biz && S.biz.shop_code, { 'aria-label': t('Switch shop'), onchange: e => { localStorage.fx_biz = e.target.value; S.biz = S.shops.find(s => s.shop_code === e.target.value); FX.render(); } }) : null;
    root.replaceChildren(h('div.app',
      h('aside.side', h('a.logo', { href: '#/' }, h('img', { src: '/icon.svg', alt: '' }), 'OFFLet'), h('nav', { style: 'display:grid;gap:2px' }), h('div.grow'),
        h('button.nav', { onclick: FX.signOut }, ico('out'), t('Log out'))),
      h('div', h('header.top', h('a.logo', { href: '#/' }, h('img', { src: '/icon.svg', alt: '' }), 'OFFLet'), shopSwitch, h('div.grow'),
        h('button.btn.ghost.sm', { onclick: () => { FX.setLang(FX.lang === 'hi' ? 'en' : 'hi'); FX.start(true); } }, FX.lang === 'hi' ? 'English' : 'हिन्दी'),
        h('button.iconbtn', { 'aria-label': t('Text size'), onclick: FX.cycleTextSize, style: 'font-weight:800;font-size:calc(13px * var(--font-scale, .8))' }, 'Aa'),
        h('button.iconbtn', { 'aria-label': t('Notifications'), onclick: FX.inbox }, ico('bell'), h('span.dot#bellDot', { hidden: true }))),
        h('main#view')),
      h('nav.tabs', { 'aria-label': 'Main' })));
    drawNav();
  }
  /* A tapped notification goes where it points. Only in-app paths are followed (the server also enforces this). */
  FX.openLink = function (link) {
    if (typeof link !== 'string' || link[0] !== '/' || link.startsWith('//') || /[\\:]/.test(link.split('#')[0])) return;
    const at = link.indexOf('#');
    if (link.startsWith('/app/') && location.pathname.startsWith('/app') && at >= 0) {
      const same = location.hash === link.slice(at);
      location.hash = link.slice(at);
      if (same) FX.render(true);
    } else location.href = link;
  };
  FX.inbox = async function () {
    const list = h('div.notif-list', h('div.skel.block'));
    const all = h('button.btn.ghost.sm', { hidden: true }, t('Mark all read'));
    const summary = h('p.small.muted', t('Tap a notification to open it.'));
    const m = modal(t('Notifications'), h('div.stack.notification-panel',
      h('div.notification-toolbar', summary, all), list), { cls: 'notifications' });
    const dec = () => { S.unread = Math.max(0, (S.unread || 0) - 1); drawNav(); };
    try {
      const items = await api('notifications/');
      const unreadCount = items.filter(n => !n.read).length;
      summary.textContent = unreadCount
        ? t('{n} unread notification(s)', { n: unreadCount })
        : t('You’re all caught up.');
      const kindFor = n => {
        const text = String(n.text || '').toLowerCase();
        if (/reward|redeem|coupon/.test(text)) return 'gift';
        if (/booking|appointment/.test(text)) return 'cal';
        if (/purchase|stamp|approval|approved/.test(text)) return 'check';
        return 'bell';
      };
      const rowFor = n => {
        const row = h('button.notif' + (n.read ? '' : '.unread'), { type: 'button', 'aria-label': FX.tr(n.text), onclick: async () => {
          if (!n.read) {
            try {
              await api('notifications/read/', 'POST', { ids: [n.id] });
              n.read = true;
              row.classList.remove('unread');
              dec();
              summary.textContent = S.unread ? t('{n} unread notification(s)', { n: S.unread }) : t('You’re all caught up.');
              all.hidden = !items.some(x => !x.read);
            } catch (e) {
              toast(e.message, true);
              return;
            }
          }
          if (n.link) { m.close(); FX.openLink(n.link); }
        } }, h('span.notif-icon.' + kindFor(n), ico(kindFor(n))),
        h('span.notif-copy', h('span.notif-text', FX.tr(n.text)), h('span.notif-time', fmtDT(n.created_at))),
        n.link ? h('span.go', { 'aria-hidden': 'true' }, '›') : null);
        return row;
      };
      list.replaceChildren(...(items.length ? items.map(rowFor) : [empty('No notifications yet', 'New updates for your shop will appear here.')]));
      all.hidden = !items.some(n => !n.read);
      all.onclick = e => busy(e.target, async () => {
        await api('notifications/read/', 'POST', {});
        items.forEach(n => { n.read = true; });
        S.unread = 0;
        drawNav();
        list.querySelectorAll('.unread').forEach(x => x.classList.remove('unread'));
        all.hidden = true;
        summary.textContent = t('You’re all caught up.');
      });
    } catch (e) { list.replaceChildren(h('p.err', e.message)); }
    return m;
  };
  async function poll() {
    if (!S.token || document.hidden) return;
    try {
      const n = await api('notifications/');
      const unread = n.filter(x => !x.read).length;
      let pend = S.pending;
      let redemptionPend = S.redemptionPending || 0;
      if ((S.role === 'owner' || S.role === 'staff') && S.biz) {
        const [entries, redemptions] = await Promise.all([
          api('owner/pending/'), api('b/' + S.biz.shop_code + '/redemptions/')
        ]);
        pend = entries.filter(e => e.shop_code === S.biz.shop_code).length + redemptions.length;
        redemptionPend = redemptions.length;
      }
      const grew = pend > S.pending;
      const newRedemption = redemptionPend > (S.redemptionPending || 0);
      if (unread !== S.unread || pend !== S.pending || redemptionPend !== (S.redemptionPending || 0)) {
        S.unread = unread; S.pending = pend; S.redemptionPending = redemptionPend; drawNav();
      }
      if (grew) {
        toast(t(newRedemption ? 'A customer requested to redeem a reward.' : 'A customer is waiting for approval.'));
        if (curPath() === '') FX.render(true);
      }
    } catch (e) { /* offline: try next tick */ }
  }
  setInterval(poll, 30000);

  /* ---------------- router ---------------- */
  FX.render = async function (keepScroll) {
    const view = $('#view'); if (!view) return;
    const y = window.scrollY, tk = ++S.nav;
    const parts = location.hash.replace(/^#\/?/, '').split('/'), seg = parts[0] || '', args = parts.slice(1);
    drawNav();
    if (!keepScroll) view.replaceChildren(FX.skel());
    let node;
    try {
      let fn = (FX.routes[S.role] || {})[seg];
      if (S.role === 'owner' && !S.biz && seg !== 'account') fn = FX.routes.owner.start;
      node = await (fn || FX.routes[S.role][''])(args);
    } catch (e) { node = h('div.card', h('p.err', e.message), h('button.btn.ghost', { onclick: () => FX.render() }, t('Try again'))); }
    if (tk !== S.nav) return;
    if (!keepScroll && node && node.classList) node.classList.add('enter');
    view.replaceChildren(node);
    window.scrollTo(0, keepScroll ? y : 0);
  };
  window.addEventListener('hashchange', () => { if (S.token && $('#view')) FX.render(); });
  FX.go = p => { location.hash = '#/' + p; };

  /* ---------------- session ---------------- */
  FX.signOut = async function () {
    try { if (S.token) await fetch('/api/auth/logout/', { method: 'POST', headers: { Authorization: 'Token ' + S.token } }); } catch (e) { /* ignore */ }
    localStorage.removeItem('t'); localStorage.removeItem('r');
    S.token = ''; S.role = ''; S.user = null; S.shops = []; S.biz = null;
    location.href = location.pathname.startsWith('/b/') ? location.pathname : '/app/';
  };
  async function loadShops() {
    if (S.role !== 'owner' && S.role !== 'staff') return;
    S.shops = await api('owner/businesses/');
    S.biz = S.shops.find(s => s.shop_code === localStorage.fx_biz) || S.shops[0] || null;
  }
  FX.reloadShops = async () => { await loadShops(); drawNav(); };
  FX.loadSub = async () => { if (S.role === 'owner') S.sub = await api('billing/'); return S.sub; };
  FX.signIn = async function (r) {
    S.token = r.token; S.role = r.role; localStorage.t = r.token; localStorage.r = r.role;
    if (r.needs_consent) await new Promise(res => { const m = modal(t('Terms and privacy'), h('div.stack', h('p', t('Please accept our Terms and Privacy Policy to continue.')), h('div.row', h('a', { href: '/terms/', target: '_blank' }, t('Terms')), h('a', { href: '/privacy/', target: '_blank' }, t('Privacy Policy'))), h('button.btn', { onclick: async e => { await busy(e.target, async () => { await api('auth/accept/', 'POST', {}); m.close(); res(); }); } }, t('I agree')))); });
    location.replace(location.href);
  };
  FX.start = async function (soft) {
    document.documentElement.lang = FX.lang;
    const rd = new URLSearchParams(location.search).get('redeem');
    if (rd && /^[0-9a-z]{4,12}$/i.test(rd)) sessionStorage.fx_redeem = rd.toUpperCase();
    const shopCode = (/^\/b\/([^/]+)/.exec(location.pathname) || [])[1];
    if (S.token) {
      try { S.user = await api('me/profile/'); S.role = S.user.role; localStorage.r = S.role; }
      catch (e) { if (!S.token) return FX.start(); }
    }
    if (!S.token) { $('#root').replaceChildren(shopCode ? await FX.publicShop(shopCode) : (FX.landing ? await FX.landing() : FX.authScreen({}))); return; }
    try { await loadShops(); if (S.role === 'owner') await FX.loadSub().catch(() => {}); } catch (e) { /* shown by route */ }
    layout(); poll();
    if (shopCode && S.role === 'customer') { $('#view').replaceChildren(await FX.shopPage(shopCode)); return; }
    if (shopCode) { location.replace('/app/'); return; }
    FX.render();
  };

  /* ---------------- auth ---------------- */
  FX.authScreen = function (o) {
    const q = new URLSearchParams(location.search), vref = location.pathname.startsWith('/b/') ? '' : q.get('ref');  // on shop pages ?ref= is a friend's code, not a partner's
    if (vref) localStorage.ref = vref;
    let mode = o.mode || (vref ? 'register' : 'login'), role = o.role || (vref ? 'owner' : 'customer');
    const box = h('div.form');
    const wrap = h('div.auth', h('section.hero', h('a.logo', { href: '/app/', style: 'color:#fff' }, h('img', { src: '/icon.svg', alt: '' }), 'OFFLet'),
      h('h1', t('Give customers a reason to come back.')),
      h('p', t('Stamp cards, rewards and bookings for local shops, salons and studios. Customers scan a QR code. No app to install.')),
      h('div.demo-card', h('div.row.between', h('b', 'Chai Point'), h('span.pill.gold', t('Gold'))), h('div.stamps', [1, 2, 3, 4, 5, 6].map(i => h('div.stamp' + (i <= 4 ? '.on' : '') + (i === 6 ? '.gift' : ''), i <= 4 ? h('span', '✓') : i === 6 ? h('span', '🎁') : null))), h('small', t('2 more visits for a free chai')))), box);
    function draw() {
      const err = h('div.err', { role: 'alert' });
      const mobile = inp({ type: 'tel', inputmode: 'numeric', autocomplete: 'username', ph: '10-digit mobile number', maxlength: 15 }), pw = inp({ type: 'password', autocomplete: mode === 'login' ? 'current-password' : 'new-password', ph: 'Password (6+ characters)' });
      const name = inp({ autocomplete: 'name', ph: 'Your name' }), agree = h('input', { type: 'checkbox', id: 'agree' });
      const roles = [['customer', '🛍️', 'I am a customer', 'Collect stamps and rewards'], ['owner', '🏪', 'I run a business', 'Bring customers back with rewards'], ['vendor', '🤝', 'I am a partner', 'Earn commission by onboarding shops']];
      const go = h('button.btn.lg.block', { type: 'submit' }, t(mode === 'login' ? 'Log in' : 'Create account'));
      const form = h('form.stack', { onsubmit: async e => {
        e.preventDefault(); err.textContent = '';
        await busy(go, async () => {
          try {
            let r;
            if (mode === 'login') r = await api('auth/login/', 'POST', { mobile: mobile.value.trim(), password: pw.value });
            else r = await api('auth/register/', 'POST', { mobile: mobile.value.trim(), password: pw.value, name: name.value.trim(), role, accepted: agree.checked, ref: role === 'owner' && !location.pathname.startsWith('/b/') ? localStorage.ref || '' : '' });
            await FX.signIn(r);
          } catch (x) { err.textContent = x.message; }
        });
      } },
        mode === 'register' ? h('div.roles', { role: 'radiogroup' }, roles.map(r => h('button.role', { type: 'button', role: 'radio', 'aria-checked': String(r[0] === role), onclick: () => { role = r[0]; draw(); } }, h('span.em', r[1]), h('div', h('b', t(r[2])), h('span', t(r[3])))))) : null,
        mode === 'register' ? field('Your name', name) : null, field('Mobile number', mobile), field('Password', pw),
        mode === 'register' ? h('label.check', agree, h('span', t('I agree to the '), h('a', { href: '/terms/', target: '_blank' }, t('Terms')), ' ', t('and'), ' ', h('a', { href: '/privacy/', target: '_blank' }, t('Privacy Policy')))) : null,
        err, go,
        mode === 'login' ? h('button.btn.ghost', { type: 'button', onclick: forgot }, t('Forgot password')) : null);
      box.replaceChildren(h('h2', t(mode === 'login' ? 'Welcome back' : 'Create your account')),
        h('div.seg', { role: 'tablist' }, ['login', 'register'].map(m => h('button', { type: 'button', role: 'tab', 'aria-selected': String(m === mode), onclick: () => { mode = m; draw(); } }, t(m === 'login' ? 'Log in' : 'Register')))), form);
    }
    function forgot() {
      const mobile = inp({ type: 'tel', ph: '10-digit mobile number' }), otp = inp({ inputmode: 'numeric', ph: '6-digit code', maxlength: 6 }), npw = inp({ type: 'password', ph: 'New password' });
      const step2 = h('div.stack', { hidden: true }, field('OTP', otp), field('New password', npw), h('button.btn', { onclick: async e => busy(e.target, async () => { await api('auth/reset/confirm/', 'POST', { mobile: mobile.value.trim(), otp: otp.value, new: npw.value }); m.close(); toast(t('Password changed. Please log in.')); }) }, t('Change password')));
      const m = modal(t('Reset password'), h('div.stack',
        field('Mobile number', mobile),
        h('p.small.muted', t('When SMS is unavailable, the code is sent to your verified recovery email. Add one in Account before you need it.')),
        h('button.btn', { onclick: e => busy(e.target, async () => { const r = await api('auth/reset/request/', 'POST', { mobile: mobile.value.trim() }); toast(FX.tr(r.detail)); step2.hidden = false; }) }, t('Send OTP')),
        step2));
    }
    draw();
    return wrap;
  };

  /* ---------------- shared: account ---------------- */
  FX.routes.customer.account = FX.routes.owner.account = FX.routes.staff.account = FX.routes.vendor.account = async function () {
    const me = S.user || await api('me/profile/');
    const name = inp({ value: me.name, maxlength: 150 });
    const recoveryEmail = inp({ type: 'email', value: me.email || '', autocomplete: 'email', ph: 'Email address' });
    const recoveryCode = inp({ inputmode: 'numeric', maxlength: 6, ph: '6-digit code' });
    const recoveryStatus = h('p.small.muted', me.email_verified
      ? t('Verified recovery email: {email}', { email: me.email })
      : me.email ? t('Recovery email not verified yet.') : t('No verified recovery email.'));
    const emailConfirm = h('div.stack.s', { hidden: true },
      field('Email verification code', recoveryCode),
      h('button.btn', { onclick: e => busy(e.target, async () => {
        const result = await api('auth/email/confirm/', 'POST', { otp: recoveryCode.value.trim() });
        recoveryEmail.value = result.email;
        recoveryStatus.textContent = t('Verified recovery email: {email}', { email: result.email });
        recoveryCode.value = '';
        emailConfirm.hidden = true;
        toast(t('Recovery email verified.'));
      }) }, t('Verify email')));
    const img = (await api('me/profile-image/')).profile_image_url;
    const hidden = S.role === 'customer' ? await api('me/shops/hidden/') : [];
    const old = inp({ type: 'password', autocomplete: 'current-password' }), nw = inp({ type: 'password', autocomplete: 'new-password' });
    const photo = h('input', { type: 'file', accept: 'image/*', hidden: true, onchange: async e => { const f = e.target.files[0]; if (!f) return; e.target.value = ''; const fd = new FormData(); fd.append('profile_image', f); try { await api('me/profile-image/', 'PATCH', fd); toast(t('Photo updated')); FX.render(true); } catch (x) { toast(x.message, true); } } });
    return h('div.stack.l', h('h1', t('Account')),
      h('div.card.stack', h('div.row', avatar(me.name, img), h('div.grow', h('b', me.name || t('Add your name')), h('div.muted.small', me.mobile)), h('button.btn.ghost.sm', { onclick: () => photo.click() }, t('Change photo')), photo),
        field('Name', name), h('button.btn', { onclick: e => busy(e.target, async () => { await api('me/profile/', 'PATCH', { name: name.value }); S.user = null; toast(t('Saved')); }) }, t('Save name'))),
      h('div.card.stack', h('h3', t('Password recovery')), h('p.small.muted', t('Add a verified email to receive password-reset codes when SMS is unavailable.')),
        field('Recovery email', recoveryEmail), recoveryStatus,
        h('button.btn.ghost', { onclick: e => busy(e.target, async () => {
          const result = await api('auth/email/request/', 'POST', { email: recoveryEmail.value.trim() });
          if (result.verified) {
            recoveryStatus.textContent = t('Verified recovery email: {email}', { email: recoveryEmail.value.trim() });
            toast(t('Recovery email is already verified.'));
            return;
          }
          emailConfirm.hidden = false;
          toast(FX.tr(result.detail));
        }) }, t('Send verification code')), emailConfirm),
      h('div.card.stack', h('h3', t('Language')), h('div.seg', ['en', 'hi'].map(l => h('button', { 'aria-selected': String(FX.lang === l), onclick: () => { FX.setLang(l); FX.start(true); } }, l === 'en' ? 'English' : 'हिन्दी')))),
      h('div.card.stack', h('h3', t('Change password')), field('Current password', old), field('New password', nw), h('button.btn.ghost', { onclick: e => busy(e.target, async () => { await api('auth/change-password/', 'POST', { old: old.value, new: nw.value }); old.value = nw.value = ''; toast(t('Password changed.')); }) }, t('Update password'))),
      hidden.length ? h('div.card', h('h3', t('Hidden shops')), hidden.map(s => h('div.li', h('span.grow', s.business__name), h('button.btn.soft.sm', { onclick: async () => { await api('me/shops/' + s.business__shop_code + '/restore/', 'POST'); FX.render(true); } }, t('Restore'))))) : null,
      h('div.card.stack', h('h3', t('Your data')), h('p.muted.small', t('You can delete your account and personal data at any time.')),
        h('button.btn.danger', { onclick: async () => { if (await confirmBox(t('Delete your account permanently? This cannot be undone.'), t('Delete my account'), true)) { await api('me/', 'DELETE'); FX.signOut(); } } }, t('Delete my account'))),
      h('button.btn.ghost', { onclick: FX.signOut }, t('Log out')));
  };

  /* ---------------- shared: counter code screen ---------------- */
  FX.routes.owner.counter = FX.routes.staff.counter = async function () {
    const biz = S.biz;
    const digits = h('div.digits', '······'), ring = h('div.ring', h('i')), img = h('img', { alt: 'QR', width: 300, height: 300 });
    let left = 0, alive = true, code = '';
    const load = async () => { const r = await api('b/' + biz.shop_code + '/counter-code/'); code = r.code; left = r.expires_in; digits.textContent = code.slice(0, 3) + ' ' + code.slice(3); img.src = '/api/b/' + biz.shop_code + '/cqr.png?c=' + code; };
    await load();
    const timer = setInterval(async () => { if (!alive || !document.body.contains(digits)) { clearInterval(timer); return; } left -= 1; ring.firstChild.style.width = Math.max(0, left / 60 * 100) + '%'; if (left <= 0) { try { await load(); } catch (e) { /* retry next tick */ } } }, 1000);
    return h('div.counter', h('div.stack.l', h('h2', { style: 'color:#fff' }, biz.name), h('p', { style: 'color:#cfe6e0' }, t('Customers scan this after paying. The code changes every minute.')),
      h('div.qr', img), digits, ring, h('button.btn.ghost', { onclick: () => { alive = false; FX.go(''); } }, t('Close'))));
  };
})(window.FX);
