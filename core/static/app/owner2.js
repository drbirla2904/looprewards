/* OFFLet v2 owner screens, part 2: bookings, offers (campaigns), insights, my shop (QR, branding, rules, services, team), billing. */
(function (FX) {
  'use strict';
  const { h, api, S, field, inp, sel, pill, empty, kpi, toast, modal, busy, confirmBox } = FX;
  const t = FX.t, R = FX.routes.owner;
  const code = () => S.biz.shop_code;

  /* ---------- bookings (owner + staff) ---------- */
  async function bookingsPage() {
    const tab = (location.hash.split('/')[1]) || 'open';
    const q = tab === 'today' ? '?when=today' : tab === 'history' ? '?status=completed' : '?status=open';
    const list = await api('b/' + code() + '/bookings/' + q);
    const done = () => FX.render(true);
    return h('div.stack.l', h('h1', t('Bookings')),
      h('div.seg', [['open', 'Upcoming'], ['today', 'Today'], ['history', 'Completed']].map(([k, l]) => h('button', { 'aria-selected': String(k === tab), onclick: () => FX.go('bookings/' + k) }, t(l)))),
      h('div.card', list.length ? (tab === 'history' ? list.map(b => h('div.li', h('div.grow', h('b', b.customer + ' · ' + b.service_name), h('div.small.muted', FX.fmtDT(b.starts_at))), b.rated ? pill('★', 'ok') : null)) : FX.bookingQueue(list, done)) : empty('Nothing here', 'Booking requests from customers appear here.')));
  }
  R.bookings = FX.routes.staff.bookings = bookingsPage;

  /* ---------- shop-wide offers ---------- */
  R.campaigns = async function () {
    const type = sel([['percent_off', 'Percentage off'], ['fixed_price', 'Fixed price'], ['bogo', 'Buy 1 get 1']], 'percent_off');
    const discount = inp({ type: 'number', min: '1', max: '100', step: '1', value: '10' });
    const discountField = h('div');
    const products = h('div.stack.s');
    const offerList = h('div.stack.s');
    const removeAll = h('button.btn.danger.sm', { onclick: async e => { if (await confirmBox(t('Turn off all offers? Customers will no longer see them.'), t('Turn off all'), true)) { await busy(e.target, async () => { await api('b/' + code() + '/offers/', 'DELETE'); await loadOffers(); }); } } }, t('Turn off all'));
    const currentHeader = h('div.row.between.wrap', h('h3', t('Current offers')), removeAll);
    const rows = [];
    const newItem = () => ({ name: inp({ maxlength: 120, ph: 'Item name' }), price: inp({ type: 'number', min: '0.01', step: '0.01', ph: 'Price (₹)' }), offerPrice: inp({ type: 'number', min: '0.01', step: '0.01', ph: 'Offer price (₹)' }), image: h('input', { type: 'file', accept: 'image/jpeg,image/png,image/webp' }) });
    const drawProducts = () => {
      products.replaceChildren(...rows.map((row, index) => h('div.offer-product.stack.s',
        field('Item name', row.name),
        h('div.g2', field('Price (₹)', row.price), type.value === 'fixed_price' ? field('Offer price (₹)', row.offerPrice) : null),
        field('Image', row.image),
        rows.length > 1 ? h('button.btn.ghost.sm', { onclick: () => { rows.splice(index, 1); drawProducts(); } }, t('Remove item')) : null)));
    };
    const drawType = () => {
      discountField.replaceChildren(type.value === 'percent_off' ? field('Discount (%)', discount) : null);
      drawProducts();
    };
    type.addEventListener('change', drawType);
    rows.push(newItem());
    drawType();
    const loadOffers = async () => {
      const offers = await api('b/' + code() + '/offers/');
      removeAll.hidden = !offers.some(offer => offer.active);
      offerList.replaceChildren(...(offers.length ? offers.map(offer => h('div.card.stack.s',
        h('div.row.between.wrap', h('b', offer.offer_type === 'percent_off' ? offer.value + '% off' : offer.offer_type === 'fixed_price' ? t('Fixed price') : t('Buy 1 get 1')),
          h('div.row.wrap', h('button.btn.ghost.sm', { onclick: e => busy(e.target, async () => { await api('b/' + code() + '/offers/' + offer.id + '/', 'PATCH', { active: !offer.active }); await loadOffers(); }) }, t(offer.active ? 'Turn off' : 'Turn on')),
            h('button.btn.danger.sm', { onclick: async e => { if (await confirmBox(t('Delete this offer permanently? Customers will no longer see it.'), t('Delete offer'), true)) { await busy(e.target, async () => { await api('b/' + code() + '/offers/' + offer.id + '/', 'DELETE'); await loadOffers(); }); } } }, t('Delete')),
            offer.active ? null : h('small.muted', t('Hidden from customers')))),
        offer.items.map(item => {
          const price = Number(item.price);
          const current = offer.offer_type === 'fixed_price' ? Number(item.offer_price) :
            offer.offer_type === 'percent_off' ? price * (1 - Number(offer.value) / 100) : null;
          return h('div.li', item.image ? h('img.offer-thumb', { src: item.image, alt: item.name }) : null,
            h('div.grow', h('b', item.name), offer.offer_type === 'bogo'
              ? h('div.small.muted', t('Price: {p}', { p: FX.rupee(price) }))
              : h('div.offer-price', h('b', FX.rupee(current)), h('del', FX.rupee(price)))));
        }))) : [empty('No offers yet', 'Add an offer to show it to everyone on your shop page.')]));
    };
    const save = h('button.btn.lg.gold.block', { onclick: e => busy(e.target, async () => {
      const items = rows.map(row => ({ name: row.name.value.trim(), price: row.price.value, offer_price: type.value === 'fixed_price' ? row.offerPrice.value : 0 }));
      if (items.some(item => !item.name || !item.price || (type.value === 'fixed_price' && !item.offer_price))) throw new Error(t('Enter a name and price for each item.'));
      const form = new FormData();
      form.append('offer_type', type.value);
      form.append('value', type.value === 'percent_off' ? discount.value : 0);
      form.append('items', JSON.stringify(items));
      rows.forEach((row, index) => { if (row.image.files[0]) form.append('image_' + index, row.image.files[0]); });
      await api('b/' + code() + '/offers/', 'POST', form);
      rows.splice(0, rows.length, newItem());
      drawType();
      await loadOffers();
      toast(t('Offer added. It is now visible to everyone.'));
    }) }, t('Add offer'));
    await loadOffers();
    return h('div.stack.l', { style: 'max-width:680px' },
      h('div', h('h1', t('Shop offers')), h('p.muted', t('These offers are visible to everyone on your shop page, separate from rewards.'))),
      h('div.card.stack', h('h3', t('Create an offer')), field('Offer type', type), discountField,
        h('div.row.between', h('b', t('Items')), h('button.btn.ghost.sm', { onclick: () => { if (rows.length >= 20) return toast(t('Add up to 20 items per offer.')); rows.push(newItem()); drawProducts(); } }, '+ ' + t('Add item'))),
        products, save),
      h('div.card.stack', currentHeader, offerList));
  };

  /* ---------- insights ---------- */
  R.insights = async function () {
    const days = +(location.hash.split('/')[1]) || 30;
    const [d, fb] = await Promise.all([api('b/' + code() + '/insights/?days=' + days), api('b/' + code() + '/feedback/')]);
    const k = d.kpis, segName = Object.fromEntries(FX.SEG);
    const maxHour = Math.max(1, ...d.hours.map(x => x.count));
    return h('div.stack.l', h('div.hd', h('div', h('h1', t('Insights')), h('p.muted', t('See who comes back and when'))),
      h('div.seg', [7, 30, 90].map(n => h('button', { 'aria-selected': String(n === days), onclick: () => FX.go('insights/' + n) }, t('{n} days', { n }))))),
      h('div.g4', kpi('Customers', k.customers), kpi('New customers', k.new_in_period), kpi('Come back rate', k.repeat_rate + '%'), kpi('Returning visits', k.returning_share + '%', t('of {n} visits', { n: k.visits_in_period }))),
      h('div.g4', kpi('Tracked sales', FX.rupee(k.tracked_sales), t('Spend-type tasks only')), kpi('Rewards used', k.redeem_rate + '%', t('{a} of {b} issued', { a: k.rewards_redeemed, b: k.rewards_issued })), kpi('Average rating', k.rating_avg ? k.rating_avg + ' ★' : '-', t('{n} reviews', { n: k.rating_count })), kpi('Upcoming bookings', k.bookings_upcoming)),
      h('div.card', h('h3', t('Visits per day')), FX.barChart(d.series, 'visits')),
      h('div.g2', h('div.card', h('h3', t('Busiest days')), FX.hbars(d.weekday.map((n, i) => [FX.wd(i), n]))),
        h('div.card', h('h3', t('Customer groups')), FX.hbars(Object.entries(d.segments).map(([s, n]) => [t(segName[s] || s), n])))),
      d.hours.length ? h('div.card', h('h3', t('Busiest hours')), FX.hbars(d.hours.map(x => [(x.hour % 12 || 12) + (x.hour < 12 ? ' am' : ' pm'), x.count]))) : null,
      h('div.card', h('h3', t('Recent feedback')), fb.length ? fb.slice(0, 10).map(f => h('div.li', h('div.grow', FX.stars(f.rating), f.comment ? h('p.small', f.comment) : null, h('small.muted', f.customer + ' · ' + FX.ago(f.created_at))))) : empty('No feedback yet', 'Customers can rate a visit after it is approved.')));
  };

  /* ---------- my shop ---------- */
  /* ---------- the one QR card: shop details + QR on a single image (download / share only) ---------- */
  const loadImg = src => new Promise(res => { const i = new Image(); i.crossOrigin = 'anonymous'; i.onload = () => res(i); i.onerror = () => res(null); i.src = src; });
  const lum = hex => { const m = /^#?([0-9a-f]{6})$/i.exec(hex || ''); if (!m) return 0; const n = parseInt(m[1], 16), c = [n >> 16, (n >> 8) & 255, n & 255].map(v => { v /= 255; return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4); }); return .2126 * c[0] + .7152 * c[1] + .0722 * c[2]; };
  function wrapText(ctx, text, maxW, maxLines) {
    const words = String(text || '').split(/\s+/).filter(Boolean), lines = []; let cur = '';
    for (const w of words) {
      const test = cur ? cur + ' ' + w : w;
      if (ctx.measureText(test).width <= maxW || !cur) cur = test; else { lines.push(cur); cur = w; }
    }
    if (cur) lines.push(cur);
    if (lines.length > maxLines) { lines.length = maxLines; let l = lines[maxLines - 1]; while (l.length > 1 && ctx.measureText(l + '…').width > maxW) l = l.slice(0, -1); lines[maxLines - 1] = l + '…'; }
    return lines;
  }
  const QR_CARD_THEMES = {
    cafe: { icon: '☕', label: 'Cafe & coffee', hi: 'कैफ़े और कॉफ़ी', accent: '#8a4b2a', soft: '#f8eee5' },
    restaurant: { icon: '🍽️', label: 'Restaurant & dining', hi: 'रेस्तराँ', accent: '#c24132', soft: '#fff0eb' },
    grocery: { icon: '🛒', label: 'Grocery & convenience', hi: 'किराना और सुविधा स्टोर', accent: '#39804b', soft: '#edf7e9' },
    retail: { icon: '🛍️', label: 'Fashion & retail', hi: 'फ़ैशन और रिटेल', accent: '#7546a8', soft: '#f3edfb' },
    salon: { icon: '✂', label: 'Salon & wellness', hi: 'सैलून और वेलनेस', accent: '#bd4f78', soft: '#fcecf2' },
    fitness: { icon: '🏋️', label: 'Fitness & studios', hi: 'फ़िटनेस और स्टूडियो', accent: '#176a91', soft: '#e9f4f9' },
    services: { icon: '🛠️', label: 'Repair, clinic & services', hi: 'रिपेयर, क्लिनिक और सेवाएँ', accent: '#3d5a80', soft: '#e9eff6' },
    other: { icon: '🏪', label: 'Shop & rewards', hi: 'दुकान और इनाम', accent: '#5e35b1', soft: '#f0eafa' }
  };
  function drawCategoryArt(ctx, category, x, y, scale, color) {
    ctx.save(); ctx.translate(x, y); ctx.scale(scale, scale);
    ctx.strokeStyle = color; ctx.fillStyle = color; ctx.lineWidth = 5; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    const line = (...points) => { ctx.beginPath(); ctx.moveTo(points[0], points[1]); for (let i = 2; i < points.length; i += 2) ctx.lineTo(points[i], points[i + 1]); ctx.stroke(); };
    const circle = (cx, cy, r) => { ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.stroke(); };
    const rounded = (rx, ry, w, h, r) => { ctx.beginPath(); ctx.roundRect(rx, ry, w, h, r); ctx.stroke(); };
    switch (category) {
      case 'salon':
        rounded(12, 6, 40, 67, 8);
        line(20, 17, 44, 17); line(20, 27, 44, 27); line(20, 37, 44, 37); line(20, 47, 44, 47); line(20, 57, 44, 57);
        circle(73, 20, 9); circle(92, 20, 9); line(68, 27, 91, 56); line(97, 27, 74, 56); circle(81, 43, 3);
        rounded(66, 63, 26, 18, 7); line(72, 81, 67, 94); line(86, 81, 91, 94); line(92, 72, 101, 72);
        break;
      case 'cafe':
        rounded(12, 17, 56, 42, 7); ctx.beginPath(); ctx.arc(68, 31, 13, -Math.PI / 2, Math.PI / 2); ctx.stroke();
        line(17, 67, 77, 67); line(28, 8, 24, 1); line(45, 8, 45, 0); line(61, 8, 66, 1);
        break;
      case 'restaurant':
        line(23, 8, 23, 43); line(13, 8, 13, 22); line(33, 8, 33, 22); line(13, 22, 33, 22); line(23, 43, 23, 70);
        line(75, 8, 75, 70); ctx.beginPath(); ctx.ellipse(75, 27, 12, 19, 0, 0, Math.PI * 2); ctx.stroke();
        break;
      case 'grocery':
        line(12, 20, 88, 20); line(19, 20, 26, 68); line(81, 20, 74, 68); line(26, 68, 74, 68);
        line(34, 20, 40, 68); line(50, 20, 50, 68); line(66, 20, 60, 68); line(38, 20, 49, 5); line(62, 20, 51, 5);
        break;
      case 'retail':
        rounded(15, 25, 70, 49, 8); ctx.beginPath(); ctx.arc(50, 27, 17, Math.PI, 0); ctx.stroke();
        break;
      case 'fitness':
        rounded(39, 39, 22, 22, 5); line(30, 30, 30, 70); line(19, 37, 19, 63); line(70, 30, 70, 70); line(81, 37, 81, 63);
        line(19, 50, 30, 50); line(70, 50, 81, 50); break;
      case 'services':
        circle(27, 25, 13); circle(73, 67, 13); line(37, 35, 63, 59); line(15, 13, 11, 5); line(37, 13, 43, 7);
        break;
      default:
        line(12, 39, 50, 12, 88, 39); line(20, 36, 20, 76); line(80, 36, 80, 76); line(20, 76, 80, 76);
        rounded(42, 49, 17, 27, 3); line(29, 48, 36, 48); line(64, 48, 71, 48);
    }
    ctx.restore();
  }
  async function drawQrCard(b) {
    const W = 1080, H = 2220, FONT = 'Inter, "Noto Sans Devanagari", -apple-system, "Segoe UI", sans-serif', hi = b.language === 'hi';
    try { await Promise.all([document.fonts.load('800 60px Inter'), document.fonts.load('500 30px Inter'), document.fonts.load('700 40px "Noto Sans Devanagari"')]); } catch (e) { /* system font fallback */ }
    const [qr, logo, offletLogo, publicBiz] = await Promise.all([
      loadImg('/api/b/' + b.shop_code + '/qr.png'),
      b.logo_url ? loadImg(b.logo_url) : null,
      loadImg('/icon.svg'),
      api('b/' + b.shop_code + '/')
    ]);
    if (!qr) throw new Error(t('Could not load the QR code. Check your connection.'));
    if (!offletLogo) throw new Error(t('Could not load the OFFLet logo. Check your connection.'));
    const brand = /^#[0-9a-f]{6}$/i.test(b.brand_color || '') ? b.brand_color : '#5e35b1', onBrand = lum(brand) > .6 ? '#1c1530' : '#ffffff';
    const theme = QR_CARD_THEMES[b.category] || QR_CARD_THEMES.other;
    const c = document.createElement('canvas'); c.width = W; c.height = H; const x = c.getContext('2d');
    const rr = (px, py, w, hh, r) => { x.beginPath(); x.roundRect ? x.roundRect(px, py, w, hh, r) : x.rect(px, py, w, hh); };
    x.fillStyle = '#f7f5f0'; x.fillRect(0, 0, W, H);
    const hero = x.createLinearGradient(48, 48, W - 48, 590); hero.addColorStop(0, '#17142b'); hero.addColorStop(1, '#30244b');
    x.fillStyle = hero; rr(48, 48, W - 96, 560, 48); x.fill();
    x.save(); x.globalAlpha = .12;
    drawCategoryArt(x, b.category, 92, 250, 1.2, theme.soft);
    drawCategoryArt(x, b.category, 890, 250, 1.2, theme.soft);
    x.restore();
    x.fillStyle = '#ffffff'; rr(88, 78, 60, 60, 18); x.fill();
    x.drawImage(offletLogo, 96, 86, 44, 44);
    x.textAlign = 'left'; x.textBaseline = 'middle'; x.fillStyle = '#fff'; x.font = '800 34px ' + FONT; x.fillText('OFFLet', 164, 108);
    const categoryLabel = hi ? theme.hi : theme.label;
    x.font = '600 20px ' + FONT;
    const badgeWidth = Math.min(460, x.measureText(categoryLabel).width + 76), badgeX = W - 88 - badgeWidth;
    x.fillStyle = '#ffffff20'; rr(badgeX, 78, badgeWidth, 60, 30); x.fill();
    x.textAlign = 'left'; x.fillStyle = '#fff'; x.font = '700 28px "Apple Color Emoji", "Segoe UI Emoji", sans-serif'; x.fillText(theme.icon, badgeX + 18, 108);
    x.font = '600 20px ' + FONT; x.fillText(categoryLabel, badgeX + 56, 108);
    x.textAlign = 'center'; x.textBaseline = 'alphabetic';
    x.fillStyle = '#ffffff'; x.beginPath(); x.arc(W / 2, 248, 78, 0, Math.PI * 2); x.fill();
    x.strokeStyle = theme.accent; x.lineWidth = 7; x.beginPath(); x.arc(W / 2, 248, 76, 0, Math.PI * 2); x.stroke();
    x.save(); x.beginPath(); x.arc(W / 2, 248, 68, 0, Math.PI * 2); x.clip();
    if (logo) { const k = Math.max(136 / logo.width, 136 / logo.height); x.fillStyle = '#fff'; x.fillRect(W / 2 - 68, 180, 136, 136); x.drawImage(logo, W / 2 - logo.width * k / 2, 248 - logo.height * k / 2, logo.width * k, logo.height * k); }
    else { x.fillStyle = brand; x.fillRect(W / 2 - 68, 180, 136, 136); }
    x.restore();
    if (!logo) { x.fillStyle = onBrand; x.font = '800 72px ' + FONT; x.fillText((b.name || '?').trim().charAt(0).toUpperCase(), W / 2, 273); }
    x.fillStyle = '#fff'; let size = 60, lines;
    do { x.font = '800 ' + size + 'px ' + FONT; lines = wrapText(x, b.name, 860, 2); if (lines.every(line => x.measureText(line).width <= 860) || size <= 40) break; size -= 2; } while (size > 38);
    let nameY = 366; lines.forEach(line => { x.fillText(line, W / 2, nameY); nameY += size + 6; });
    const ratingCount = Number(publicBiz.rating_count || 0), ratingAverage = Number(publicBiz.rating_average);
    x.textAlign = 'center'; x.textBaseline = 'alphabetic';
    let identityY = nameY + 24;
    if (ratingCount > 0 && Number.isFinite(ratingAverage)) {
      const filledStars = Math.max(0, Math.min(5, Math.round(ratingAverage)));
      x.fillStyle = '#f5b52e'; x.font = '700 31px ' + FONT;
      x.fillText('★'.repeat(filledStars) + '☆'.repeat(5 - filledStars), W / 2, identityY);
      identityY += 38;
    }
    if (b.tagline) { x.fillStyle = '#e8e4f0'; x.font = '500 26px ' + FONT; x.fillText(wrapText(x, b.tagline, 820, 1)[0], W / 2, Math.min(590, identityY + 8)); }

    x.textAlign = 'center'; x.fillStyle = '#1c1530'; x.font = '800 36px ' + FONT;
    x.fillText(hi ? 'हर विज़िट पर कुछ और पाएँ' : 'A LITTLE EXTRA EVERY VISIT', W / 2, 675);
    x.fillStyle = '#6b6485'; x.font = '500 23px ' + FONT;
    x.fillText(hi ? 'इन रिवॉर्ड्स का आनंद लेने के लिए स्कैन करें' : 'Scan once. Enjoy more every time.', W / 2, 713);
    const rewards = hi
      ? [
          ['🎁', 'स्टैम्प रिवॉर्ड', 'हर विज़िट पर स्टैम्प पाएँ'],
          ['🎡', 'स्पिन करें और जीतें', 'शानदार इनाम जीतने का मौका'],
          ['🛍️', 'शॉप ऑफ़र', 'खास डील और ऑफ़र पाएँ'],
          ['💸', 'रेफ़र करें और कमाएँ', 'दोस्तों को बुलाएँ, रिवॉर्ड पाएँ']
        ]
      : [
          ['🎁', 'Stamp rewards', 'Collect stamps on every visit'],
          ['🎡', 'Spin & Win', 'Get a chance to win prizes'],
          ['🛍️', 'Shop offers', 'Unlock special deals here'],
          ['💸', 'Refer & earn', 'Invite friends. Earn rewards.']
        ];
    rewards.forEach(([icon, title, detail], index) => {
      const col = index % 2, row = Math.floor(index / 2), px = 70 + col * 480, py = 750 + row * 290, cw = 460, ch = 265;
      x.save(); x.shadowColor = 'rgba(25, 20, 43, .12)'; x.shadowBlur = 18; x.shadowOffsetY = 6;
      x.fillStyle = '#fff'; rr(px, py, cw, ch, 30); x.fill(); x.restore();
      x.strokeStyle = theme.accent + '66'; x.lineWidth = 3; rr(px, py, cw, ch, 30); x.stroke();
      x.fillStyle = theme.accent; rr(px, py, cw, 13, 7); x.fill();
      x.fillStyle = theme.soft; x.beginPath(); x.arc(px + cw / 2, py + 82, 58, 0, Math.PI * 2); x.fill();
      x.strokeStyle = theme.accent + '66'; x.lineWidth = 3; x.beginPath(); x.arc(px + cw / 2, py + 82, 58, 0, Math.PI * 2); x.stroke();
      x.textAlign = 'center'; x.textBaseline = 'middle';
      x.font = '700 68px "Apple Color Emoji", "Segoe UI Emoji", sans-serif'; x.fillText(icon, px + cw / 2, py + 83);
      x.fillStyle = '#1c1530'; x.font = '800 30px ' + FONT; x.fillText(title, px + cw / 2, py + 169, cw - 34);
      x.fillStyle = '#6b6485'; x.font = '500 21px ' + FONT;
      wrapText(x, detail, cw - 52, 2).forEach((line, lineIndex) => x.fillText(line, px + cw / 2, py + 208 + lineIndex * 26));
    });

    x.save(); x.shadowColor = 'rgba(25, 20, 43, .16)'; x.shadowBlur = 22; x.shadowOffsetY = 8;
    x.fillStyle = '#fff'; rr(260, 1350, 560, 440, 38); x.fill(); x.restore();
    x.strokeStyle = '#e9e4ee'; x.lineWidth = 2; rr(260, 1350, 560, 440, 38); x.stroke();
    const qs = 280, qy = 1370;
    x.imageSmoothingEnabled = false; x.drawImage(qr, W / 2 - qs / 2, qy, qs, qs);
    x.textAlign = 'center'; x.textBaseline = 'alphabetic'; x.fillStyle = '#1c1530'; x.font = '800 34px ' + FONT;
    const scanLabel = hi ? 'स्कैन करें और इनाम पाएँ' : 'Scan to join rewards';
    x.fillText(scanLabel, W / 2, 1688);
    const actionLabel = hi ? 'अभी स्कैन करें' : 'SCAN & START';
    x.font = '800 25px ' + FONT;
    const pw = Math.min(420, x.measureText(actionLabel).width + 72);
    x.fillStyle = brand; rr(W / 2 - pw / 2, 1708, pw, 58, 29); x.fill();
    x.fillStyle = onBrand; x.fillText(actionLabel, W / 2, 1746);

    x.save(); x.fillStyle = '#fff'; rr(90, 1830, 900, 300, 30); x.fill(); x.restore();
    x.strokeStyle = '#e9e4ee'; x.lineWidth = 2; rr(90, 1830, 900, 300, 30); x.stroke();
    x.fillStyle = theme.soft; x.beginPath(); x.arc(145, 1880, 27, 0, Math.PI * 2); x.fill();
    x.textAlign = 'center'; x.textBaseline = 'middle'; x.font = '700 27px "Apple Color Emoji", "Segoe UI Emoji", sans-serif'; x.fillStyle = theme.accent; x.fillText('📍', 145, 1881);
    x.textAlign = 'left'; x.textBaseline = 'alphabetic'; x.fillStyle = theme.accent; x.font = '800 22px ' + FONT;
    x.fillText(hi ? 'हमारी दुकान' : 'YOUR NEIGHBOURHOOD SHOP', 190, 1888);
    const info = [b.address, [b.hours, b.phone].filter(Boolean).join('  ·  '), b.pay_upi_id ? 'UPI: ' + b.pay_upi_id : ''].filter(Boolean);
    x.fillStyle = '#4a4466'; x.font = '500 22px ' + FONT;
    const detailLines = info.flatMap(row => wrapText(x, row, 820, 2));
    detailLines.slice(0, 5).forEach((line, index) => {
      const y = 1930 + index * 34;
      x.fillStyle = theme.accent; x.beginPath(); x.arc(145, y - 7, 4, 0, Math.PI * 2); x.fill();
      x.fillStyle = '#4a4466'; x.fillText(line, 164, y);
    });
    x.textAlign = 'center'; x.globalAlpha = .8; x.fillStyle = '#6b6485'; x.font = '700 19px ' + FONT; x.fillText('Powered by OFFLet', W / 2, 2175); x.globalAlpha = 1;
    return c;
  }
  function qrCard() {
    const b = S.biz, url = location.origin + '/b/' + b.shop_code + '/', box = h('div', { style: 'display:grid;place-items:center;min-height:240px' }, h('div.spin'));
    let canvas = null;
    const blob = () => new Promise((res, rej) => canvas.toBlob(x => (x ? res(x) : rej(new Error(t('Something went wrong. Please try again.')))), 'image/png'));
    const fname = (b.name || 'shop').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'shop';
    const mark = () => { localStorage['fx_printed_' + b.shop_code] = '1'; };
    const download = btn => busy(btn, async () => {
      const f = await blob(), a = h('a', { href: URL.createObjectURL(f), download: fname + '-qr.png' });
      document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 4000); mark();
    });
    const shareCard = btn => busy(btn, async () => {
      const f = new File([await blob()], fname + '-qr.png', { type: 'image/png' }), text = t('Collect rewards at {shop}', { shop: b.name });
      if (navigator.canShare && navigator.canShare({ files: [f] })) { try { await navigator.share({ files: [f], text: text + ' ' + url }); mark(); } catch (e) { if (e.name !== 'AbortError') throw e; } }
      else FX.share(text, url);
    });
    drawQrCard(b).then(c => { canvas = c; c.setAttribute('role', 'img'); c.setAttribute('aria-label', t('Your QR code')); c.style.cssText = 'width:100%;max-width:340px;height:auto;border-radius:16px;box-shadow:0 8px 26px -10px #0004'; box.replaceChildren(c); })
      .catch(e => box.replaceChildren(h('p.err', e.message), h('button.btn.ghost.sm', { onclick: () => FX.render(true) }, t('Try again'))));
    return h('div.card.stack', h('h3', t('Your QR card')), h('p.muted.small', t('One card with your shop details and QR code. Download it to print, or share it on WhatsApp.')), box,
      h('div.stack.s', { style: 'width:100%;max-width:340px;margin:0 auto' }, h('button.btn', { onclick: e => { if (canvas) download(e.currentTarget); } }, t('Download')), h('button.btn.ghost', { onclick: e => { if (canvas) shareCard(e.currentTarget); } }, t('Share'))),
      h('div.stack.s', { style: 'text-align:center' }, h('small.muted', t('Your shop link')), h('code', { style: 'word-break:break-all;font-size:calc(12.5px * var(--font-scale, .8))' }, url),
        h('div.row.wrap', { style: 'justify-content:center' }, h('button.btn.ghost.sm', { onclick: () => FX.copy(url) }, t('Copy link')), h('a.btn.ghost.sm', { href: '#/counter' }, t('Counter code screen')))));
  }
  function servicesCard(biz) {
    const box = h('div.stack.s');
    const edit = (s) => {
      const name = inp({ value: s ? s.name : '', maxlength: 80 }), price = inp({ type: 'number', min: '0', value: s ? s.price : 0 }), dur = inp({ type: 'number', min: '5', max: '600', value: s ? s.duration_min : 30 });
      const m = modal(t(s ? 'Edit service' : 'New service'), h('div.stack', field('Name', name), h('div.g2', field('Price (₹)', price), field('Minutes', dur)), h('div.row',
        s ? h('button.btn.danger', { onclick: e => busy(e.target, async () => { await api('services/' + s.id + '/', 'DELETE'); m.close(); load(); }) }, t('Delete')) : null,
        h('button.btn.grow', { onclick: e => busy(e.target, async () => { const b = { name: name.value, price: price.value, duration_min: dur.value }; await api(s ? 'services/' + s.id + '/' : 'b/' + code() + '/services/', s ? 'PATCH' : 'POST', b); m.close(); load(); }) }, t('Save')))));
    };
    const load = async () => { const l = await api('b/' + code() + '/services/'); box.replaceChildren(...(l.length ? l.map(s => h('div.li.click', { onclick: () => edit(s) }, h('span.grow', s.name + (s.active ? '' : ' (' + t('hidden') + ')')), h('small.muted', s.duration_min + ' min'), h('b.num', FX.rupee(s.price)))) : [h('p.muted', t('Add the services customers can book.'))])); };
    load();
    const on = h('input', { type: 'checkbox', checked: biz.bookings_enabled, onchange: e => busy(e.target, async () => { await api('b/' + code() + '/settings/', 'PATCH', { bookings_enabled: e.target.checked }); await FX.reloadShops(); toast(t('Saved')); }) });
    return h('div.card.stack', h('div.hd', h('h3', t('Services and bookings')), h('button.btn.soft.sm', { onclick: () => edit(null) }, '+ ' + t('Add service'))),
      h('label.check', on, h('span', t('Let customers request appointments online'))), box,
      h('small.muted', t('When you mark a booking completed, the visit is added to your reward programs automatically.')));
  }
  function teamCard() {
    const box = h('div.stack.s');
    const load = async () => { const l = await api('b/' + code() + '/staff/'); box.replaceChildren(...(l.length ? l.map(s => h('div.li', h('span.grow', s.name || s.mobile, h('small.muted', ' ' + s.mobile)), h('button.btn.danger.sm', { onclick: async () => { if (await confirmBox(t('Remove this team member?'), t('Remove'), true)) { await api('b/' + code() + '/staff/', 'DELETE', { mobile: s.mobile }); load(); } } }, t('Remove')))) : [h('p.muted', t('Add a cashier so they can approve purchases and redeem rewards.'))])); };
    load();
    const add = () => { const n = inp({ maxlength: 60 }), mo = inp({ type: 'tel' }), pw = inp({ type: 'password', autocomplete: 'new-password' });
      const m = modal(t('Add team member'), h('div.stack', field('Name', n), field('Mobile number', mo), field('Password', pw, 'They log in with their mobile number and this password.'), h('button.btn', { onclick: e => busy(e.target, async () => { await api('b/' + code() + '/staff/', 'POST', { name: n.value, mobile: mo.value.trim(), password: pw.value }); m.close(); load(); }) }, t('Add')))); };
    return h('div.card.stack', h('div.hd', h('h3', t('Team')), h('button.btn.soft.sm', { onclick: add }, '+ ' + t('Add'))), box);
  }
  R.shop = async function () {
    const b = S.biz, url = location.origin + '/b/' + b.shop_code + '/';
    const f = { name: inp({ value: b.name, maxlength: 120 }), tagline: inp({ value: b.tagline, maxlength: 140 }), about: h('textarea', { maxlength: 600, value: b.about }), address: inp({ value: b.address }), hours: inp({ value: b.hours, ph: 'e.g. Mon-Sat 9am-9pm' }),
      phone: inp({ type: 'tel', value: b.phone }), whatsapp: inp({ type: 'tel', value: b.whatsapp, ph: 'with country code, e.g. 919876543210' }), maps_url: inp({ type: 'url', value: b.maps_url, ph: 'https://maps.google.com/...' }), pay_upi_id: inp({ value: b.pay_upi_id || '' }),
      instagram_url: inp({ type: 'url', value: b.instagram_url, ph: 'https://instagram.com/yourshop' }), facebook_url: inp({ type: 'url', value: b.facebook_url, ph: 'https://facebook.com/yourshop' }),
      youtube_url: inp({ type: 'url', value: b.youtube_url, ph: 'https://youtube.com/@yourshop' }), tiktok_url: inp({ type: 'url', value: b.tiktok_url, ph: 'https://tiktok.com/@yourshop' }),
      x_url: inp({ type: 'url', value: b.x_url, ph: 'https://x.com/yourshop' }),
      brand_color: h('input', { type: 'color', value: b.brand_color || '#5e35b1' }), language: sel([['en', 'English'], ['hi', 'हिन्दी']], b.language) };
    const logo = h('input', { type: 'file', accept: 'image/*' });
    const rules = { approval_mode: sel([['manual', 'I approve each purchase'], ['auto', 'Approve automatically']], b.approval_mode), cooldown_minutes: inp({ type: 'number', min: '0', value: b.cooldown_minutes }), daily_cap: inp({ type: 'number', min: '1', value: b.daily_cap }), max_distance_m: inp({ type: 'number', min: '0', value: b.max_distance_m || 0 }), require_bill_photo: h('input', { type: 'checkbox', checked: b.require_bill_photo }) };
    const hasLocation = b.lat != null && b.lng != null;
    const locationStatus = h('p.small.muted', hasLocation
      ? t('Shop location is set. Customers can get directions. Detect again to update it.')
      : t('No shop location is set. Detect it from the device used at your shop.'));
    const locationMap = hasLocation
      ? h('a.btn.ghost.sm', { href: 'https://www.google.com/maps/search/?api=1&query=' + encodeURIComponent(b.lat + ',' + b.lng), target: '_blank', rel: 'noopener' }, t('View saved location'))
      : null;
    const detectLocation = h('button.btn.ghost.sm', { onclick: e => busy(e.target, async () => {
      locationStatus.textContent = t('Getting device location…');
      try {
        const position = await FX.locate();
        await api('b/' + code() + '/settings/', 'PATCH', { lat: position.coords.latitude, lng: position.coords.longitude });
        await FX.reloadShops();
        toast(t('Shop location saved.'));
        FX.render(true);
      } catch (error) {
        locationStatus.textContent = error.message;
      }
    }) }, t('Detect and save location'));
    const save = (fields, extra) => async e => busy(e.target, async () => {
      let body;
      if (extra && extra.logo && extra.logo.files[0]) { body = new FormData(); body.append('logo', extra.logo.files[0]); for (const [k, v] of Object.entries(fields)) body.append(k, v.type === 'checkbox' ? v.checked : v.value); }
      else { body = {}; for (const [k, v] of Object.entries(fields)) body[k] = v.type === 'checkbox' ? v.checked : v.value; }
      await api('b/' + code() + '/settings/', 'PATCH', body); await FX.reloadShops(); toast(t('Saved')); FX.render(true);
    });
    return h('div.stack.l', { style: 'max-width:820px;min-width:0' }, h('h1', t('My shop')),
      qrCard(),
      h('div.card.stack', h('h3', t('Shop page')), h('div.g2', field('Shop name', f.name), field('Tagline', f.tagline)), field('About', f.about), h('div.g2', field('Address', f.address), field('Opening hours', f.hours)),
        h('div.row.wrap', detectLocation, locationMap), locationStatus,
        h('div.g2', field('Phone', f.phone), field('WhatsApp', f.whatsapp)), field('Google Maps link', f.maps_url), h('div.g2', field('UPI ID', f.pay_upi_id), field('Language', f.language)),
        h('details.card', h('summary', t('Social media accounts')), h('p.small.muted', t('Add public profile links. Customers see small follow icons on your shop page.')),
          h('div.g2', field('Instagram profile URL', f.instagram_url), field('Facebook profile URL', f.facebook_url)),
          h('div.g2', field('YouTube profile URL', f.youtube_url), field('TikTok profile URL', f.tiktok_url)),
          field('X profile URL', f.x_url)),
        h('div.g2', field('Brand colour', f.brand_color), field('Logo', logo)), h('button.btn', { style: 'justify-self:start', onclick: save(f, { logo }) }, t('Save shop page'))),
      h('div.card.stack', h('h3', t('Purchase rules')), field('Approval', rules.approval_mode), h('div.g2', field('Minutes between purchases', rules.cooldown_minutes), field('Purchases per day', rules.daily_cap)),
        h('label.check', rules.require_bill_photo, h('span', t('Ask customers for a bill photo'))), field('Shop radius (metres, 0 = off)', rules.max_distance_m, 'Purchases from farther away are flagged for your review.'),
        h('button.btn', { style: 'justify-self:start', onclick: save(rules) }, t('Save rules'))),
      servicesCard(b), teamCard(),
      h('div.card.stack', h('h3', t('Danger zone')), h('p.muted.small', t('Making a new QR code stops the old printed QR from working.')),
        h('button.btn.danger', { style: 'justify-self:start', onclick: async () => { if (await confirmBox(t('Make a new QR code? Printed QR codes will stop working.'), t('Make new QR'), true)) { const r = await api('b/' + code() + '/regenerate-qr/', 'POST'); localStorage.fx_biz = r.shop_code; await FX.reloadShops(); FX.render(); } } }, t('Make a new QR code'))));
  };

  /* ---------- billing ---------- */
  const loadRz = () => FX.loadRazorpay();
  R.billing = async function () {
    const s = await FX.loadSub();
    const plan = k => s.plans[k];
    const checkout = k => async e => busy(e.target, async () => {
      let order;
      try {
        order = await api('billing/order/', 'POST', { plan: k });
        await loadRz();
      } catch (x) {
        if (methods.upi) {
          toast(t('Razorpay is unavailable. Continue with UPI and submit your screenshot for approval.'));
          payUpi(k);
          return;
        }
        throw x;
      }
      const widget = new window.Razorpay({ key: order.key, order_id: order.order_id, amount: order.amount,
        currency: order.currency, name: 'OFFLet', description: plan(k).label, theme: { color: '#5e35b1' },
        handler: async resp => { try { await api('billing/verify/', 'POST', resp); toast(t('Payment received. Thank you!')); await FX.loadSub(); FX.render(); } catch (x) { toast(x.message, true); } } });
      widget.on('payment.failed', resp => toast(resp.error?.description || t('Payment failed. Please try again.'), true));
      widget.open();
    });
    const subscribe = k => async e => busy(e.target, async () => {
      const r = await api('billing/autopay/', 'POST', { plan: k }); await loadRz();
      new window.Razorpay({ key: r.key, subscription_id: r.subscription_id, name: 'OFFLet', description: plan(k).label, theme: { color: '#5e35b1' },
        handler: async resp => { try { await api('billing/autopay/verify/', 'POST', { razorpay_payment_id: resp.razorpay_payment_id, razorpay_subscription_id: resp.razorpay_subscription_id, razorpay_signature: resp.razorpay_signature }); toast(t('Payment received. Thank you!')); await FX.loadSub(); FX.render(); } catch (x) { toast(x.message, true); } } }).open();
    });
    const payUpi = k => {
      const utr = inp({ maxlength: 20, autocomplete: 'off', required: true });
      const proof = inp({ type: 'file', accept: 'image/*', required: true });
      const error = h('div.err', { role: 'alert' });
      const form = h('form.stack', { onsubmit: async e => {
        e.preventDefault();
        if (!utr.value.trim() || !proof.files.length) { error.textContent = t('Enter the transaction reference and attach a payment screenshot.'); return; }
        const data = new FormData(); data.append('plan', k); data.append('utr', utr.value.trim()); data.append('proof', proof.files[0]);
        try {
          await api('billing/upi/', 'POST', data); dialog.close(); toast(t('UPI payment submitted for admin verification.'));
          await FX.loadSub(); FX.render();
        } catch (x) { error.textContent = x.message; }
      } },
        h('p.muted', t('Pay exactly {a} to the platform UPI ID, then upload the completed-payment screenshot and UTR.', { a: FX.rupee(plan(k).amount / 100) })),
        h('p', h('b', t('Platform UPI ID: {upi}', { upi: s.upi_id }))),
        h('img', { src: '/api/billing/upi-qr.png?plan=' + encodeURIComponent(k) + '&ref=' + encodeURIComponent(s.owner_ref),
          alt: t('UPI payment QR code'), width: 220, height: 220, style: 'justify-self:center;background:#fff' }),
        h('a.btn.ghost', { href: s.upi_links[k] }, t('Open UPI app')),
        field('UPI transaction reference / UTR', utr),
        field('Payment screenshot (image, up to 5 MB)', proof),
        error, h('button.btn', { type: 'submit' }, t('Submit for admin verification')));
      const dialog = modal(t('Pay by UPI'), form);
    };
    const methods = s.payment_methods || {}, saving = s.yearly_saving || 0;
    const live = s.state === 'active' || s.state === 'trial';
    const pct = s.state === 'trial' ? Math.max(4, Math.min(100, Math.round(100 * (s.trial_days - s.days_until_end) / s.trial_days))) : 100;
    const stateHead = { trial: t('Free trial: {n} days left', { n: s.days_until_end }), active: t('Active until {d}', { d: FX.fmtDate(s.ends) }),
      grace: t('Plan ended. Your shop is paused.'), expired: t('Plan ended') }[s.state] || s.state;
    const stateSub = s.state === 'grace' ? t('Renew within {n} days to keep everything.', { n: Math.max(0, Math.ceil((new Date(s.data_until) - Date.now()) / 864e5)) })
      : s.state === 'expired' ? t('Renew any time to restore your QR, customers and rewards.')
      : s.autorenew ? t('AutoPay is on. Next charge on {d}.', { d: FX.fmtDate(s.next_charge || s.ends) })
      : s.state === 'trial' ? t('Pick a plan before it ends to keep your shop live.') : t('Renew before it ends to avoid a pause.');
    const pendingBox = s.pending_payment ? h('div.banner.blue', h('div.grow', h('b', '⏳ ' + t('UPI payment verification pending')), h('div.small', t('Transaction reference: {utr}. Your plan activates after an admin verifies the payment.', { utr: s.pending_payment.utr || '—' })))) : null;
    const rejectedBox = s.last_rejected ? h('div.banner.red', h('div.grow', h('b', t('We could not verify your last UPI payment')), h('div.small', t('Reference {utr}. Check the amount and reference, then submit it again below.', { utr: s.last_rejected.utr || '—' })))) : null;
    const FEATURES = ['Unlimited customers and rewards', 'Counter code and instant approvals', 'Offers, boosts and bookings', 'Insights, CSV export and print kit', 'Hindi and English for your customers'];
    const planCard = k => {
      const p = plan(k), best = k === 'yearly', per = best ? p.amount / 100 / 12 : null;
      const lowerPlanBlocked = k === 'monthly' && s.active_plan === 'yearly';
      return h('div.plan' + (best ? '.best' : ''), best && saving ? h('span.ribbon', t('Save {a}', { a: FX.rupee(saving / 100) })) : null,
        h('div', h('h3', t(p.label)), h('div.price', FX.rupee(p.amount / 100), h('small', ' / ' + t(best ? 'year' : 'month')))),
        h('small.muted', best ? t('Just {a} a month. Includes GST.', { a: FX.rupee(Math.round(per)) }) : t('Includes GST. {n} days.', { n: p.days })),
        lowerPlanBlocked ? h('p.small.muted', t('Your active yearly plan cannot be changed to monthly before it ends.')) : null,
        h('ul', FEATURES.map(f => h('li', t(f)))),
        methods.online ? h('button.btn.lg' + (best ? '.gold' : ''), { disabled: lowerPlanBlocked, onclick: checkout(k) }, t('Pay securely with Razorpay')) : null,
        methods.upi ? h('button.btn' + (!methods.online && best ? '.gold' : '.ghost'), { disabled: lowerPlanBlocked, onclick: () => payUpi(k) },
          t(methods.online ? 'Pay by UPI and upload screenshot' : 'Pay by UPI and upload screenshot for approval')) : null,
        s.autopay && !s.autorenew && !s.autopay_pending ? h('button.btn.ghost', { disabled: lowerPlanBlocked, onclick: subscribe(k) }, t('Enable AutoPay')) : null,
        !methods.online && !methods.upi ? h('p.small.muted', t('Online payments are not set up yet. Please contact support.')) : null);
    };
    const METHOD = { gateway: 'Razorpay', upi: 'UPI' }, STAT = { paid: ['Paid', 'ok'], pending: ['Verifying', 'warn'], rejected: ['Not verified', 'bad'], refunded: ['Refunded', ''] };
    return h('div.stack.l', { style: 'max-width:860px' }, h('h1', t('Billing')),
      h('div.state-card' + (live ? (s.state === 'trial' ? '.trial' : '') : '.bad'),
        h('div.row.between.wrap', h('div', h('h2', stateHead), h('p', stateSub)), pill(t(s.state), live ? 'ok' : 'bad')),
        s.state === 'trial' ? h('div.meter', h('i', { style: { width: pct + '%' } })) : null),
      pendingBox, rejectedBox,
      s.payment_mode === 'test' ? h('p.card.small.muted', t('Razorpay test mode: payments are simulated and will not charge a real account.')) : null,
      h('div.plans', Object.keys(s.plans).map(planCard)),
      s.autopay_pending ? h('p.small.muted', t('AutoPay setup is waiting for your approval in your UPI or card app.')) : null,
      s.autorenew || s.autopay_pending ? h('button.btn.danger', { style: 'justify-self:start', onclick: async () => { if (await confirmBox(t('Turn off AutoPay? Your plan stays active until it ends.'), t('Turn off'), true)) { await api('billing/autopay/cancel/', 'POST'); toast(t('AutoPay turned off')); FX.render(); } } }, t('Turn off AutoPay')) : null,
      s.payments && s.payments.length ? h('div.card.paylist', h('h3', t('Payment history')), s.payments.map(p => {
        const inv = s.invoices.find(i => i.no && i.no === p.invoice_no), st = STAT[p.status] || [p.status, ''];
        return h('div.li', h('div.grow', h('b', FX.rupee(p.amount / 100) + ' · ' + t((s.plans[p.plan] || { label: p.plan }).label)), h('small.muted', FX.fmtDate(p.created_at) + ' · ' + (METHOD[p.method] || p.method) + (p.invoice_no ? ' · ' + p.invoice_no : ''))),
          pill(t(st[0]), st[1]), inv ? h('a.btn.ghost.sm', { href: inv.url, target: '_blank', rel: 'noopener' }, t('Invoice')) : null);
      })) : null,
      h('p.small.muted', t('If payments stop, your data is kept for {m} months before deletion.', { m: s.retention_months })),
      h('p.small.muted', h('a', { href: '/refund/' }, t('Refund policy')), ' · ', h('a', { href: '/contact/' }, t('Need help? Contact us'))));
  };
})(window.FX);
