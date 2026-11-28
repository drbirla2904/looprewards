/* OFFLet v2 customer screens: wallet home, shop page (earn / rewards / book / history / invite), rewards, bookings. */
(function (FX) {
  'use strict';
  const { h, t, api, S, field, inp, sel, pill, empty, avatar, stampRow, tierPill, toast, modal, busy } = Object.assign({}, FX, { t: FX.t, S: FX.S });
  const R = FX.routes.customer;
  const TYPE_HINT = { count: 'How many?', amount: 'Bill amount (₹)', visit: 'Visit' };
  const SOCIALS = [
    ['instagram_url', 'Instagram', 'instagram'],
    ['facebook_url', 'Facebook', 'facebook'],
    ['youtube_url', 'YouTube', 'youtube'],
    ['tiktok_url', 'TikTok', 'tiktok'],
    ['x_url', 'X', 'x']
  ];
  const svg = (name, attrs, ...kids) => {
    const el = document.createElementNS('http://www.w3.org/2000/svg', name);
    for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, value);
    kids.forEach(child => el.appendChild(child));
    return el;
  };
  const SHOP_ICONS = {
    instagram: svg('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': '2', 'aria-hidden': 'true' },
      svg('rect', { x: 3, y: 3, width: 18, height: 18, rx: 5 }), svg('circle', { cx: 12, cy: 12, r: 4 }),
      svg('circle', { cx: 17.5, cy: 6.5, r: 1, fill: 'currentColor', stroke: 'none' })),
    facebook: svg('svg', { viewBox: '0 0 24 24', fill: 'currentColor', 'aria-hidden': 'true' },
      svg('path', { d: 'M13.5 21v-8h2.7l.4-3h-3.1V8.1c0-.9.3-1.6 1.6-1.6h1.7V3.8c-.3 0-1.3-.1-2.5-.1-2.5 0-4.2 1.5-4.2 4.3V10H7.3v3h2.8v8h3.4Z' })),
    tiktok: svg('svg', { viewBox: '0 0 24 24', fill: 'currentColor', 'aria-hidden': 'true' },
      svg('path', { d: 'M19.6 6.2a5.3 5.3 0 0 1-3.3-3.8V2h-4v13.6a2.8 2.8 0 1 1-2-2.7V8.8a6.8 6.8 0 1 0 6 6.8V9.1a9.3 9.3 0 0 0 5 1.5v-4a5.3 5.3 0 0 1-1.7-.4Z' })),
    x: svg('svg', { viewBox: '0 0 24 24', fill: 'currentColor', 'aria-hidden': 'true' },
      svg('path', { d: 'M18.9 2H22l-6.8 7.8L23.2 22h-6.3L12 14.6 5.6 22H2.5l7.3-8.4L1.9 2h6.5l4.5 6.8L18.9 2Zm-1.1 18h1.7L7.4 3.9H5.6L17.8 20Z' })),
    youtube: svg('svg', { viewBox: '0 0 24 24', fill: 'currentColor', 'aria-hidden': 'true' },
      svg('path', { d: 'M23.5 6.2a3 3 0 0 0-2.1-2.1C19.5 3.6 12 3.6 12 3.6s-7.5 0-9.4.5A3 3 0 0 0 .5 6.2 31 31 0 0 0 0 12a31 31 0 0 0 .5 5.8 3 3 0 0 0 2.1 2.1c1.9.5 9.4.5 9.4.5s7.5 0 9.4-.5a3 3 0 0 0 2.1-2.1A31 31 0 0 0 24 12a31 31 0 0 0-.5-5.8ZM9.6 15.6V8.4l6.3 3.6-6.3 3.6Z' })),
    whatsapp: svg('svg', { viewBox: '0 0 24 24', fill: 'currentColor', 'aria-hidden': 'true' },
      svg('path', { d: 'M20.52 3.48A11.88 11.88 0 0 0 12.08 0C5.48 0 .11 5.36.11 11.96c0 2.11.55 4.17 1.6 5.99L0 24l6.22-1.63a11.97 11.97 0 0 0 5.86 1.49h.01c6.6 0 11.97-5.37 11.97-11.97 0-3.2-1.25-6.2-3.54-8.41ZM12.09 21.83h-.01c-1.83 0-3.63-.49-5.2-1.42l-.37-.22-3.69.97.99-3.6-.24-.37a9.82 9.82 0 0 1-1.51-5.23c0-5.43 4.42-9.85 9.86-9.85a9.8 9.8 0 0 1 6.97 2.89 9.78 9.78 0 0 1 2.88 6.96c0 5.44-4.43 9.86-9.87 9.86Zm5.41-7.38c-.3-.15-1.77-.87-2.05-.97-.28-.1-.48-.15-.68.15-.2.3-.78.97-.95 1.17-.17.2-.35.23-.65.08-.3-.15-1.27-.47-2.42-1.5-.9-.8-1.51-1.78-1.68-2.08-.18-.3-.02-.46.13-.61.13-.13.3-.35.45-.52.15-.18.2-.3.3-.5.1-.2.05-.38-.03-.53-.07-.15-.68-1.64-.93-2.24-.24-.59-.49-.51-.68-.52h-.58c-.2 0-.53.08-.8.38-.28.3-1.05 1.02-1.05 2.5s1.08 2.9 1.23 3.1c.15.2 2.12 3.24 5.13 4.54.72.31 1.28.5 1.72.64.72.23 1.37.2 1.88.12.57-.08 1.77-.72 2.02-1.42.25-.7.25-1.3.18-1.42-.08-.13-.28-.2-.58-.35Z' })),
    phone: svg('svg', { viewBox: '0 0 24 24', fill: 'currentColor', 'aria-hidden': 'true' },
      svg('path', { d: 'M6.62 10.79a15.05 15.05 0 0 0 6.59 6.59l2.2-2.2a1 1 0 0 1 1.02-.24 11.36 11.36 0 0 0 3.56.57 1 1 0 0 1 1 1V20a1 1 0 0 1-1 1A17 17 0 0 1 3 4a1 1 0 0 1 1-1h3.5a1 1 0 0 1 1 1 11.36 11.36 0 0 0 .57 3.56 1 1 0 0 1-.25 1.02l-2.2 2.21Z' })),
    map: svg('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': '2', 'aria-hidden': 'true' },
      svg('path', { d: 'M20 10c0 5-8 12-8 12S4 15 4 10a8 8 0 1 1 16 0Z' }), svg('circle', { cx: 12, cy: 10, r: 2.5 })),
    clock: svg('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': '2', 'aria-hidden': 'true' },
      svg('circle', { cx: 12, cy: 12, r: 9 }), svg('path', { d: 'M12 7v5l3 2' }))
  };
  const shopIcon = name => SHOP_ICONS[name].cloneNode(true);

  function ratingSummary(shop) {
    const average = shop.rating_average;
    const count = Number(shop.rating_count || 0);
    if (!count) return null;
    return h('span.shop-rating', { 'aria-label': t('Average rating: {rating} out of 5', {
      rating: Number(average).toFixed(1)
    }) }, FX.stars(Number(average)), h('b', Number(average).toFixed(1)));
  }

  /* ---------- home: one punch card per shop ---------- */
  function shopCard(s) {
    const b = s.best, tier = s.tier;
    return h('a.shopcard' + (s.active_rewards ? '.ready' : ''), { href: '#/shop/' + s.shop_code, style: FX.shopVars(s.brand_color), 'aria-label': s.shop },
      h('div.row', h('div.logo-s', s.logo_url ? h('img', { src: s.logo_url, alt: '' }) : FX.initial(s.shop)), h('div.grow', h('h3', s.shop), ratingSummary(s), h('small.shop-category', FX.lang === 'hi' ? s.category_label_hi : s.category_label)),
        tierPill(tier.tier)),
      b ? h('div.stack.s', h('div.row.between', h('small', b.title), h('small.num', FX.fmtVal(b.type, b.current) + ' / ' + FX.fmtVal(b.type, b.target))),
        stampRow(b.current, b.target, b.type) || h('div.meter', h('i', { style: { width: b.pct + '%' } })),
        b.rewards[0] ? h('small', t('Reward: {r}', { r: b.rewards[0].title })) : null) : h('small', t('Make your first purchase to start collecting.')),
      h('div.meta', s.active_rewards ? h('span.pill.glow', '🎁 ' + t('{n} reward ready', { n: s.active_rewards })) : null,
        s.coins != null && s.coins > 0 ? h('span.pill', '🪙 ' + t('{n} coins', { n: s.coins })) : null,
        s.streak ? h('span.pill', '🔥 ' + t('{n}-week streak', { n: s.streak })) : null,
        s.boosts_now[0] ? h('span.pill', '⚡ ' + s.boosts_now[0].multiplier + 'x ' + t('today')) : null,
        s.next_booking ? h('span.pill', '📅 ' + FX.fmtDT(s.next_booking.starts_at)) : null,
        tier.next ? h('small', t('{n} more visits to {tier}', { n: tier.to_next, tier: t(tier.next === 'gold' ? 'Gold' : 'Silver') })) : null));
  }
  R[''] = async function () {
    const w = await api('me/wallet/');
    const code = inp({ ph: 'Shop code', maxlength: 12, 'aria-label': t('Shop code') });
    const search = inp({ ph: 'Search shop name or area', maxlength: 120, 'aria-label': t('Search shops') });
    const discoverBox = h('div.g2');
    let userLoc = null;
    const discover = async () => {
      discoverBox.replaceChildren(h('div.card.muted', t('Finding shops...')));
      try {
        const params = new URLSearchParams();
        if (search.value.trim()) params.set('q', search.value.trim());
        if (userLoc) { params.set('lat', userLoc.lat); params.set('lng', userLoc.lng); }
        const r = await api('shops/discover/?' + params.toString());
        discoverBox.replaceChildren(...(r.shops.length ? r.shops.map(s => h('a.shopcard', {
          href: '#/shop/' + s.shop_code, style: FX.shopVars(s.brand_color)
        }, h('div.row', h('div.logo-s', s.logo_url ? h('img', { src: s.logo_url, alt: '' }) : FX.initial(s.name)),
          h('div.grow', h('h3', s.name), ratingSummary(s), h('small.shop-category', FX.lang === 'hi' ? s.category_label_hi : s.category_label)),
          s.distance_km != null ? h('small.pill', s.distance_km < 1 ? '< 1 km' : s.distance_km + ' km') : null),
        s.tagline ? h('small', s.tagline) : null,
          s.address ? h('small.muted', s.address) : null,
          h('span.pill', s.joined ? t('Joined') : t('View shop')))) : [empty('No shops found', 'Try another name or area.')]));
      } catch (e) {
        discoverBox.replaceChildren(h('div.card', h('p.err', e.message)));
      }
    };
    let searchTimer = null;
    search.addEventListener('input', () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(discover, 300);
    });
    const nearbyBtn = h('button.btn.ghost', { onclick: () => {
      if (!navigator.geolocation) return toast(t('Location is not supported on this device.'));
      navigator.geolocation.getCurrentPosition(pos => {
        userLoc = { lat: pos.coords.latitude, lng: pos.coords.longitude };
        discover();
      }, () => toast(t('Location permission was denied. Search by name instead.')), {
        enableHighAccuracy: false, timeout: 10000, maximumAge: 300000
      });
    } }, '📍 ' + t('Near me'));
    discover();
    const hr = new Date().getHours(), hello = hr < 12 ? 'Good morning' : hr < 17 ? 'Good afternoon' : 'Good evening';
    const name = (S.user && S.user.name) || '';
    const hero = h('div.hero-me', h('div', h('h1', t(hello) + (name ? ', ' + name : '')),
      h('p', w.total_rewards ? t('{n} rewards ready to use', { n: w.total_rewards }) : w.shops.length ? t('Keep collecting. Your next reward is closer than you think.') : t('Scan a shop QR code to get your first stamp.'))),
      w.shops.length ? h('div.hero-stats', h('div.hero-stat', h('b', w.total_rewards), h('span', t('Rewards ready'))), h('div.hero-stat', h('b', w.shops.length), h('span', t('Shops'))), h('div.hero-stat', h('b', w.total_visits), h('span', t('Visits')))) : null);
    const supportOfflet = () => {
      const amount = inp({ type: 'number', inputmode: 'decimal', min: '1', max: '100000', step: '0.01', required: true,
        ph: 'Donation amount (₹)', 'aria-label': t('Donation amount in rupees') });
      const error = h('p.err', { role: 'alert' });
      let dialog;
      const pay = h('button.btn.block', { type: 'button', onclick: e => busy(e.currentTarget, async () => {
        const value = Number(amount.value);
        if (!amount.value || !amount.checkValidity() || !Number.isFinite(value) || value < 1 || value > 100000) {
          error.textContent = t('Enter an amount between ₹1 and ₹100,000, in whole paise.');
          amount.focus();
          return;
        }
        error.textContent = '';
        const order = await api('billing/donation/order/', 'POST', { amount: amount.value });
        if (order.method === 'upi') {
          dialog.close();
          toast(t('Opening your UPI app to pay OFFLet.'));
          location.href = order.upi_link;
          return;
        }
        try {
          await FX.loadRazorpay();
        } catch (failure) {
          if (order.upi_link) {
            dialog.close();
            toast(t('Razorpay is unavailable. Opening your UPI app instead.'));
            location.href = order.upi_link;
            return;
          }
          throw failure;
        }
        const checkout = new window.Razorpay({
          key: order.key, order_id: order.order_id, amount: order.amount, currency: order.currency,
          name: 'OFFLet', description: t('Voluntary support for OFFLet'), image: '/icon.svg',
          theme: { color: '#5e35b1' },
          handler: async response => {
            try {
              const result = await api('billing/donation/verify/', 'POST', response);
              dialog.close();
              toast(FX.tr(result.detail) || t('Thank you for supporting OFFLet.'));
            } catch (failure) {
              toast(failure.message, true);
            }
          }
        });
        checkout.on('payment.failed', response => toast(response.error?.description || t('Payment failed. Please try again.'), true));
        dialog.close();
        checkout.open();
      }) }, t('Continue to payment'));
      dialog = modal(t('Support OFFLet'), h('div.stack',
        h('p.muted', t('OFFLet is free for customers. Your voluntary support helps keep it available.')),
        field('Donation amount (₹)', amount), error, pay));
    };
    const how = h('div.card.stack', h('h3', t('How it works')),
      [['📷', 'Scan the QR code at the counter'], ['✅', 'Tap once after you buy to collect a stamp'], ['🎁', 'Show your reward pass and enjoy']].map(([e, x]) => h('div.row', h('span', { style: 'font-size:calc(26px * var(--font-scale, .8))' }, e), h('span', t(x)))));
    const tiles = FX.tiles([['🏪', 'Add shop', () => { code.focus(); code.scrollIntoView({ behavior: 'smooth', block: 'center' }); }], ['🎁', 'My rewards', '#/rewards', w.total_rewards || null], ['🔔', 'Alerts', FX.inbox, S.unread || null], ['👤', 'Account', '#/account']]);
    return h('div.stack.l', hero, tiles,
      w.shops.length ? h('div.section-t', t('My shops')) : null,
      w.shops.length ? h('div.g2', w.shops.map(shopCard)) : how,
      h('div.card.stack', h('div.row.between', h('h3', t('Discover shops')), nearbyBtn),
        h('div.row', search), discoverBox),
      h('div.card.stack', h('h3', t('Add a shop by code')), h('div.row', code, h('button.btn', { onclick: () => { const c = code.value.trim(); if (c) FX.go('shop/' + encodeURIComponent(c)); } }, t('Open')))),
      h('div.card.stack', h('div', h('h3', t('Support OFFLet')), h('p.muted.small', t('OFFLet is free for customers. Your voluntary support helps keep it available.'))),
        h('button.btn.soft.block', { onclick: supportOfflet }, t('Donate to OFFLet'))));
  };
  R.shop = async function (args) {
    const [codeAndQuery = ''] = args;
    const [code, query = ''] = codeAndQuery.split('?');
    const params = new URLSearchParams(query);
    return FX.shopPage(code, params.get('tab'), params.get('ref'));
  };

  /* ---------- logged-out shop page (QR landing) ---------- */
  FX.publicShop = async function (code) {
    let biz;
    try { biz = await api('b/' + code + '/'); } catch (e) { return h('div.page', empty('Shop not found', 'Check the code and try again.', h('a.btn', { href: '/app/' }, t('Go to OFFLet')))); }
    if (biz.paused) return h('div.page', empty(biz.name, 'This shop is not taking rewards right now.'));
    const perk = biz.perks && biz.perks.welcome;
    return h('div.page', { style: 'max-width:720px' }, head(biz), offerCatalog(biz),
      h('div.card.stack', { style: 'margin-top:16px' }, h('h2', t('Collect rewards at {shop}', { shop: biz.name })),
        h('p.muted', t('Join in 10 seconds with your mobile number. No app to install.')),
        perk ? h('div.banner.green', '🎁 ' + t('Welcome gift: {r}', { r: perk.title })) : null,
        biz.boosts_now.length ? h('div.boost', '⚡ ' + biz.boosts_now[0].title + ' (' + biz.boosts_now[0].multiplier + 'x)') : null,
        biz.programs.slice(0, 1).map(p => h('div.stack.s', p.tasks.map(tk => h('div.li', h('span', '✦'), h('div.grow', h('b', tk.title), tk.rewards[0] ? h('div.small.muted', t('Reward: {r}', { r: tk.rewards[0].title })) : null))))),
        h('button.btn.lg', { onclick: () => { const m = modal(t('Join {shop}', { shop: biz.name }), FX.authScreen({ mode: 'register', role: 'customer' }).querySelector('.form')); } }, t('Join and start earning')),
        h('button.btn.ghost', { onclick: () => { const m = modal(t('Log in'), FX.authScreen({ mode: 'login' }).querySelector('.form')); } }, t('I already have an account'))),
      biz.services.length ? h('div.card', h('h3', t('Services')), biz.services.map(s => h('div.li', h('span.grow', s.name), h('b.num', FX.rupee(s.price))))) : null);
  };

  function offerCatalog(biz) {
    if (!biz.offers || !biz.offers.length) return null;
    return h('div.card.stack', h('h2', t('Shop offers')), biz.offers.map(offer => {
      const label = offer.offer_type === 'percent_off' ? Number(offer.value) + '% off' :
        offer.offer_type === 'fixed_price' ? t('Fixed price') : t('Buy 1 get 1');
      const left = offer.ends_on ? Math.ceil((new Date(offer.ends_on + 'T23:59:59') - Date.now()) / 864e5) : null;
      return h('div.offer-group.stack.s', h('div.row.between.wrap', h('span.offer-badge', label),
        left != null ? h('span.offer-left' + (left <= 2 ? '.hot' : ''), left <= 0 ? t('Ends today') : left === 1 ? t('1 day left') : t('{n} days left', { n: left })) : null),
        offer.title ? h('b.offer-title', offer.title) : null,
        h('div.offer-customer-items', offer.items.map(item => {
        const price = Number(item.price), current = offer.offer_type === 'percent_off' ? price * (1 - Number(offer.value) / 100) : Number(item.offer_price);
        return h('div.offer-customer-item', item.image ? h('img.offer-thumb', { src: item.image, alt: item.name }) : null,
          h('div.grow', h('b', item.name), h('div.offer-price',
            offer.offer_type === 'fixed_price' || offer.offer_type === 'percent_off' ? h('b', FX.rupee(current)) : null,
            offer.offer_type === 'fixed_price' || offer.offer_type === 'percent_off' ? h('del', FX.rupee(price)) : h('b', FX.rupee(price)))));
      })));
    }));
  }

  function head(biz) {
    const c = FX.shopVars(biz.brand_color);
    const hasLocation = biz.lat != null && biz.lng != null && Number.isFinite(Number(biz.lat)) && Number.isFinite(Number(biz.lng));
    const directionsUrl = biz.maps_url || (hasLocation ? 'https://www.google.com/maps/search/?api=1&query=' + encodeURIComponent(biz.lat + ',' + biz.lng) : '');
    const socialLinks = SOCIALS.filter(([key]) => biz[key]).map(([key, name, icon]) =>
      h('a.social-link.' + icon, { href: biz[key], target: '_blank', rel: 'noopener noreferrer', title: t('Follow on {platform}', { platform: name }), 'aria-label': t('Follow on {platform}', { platform: name }) }, shopIcon(icon)));
    const contactLink = (href, label, icon, extra) =>
      h('a.shop-contact-action', Object.assign({ href, title: t(label), 'aria-label': t(label) }, extra || {}), shopIcon(icon));
    const links = [
      biz.phone && contactLink('tel:' + biz.phone, 'Call', 'phone'),
      biz.whatsapp && contactLink('https://wa.me/' + biz.whatsapp.replace(/\D/g, ''), 'WhatsApp', 'whatsapp', { target: '_blank', rel: 'noopener noreferrer' }),
      directionsUrl && contactLink(directionsUrl, 'Directions', 'map', { target: '_blank', rel: 'noopener noreferrer' })
    ].filter(Boolean);
    const contactActions = biz.hours || socialLinks.length || links.length ? h('div.shop-contact-actions',
      biz.hours ? h('span.shop-hours', { title: t('Open: {h}', { h: biz.hours }) },
        shopIcon('clock'), h('span', t('Open: {h}', { h: biz.hours }))) : null,
      socialLinks, links) : null;
    return h('div.stack', h('div.shophead', { style: c },
      h('div.shophead-main', h('div.logo-s', biz.logo_url ? h('img', { src: biz.logo_url, alt: '' }) : FX.initial(biz.name)),
        h('div.grow', h('h1', biz.name), h('div.small', FX.lang === 'hi' ? biz.category_label_hi : biz.category_label), ratingSummary(biz), biz.tagline ? h('div.small', biz.tagline) : null, biz.address ? h('div.small.muted', biz.address) : null)),
      contactActions),
      biz.about ? h('p.muted', biz.about) : null);
  }

  /* ---------- logged-in shop page ---------- */
  FX.shopPage = async function (code, tab, referral) {
    let biz = await api('b/' + code + '/'), me;
    if (biz.paused) return empty(biz.name, 'This shop is not taking rewards right now.');
    try { me = await api('me/shop/' + code + '/'); } catch (e) { me = null; }
    if (!me) return joinView(biz, referral);
    let spinData = null;
    try { spinData = await api('b/' + code + '/spin/'); } catch (e) { /* A missing wheel is not an error on the shop page. */ }
    const asked = new URLSearchParams(location.search).get('tab');  // set when a notification is tapped
    tab = tab || (['earn', 'rewards', 'book', 'history', 'invite', 'spin'].includes(asked) ? asked : null) || sessionStorage['tab_' + code] || 'earn';
    const body = h('div.stack');
    const tabs = [['earn', 'Earn'], ['rewards', 'Rewards' + (me.active_rewards ? ' (' + me.active_rewards + ')' : '')]];
    if (spinData && spinData.available) tabs.push(['spin', 'Spin & Win']);
    if (biz.bookings_enabled && biz.services.length) tabs.push(['book', 'Book']);
    tabs.push(['history', 'History'], ['invite', 'Invite']);
    if (!tabs.some(([key]) => key === tab)) tab = 'earn';
    const bar = h('div.seg', { role: 'tablist', style: 'overflow:auto;max-width:100%' });
    const draw = () => {
      sessionStorage['tab_' + code] = tab;
      bar.replaceChildren(...tabs.map(([k, l]) => h('button', { role: 'tab', 'aria-selected': String(k === tab), onclick: () => { tab = k; draw(); } }, t(l.split(' (')[0]) + (l.includes('(') ? ' (' + me.active_rewards + ')' : ''))));
      body.replaceChildren(tab === 'spin' ? FX.spinTab(biz, spinData) :
        ({ earn: earnTab, rewards: rewardsTab, book: bookTab, history: historyTab, invite: inviteTab })[tab](biz, me));
    };
    const goTab = k => { tab = k; draw(); window.scrollTo({ top: bar.offsetTop - 70, behavior: 'smooth' }); };
    draw();
    watchPending(biz, me);
    const ti = me.tier;
    return h('div.stack.l', { style: Object.assign({ maxWidth: '760px', margin: '0 auto', width: '100%' }, FX.shopVars(biz.brand_color)) }, head(biz), socialFollowCard(biz, me), offerCatalog(biz), focusCard(biz, me, goTab),
      h('div.card.row.between.wrap', h('div.row', tierPill(ti.tier), h('div', h('div.bold', t('{n} visits', { n: ti.visits })), ti.perk ? h('small.muted', ti.perk) : null)),
        ti.next ? h('small.muted', t('{n} more visits to {tier}', { n: ti.to_next, tier: t(ti.next === 'gold' ? 'Gold' : 'Silver') }) + (ti.next_perk ? ': ' + ti.next_perk : '')) : h('small.muted', t('Top tier reached')),
        streakView(me)),
      me.boosts_now[0] ? h('div.boost', '⚡ ' + t('{t}: earn {n}x stamps right now', { t: me.boosts_now[0].title, n: me.boosts_now[0].multiplier })) : null,
      bar, body);
  };

  /* what matters most right now: a ready reward, or how close the next one is */
  function focusCard(biz, me, goTab) {
    if (me.active_rewards) {
      return h('div.focus.ready', FX.ring(100, '🎁', '', 84), h('div.stack.s', h('h3', t('{n} reward ready to use', { n: me.active_rewards })),
        h('div.row.wrap', h('button.btn.gold', { onclick: () => goTab('rewards') }, t('Show my reward')), me.next_expiry ? h('small.muted', FX.until(me.next_expiry)) : null)));
    }
    const b = me.best;
    if (!b) return null;
    const left = Math.max(0, Number(b.target) - Number(b.current)), whole = Math.ceil(left - 1e-9);
    const msg = b.type === 'amount' ? t('Spend {a} more to unlock: {r}', { a: FX.rupee(left), r: b.rewards[0].title })
      : whole <= 1 ? t('One more to unlock: {r}', { r: b.rewards[0].title }) : t('{n} more to unlock: {r}', { n: whole, r: b.rewards[0].title });
    return h('div.focus', FX.ring(b.pct, Math.round(b.pct) + '%', t('done'), 84), h('div.stack.s', h('small.muted', b.title), h('h3', b.rewards[0].title), h('div.nudge', msg)));
  }
  function streakView(me) {
    if (!me.streak) return h('small.muted', t('Visit this week to start a streak'));
    const dots = h('div.week', Array.from({ length: Math.min(me.streak, 8) }, (_, i) => h('i.on' + (i === Math.min(me.streak, 8) - 1 && me.streak_this_week ? '.now' : ''), '🔥')));
    return h('div.stack.s', h('span.flame', '🔥 ' + t('{n}-week streak', { n: me.streak })), dots,
      me.streak_this_week ? null : h('small', { style: 'color:var(--red)' }, t('Visit this week to keep your streak')));
  }

  /* While a purchase waits for the shop, quietly check and celebrate the moment it is approved. */
  let watcher = null;
  function watchPending(biz, me) {
    clearInterval(watcher);
    const waiting = new Set(me.entries.filter(e => e.status === 'pending').map(e => e.id));
    if (!waiting.size) return;
    const seen = new Set(me.rewards.map(g => g.code));
    watcher = setInterval(async () => {
      if (document.hidden) return;
      if (!document.querySelector('.focus, .shophead')) { clearInterval(watcher); return; }
      let fresh;
      try { fresh = await api('me/shop/' + biz.shop_code + '/'); } catch (e) { return; }
      const done = fresh.entries.filter(e => waiting.has(e.id) && e.status !== 'pending');
      if (!done.length) return;
      clearInterval(watcher);
      await afterEntry(biz, fresh, seen, done.some(e => e.status === 'approved') ? 'approved' : 'rejected', me);
    }, 6000);
  }
  async function refreshShop(code) { const v = document.querySelector('#view'); if (v) v.replaceChildren(await FX.shopPage(code)); }
  /* Show every benefit from an approved visit together, then refresh the shop wallet. */
  async function afterEntry(biz, me, seenCodes, status, previousMe) {
    const fresh = me.rewards.filter(g => g.status === 'active' && !seenCodes.has(g.code));
    if (status === 'approved') {
      const oldTickets = new Set((previousMe && previousMe.scratch_tickets || []).map(ticket => ticket.id));
      const newTickets = (me.scratch_tickets || []).filter(ticket => !oldTickets.has(ticket.id));
      const coinGain = Math.max(0, Number(me.coins && me.coins.balance || 0) - Number(previousMe && previousMe.coins && previousMe.coins.balance || 0));
      const moments = [
        ...fresh.map(grant => ['🎁', grant.title]),
        ...(coinGain ? [['🪙', t('Coins earned') + ': +' + coinGain]] : []),
        ...(newTickets.length ? [['🎟️', t(newTickets.length === 1 ? 'Scratch card ready' : '{n} scratch cards ready', { n: newTickets.length })]] : [])
      ];
      const actions = [];
      if (fresh.length) actions.push([t('Show reward pass'), () => passModal(fresh[0], biz.brand_color, biz.name)]);
      if (newTickets.length) actions.push([t('Scratch now'), () => {
        sessionStorage['tab_' + biz.shop_code] = 'rewards';
        FX.go('shop/' + biz.shop_code + '?tab=rewards');
      }]);
      const b = me.best;
      const title = fresh.length ? t('Reward unlocked!') : newTickets.length ? t('Scratch card ready') :
        coinGain ? t('Coins earned') : t('Stamp added!');
      FX.celebrate({
        icon: fresh.length ? '🎁' : newTickets.length ? '🎟️' : coinGain ? '🪙' : '✅',
        ok: !fresh.length && !newTickets.length && !coinGain,
        big: Boolean(fresh.length || newTickets.length),
        title,
        text: moments.length ? '' : b && b.rewards[0] ? t('{p}% of the way to: {r}', { p: Math.round(b.pct), r: b.rewards[0].title }) : '',
        body: moments.length ? h('div.activity-recap', moments.map(([icon, label]) =>
          h('div.activity-recap-item', h('span', icon), h('b', label)))) : null,
        actions
      });
    } else if (status === 'rejected') {
      FX.toast(t('The shop could not confirm your last purchase.'), true);
    } else {
      FX.toast(t('Sent to the shop for confirmation.'));
    }
    await refreshShop(biz.shop_code);
  }

  function joinView(biz, referral) {
    const consent = h('input', { type: 'checkbox', checked: true });
    const ref = referral || new URLSearchParams(location.search).get('ref') || '';
    const perk = biz.perks && biz.perks.welcome;
    const socialPerk = biz.perks && biz.perks.social && SOCIALS.some(([key]) => biz[key]);
    return h('div.stack.l', { style: 'max-width:720px;margin:0 auto' }, head(biz), h('div.card.stack', h('h2', t('Join {shop}', { shop: biz.name })),
      perk ? h('div.banner.green', '🎁 ' + t('Welcome gift: {r}', { r: perk.title })) : null,
      socialPerk ? h('div.banner.green', '🎁 ' + t('Follow a social profile and show staff in store to claim: {r}', { r: socialPerk.title })) : null,
      biz.tiers.length ? h('p.muted', biz.tiers.map(x => t(x.tier === 'gold' ? 'Gold' : 'Silver') + ' = ' + x.visits + ' ' + t('visits')).join('  ·  ')) : null,
      h('label.check', consent, h('span', t('Send me offers from this shop (you can turn this off any time)'))),
      h('button.btn.lg', { onclick: e => busy(e.target, async () => { await api('b/' + biz.shop_code + '/join/', 'POST', { consent: consent.checked, ref }); await FX.start(true); if (perk) FX.celebrate({ icon: '🎁', title: t('Welcome!'), text: t('Your welcome gift unlocks after your first purchase: {r}', { r: perk.title }) }); }) }, t('Join now'))));
  }

  function socialFollowCard(biz, me) {
    const reward = me.social_follow_reward, claim = me.social_follow_claim;
    const hasSocialProfiles = SOCIALS.some(([key]) => biz[key]);
    if ((!reward && !claim) || (!hasSocialProfiles && !claim)) return null;
    const status = claim && claim.status;
    let message = hasSocialProfiles
      ? t('Follow any profile above and show it to staff in store. Staff verify before issuing this reward.')
      : t('Your shop removed its social profiles. Ask staff about your pending request.');
    if (status === 'pending') message = t('Your request is pending. Show your followed profile to shop staff.');
    else if (status === 'approved') message = t('Staff approved your follow. Your reward is in the Rewards tab.');
    else if (status === 'rejected') message = t('Staff could not verify the follow. Follow a listed profile and request again.');
    const canRequest = reward && status !== 'pending' && status !== 'approved';
    return h('div.card.stack.social-follow-card',
      h('div.row', h('span.social-reward-icon', '🎁'), h('div.grow', h('b', t('Social follow reward')), h('div.small.muted', (claim && claim.reward_title) || (reward && reward.title) || ''))),
      h('p.small.muted', message),
      canRequest ? h('button.btn.soft.sm', { style: 'justify-self:start', onclick: e => busy(e.target, async () => {
        await api('b/' + biz.shop_code + '/social-follow/claim/', 'POST', {});
        toast(t('Follow request sent. Show your profile to staff for verification.'));
        await refreshShop(biz.shop_code);
      }) }, t(status === 'rejected' ? 'Request again' : 'I followed — request reward')) : null);
  }

  /* ---------- earn: one big tap ---------- */
  const mmss = n => Math.floor(n / 60) + ':' + String(n % 60).padStart(2, '0');
  function claimBtn(biz, me, tk, live, seen) {
    const b = h('button.claim', { type: 'button' });
    let left = me.cooldown_seconds || 0;
    const paint = () => {
      b.disabled = true;
      if (!live) return b.replaceChildren(t('Not taking rewards right now'));
      if (me.entries_left_today <= 0) return b.replaceChildren(t('Daily limit reached. See you tomorrow!'));
      if (left > 0) return b.replaceChildren('⏱ ' + t('Next entry in {m}', { m: mmss(left) }));
      b.disabled = false;
      b.replaceChildren(h('span', tk.type === 'visit' ? '📍' : '✨'), t(tk.type === 'visit' ? 'Check in' : 'I made a purchase'));
    };
    paint();
    if (live && left > 0 && me.entries_left_today > 0) {
      const iv = setInterval(() => { if (!document.body.contains(b)) { if (b.dataset.seen) clearInterval(iv); return; } b.dataset.seen = '1'; left -= 1; paint(); if (left <= 0) clearInterval(iv); }, 1000);
    }
    b.addEventListener('click', e => { FX.ripple(b, e); FX.haptic(); submitSheet(biz, me, tk, seen); });
    return b;
  }
  function earnTab(biz, me) {
    const live = me.live && me.status === 'active';
    const pend = me.entries.filter(e => e.status === 'pending');
    const seen = new Set(me.rewards.map(g => g.code));
    const list = me.tasks.map(tk => h('div.task' + (pend.length ? '.waiting' : ''), h('div.row.between', h('b', tk.title), tk.repeatable && tk.completed ? pill(t('Earned {n}x', { n: tk.completed }), 'ok') : null),
      stampRow(tk.current, tk.target, tk.type, true) || null,
      h('div.bar', h('i', { style: { width: tk.pct + '%' } })),
      h('div.row.between', h('small.muted', FX.fmtVal(tk.type, tk.current) + ' / ' + FX.fmtVal(tk.type, tk.target)), tk.rewards[0] ? h('small', '🎁 ' + tk.rewards[0].title) : null),
      claimBtn(biz, me, tk, live, seen),
      live && me.entries_left_today > 0 ? h('div.claim-note', me.approval_mode === 'auto' ? t('Approved instantly at this shop') : t('Scan the counter QR for instant approval')) : null));
    return h('div.stack', me.status === 'blocked' ? h('div.banner.red', t('This shop has paused your account.')) : null,
      pend.length ? h('div.banner.blue', '⏳ ' + t('{n} purchase waiting for the shop to confirm', { n: pend.length }) + ' · ' + t('We will tell you the moment it is approved.')) : null,
      list.length ? list : empty('No rewards running right now', 'Check back soon.'),
      biz.pay_link ? h('a.btn.ghost', { href: biz.pay_link }, t('Pay with UPI')) : null);
  }
  async function submitSheet(biz, me, tk, seen) {
    const q = new URLSearchParams(location.search), isVisit = tk.type === 'visit';
    const cc = inp({ inputmode: 'numeric', maxlength: 6, value: q.get('c') || '', ph: '6-digit counter code', autocomplete: 'one-time-code' });
    const bill = h('input', { type: 'file', accept: 'image/*', capture: 'environment', required: biz.require_bill_photo });
    const err = h('div.err', { role: 'alert' });
    const note = h('div.instant');
    const setNote = () => { const fast = cc.value.trim() || me.approval_mode === 'auto'; note.className = 'instant' + (fast ? '' : ' wait'); note.replaceChildren(h('span', fast ? '⚡' : '⏳'), t(fast ? 'This will be approved instantly.' : 'The shop will confirm this shortly.')); };
    cc.addEventListener('input', setNote); setNote();
    let val = null, quick = null;
    if (!isVisit) {
      const amt = tk.type === 'amount', vals = amt ? [100, 200, 500, 1000] : [1, 2, 3, 5];
      val = inp({ type: 'number', inputmode: amt ? 'decimal' : 'numeric', min: '1', step: amt ? '0.01' : '1', value: amt ? '' : '1', 'aria-label': t(TYPE_HINT[tk.type]) });
      const paint = () => [...quick.children].forEach((x, i) => x.setAttribute('aria-pressed', String(String(vals[i]) === String(val.value))));
      quick = h('div.quick', vals.map(v => h('button', { type: 'button', onclick: () => { val.value = v; paint(); FX.haptic(8); } }, amt ? FX.rupee(v) : '×' + v)));
      val.addEventListener('input', paint); paint();
      if (!amt) {
        const step = d => () => { val.value = Math.max(1, (parseInt(val.value, 10) || 1) + d); paint(); FX.haptic(8); };
        val._wrap = h('div.qty', h('button', { type: 'button', 'aria-label': '−1', onclick: step(-1) }, '−'), val, h('button', { type: 'button', 'aria-label': '+1', onclick: step(1) }, '+'));
      } else { val.style.cssText = 'height:56px;text-align:center;font-size:calc(26px * var(--font-scale, .8));font-family:var(--f-d);font-weight:700'; val._wrap = val; }
    }
    const go = h('button.claim', { type: 'button', onclick: () => busy(go, async () => {
      err.textContent = '';
      const fd = new FormData();
      fd.append('task', tk.task_id); fd.append('value', val ? val.value : '1');
      if (cc.value.trim()) fd.append('counter_code', cc.value.trim());
      if (bill && bill.files[0]) fd.append('bill_photo', bill.files[0]);
      const pos = await FX.getPos(); if (pos) { fd.append('lat', pos.latitude); fd.append('lng', pos.longitude); }
      try {
        const r = await api('entries/', 'POST', fd); m.close();
        const fresh = await api('me/shop/' + biz.shop_code + '/');
        await afterEntry(biz, fresh, seen, r.status, me);
      } catch (x) { err.textContent = x.message; FX.haptic([30, 40, 30]); }
    }) }, h('span', '✓'), t(isVisit ? 'Confirm check-in' : 'Confirm'));
    const m = modal(tk.title, h('div.stack', h('div.grab'),
      tk.rewards[0] ? h('div.row', h('span', { style: 'font-size:calc(22px * var(--font-scale, .8))' }, '🎁'), h('small.muted', t('Reward: {r}', { r: tk.rewards[0].title }))) : null,
      isVisit ? h('p.muted', t('Records one visit.')) : [h('div.field', h('span', t(TYPE_HINT[tk.type])), val._wrap), quick],
      field('Counter code', cc, 'Optional. Scan the QR at the counter for instant approval.'),
      field(biz.require_bill_photo ? 'Bill photo (required)' : 'Bill photo (optional)', bill), note, err, go), { cls: 'sheet' });
    if (val) setTimeout(() => val.focus && val.focus(), 250);
  }

  /* ---------- rewards ---------- */
  function passModal(g, color, shop) {
    modal(t('Reward pass'), h('div.passbody', shop ? h('small', shop) : null, g.image ? h('img.offer-image', { src: g.image, alt: g.item_name || g.title }) : null,
      g.item_name ? h('div.offer-item', g.item_name) : null, h('div.t', g.title),
      g.offer_price && Number(g.offer_price) > 0 ? h('div.offer-price', h('b', FX.rupee(g.offer_price)), g.original_price && Number(g.original_price) > 0 ? h('del', FX.rupee(g.original_price)) : null) : null,
      g.type === 'percent_off' ? h('div.offer-badge', g.value + '% OFF') : g.type === 'flat_off' ? h('div.offer-badge', FX.rupee(g.value) + ' OFF') : null,
      h('div.qrw', h('img', { src: '/api/rewards/qr/' + encodeURIComponent(g.code) + '.png', alt: t('QR code for this reward'), width: 230, height: 230 })),
      h('div.big', g.code), h('small', FX.until(g.expires_at)), g.terms ? h('small', g.terms) : null,
      h('small', t('Show this to the staff. They scan it or type the code.')),
      h('button.btn.block', { style: 'background:#fff;color:#15192b;background-image:none', onclick: () => FX.copy(g.code) }, t('Copy code'))),
      { cls: 'pass', style: FX.shopVars(color) });
  }
  const ticket = (g, shop, color, shopName) => {
    const requestStatus = g.redemption_request_status;
    const requestButton = () => h('button.btn.sm', { onclick: e => busy(e.target, async () => {
      await api('rewards/' + g.id + '/request/', 'POST');
      toast(t('Redemption request sent. The shop will approve it.'));
      FX.render(true);
    }) }, t('Request redemption'));
    const requestActions = g.status === 'active' ? requestStatus === 'pending'
      ? h('div.stack.s', h('span.pill.warn', t('Waiting for shop approval')),
        h('button.btn.ghost.sm', { onclick: e => busy(e.target, async () => {
          await api('rewards/' + g.id + '/request/', 'DELETE');
          toast(t('Redemption request cancelled.'));
          FX.render(true);
        }) }, t('Cancel request')))
      : h('div.stack.s',
        requestStatus === 'declined' ? h('small.muted', t('The shop declined your last request. Your reward is still available.')) : null,
        requestButton()) : null;
    const codePass = h('div.stack.s', h('small.muted', t('Show this code to staff if you cannot request approval in the app.')),
      h('div.code', g.code),
      h('div.row.wrap', h('button.btn.sm', { onclick: () => passModal(g, color, shopName || shop) }, t('Show at counter')),
        h('button.btn.ghost.sm', { onclick: () => FX.copy(g.code) }, t('Copy'))));
    return h('div.ticket.' + g.status, h('div.main',
    g.image ? h('img.offer-thumb', { src: g.image, alt: g.item_name || g.title }) : null,
    g.item_name ? h('b', g.item_name) : null, h('b', g.title),
    g.type === 'percent_off' ? h('span.offer-badge', g.value + '% OFF') :
      g.type === 'flat_off' ? h('span.offer-badge', FX.rupee(g.value) + ' OFF') : null,
    g.offer_price && Number(g.offer_price) > 0 ? h('div.offer-price', h('b', FX.rupee(g.offer_price)),
      g.original_price && Number(g.original_price) > 0 ? h('del', FX.rupee(g.original_price)) : null) : null,
    shop ? h('small.muted', shop) : null,
    g.terms ? h('small.muted', g.terms) : null, h('small', g.status === 'active' ? FX.until(g.expires_at) : t(g.status === 'used' ? 'Used' : g.status === 'expired' ? 'Expired' : 'Cancelled')),
    g.trigger === 'welcome' ? pill(t('Welcome gift'), 'ok') : g.trigger === 'winback' ? pill(t('Welcome-back gift'), 'ok') : g.trigger === 'referral' ? pill(t('Referral reward'), 'info') : g.trigger === 'social' ? pill(t('Social follow reward'), 'info') : null),
    requestActions,
    g.status === 'active' ? h('details.code-fallback', h('summary.muted', t('Use code instead')), codePass) :
      h('div.stub', h('small.muted', t('Reward code')), h('div.code', g.code)));
  };
  const coinWhy = (it) => it.kind === 'bonus' ? t(it.reason === 'welcome' ? 'Welcome bonus' : it.reason === 'referrer' ? 'A friend joined: referral bonus' : 'Joining bonus (invited by a friend)') :
    it.kind === 'purchase' ? t('Earned from your visit') : it.kind === 'redemption' ? t('Spent on {item}', { item: it.title }) :
    it.kind === 'refund' ? t('Returned: {item}', { item: it.title }) : t('Visit undone by the shop');
  function coinRules(c) {
    const r = c.rules || {}, out = [];
    if (r.spend_per_coin) out.push(t('1 coin for every ₹{n} you spend', { n: r.spend_per_coin }));
    if (r.visit_coins) out.push(t('{n} coins on every visit', { n: r.visit_coins }));
    if (r.welcome_bonus) out.push(t('{n} welcome coins on your first purchase', { n: r.welcome_bonus }));
    if (r.referrer_bonus) out.push(t('{n} coins for each friend you bring', { n: r.referrer_bonus }));
    return out;
  }
  function coinRewardsCard(coins, onChange) {
    coins = coins || { enabled: false, balance: 0, rewards: [], redemptions: [], history: [] };
    if (!coins.enabled && !coins.balance && !coins.redemptions.length) return null;
    const next = coins.next_reward, rules = coinRules(coins), history = coins.history || [];
    const pending = coins.redemptions.filter(r => r.status === 'pending');
    return h('div.card.stack.coin-card',
      h('div.coin-hero', h('div', h('small', t('Your coins')), h('div.coin-big', '🪙 ', h('span.num', String(coins.balance)))),
        next ? h('div.coin-next', h('div.bar', h('i', { style: { width: next.pct + '%' } })),
          h('small', t('{n} more coins to unlock {item}', { n: next.needed, item: next.title }))) :
          coins.rewards.length ? h('small', '🎉 ' + t('You can afford every reward below')) : null),
      rules.length ? h('div.coin-rules', rules.map(r => h('span.chip', r))) : null,
      pending.map(r => h('div.coin-pass', h('div.stack.s', h('b', r.title), h('small.muted', t('Show this code to the shop') + ' · ' + t('{n} coins', { n: r.coins }))),
        h('div.row', h('span.coin-code', r.code), h('button.btn.ghost.sm', { onclick: async e => {
          if (!await FX.confirmBox(t('Cancel this request and get your {n} coins back?', { n: r.coins }), t('Cancel request'), true)) return;
          await busy(e.target, async () => { await api('coin-redemptions/' + r.id + '/cancel/', 'POST', {}); toast(t('Request cancelled. Your coins are back.')); await onChange(); });
        } }, t('Cancel'))))),
      coins.enabled && coins.rewards.length ? coins.rewards.map(reward => {
        const can = coins.balance >= reward.cost;
        return h('div.li.coin-reward-row',
          h('div.grow.stack.s', h('div.row.wrap', h('b', reward.title), pill(t('{n} coins', { n: reward.cost }), can ? 'ok' : 'info')),
            reward.description ? h('small.muted', reward.description) : null,
            can ? null : h('div.bar.thin', h('i', { style: { width: Math.min(100, Math.floor(100 * coins.balance / reward.cost)) + '%' } }))),
          h('button.btn.sm', { disabled: !can, onclick: async e => {
            if (!await FX.confirmBox(t('Request {item} for {n} coins? The shop must approve it.', { item: reward.title, n: reward.cost }), t('Request item'))) return;
            await busy(e.target, async () => {
              await api('coin-rewards/' + reward.id + '/request/', 'POST', {});
              toast(t('Coin redemption requested. The shop will review it.'));
              await onChange();
            });
          } }, can ? t('Get it') : t('{n} to go', { n: reward.cost - coins.balance })));
      }) : coins.enabled ? empty('No coin rewards available', 'The shop has not added any coin rewards yet.') :
        h('p.small.muted', t('Coin redemption is paused by the shop.')),
      history.length ? h('details', h('summary.muted', t('Coin history')),
        h('div.stack.s', { style: 'margin-top:10px' }, history.map(it => h('div.li',
          h('div.grow', h('b', coinWhy(it)), h('small.muted', FX.fmtDT(it.at))),
          h('b.num.coin-delta' + (it.delta > 0 ? '.up' : '.down'), (it.delta > 0 ? '+' : '') + it.delta))))) : null,
      coins.redemptions.filter(r => r.status !== 'pending').length ? h('details', h('summary.muted', t('Coin redemption history')),
        h('div.stack.s', { style: 'margin-top:10px' }, coins.redemptions.filter(r => r.status !== 'pending').map(item => h('div.li',
          h('div.grow', h('b', item.title), h('small.muted', t('{n} coins', { n: item.coins }) + ' · ' + item.code)),
          pill(t(item.status), item.status === 'approved' ? 'ok' : ''))))) : null);
  }
  function rewardsTab(biz, me) {
    const act = me.rewards.filter(g => g.status === 'active'), old = me.rewards.filter(g => g.status !== 'active');
    const coinCard = coinRewardsCard(me.coins, () => refreshShop(biz.shop_code));
    const tickets = me.scratch_tickets || [];
    const scratchCard = tickets.length ? h('div.card.stack.scratch-cards',
      h('div.row', h('span.scratch-section-icon', '🎟️'), h('h3', t('Scratch Cards')), pill(t('{n} ready', { n: tickets.filter(item => !item.revealed).length }), 'info')),
      tickets.map(item => h('div.scratch-ticket' + (item.revealed ? '.revealed' : '.ready'),
        h('div.scratch-ticket-art', h('span.scratch-art-icon', item.revealed ? item.is_winner ? '🎁' : '✨' : '🎟️'),
          item.revealed ? null : h('span.scratch-foil', h('b', 'OFFLet'), h('i', '✦'))),
        h('div.grow.stack.s', h('b', item.revealed
          ? item.is_winner ? t('You won: {prize}', { prize: item.prize_title }) : t('No prize this time')
          : t('Scratch card ready')),
        item.revealed && item.reward_code ? h('small.muted', t('Reward code: {code}', { code: item.reward_code })) :
          h('small.muted', FX.fmtDT(item.issued_at))),
        item.revealed ? pill(t('Revealed'), item.is_winner ? 'ok' : '') :
          h('button.btn.sm.scratch-trigger', { onclick: e => busy(e.currentTarget, async () => {
            const result = await api('scratch-tickets/' + item.id + '/reveal/', 'POST', {});
            await FX.render(true);
            FX.celebrate({
              icon: result.is_winner ? '🎁' : '🎟️',
              big: result.is_winner,
              title: t(result.is_winner ? 'You won!' : 'No prize this time'),
              text: result.is_winner ? t('You won: {prize}', { prize: result.prize_title }) : t('No prize this time. Keep shopping!'),
              body: result.is_winner ? h('div.scratch-prize', h('img', {
                src: '/api/rewards/qr/' + encodeURIComponent(result.reward_code) + '.png',
                width: 144, height: 144, alt: t('Reward code: {code}', { code: result.reward_code })
              }), h('b', result.reward_code)) : null,
              actions: result.is_winner ? [[t('Show reward pass'), () => {
                sessionStorage['tab_' + biz.shop_code] = 'rewards';
                FX.go('shop/' + biz.shop_code + '?tab=rewards');
              }]] : []
            });
          }) }, t('Scratch now'))))) : null;
    return h('div.stack', coinCard, scratchCard,
      act.length ? act.map(g => ticket(g, null, biz.brand_color, biz.name)) : empty('No rewards ready', 'Keep collecting stamps. Your rewards appear here.'),
      old.length ? h('details', h('summary.muted', t('Past rewards ({n})', { n: old.length })), h('div.stack', { style: 'margin-top:10px' }, old.map(g => ticket(g)))) : null);
  }
  R.rewards = async function () {
    const w = await api('me/wallet/');
    const groups = await Promise.all(w.shops.map(async shop => {
      const me = await api('me/shop/' + shop.shop_code + '/');
      return { shop, me, active: me.rewards.filter(g => g.status === 'active') };
    }));
    const available = groups.filter(({ me, active }) =>
      active.length || me.coins.enabled || me.coins.balance || me.coins.redemptions.length);
    return h('div.stack.l', h('h1', t('My rewards')), available.length ? available.map(({ shop, me, active }) =>
      h('div.stack', h('h2', shop.shop), coinRewardsCard(me.coins, () => FX.render(true)),
        active.length ? active.map(g => ticket(g, shop.shop, shop.brand_color, shop.shop)) : null)) :
      empty('No rewards ready', 'Keep collecting stamps. Your rewards appear here.'));
  };

  /* ---------- history + rating ---------- */
  function rateModal(entry) {
    let v = 0; const c = inp({ maxlength: 300, ph: 'Tell the shop how it went (optional)' });
    const m = modal(t('Rate your visit'), h('div.stack', h('p.muted', t('Your rating helps customers choose a shop.')), FX.stars(0, n => { v = n; }), c, h('button.btn', { onclick: e => busy(e.target, async () => { if (!v) throw new Error(t('Choose a rating from 1 to 5.')); await api('feedback/', 'POST', Object.assign({ rating: v, comment: c.value }, entry)); m.close(); toast(t('Thanks for your feedback!')); FX.start(true); }) }, t('Send'))));
  }
  function historyTab(biz, me) {
    return h('div.card', me.entries.length ? me.entries.map(e => h('div.li', h('div.grow', h('b', e.task_title), h('div.small.muted', FX.fmtDT(e.created_at))),
      e.multiplier > 1 ? pill(e.multiplier + 'x', 'warn') : null,
      e.status === 'approved' && !e.rated ? h('button.btn.ghost.sm', { onclick: () => rateModal({ entry: e.id }) }, '★ ' + t('Rate')) : null,
      pill(t(e.status === 'approved' ? 'Approved' : e.status === 'pending' ? 'Waiting' : e.status === 'rejected' ? 'Declined' : 'Reversed'), e.status === 'approved' ? 'ok' : e.status === 'pending' ? 'warn' : 'bad'))) : empty('No activity yet'));
  }

  /* ---------- invite ---------- */
  function inviteGives(biz, r) {
    const you = [], friend = [];
    if (r.reward) you.push('🎁 ' + r.reward);
    if (r.referrer_bonus) you.push('🪙 ' + t('{n} coins', { n: r.referrer_bonus }));
    const welcome = biz.perks && biz.perks.welcome;
    if (welcome) friend.push('🎁 ' + welcome.title);
    if (r.friend_bonus) friend.push('🪙 ' + t('{n} coins', { n: r.friend_bonus }));
    return { you, friend };
  }
  function inviteTab(biz, me) {
    const r = me.referral || { code: me.referral_code, url: me.referral_url, reward: me.referral_reward, joined: me.friends_referred, purchased: 0, coins_earned: 0, friends: [] };
    const brand = biz.brand || { name: 'OFFLet', domain: location.host };
    const text = t('Join me at {shop} on {brand} and we both earn rewards! {domain}', { shop: biz.name, brand: brand.name, domain: brand.domain });
    const g = inviteGives(biz, r);
    return h('div.stack',
      me.referral && me.referral.invited_pending && (r.friend_bonus || (biz.perks && biz.perks.welcome)) ? h('div.banner.blue', '🤝 ' + t('{name} invited you. Make your first purchase to unlock your joining bonus.', { name: r.invited_by })) : null,
      h('div.card.stack.invite-hero',
        h('h3', t('Invite friends. You both win.')),
        h('div.g2.invite-gives',
          h('div.give', h('small', t('You get')), g.you.length ? g.you.map(x => h('b', x)) : h('b', t('Rewards from this shop'))),
          h('div.give', h('small', t('Your friend gets')), g.friend.length ? g.friend.map(x => h('b', x)) : h('b', t('Rewards from this shop')))),
        h('small.muted', t('Paid after your friend’s first approved purchase.')),
        h('div.invite-code', h('div', h('small.muted', t('Your code')), h('div.code-big', r.code)), h('button.btn.ghost.sm', { onclick: () => FX.copy(r.code) }, t('Copy'))),
        h('div.row.wrap', h('button.btn.grow', { onclick: () => FX.share(text, r.url) }, t('Share on WhatsApp')), h('button.btn.ghost', { onclick: () => FX.copy(r.url) }, t('Copy link')))),
      h("div.invite-stats", FX.kpi(t("Friends joined"), r.joined), FX.kpi(t("Made a purchase"), r.purchased), FX.kpi(t("Coins earned"), r.coins_earned)),
      r.friends && r.friends.length ? h('div.card', h('h3', t('Your friends')), r.friends.map(f => h('div.li', h('div.grow', h('b', f.name), h('div.small.muted', FX.fmtDT(f.joined_at))),
        pill(t(f.status === 'purchased' ? 'Purchased' : 'Joined'), f.status === 'purchased' ? 'ok' : 'warn')))) : null);
  }

  /* ---------- booking ---------- */
  function bookTab(biz, me) {
    const svc = sel(biz.services.map(s => [s.id, s.name + ' (' + FX.rupee(s.price) + ', ' + s.duration_min + ' min)']), biz.services[0].id);
    const d = new Date(Date.now() + 36e5); d.setMinutes(0, 0, 0);
    const iso = new Date(d.getTime() - d.getTimezoneOffset() * 6e4).toISOString().slice(0, 16);
    const when = inp({ type: 'datetime-local', value: iso, min: iso }), note = inp({ maxlength: 200, ph: 'Note for the shop (optional)' });
    const mine = me.bookings.filter(b => ['requested', 'confirmed'].includes(b.status));
    return h('div.stack', h('div.card.stack', h('h3', t('Book a service')), field('Service', svc), field('Date and time', when), field('Note', note),
      h('button.btn.lg', { onclick: e => busy(e.target, async () => { await api('b/' + biz.shop_code + '/bookings/', 'POST', { service: svc.value, starts_at: new Date(when.value).toISOString(), note: note.value }); toast(t('Booking requested. The shop will confirm.')); FX.start(true); }) }, t('Request booking'))),
      mine.length ? h('div.card', h('h3', t('Upcoming')), mine.map(bookingRow)) : null);
  }
  const bookingRow = b => h('div.li', h('div.grow', h('b', b.service_name), h('div.small.muted', FX.fmtDT(b.starts_at) + (b.shop ? ' · ' + b.shop : ''))),
    pill(t(b.status.replace('_', ' ')), b.status === 'confirmed' ? 'ok' : b.status === 'requested' ? 'warn' : b.status === 'completed' ? 'info' : 'bad'),
    ['requested', 'confirmed'].includes(b.status) ? h('button.btn.ghost.sm', { onclick: async () => { if (await FX.confirmBox(t('Cancel this booking?'), t('Cancel booking'), true)) { await api('bookings/' + b.id + '/action/', 'POST', { action: 'cancel' }); FX.render(true); FX.start(true); } } }, t('Cancel')) : null,
    b.status === 'completed' && !b.rated ? h('button.btn.ghost.sm', { onclick: () => rateModal({ booking: b.id }) }, '★ ' + t('Rate')) : null);
  R.bookings = async function () {
    const list = await api('me/bookings/');
    return h('div.stack.l', h('h1', t('My bookings')), h('div.card', list.length ? list.map(bookingRow) : empty('No bookings yet', 'Open a shop that takes bookings to book a service.')));
  };
})(window.FX);
