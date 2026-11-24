/* Spin & Win campaign studio and customer wheel. */
(function (FX) {
  'use strict';
  const { h, api, S, field, inp, sel, empty, kpi, toast, modal, busy } = FX;
  const t = FX.t, R = FX.routes.owner;
  const code = () => S.biz.shop_code;
  const audienceLabel = value => ({ all: 'Everyone', new: 'New customers', returning: 'Returning customers' })[value] || value;

  function wheelEditor(wheel) {
    let segments = wheel ? wheel.segments.map(s => Object.assign({}, s, {
      reward_type: s.reward_type === 'percent_off' ? 'percent_off' : 'free_item'
    })) : [
      { label: '10% off', reward_type: 'percent_off', probability: 50, color: '#5e35b1', icon: '🎁', value: 10, expiry_days: 30 },
      { label: 'Free coffee', reward_type: 'free_item', probability: 50, color: '#e3e6ee', icon: '🎁', value: 0, expiry_days: 30 }
    ];
    const segmentBox = h('div.stack');
    const error = h('div.err', { role: 'alert' });
    function rebalance() {
      const base = Math.floor(100 / segments.length);
      const remainder = 100 % segments.length;
      segments.forEach((segment, i) => { segment.probability = base + (i < remainder ? 1 : 0); });
    }
    function addReward(rewardType) {
      if (segments.length >= 12) return;
      syncSegments();
      const percentOff = rewardType === 'percent_off';
      segments.push({ label: percentOff ? '10% off' : 'Free item', reward_type: rewardType,
        color: '#f2a516', icon: '🎁', value: percentOff ? 10 : 0, expiry_days: 30, minimum_order: 0 });
      rebalance();
      drawSegments();
    }
    const addItem = h('button.btn.ghost', { type: 'button', onclick: () => addReward('free_item') }, t('Add free item'));
    const addDiscount = h('button.btn.ghost', { type: 'button', onclick: () => addReward('percent_off') }, t('Add percentage off'));
    function syncSegments() {
      segments = segments.map((segment, i) => {
        const fields = segmentBox.children[i].querySelectorAll('input');
        return Object.assign({}, segment, { label: fields[0].value,
          value: segment.reward_type === 'percent_off' ? fields[1].value : 0,
          minimum_order: fields[2].value,
          color: segment.color || '#5e35b1', icon: segment.icon || '🎁', image_url: '',
          expiry_days: 30, product_restrictions: '', terms: '' });
      });
    }
    function drawSegments() {
      const rows = segments.map((segment, i) => {
        const percentOff = segment.reward_type === 'percent_off';
        const label = inp({ maxlength: 80, value: segment.label || '', ph: percentOff ? 'e.g. 10% off' : 'e.g. Free coffee' });
        const value = inp({ type: 'number', min: 1, max: 100, step: 1,
          value: segment.value || (percentOff ? 10 : 0) });
        const discountField = field('Discount (%)', value);
        discountField.hidden = !percentOff;
        const minimum = inp({ type: 'number', min: 0, step: '0.01', value: segment.minimum_order || 0 });
        return h('div.card.stack.s',
          h('div.row.between', h('b', t('Reward {n} · {chance}% chance', { n: i + 1, chance: segment.probability })),
            segments.length > 2 ? h('button.btn.ghost.sm', { type: 'button', onclick: () => {
              syncSegments();
              segments.splice(i, 1);
              rebalance();
              drawSegments();
            } }, t('Remove')) : null),
          field(percentOff ? 'Offer name' : 'Item name', label),
          discountField, field('Minimum purchase amount (optional)', minimum));
      });
      segmentBox.replaceChildren(...rows);
      addItem.disabled = addDiscount.disabled = segments.length >= 12;
    }
    rebalance();
    drawSegments();
    const box = h('div.stack', h('p.small.muted', t('Add at least two rewards. Winning chances are shared equally. Minimum purchase is optional.')),
      h('div.stack', h('div.row.between', h('h3', t('Wheel rewards')),
        h('div.row.wrap', addItem, addDiscount)), segmentBox), error,
      h('button.btn.lg', { onclick: e => busy(e.target, async () => {
        try {
          syncSegments();
          rebalance();
          const segmentsData = segments.map(segment => Object.assign({}, segment, { label: segment.label.trim() }));
          const body = { name: wheel ? wheel.name : 'Spin & Win',
            audience: wheel ? wheel.audience : 'all', start_date: null,
            end_date: null, spins_per_day: wheel ? wheel.spins_per_day : 1,
            active: wheel ? wheel.active : true,
            weekdays: [], segments: segmentsData };
          if (wheel) await api('spin-wheels/' + wheel.id + '/', 'PATCH', body);
          else await api('b/' + code() + '/spin-wheels/', 'POST', body);
          modalRef.close(); toast(t('Spin campaign saved')); FX.render(true);
        } catch (x) { error.textContent = x.message; }
      }) }, t('Save campaign')));
    const modalRef = modal(wheel ? t('Edit Spin & Win campaign') : t('Create Spin & Win campaign'), box, { drawer: true });
  }

  R.spin = async function () {
    const wheels = await api('b/' + code() + '/spin-wheels/');
    const link = location.origin + '/b/' + code() + '/?tab=spin';
    const qr = h('img', { src: '/api/b/' + code() + '/spin-qr.png', width: 150, height: 150, alt: t('QR code for Spin & Win') });
    const cards = wheels.map(wheel => {
      const stats = wheel.analytics;
      return h('div.card.stack', h('div.hd', h('div', h('h3', wheel.name), h('p.small.muted', audienceLabel(wheel.audience))),
        h('span.pill' + (wheel.active ? '.ok' : ''), wheel.active ? t('Active') : t('Paused'))),
        h('div.g4', kpi('Spins', stats.spins), kpi('Wins', stats.wins), kpi('Coupons redeemed', stats.redeemed), kpi('Coupons ready', stats.active_coupons)),
        h('div.row.wrap', h('button.btn', { onclick: () => wheelEditor(wheel) }, t('Edit')),
          h('button.btn.ghost', { onclick: async () => { await api('spin-wheels/' + wheel.id + '/', 'PATCH', { active: !wheel.active }); FX.render(true); } }, wheel.active ? t('Pause') : t('Activate')),
          h('button.btn.danger', { onclick: async e => { if (await confirmBox(t('Delete this wheel permanently? Past spin records will be kept.'), t('Delete wheel'), true)) { await busy(e.target, async () => { await api('spin-wheels/' + wheel.id + '/', 'DELETE'); FX.render(true); }); } } }, t('Delete')),
          h('button.btn.ghost', { onclick: () => FX.share(t('Try your luck at {shop}', { shop: S.biz.name }), link) }, t('Share wheel')),
          h('button.btn.ghost', { onclick: () => FX.copy(link) }, t('Copy link'))),
        stats.recent.length ? h('details', h('summary', t('Recent spins')),
          stats.recent.map(r => h('div.li', h('div.grow', h('b', r.customer + ' · ' + r.prize), h('small.muted', FX.fmtDT(r.created_at))),
            h('span.pill' + (r.coupon_status === 'used' ? '.ok' : ''), r.outcome === 'try_again' ? t('Try again') : t(r.coupon_status || 'Won'))))) : null);
    });
    const errQr = h('div.card.row.wrap', qr, h('div.grow.stack', h('h3', t('Spin & Win QR code')),
      h('p.small.muted', t('Print this code at your counter. It opens today’s wheel for the customer group automatically selected for each visitor.')),
      h('div.row.wrap', h('a.btn.ghost', { href: '/api/b/' + code() + '/spin-qr.png?download=1' }, t('Download QR')),
        h('button.btn.ghost', { onclick: () => FX.copy(link) }, t('Copy customer link')))));
    return h('div.stack.l', h('div.hd', h('div', h('h1', t('Smart Spin & Win')), h('p.muted', t('Build reward wheels, schedule daily campaigns and track coupon results.'))),
      h('button.btn', { onclick: () => wheelEditor(null) }, t('Create wheel'))),
      errQr, cards.length ? cards : empty('No Spin & Win wheel yet', 'Create a campaign and add reward segments to launch your first wheel.'));
  };

  function tone(frequency, duration) {
    try {
      const Context = window.AudioContext || window.webkitAudioContext;
      if (!Context) return;
      const ctx = new Context(), osc = ctx.createOscillator(), gain = ctx.createGain();
      osc.frequency.value = frequency; gain.gain.setValueAtTime(0.08, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + duration);
      osc.connect(gain); gain.connect(ctx.destination); osc.start(); osc.stop(ctx.currentTime + duration);
      osc.onended = () => ctx.close();
    } catch (e) { /* Audio is an optional browser enhancement. */ }
  }

  FX.spinTab = function (business, initial) {
    const data = initial || {};
    if (!data.available || !data.wheel) return empty('No wheel today', 'Check back another day for the next Spin & Win campaign.');
    const wheel = data.wheel, segments = wheel.segments;
    let startAngle = 0;
    const stops = [];
    for (const segment of segments) {
      stops.push([startAngle, segment.color]);
      startAngle += segment.probability * 3.6;
    }
    const gradient = 'conic-gradient(' + stops.map(([start, color], i) =>
      color + ' ' + start + 'deg ' + (i + 1 < stops.length ? stops[i + 1][0] : 360) + 'deg').join(',') + ')';
    const dial = h('div.spin-dial', { style: { background: gradient } });
    let offset = 0;
    let cumulative = 0;
    segments.forEach(segment => {
      const angle = cumulative + segment.probability * 1.8;
      const content = segment.image_url ? h('img', { src: segment.image_url, alt: '', loading: 'lazy' }) : h('span', segment.icon);
      dial.appendChild(h('div.spin-label', { style: { transform: `translate(-50%,-50%) rotate(${angle}deg) translateY(-82px) rotate(-${angle}deg)`, color: segment.color === '#e3e6ee' ? '#333' : '#fff' } },
        content, h('small', segment.label)));
      cumulative += segment.probability * 3.6;
    });
    dial.appendChild(h('div.spin-center', business.logo_url ? h('img', { src: business.logo_url, alt: '' }) : '✦'));
    const pointer = h('div.spin-pointer', '▼');
    const status = h('p.center.muted', data.spins_remaining ? t('{n} spin(s) left today', { n: data.spins_remaining }) : t('You have used today’s spins. Come back tomorrow!'));
    const spinButton = h('button.btn.lg', { disabled: data.spins_remaining < 1 });
    let spinning = false;
    const history = h('div.stack.s', (data.history || []).map(item => h('div.li', h('div.grow', h('b', item.prize), h('small.muted', FX.fmtDT(item.created_at))),
      h('span.pill', item.outcome === 'try_again' ? t('Try again') : t(item.status || 'Won')))));
    if (!history.children.length) history.appendChild(h('p.small.muted', t('Your spins will appear here.')));
    const drawHistory = rows => history.replaceChildren(...(rows.length ? rows.map(item => h('div.li', h('div.grow', h('b', item.prize), h('small.muted', FX.fmtDT(item.created_at))),
      h('span.pill', item.outcome === 'try_again' ? t('Try again') : t(item.status || 'Won')))) : [h('p.small.muted', t('Your spins will appear here.'))]));
    spinButton.textContent = t('Spin the wheel');
    spinButton.onclick = () => {
      if (spinning || data.spins_remaining < 1) return;
      spinning = true; spinButton.disabled = true; spinButton.textContent = t('Spinning…'); tone(460, 0.12);
      api('b/' + business.shop_code + '/spin/', 'POST', {}).then(result => {
        const segment = result.segment;
        const index = segments.findIndex(x => x.id === segment.id);
        const center = segments.slice(0, index).reduce((sum, item) => sum + item.probability * 3.6, 0) + segment.probability * 1.8;
        offset += 360 * 5 + ((360 - center - (offset % 360) + 360) % 360);
        dial.style.transform = 'rotate(' + offset + 'deg)';
        window.setTimeout(() => {
          data.spins_remaining = result.spins_remaining;
          status.textContent = data.spins_remaining ? t('{n} spin(s) left today', { n: data.spins_remaining }) : t('You have used today’s spins. Come back tomorrow!');
          drawHistory(result.history);
          spinButton.disabled = data.spins_remaining < 1;
          spinButton.textContent = t('Spin the wheel');
          spinning = false;
          if (result.outcome === 'won' && result.grant) {
            tone(880, 0.3);
            FX.celebrate({ title: t('You won!'), icon: segment.icon, big: true,
              text: segment.label,
              body: h('div.card.stack.center', h('img', { src: '/api/rewards/qr/' + encodeURIComponent(result.grant.code) + '.png', width: 150, height: 150, alt: t('Coupon QR code') }),
                h('b', result.grant.code), result.grant.terms ? h('small.muted', result.grant.terms) : null,
                h('small.muted', FX.until(result.grant.expires_at))),
              actions: [[t('My rewards'), () => { location.href = '/b/' + business.shop_code + '/?tab=rewards'; }]] });
          } else {
            const resultModal = modal(t('No luck this time'), h('div.stack.center', h('span', { style: 'font-size:48px' }, segment.icon),
              h('p', t('No prize this spin. Your next chance is waiting!')),
              h('button.btn', { onclick: () => resultModal.close() }, t('Close'))));
          }
        }, window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 50 : 5200);
      }).catch(error => {
        spinning = false; spinButton.disabled = false; spinButton.textContent = t('Spin the wheel');
        toast(error.message, true);
      });
    };
    const rules = segments.filter(s => s.reward_type !== 'empty').map(s => h('div.li',
      h('span.spin-swatch', { style: { background: s.color } }, s.icon),
      h('div.grow', h('b', s.label), h('small.muted', t('{n}% chance', { n: s.probability })))));
    return h('div.stack.l.spin-page', h('div.center', h('h2', wheel.name),
      h('p.muted', t('Good luck! Rewards are added to your wallet automatically.'))),
      h('div.spin-board', pointer, dial), status, spinButton, h('div.card.stack', h('h3', t('Possible rewards')), rules),
      h('div.card.stack', h('h3', t('Spin history')), history));
  };
})(window.FX);
