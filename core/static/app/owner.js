/* OFFLet v2 owner screens, part 1: onboarding, Today (action queue), Customers CRM, Rewards studio. Also staff queue. */
(function (FX) {
  'use strict';
  const { h, api, S, field, inp, sel, pill, empty, kpi, toast, modal, busy, confirmBox } = FX;
  const t = FX.t, R = FX.routes.owner;
  const loc = () => (FX.lang === 'hi' ? 'hi-IN' : 'en-IN');
  const wd = i => new Date(2024, 0, 1 + i).toLocaleDateString(loc(), { weekday: 'short' });
  const code = () => S.biz.shop_code;
  const SEG = [['all', 'All'], ['new', 'New'], ['regular', 'Regular'], ['at_risk', 'Slipping away'], ['lapsed', 'Lapsed'], ['never', 'Not yet bought']];
  FX.SEG = SEG; FX.wd = wd;

  /* ---------- onboarding wizard: pick a business type, get a complete setup ---------- */
  R.start = async function () {
    const types = await api('blueprints/');
    let pick = 'cafe', step = 1;
    const name = inp({ maxlength: 120, ph: 'Business name' }), upi = inp({ ph: 'yourname@upi (optional)' }), addr = inp({ ph: 'Area or address (optional)' });
    let shopLocation = null;
    const locationStatus = h('p.small.muted', t('No shop location is set. You can detect it now or later from My shop.'));
    const detectLocation = h('button.btn.ghost.sm', { onclick: e => busy(e.target, async () => {
      locationStatus.textContent = t('Getting device location…');
      try {
        const position = await FX.locate();
        shopLocation = { lat: position.coords.latitude, lng: position.coords.longitude };
        locationStatus.textContent = t('Location detected (±{accuracy} m). It will be attached when you launch.', { accuracy: Math.round(position.coords.accuracy) });
      } catch (error) {
        locationStatus.textContent = error.message;
      }
    }) }, t('Detect shop location'));
    const box = h('div.stack.l', { style: 'max-width:720px;margin:0 auto' });
    let draft = null;
    const rewardTypes = [['free_item', 'Free item'], ['percent_off', 'Percent off'], ['flat_off', 'Flat amount off'], ['gift', 'Gift'], ['cashback', 'Cashback'], ['special_offer', 'Special offer'], ['custom', 'Other']];
    const taskTypes = [['visit', 'Number of visits'], ['count', 'Number of items'], ['amount', 'Total spend (₹)']];
    const editReward = (label, current, save) => {
      const title = inp({ value: current ? current.title : '', maxlength: 120, ph: 'Reward name' });
      const type = sel(rewardTypes, current ? current.type : 'gift');
      const value = inp({ type: 'number', min: '0', value: current ? current.value : 0 });
      const days = inp({ type: 'number', min: '1', max: '365', value: current ? current.expiry_days : 30 });
      const terms = h('textarea', { maxlength: 500, placeholder: t('Optional reward terms') });
      terms.value = current ? current.terms || '' : '';
      let m;
      m = modal(t(label), h('div.stack', field('Reward', title), h('div.g2', field('Type', type), field('Value (₹ or %)', value)),
        field('Valid for (days)', days), field('Terms', terms),
        h('button.btn', { onclick: e => busy(e.target, async () => {
          if (!title.value.trim()) return toast(t('Enter a reward name.'), true);
          save({ title: title.value.trim(), type: type.value, value: value.value || 0, expiry_days: +days.value || 30, terms: terms.value });
          m.close(); draw();
        }) }, t('Save'))));
    };
    const editTask = index => {
      const current = draft.tasks[index], reward = current.rewards[0] || null;
      const title = inp({ value: current.title, maxlength: 120 });
      const type = sel(taskTypes, current.type);
      const target = inp({ type: 'number', min: '1', value: current.target });
      const item = inp({ value: current.item_name || '', maxlength: 80, ph: 'Item name (optional)' });
      const rewardTitle = inp({ value: reward ? reward.title : '', maxlength: 120, ph: 'Reward name' });
      const rewardType = sel(rewardTypes, reward ? reward.type : 'gift');
      const rewardValue = inp({ type: 'number', min: '0', value: reward ? reward.value : 0 });
      const days = inp({ type: 'number', min: '1', max: '365', value: reward ? reward.expiry_days : 30 });
      const terms = h('textarea', { maxlength: 500, placeholder: t('Optional reward terms') });
      terms.value = reward ? reward.terms || '' : '';
      let m;
      m = modal(t('Edit default reward'), h('div.stack',
        field('Task name', title), h('div.g2', field('Earn by', type), field('Target', target)), field('Item name', item),
        h('div.card.stack', h('b', t('What customers get')), field('Reward', rewardTitle),
          h('div.g2', field('Type', rewardType), field('Value (₹ or %)', rewardValue)), field('Valid for (days)', days), field('Terms', terms)),
        h('button.btn.lg', { onclick: e => busy(e.target, async () => {
          if (!title.value.trim() || !rewardTitle.value.trim() || !target.value || +target.value < 1) return toast(t('Enter a task, target and reward name.'), true);
          draft.tasks[index] = { ...current, title: title.value.trim(), type: type.value, target: +target.value,
            item_name: item.value.trim(), rewards: [{ title: rewardTitle.value.trim(), type: rewardType.value,
              value: rewardValue.value || 0, expiry_days: +days.value || 30, terms: terms.value }] };
          m.close(); draw();
        }) }, t('Save'))));
    };
    const editBoost = index => {
      const current = draft.boosts[index];
      const title = inp({ value: current.title, maxlength: 80 });
      const multiplier = sel([[2, '2x'], [3, '3x'], [4, '4x'], [5, '5x']], current.multiplier);
      const weekdays = inp({ value: current.weekdays || '', ph: '0,1,2 (Mon=0, Sun=6)' });
      const start = inp({ type: 'time', value: current.start_time || '' });
      const end = inp({ type: 'time', value: current.end_time || '' });
      let m;
      m = modal(t('Edit default boost'), h('div.stack',
        field('Name', title), field('Multiplier', multiplier), field('Days (0=Mon, 6=Sun; empty=every day)', weekdays),
        h('div.g2', field('From', start), field('Until', end)),
        h('button.btn.lg', { onclick: e => busy(e.target, async () => {
          if (!title.value.trim()) return toast(t('Enter a boost name.'), true);
          draft.boosts[index] = { ...current, title: title.value.trim(), multiplier: +multiplier.value,
            weekdays: weekdays.value.trim(), start_time: start.value || null, end_time: end.value || null };
          m.close(); draw();
        }) }, t('Save'))));
    };
    const editProgram = () => {
      const title = inp({ value: draft.program, maxlength: 120 });
      let m;
      m = modal(t('Edit program'), h('div.stack', field('Program name', title),
        h('button.btn', { onclick: e => busy(e.target, async () => {
          if (!title.value.trim()) return toast(t('Enter a program name.'), true);
          draft.program = title.value.trim(); m.close(); draw();
        }) }, t('Save'))));
    };
    const taskRow = (task, index) => h('div.li',
      h('span', task.type === 'amount' ? '₹' : '✦'),
      h('div.grow', h('b', task.title), h('div.small.muted', '🎁 ' + (task.rewards[0] ? task.rewards[0].title : t('No reward')))),
      h('div.row.wrap',
        h('button.btn.ghost.sm', { onclick: () => editTask(index) }, t('Edit')),
        h('button.btn.danger.sm', { onclick: async () => {
          if (await confirmBox(t('Remove this starter reward?'), t('Delete'), true)) { draft.tasks.splice(index, 1); draw(); }
        } }, t('Delete'))));
    const boostRow = (boost, index) => h('div.li',
      h('span', '⚡'),
      h('div.grow', h('b', boost.title + ' (' + boost.multiplier + 'x)'), h('div.small.muted', t('Fills your quiet hours'))),
      h('div.row.wrap',
        h('button.btn.ghost.sm', { onclick: () => editBoost(index) }, t('Edit')),
        h('button.btn.danger.sm', { onclick: async () => {
          if (await confirmBox(t('Remove this starter boost?'), t('Delete'), true)) { draft.boosts.splice(index, 1); draw(); }
        } }, t('Delete'))));
    const perkRow = (trigger, label, icon) => {
      const current = draft[trigger];
      return h('div.li',
        h('span', icon),
        h('div.grow', h('b', t(label)), h('div.small.muted', current ? current.title : t('Not included'))),
        h('div.row.wrap',
          h('button.btn.ghost.sm', { onclick: () => editReward(label, current, value => { draft[trigger] = value; }) }, t(current ? 'Edit' : 'Add')),
          current ? h('button.btn.danger.sm', { onclick: async () => {
            if (await confirmBox(t('Remove this starter reward?'), t('Delete'), true)) { draft[trigger] = null; draw(); }
          } }, t('Delete')) : null));
    };
    const draw = () => {
      const bp = types.find(x => x.key === pick), err = h('div.err');
      if (step === 2 && (!draft || draft.key !== pick)) draft = { ...JSON.parse(JSON.stringify(bp.setup)), key: pick };
      const progress = h('div.steps', [1, 2].map(i => h('i' + (i <= step ? '.on' : ''))));
      let content;
      if (step === 1) {
        content = h('div.stack.l',
          h('div', h('h1', t('Set up your rewards in a minute')), h('p.muted', t('Tell us about your business. We create a ready-made program you can edit before launch.'))),
          h('div.card.stack', field('Business name', name), field('UPI ID', upi, 'Customers can pay you directly.'), field('Address', addr),
            h('div.row.wrap', detectLocation), locationStatus),
          h('div.stack', h('h3', t('What kind of business is it?')),
            h('div.g2', { role: 'radiogroup' }, types.map(x => h('button.blueprint', {
              role: 'radio', 'aria-checked': String(x.key === pick), onclick: () => { pick = x.key; draw(); }
            }, h('span.em', x.emoji), h('b', FX.lang === 'hi' ? x.hi : x.label), h('small.muted', x.tasks.map(k => k.reward).join(', ')))))),
          err, h('button.btn.lg', { onclick: () => {
            if (!name.value.trim()) { err.textContent = t('Enter your business name.'); return; }
            step = 2; draw();
          } }, t('Next')));
      } else {
        const setupCard = h('div.card.stack',
          h('div.row.between.wrap', h('h3', draft.program), h('button.btn.ghost.sm', { onclick: editProgram }, t('Edit'))),
          draft.tasks.length ? h('div.stack.s', draft.tasks.map(taskRow)) : empty('No starter rewards', 'You can launch without a starter reward.'),
          draft.boosts.length ? h('div.stack.s', h('b', t('Boosts')), draft.boosts.map(boostRow)) : null,
          bp.services.length ? h('div.li', h('span', '📅'), h('div.grow', h('b', t('Online booking')), h('div.small.muted', bp.services.join(', ')))) : null,
          perkRow('welcome', 'Welcome gift', '🎁'),
          perkRow('referral', 'Friend referral reward', '🤝'));
        const launch = h('button.btn.lg.grow', { onclick: e => busy(e.target, async () => {
          try {
            const setup = { ...draft };
            delete setup.key;
            const business = { name: name.value.trim(), category: pick, pay_upi_id: upi.value.trim() || undefined,
              address: addr.value.trim(), language: FX.lang, setup };
            if (shopLocation) { business.lat = shopLocation.lat; business.lng = shopLocation.lng; }
            const b = await api('businesses/', 'POST', business);
            localStorage.fx_biz = b.shop_code; await FX.reloadShops(); await FX.loadSub().catch(() => {});
            toast(t('Your program is live! Print your QR code next.')); FX.go('shop');
          } catch (x) { err.textContent = x.message; }
        }) }, t('Launch my rewards'));
        content = h('div.stack.l',
          h('div', h('h1', t('Here is what you get')), h('p.muted', t('Edit or remove any starter reward before launching.'))),
          setupCard, err,
          h('div.row', h('button.btn.ghost', { onclick: () => { step = 1; draw(); } }, t('Back')), launch));
      }
      box.replaceChildren(progress, content);
    };
    draw();
    return box;
  };

  /* ---------- Today: the action queue ---------- */
  const typeVal = e => (e.task_type === 'amount' ? FX.rupee(e.value) : e.task_type === 'count' ? '×' + FX.num(e.value) : t('Visit'));
  function queueRow(e, onDone) {
    const review = (action, button, close) => busy(button.currentTarget || button.target, async () => {
      await api('entries/' + e.id + '/review/', 'POST', { action });
      if (close) close();
      onDone();
      if (action === 'approve') toast(t('Approved: {c}', { c: e.customer || '…' }), false, { label: t('Undo'), fn: async () => { try { await api('entries/' + e.id + '/reverse/', 'POST'); toast(t('Undone')); onDone(); } catch (x) { toast(x.message, true); } } });
    });
    const act = a => b => review(a, b);
    const showBill = () => {
      let m;
      m = modal(t('Purchase bill'), h('div.stack', h('div.center', h('img', {
        src: e.bill_url, alt: t('Customer purchase bill'), style: 'display:block;width:auto;max-width:100%;max-height:52vh;margin:0 auto;object-fit:contain;border-radius:10px'
      })), h('div.approval-actions',
        h('button.btn.ghost', { onclick: b => review('reject', b, () => m.close()) }, t('Decline')),
        h('button.btn', { onclick: b => review('approve', b, () => m.close()) }, t('Approve')))), { style: 'width:min(92vw,640px);max-height:85vh' });
    };
    return h('div.li', FX.avatar(e.customer, e.customer_image_url), h('div.grow', h('b', e.customer || t('Customer')), h('div.small.muted', e.task_title + ' · ' + typeVal(e) + ' · ' + FX.ago(e.created_at)),
      e.far ? h('div', pill(t('Far from shop ({m} m)', { m: Math.round(e.distance_m || 0) }), 'warn')) : null,
      e.bill_url ? h('button.btn.ghost.sm', { type: 'button', onclick: showBill }, t('View bill')) : null),
      h('div.approval-actions', h('button.btn.ghost.sm', { onclick: act('reject') }, t('Decline')),
        h('button.btn.sm', { onclick: act('approve') }, t('Approve'))));
  }
  /* two steps so the wrong customer or reward is never redeemed: look up, check, then confirm */
  function redeemBox() {
    const pre = sessionStorage.fx_redeem || ''; delete sessionStorage.fx_redeem;  // set when staff scan a customer's reward QR
    const c = inp({ ph: 'Reward code', maxlength: 12, autocapitalize: 'characters', autocomplete: 'off', value: pre, 'aria-label': t('Reward code') });
    const out = h('div', { 'aria-live': 'polite' });
    const STATUS = { used: 'Already used', expired: 'Expired', revoked: 'Cancelled' };
    const preview = g => h('div.redeem-preview' + (g.redeemable ? '.ok' : '.bad'), h('div.t', '🎁 ' + g.reward),
      h('div.small', g.customer + ' · …' + g.customer_mobile_tail), g.terms ? h('div.small.muted', g.terms) : null,
      g.redeemable ? h('small', FX.until(g.expires_at)) : h('b', t(STATUS[g.status] || g.status)),
      g.redeemable ? h('button.btn.lg.block', { onclick: e => busy(e.target, async () => {
        await api('rewards/redeem/', 'POST', { code: g.code }); FX.confetti(50); FX.haptic([20, 30, 20]);
        toast(t('Redeemed: {r}', { r: g.reward })); c.value = ''; out.replaceChildren(); }) }, t('Redeem now')) : null);
    const look = async () => {
      const code = c.value.trim(); if (!code) return;
      out.replaceChildren(h('div.skel.block'));
      try { out.replaceChildren(preview(await api('rewards/lookup/', 'POST', { code }))); }
      catch (e) { out.replaceChildren(h('div.redeem-preview.bad', h('b', e.message))); }
    };
    c.addEventListener('keydown', e => { if (e.key === 'Enter') look(); });
    c.addEventListener('input', () => { c.value = c.value.toUpperCase(); if (out.firstChild) out.replaceChildren(); });
    if (pre) look();
    return h('div.card.stack#redeem', h('h3', t('Redeem a reward')), h('p.small.muted', t('Type the code, or scan the QR on the customer\'s reward pass with your phone camera.')),
      h('div.row', c, h('button.btn', { onclick: look }, t('Check'))), out);
  }
  async function queueData() {
    const [pend, recent] = await Promise.all([api('owner/pending/'), api('owner/recent/')]);
    return [pend.filter(e => e.shop_code === code()), recent.filter(e => e.shop_code === code())];
  }
  function bookingQueue(list, onDone) {
    return list.map(b => h('div.li', h('div.grow', h('b', b.customer + ' · ' + b.service_name), h('div.small.muted', FX.fmtDT(b.starts_at)), b.note ? h('div.small', '“' + b.note + '”') : null),
      b.status === 'requested' ? [h('button.btn.ghost.sm', { onclick: e => busy(e.target, async () => { await api('bookings/' + b.id + '/action/', 'POST', { action: 'decline' }); onDone(); }) }, t('Decline')), h('button.btn.sm', { onclick: e => busy(e.target, async () => { await api('bookings/' + b.id + '/action/', 'POST', { action: 'confirm' }); onDone(); }) }, t('Confirm'))] :
        [h('button.btn.ghost.sm', { onclick: e => busy(e.target, async () => { await api('bookings/' + b.id + '/action/', 'POST', { action: 'no_show' }); onDone(); }) }, t('No-show')), h('button.btn.sm', { onclick: e => busy(e.target, async () => { await api('bookings/' + b.id + '/action/', 'POST', { action: 'complete' }); toast(t('Visit recorded')); onDone(); }) }, t('Completed'))]));
  }
  FX.bookingQueue = bookingQueue;
  const refresh = () => { FX.render(true); };
  const TIPS = {
    winback: (x) => [t('{n} customers have not visited in over 30 days.', { n: x.n }), t('Manage shop offers'), () => FX.go('campaigns')],
    boost: (x) => [t('{d} is your quietest day. Double stamps can fill it.', { d: wd(x.weekday) }), t('Create a boost'), () => FX.go('rewards')],
    reviews: (x) => [t('Your average rating is {a}. Read recent feedback.', { a: x.avg }), t('See feedback'), () => FX.go('insights')],
    referral: () => [t('Turn happy customers into your best marketing: add a referral reward.'), t('Set up referrals'), () => FX.go('rewards')],
    redeem: (x) => [t('Only {n}% of rewards get used. Shorter expiry or reminders can help.', { n: x.rate }), t('Review rewards'), () => FX.go('rewards')]
  };
  function subBanner() {
    const s = S.sub; if (!s) return null;
    const out = [];
    if (s.last_rejected) out.push(h('div.banner.red', h('span.grow', t('We could not verify your last UPI payment. Please submit it again.')), h('a.btn.sm', { href: '#/billing' }, t('Fix payment'))));
    else if (s.pending_payment) out.push(h('div.banner.blue', h('span.grow', '⏳ ' + t('Your UPI payment is being verified. You will get a notification when your plan is active.'))));
    if (s.state === 'trial' && !s.pending_payment) {
      const pct = Math.max(4, Math.min(100, Math.round(100 * (s.trial_days - s.days_until_end) / s.trial_days)));
      out.push(h('div.banner', h('div.grow.stack.s', h('b', t('Free trial: {n} days left.', { n: s.days_until_end })), h('div.bar', { style: 'height:6px;background:#00000014;border-radius:9px;overflow:hidden' }, h('i', { style: { display: 'block', height: '100%', width: pct + '%', background: 'var(--gold)' } }))), h('a.btn.sm.gold', { href: '#/billing' }, t('Choose a plan'))));
    } else if (s.state === 'active' && s.days_until_end <= 7 && !s.autorenew && !s.pending_payment) {
      out.push(h('div.banner', h('span.grow', t('Your plan ends in {n} days. Renew to keep your shop live.', { n: s.days_until_end })), h('a.btn.sm.gold', { href: '#/billing' }, t('Renew'))));
    } else if (s.state === 'grace' || s.state === 'expired') {
      out.push(h('div.banner.red', h('span.grow', t('Your plan has ended. Customers cannot earn until you renew.')), h('a.btn.sm', { href: '#/billing' }, t('Renew now'))));
    }
    return out.length ? h('div.stack.s', out) : null;
  }
  /* "Get set up" checklist: shows only until the shop is fully live, one tap to each step */
  function setupCard(k) {
    const code0 = code(), printed = localStorage['fx_printed_' + code0] === '1', b = S.biz || {};
    const items = [
      ['🎨', 'Add your logo and brand colour', 'Customers see this on their stamp card.', !!b.logo_url, 'shop'],
      ['📍', 'Set your shop location', 'Turns on the “far from shop” check.', b.lat != null && b.lng != null, 'shop'],
      ['🖨️', 'Print your counter QR card', 'Customers scan it to join in 10 seconds.', printed, 'shop', () => { localStorage['fx_printed_' + code0] = '1'; }],
      ['👋', 'Get your first customer', 'Share your shop link on WhatsApp.', k.customers > 0, 'shop'],
      ['✅', 'Approve a first purchase', 'Your approval queue lives on this screen.', k.visits_in_period > 0, ''],
      ['💳', 'Choose a plan before the trial ends', 'Keeps your QR and customers live.', !!(S.sub && (S.sub.state === 'active' || S.sub.pending_payment)), 'billing']];
    const done = items.filter(x => x[3]).length;
    if (done === items.length) return null;
    return h('div.card.check-card', h('div.hd', h('div', h('h3', t('Get set up')), h('small.muted', t('{a} of {b} done', { a: done, b: items.length }))), pill(Math.round(100 * done / items.length) + '%', 'info')),
      h('div.meter', h('i', { style: { width: Math.round(100 * done / items.length) + '%' } })),
      items.map(([em, title, sub, ok, route, fn]) => h('button.todo' + (ok ? '.done' : ''), { type: 'button', onclick: () => { if (fn) fn(); FX.go(route); } },
        h('span.dot2', ok ? '✓' : ''), h('div.grow', h('b', t(title)), h('div', h('small', t(sub)))), h('span', em))));
  }
  R[''] = async function () {
    const [[pend, recent], ins, bk] = await Promise.all([queueData(), api('b/' + code() + '/insights/?days=30'), S.biz.bookings_enabled ? api('b/' + code() + '/bookings/?status=open') : []]);
    S.pending = pend.length;
    const k = ins.kpis, reqs = bk.filter(b => b.status === 'requested'), todays = bk.filter(b => b.status === 'confirmed' && new Date(b.starts_at).toDateString() === new Date().toDateString());
    return h('div.stack.l', subBanner(),
      h('div.hd', h('div', h('h1', S.biz.name), h('p.muted', t('What needs you right now'))), h('div.row', h('a.btn.ghost', { href: '#/counter' }, t('Counter code')))),
      FX.tiles([['🎟️', 'Redeem', () => { const r = document.getElementById('redeem'); if (r) { r.scrollIntoView({ behavior: 'smooth', block: 'center' }); const i = r.querySelector('input'); if (i) i.focus(); } }],
        ['👥', 'Customers', '#/customers'], ['🎁', 'Rewards', '#/rewards'], ['🎡', 'Spin & Win', '#/spin'], ['📣', 'Offers', '#/campaigns'], ['📊', 'Insights', '#/insights'], ['🖨️', 'QR card', '#/shop'], ['💰', 'Refer & Earn', '#/refer'], ['🔔', 'Alerts', FX.inbox, S.unread || null]]),
      h('div.card', h('div.hd', h('h3', t('Waiting for approval')), pend.length ? pill(pend.length, 'warn') : null),
        pend.length ? pend.map(e => queueRow(e, refresh)) : empty('All caught up', 'New purchases from customers show up here.')),
      reqs.length || todays.length ? h('div.card', h('h3', t('Bookings')), bookingQueue(reqs.concat(todays), refresh)) : null,
      redeemBox(), setupCard(k),
      k.rating_count || k.customers ? h('div.g4', kpi('Customers', k.customers), kpi('Active this month', k.active_30d), kpi('Come back rate', k.repeat_rate + '%', t('customers with 2+ visits')), kpi('Visits in 30 days', k.visits_in_period, t('{n}% from returning customers', { n: k.returning_share }))) : null,
      k.customers ? h('div.card', h('h3', t('Visits, last 30 days')), FX.barChart(ins.series, 'visits')) : h('div.card.stack', h('h3', t('Get your first customers')), h('p.muted', t('Print your QR code and place it at the counter.')), h('a.btn', { href: '#/shop' }, t('Get my QR code'))),
      ins.tips.length ? h('div.stack', ins.tips.map(x => { const [msg, label, fn] = TIPS[x.key](x); return h('div.card.row', h('span', { style: 'font-size:calc(22px * var(--font-scale, .8))' }, '💡'), h('p.grow', msg), h('button.btn.soft.sm', { onclick: fn }, label)); })) : null,
      recent.length ? h('div.card', h('h3', t('Recently approved')), recent.slice(0, 5).map(e => h('div.li', FX.avatar(e.customer, e.customer_image_url), h('div.grow', h('b', e.customer || t('Customer')), h('div.small.muted', e.task_title + ' · ' + FX.ago(e.reviewed_at || e.created_at))),
        h('button.btn.ghost.sm', { onclick: async b => { if (await confirmBox(t('Undo this approval?'), t('Undo'), true)) busy(b.target, async () => { await api('entries/' + e.id + '/reverse/', 'POST'); refresh(); }); } }, t('Undo'))))) : null);
  };
  /* staff: same queue, nothing else */
  FX.routes.staff[''] = async function () {
    const [pend] = await queueData(); S.pending = pend.length;
    const followRequests = await socialFollowRequests();
    return h('div.stack.l', h('h1', S.biz ? S.biz.name : ''), h('div.card', h('div.hd', h('h3', t('Waiting for approval')), pend.length ? pill(pend.length, 'warn') : null), pend.length ? pend.map(e => queueRow(e, refresh)) : empty('All caught up', 'New purchases from customers show up here.')), followRequests, redeemBox());
  };

  /* ---------- Customers CRM ---------- */
  function customerDrawer(id, onChange) {
    const body = h('div.stack', h('div.spin'));
    const m = modal(t('Customer'), body, { drawer: true });
    api('b/' + code() + '/customers/' + id + '/').then(c => {
      const note = h('textarea', { maxlength: 300, value: c.note, placeholder: t('Private note, only you can see this') });
      body.replaceChildren(
        h('div.row', FX.avatar(c.name), h('div.grow', h('h3', c.name), h('div.small.muted', c.mobile)), FX.tierPill(c.tier.tier)),
        h('div.row.wrap', h('a.btn.ghost.sm', { href: 'tel:' + c.mobile }, t('Call')), h('a.btn.ghost.sm', { href: 'https://wa.me/91' + c.mobile.slice(-10), target: '_blank', rel: 'noopener' }, 'WhatsApp'),
          h('button.btn.danger.sm', { onclick: async () => { const block = c.status === 'active'; if (await confirmBox(block ? t('Block this customer? They stop earning here.') : t('Unblock this customer?'), block ? t('Block') : t('Unblock'), block)) { await api('b/' + code() + '/customers/' + id + '/block/', 'POST', { blocked: block }); m.close(); onChange(); } } }, t(c.status === 'active' ? 'Block' : 'Unblock'))),
        h('div.g2', kpi('Visits', c.visits), kpi('Last visit', FX.ago(c.last_visit)), kpi('Streak', c.streak ? c.streak + ' ' + t('weeks') : '0'), kpi('Friends invited', c.referred)),
        field('Note', note), h('button.btn.sm', { onclick: e => busy(e.target, async () => { await api('b/' + code() + '/customers/' + id + '/', 'PATCH', { note: note.value }); toast(t('Saved')); onChange(); }) }, t('Save note')),
        c.rewards.length ? h('div.stack.s', h('h4', t('Rewards')), c.rewards.map(g => h('div.li', h('span.grow', g.title), pill(t(g.status === 'active' ? 'Ready' : g.status === 'used' ? 'Used' : g.status), g.status === 'active' ? 'ok' : '')))) : null,
        c.ratings.length ? h('div.stack.s', h('h4', t('Feedback')), c.ratings.map(r => h('div', FX.stars(r.rating), r.comment ? h('p.small', r.comment) : null))) : null,
        h('div.stack.s', h('h4', t('Recent activity')), c.entries.length ? c.entries.map(e => h('div.li', h('div.grow', h('b', e.task_title), h('div.small.muted', FX.fmtDT(e.created_at))), e.multiplier > 1 ? pill(e.multiplier + 'x', 'warn') : null, pill(t(e.status), e.status === 'approved' ? 'ok' : ''))) : h('p.muted', t('No activity yet'))));
    }).catch(e => body.replaceChildren(h('p.err', e.message)));
  }
  R.customers = async function () {
    let seg = 'all', q = '', sort = 'recent';
    const box = h('div.stack');
    const load = async () => {
      box.replaceChildren(h('div.spin'));
      const d = await api('b/' + code() + '/customers/?segment=' + seg + '&q=' + encodeURIComponent(q) + '&sort=' + sort);
      const search = inp({ type: 'search', value: q, ph: 'Search name or mobile', 'aria-label': t('Search') });
      search.addEventListener('change', () => { q = search.value.trim(); load(); });
      box.replaceChildren(
        h('div.chips', SEG.map(([k, l]) => h('button.chip', { 'aria-pressed': String(k === seg), onclick: () => { seg = k; load(); } }, t(l), h('b', k === 'all' ? Object.values(d.segments).reduce((a, b) => a + b, 0) : d.segments[k])))),
        h('div.row.wrap', h('div.grow', search), FX.sel([['recent', 'Recently active'], ['visits', 'Most visits'], ['spend', 'Highest spend']], sort, { onchange: e => { sort = e.target.value; load(); }, style: 'width:auto' })),
        h('div.card', d.results.length ? d.results.map(c => h('div.li.click', { tabindex: 0, onclick: () => customerDrawer(c.id, load), onkeydown: e => { if (e.key === 'Enter') customerDrawer(c.id, load); } },
          FX.avatar(c.name, c.image), h('div.grow', h('b', c.name), h('div.small.muted', t('{n} visits', { n: c.visits }) + ' · ' + FX.ago(c.last_visit))),
          c.active_rewards ? pill('🎁 ' + c.active_rewards, 'ok') : null, FX.tierPill(c.tier), c.status === 'blocked' ? pill(t('Blocked'), 'bad') : null)) :
          empty('No customers here yet', seg === 'all' ? 'Share your QR code to get your first customers.' : 'Nobody matches this filter.')));
    };
    await load();
    return h('div.stack.l', h('div.hd', h('div', h('h1', t('Customers')), h('p.muted', t('Everyone who joined your rewards program'))),
      h('button.btn.ghost', { onclick: async () => { const r = await api('b/' + code() + '/report/'); window.open(r.csv_url, '_blank'); } }, t('Export CSV'))), box);
  };

  /* ---------- Rewards studio ---------- */
  const REWARD_TYPES = [['free_item', 'Free item'], ['percent_off', 'Percent off'], ['flat_off', 'Flat amount off'], ['gift', 'Gift'], ['cashback', 'Cashback'], ['special_offer', 'Special offer'], ['custom', 'Other']];
  const TASK_TYPES = [['visit', 'Number of visits'], ['count', 'Number of items'], ['amount', 'Total spend (₹)']];
  function programBuilder(onDone) {
    const title = inp({ value: 'Loyalty Rewards', maxlength: 120 });
    const rows = h('div.stack');
    const addRow = () => { const r = { title: inp({ ph: 'e.g. Buy 5 coffees' }), type: sel(TASK_TYPES, 'count'), target: inp({ type: 'number', min: '1', value: '5' }), item: inp({ ph: 'Item name (optional)' }), rt: inp({ ph: 'Reward, e.g. Free coffee' }), rtype: sel(REWARD_TYPES, 'free_item'), rv: inp({ type: 'number', min: '0', value: '0' }) };
      r.el = h('div.card.stack', field('Task', r.title), h('div.g2', field('Counts', r.type), field('Target', r.target)), field('Item name', r.item), field('Reward', r.rt), h('div.g2', field('Reward type', r.rtype), field('Value (₹ or %)', r.rv)), h('button.btn.ghost.sm', { onclick: () => { list.splice(list.indexOf(r), 1); r.el.remove(); } }, t('Remove')));
      list.push(r); rows.appendChild(r.el); };
    const list = []; addRow();
    const err = h('div.err');
    const m = modal(t('New program'), h('div.stack', field('Program name', title), rows, h('button.btn.ghost', { onclick: addRow }, '+ ' + t('Add another task')), err,
      h('button.btn.lg', { onclick: e => busy(e.target, async () => {
        try {
          const tasks = list.map(r => ({ title: r.title.value.trim(), type: r.type.value, target: r.target.value, item_name: r.item.value.trim(), repeatable: true, rewards: [{ title: r.rt.value.trim(), type: r.rtype.value, value: r.rv.value || 0, expiry_days: 30 }] }));
          if (!tasks.length || tasks.some(x => !x.title || !x.rewards[0].title)) throw new Error(t('Give every task a name and a reward.'));
          await api('b/' + code() + '/programs/', 'POST', { title: title.value, tasks }); m.close(); await FX.reloadShops(); onDone();
        } catch (x) { err.textContent = x.message; }
      }) }, t('Create program'))));
  }
  function blueprintPicker(onDone) {
    api('blueprints/').then(types => {
      let pick = null; const body = h('div.stack'); const draw = () => body.replaceChildren(h('div.g2', types.map(x => h('button.blueprint', { 'aria-checked': String(x.key === pick), onclick: () => { pick = x.key; draw(); } }, h('span.em', x.emoji), h('b', FX.lang === 'hi' ? x.hi : x.label)))),
        h('button.btn.lg', { disabled: !pick, onclick: e => busy(e.target, async () => { await api('b/' + code() + '/blueprint/', 'POST', { key: pick }); m.close(); await FX.reloadShops(); toast(t('Template added')); onDone(); }) }, t('Add this template')));
      const m = modal(t('Start from a template'), body); draw();
    });
  }
  /* shared reward fields so "edit" and "add" look and behave the same */
  function rewardFields(rw) {
    const f = { title: inp({ value: rw ? rw.title : '', maxlength: 120, ph: 'e.g. Free coffee' }), type: sel(REWARD_TYPES, rw ? rw.type : 'free_item'),
      value: inp({ type: 'number', min: '0', value: rw ? rw.value : 0 }), days: inp({ type: 'number', min: '1', max: '365', value: rw ? rw.expiry_days : 30 }),
      terms: h('textarea', { maxlength: 500, placeholder: t('Optional, e.g. Dine-in only') }) };
    f.terms.value = rw ? rw.terms || '' : '';
    f.body = () => ({ title: f.title.value, type: f.type.value, value: f.value.value || 0, expiry_days: +f.days.value || 30, terms: f.terms.value });
    f.view = h('div.stack', field('Reward', f.title), h('div.g2', field('Type', f.type), field('Value (₹ or %)', f.value)), field('Valid for (days)', f.days), field('Terms', f.terms));
    return f;
  }
  function taskEditor(tk, onDone) {
    const rw = tk.rewards[0] || null, rf = rw ? rewardFields(rw) : null, err = h('div.err', { role: 'alert' });
    const title = inp({ value: tk.title, maxlength: 120 }), target = inp({ type: 'number', min: '1', value: tk.target }), item = inp({ value: tk.item_name || '', maxlength: 80, ph: 'e.g. coffee' });
    const rep = h('input', { type: 'checkbox', checked: tk.repeatable }), cap = inp({ type: 'number', min: '0', value: tk.max_per_customer || 0 });
    const m = modal(t('Edit reward'), h('div.stack',
      h('div.card.stack', h('b', t('How customers earn')), field('Name', title), h('div.g2', field(tk.type === 'amount' ? 'Spend target (₹)' : 'Target', target), tk.type === 'count' ? field('Item', item) : h('div'))),
        h('small.muted', t('Customers already in progress keep the target they started with.')),
      h('label.row', rep, t('Customers can earn this again and again')), field('Limit per customer (0 = no limit)', cap),
      rf ? h('div.card.stack', h('b', t('What they get')), rf.view, h('small.muted', t('Codes already given out keep working. New wording and value apply from now on.'))) : null, err,
      h('button.btn.lg', { onclick: e => busy(e.target, async () => {
        try {
          await api('tasks/' + tk.id + '/', 'PATCH', { title: title.value, target: +target.value, item_name: item.value, repeatable: rep.checked, max_per_customer: +cap.value || 0 });
          if (rw) await api('rewards/' + rw.id + '/', 'PATCH', rf.body());
          m.close(); await FX.reloadShops(); toast(t('Saved')); onDone();
        } catch (x) { err.textContent = x.message; }
      }) }, t('Save changes'))), { drawer: true });
  }
  function addTaskEditor(p, onDone) {
    const rf = rewardFields(null), err = h('div.err', { role: 'alert' });
    const title = inp({ ph: 'e.g. Buy 5 coffees', maxlength: 120 }), type = sel(TASK_TYPES, 'count'), target = inp({ type: 'number', min: '1', value: '5' }), item = inp({ ph: 'Item name (optional)', maxlength: 80 });
    const m = modal(t('Add a reward'), h('div.stack', h('p.muted', t('Add another stamp card to “{p}”. Nobody\'s current progress changes.', { p: p.title })),
      h('div.card.stack', h('b', t('How customers earn')), field('Name', title), h('div.g2', field('Earn by', type), field('Target', target)), field('Item', item)),
      h('div.card.stack', h('b', t('What they get')), rf.view), err,
      h('button.btn.lg', { onclick: e => busy(e.target, async () => {
        try { await api('programs/' + p.id + '/tasks/', 'POST', { title: title.value, type: type.value, target: +target.value, item_name: item.value, reward: rf.body() });
          m.close(); await FX.reloadShops(); toast(t('Reward added')); onDone(); } catch (x) { err.textContent = x.message; }
      }) }, t('Add reward'))), { drawer: true });
  }
  function programEditor(p, onDone) {
    const title = inp({ value: p.title, maxlength: 120 }), st = inp({ type: 'date', value: p.start || '' }), en = inp({ type: 'date', value: p.end || '' }), err = h('div.err', { role: 'alert' });
    const m = modal(t('Edit program'), h('div.stack', field('Name', title), h('div.g2', field('Starts', st), field('Ends', en)), h('small.muted', t('Leave dates empty to run all the time.')), err,
      h('button.btn', { onclick: e => busy(e.target, async () => { try { await api('programs/' + p.id + '/', 'PATCH', { title: title.value.trim() || p.title, start: st.value || null, end: en.value || null }); m.close(); await FX.reloadShops(); toast(t('Saved')); onDone(); } catch (x) { err.textContent = x.message; } }) }, t('Save'))));
  }
  /* who is collecting this reward: progress, who is close, who has a reward waiting, and a one-tap reminder */
  async function peopleDrawer(tk) {
    const body = h('div.stack', h('div.skel.block'), h('div.skel.block')), m = modal(tk.title, body, { drawer: true });
    try {
      const rw = tk.rewards[0], row = rw && (await api('b/' + code() + '/reward-activity/')).rewards.find(x => x.id === rw.id);
      if (!row || !row.customers.length) { body.replaceChildren(empty('No customers yet', 'Customers appear here as soon as they start collecting.')); return; }
      const pct = c => Math.min(100, Math.round(100 * Number(c.current) / Number(c.target || 1)));
      const FILTERS = [['all', 'Everyone'], ['close', 'Close to reward'], ['ready', 'Reward ready'], ['done', 'Redeemed']];
      const match = (c, f) => f === 'all' || (f === 'close' && pct(c) >= 60 && !c.available) || (f === 'ready' && c.available > 0) || (f === 'done' && c.redeemed > 0);
      const msgFor = c => c.available > 0 ? t('Your reward is ready to use!') : t('Only {n} more to unlock: {r}', { n: FX.fmtVal(row.task_type, Math.max(0, c.target - c.current)), r: row.title });
      let f = 'all'; const chips = h('div.chips'), list = h('div.stack.s');
      const person = c => h('div.li', { style: 'align-items:flex-start' }, h('div.grow.stack.s', h('div.row.wrap', h('b', c.name + ' · …' + c.mobile.slice(-4)),
          c.available > 0 ? pill('🎁 ' + t('{n} ready', { n: c.available }), 'ok') : null, c.redeemed ? pill(t('Redeemed {n}', { n: c.redeemed }), 'info') : null),
        h('div.bar', h('i', { style: { width: pct(c) + '%' } })),
        h('small.muted', FX.fmtVal(row.task_type, c.current) + ' / ' + FX.fmtVal(row.task_type, c.target) + (c.last_activity ? ' · ' + t('last activity {d}', { d: FX.fmtDate(c.last_activity) }) : '')),
        h('div.row.wrap', h('a.btn.ghost.sm', { href: 'tel:' + c.mobile }, t('Call')), h('a.btn.ghost.sm', { href: 'https://wa.me/91' + c.mobile.slice(-10), target: '_blank', rel: 'noopener' }, 'WhatsApp'),
          c.can_nudge ? h('button.btn.sm', { onclick: e => busy(e.target, async () => { await api('b/' + code() + '/customers/' + c.profile_id + '/nudge/', 'POST', { text: msgFor(c) }); toast(t('Reminder sent')); e.target.disabled = true; }) }, t('Send reminder')) : h('small.muted', t('Has not agreed to offers')))));
      const draw = () => {
        chips.replaceChildren(...FILTERS.map(([k, l]) => h('button.chip', { 'aria-pressed': String(k === f), onclick: () => { f = k; draw(); } }, t(l) + ' (' + row.customers.filter(c => match(c, k)).length + ')')));
        const rows = row.customers.filter(c => match(c, f));
        list.replaceChildren(...(rows.length ? rows.map(person) : [empty('Nobody here yet')]));
      };
      draw();
      const st = row.stats;
      body.replaceChildren(h('div.row.wrap', pill('👥 ' + t('{n} collecting', { n: st.in_progress }), 'info'), pill('🎁 ' + t('{n} ready', { n: st.available }), st.available ? 'ok' : ''), pill('✅ ' + t('{n} redeemed', { n: st.redeemed }))),
        h('small.muted', t('Reminders go only to customers who agreed to offers, one every 3 days per customer.')), chips, list);
    } catch (x) { body.replaceChildren(h('p.err', x.message)); }
  }
  /* Quick add: the whole reward on one screen. Pick how customers earn, set a number, say what they get, see it, done. */
  const GIVE_IDEAS = { cafe: ['Free coffee', 'Free cookie', 'Free pastry'], restaurant: ['Free dessert', 'Free starter', 'Free drink'], grocery: ['Free item', 'Free delivery', 'Free bag of rice'],
    retail: ['Free gift', 'Free accessory', 'Free alteration'], salon: ['Free hair spa', 'Free add-on', 'Free head massage'], fitness: ['Free class', 'Free protein shake', '1 week free'],
    services: ['Free service check', 'Free add-on', 'Free pickup'], other: ['Free item', 'Free gift', 'Free upgrade'] };
  const QUICK_TPL = { stamps: ['🛍️', 'Buy and get', [5, 8, 10, 12]], spend: ['💰', 'Spend and get', [500, 1000, 2000, 5000]], visits: ['🔁', 'Visit and get', [3, 5, 8, 10]] };
  function quickReward(onDone) {
    const cat = (S.biz && S.biz.category) || 'other';
    let tpl = 'stamps', gtype = 'free_item', touched = false;
    const n = inp({ type: 'number', inputmode: 'numeric', min: '1', value: '8', 'aria-label': t('How many?') }), item = inp({ maxlength: 80, ph: 'e.g. coffees' });
    const gval = inp({ type: 'number', inputmode: 'numeric', min: '1', value: '10', 'aria-label': t('Amount') }), give = inp({ maxlength: 120, ph: 'e.g. Free coffee' });
    const days = sel([[7, '7 days'], [15, '15 days'], [30, '30 days'], [60, '60 days'], [90, '90 days']].map(([v, l]) => [v, t(l)]), 30), err = h('div.err', { role: 'alert' });
    const tplBox = h('div.tplrow'), nChips = h('div.chips'), giveBox = h('div.chips'), ideas = h('div.chips'), prev = h('div.focus'), nLabel = h('span'), gvalField = h('div.field', h('span', t('Amount')), gval);
    const itemField = h('div.field', h('span', t('What do they buy? (optional)')), item);
    const autoTitle = () => { if (touched) return; give.value = gtype === 'percent_off' ? t('{v}% off your next bill', { v: gval.value || 0 }) : gtype === 'flat_off' ? t('₹{v} off your next bill', { v: gval.value || 0 }) : gtype === 'cashback' ? t('₹{v} cashback', { v: gval.value || 0 }) : give.value; };
    const sentence = () => { const g = give.value.trim() || t('your reward'), nn = n.value || 0;
      return tpl === 'stamps' ? t('Customers buy {n} {i} and get: {g}', { n: nn, i: item.value.trim() || t('times'), g })
        : tpl === 'spend' ? t('Customers spend {a} in total and get: {g}', { a: FX.rupee(nn), g }) : t('Customers visit {n} times and get: {g}', { n: nn, g }); };
    const drawPrev = () => { const stamps = tpl !== 'spend' && Number(n.value) > 0 && Number(n.value) <= 12 ? FX.stampRow(0, Number(n.value), 'count', true) : null;
      prev.replaceChildren(h('div.stack.s', h('small.muted', t('What your customers will see')), h('b', QUICK_TPL[tpl][0] + ' ' + (tpl === 'stamps' ? t('Buy {n} {i}', { n: n.value || 0, i: item.value.trim() }) : tpl === 'spend' ? t('Spend {a}', { a: FX.rupee(n.value || 0) }) : t('Visit {n} times', { n: n.value || 0 })).trim()),
        stamps, h('div.bar', h('i', { style: 'width:0%' })), h('p.small', sentence()))); };
    const draw = () => {
      tplBox.replaceChildren(...Object.entries(QUICK_TPL).map(([k, [em, label]]) => h('button.tplbtn', { type: 'button', 'aria-pressed': String(k === tpl), onclick: () => { tpl = k; n.value = QUICK_TPL[k][2][1]; draw(); } }, h('span.te', em), h('span', t(label)))));
      nLabel.textContent = tpl === 'stamps' ? t('How many purchases?') : tpl === 'spend' ? t('How much do they spend (₹)?') : t('How many visits?');
      nChips.replaceChildren(...QUICK_TPL[tpl][2].map(v => h('button.chip', { type: 'button', 'aria-pressed': String(String(v) === String(n.value)), onclick: () => { n.value = v; draw(); } }, tpl === 'spend' ? FX.rupee(v) : '×' + v)));
      itemField.hidden = tpl !== 'stamps';
      giveBox.replaceChildren(...[['free_item', '🎁', 'A free item'], ['percent_off', '％', 'Percent off'], ['flat_off', '₹', 'Money off'],
        ['cashback', '↩️', 'Cashback'], ['special_offer', '✨', 'Special offer']].map(([k, em, l]) => h('button.chip', { type: 'button', 'aria-pressed': String(k === gtype), onclick: () => { gtype = k; touched = false; if (k === 'free_item') give.value = ''; autoTitle(); draw(); } }, em + ' ' + t(l))));
      gvalField.hidden = gtype === 'free_item'; gvalField.querySelector('span').textContent = gtype === 'percent_off' ? t('Percent off (1 to 100)') : gtype === 'cashback' ? t('Cashback amount') : gtype === 'special_offer' ? t('Amount (optional)') : t('Rupees off');
      ideas.replaceChildren(...(gtype === 'free_item' ? (GIVE_IDEAS[cat] || GIVE_IDEAS.other).map(x => h('button.chip', { type: 'button', onclick: () => { give.value = x; touched = true; drawPrev(); } }, t(x))) : []));
      drawPrev();
    };
    [n, item, give].forEach(x => x.addEventListener('input', () => { if (x === give) touched = true; if (x === n) nChips.querySelectorAll('.chip').forEach((c, i) => c.setAttribute('aria-pressed', String(String(QUICK_TPL[tpl][2][i]) === String(n.value)))); drawPrev(); }));
    gval.addEventListener('input', () => { autoTitle(); drawPrev(); });
    draw();
    const go = h('button.btn.lg', { onclick: () => busy(go, async () => {
      err.textContent = '';
      try {
        await api('b/' + code() + '/rewards/quick/', 'POST', { template: tpl, n: +n.value, item: item.value, give: give.value, give_type: gtype, give_value: gtype === 'free_item' ? 0 : +gval.value, expiry_days: +days.value });
        m.close(); await FX.reloadShops(); FX.confetti(40); toast(t('Reward added. Customers can start earning it now.')); onDone();
      } catch (x) { err.textContent = x.message; }
    }) }, t('Add reward'));
    const m = modal(t('Quick add a reward'), h('div.stack', h('p.muted', t('Three quick steps. You can edit everything later.')),
      h('div.stack.s', h('b', '1. ' + t('How do customers earn?')), tplBox),
      h('div.stack.s', h('b', '2. '), h('div.field', nLabel, n), nChips, itemField),
      h('div.stack.s', h('b', '3. ' + t('What do they get?')), giveBox, gvalField, ideas, h('div.field', h('span', t('Reward name')), give), h('div.field', h('span', t('Valid for')), days)),
      prev, err, go), { drawer: true });
  }
  function programCard(p, onDone, stats) {
    const pill1 = p.archived ? pill(t('Archived')) : p.active ? pill(t('Active'), 'ok') : pill(t('Paused'), 'warn');
    const when = p.start || p.end ? h('small.muted', (p.start ? t('From {d}', { d: FX.fmtDate(p.start) }) : '') + (p.start && p.end ? ' · ' : '') + (p.end ? t('Until {d}', { d: FX.fmtDate(p.end) }) : '')) : null;
    return h('div.card.stack', h('div.hd', h('div', h('h3', p.title), when), pill1),
      p.tasks.map(tk => { const st = tk.rewards[0] && stats[tk.rewards[0].id];
        const rewardRows = tk.rewards.map(r => {
          const rewardStats = stats[r.id], canDelete = rewardStats && rewardStats.participants === 0;
          return h('div.row.wrap', h('span.grow.small.muted', '🎁 ' + r.title),
            p.archived ? null : h('button.btn.danger.sm', {
              disabled: !canDelete,
              title: canDelete ? t('Delete this reward') : rewardStats ? t('Customers are already using this reward') : t('Customer activity could not be checked'),
              onclick: e => busy(e.target, async () => {
                if (!await confirmBox(t('Delete this reward? This removes only this reward and cannot be undone.'), t('Delete reward'), true)) return;
                await api('rewards/' + r.id + '/', 'DELETE');
                await FX.reloadShops(); toast(t('Reward deleted')); onDone();
              })
            }, t('Delete reward')));
        });
        return h('div.li', { style: 'align-items:flex-start' }, h('div.grow.stack.s', h('b', tk.title), h('div.stack.s', rewardRows),
          st ? h('small', '👥 ' + t('{n} collecting', { n: st.in_progress }) + (st.available ? ' · 🎁 ' + t('{n} ready', { n: st.available }) : '') + (st.redeemed ? ' · ✅ ' + t('{n} redeemed', { n: st.redeemed }) : '')) : null),
          h('div.row.wrap', { style: 'justify-content:flex-end' }, h('button.btn.soft.sm', { onclick: () => peopleDrawer(tk) }, '👥 ' + t('Who')), p.archived ? null : h('button.btn.ghost.sm', { onclick: () => taskEditor(tk, onDone) }, t('Edit'))));
      }),
      p.archived ? null : h('div.row.wrap', h('button.btn.soft.sm', { onclick: () => addTaskEditor(p, onDone) }, '+ ' + t('Add reward')), h('button.btn.ghost.sm', { onclick: () => programEditor(p, onDone) }, t('Rename and dates')),
        h('button.btn.ghost.sm', { onclick: e => busy(e.target, async () => { await api('programs/' + p.id + '/', 'PATCH', { active: !p.active }); await FX.reloadShops(); onDone(); }) }, t(p.active ? 'Pause' : 'Resume')),
        h('button.btn.danger.sm', { onclick: async () => { if (await confirmBox(t('Delete this program? If customers already have progress it is archived instead.'), t('Delete'), true)) { await api('programs/' + p.id + '/', 'DELETE'); await FX.reloadShops(); onDone(); } } }, t('Delete'))));
  }
  function boostEditor(b, onDone) {
    const title = inp({ value: b ? b.title : '', maxlength: 80, ph: 'e.g. Tuesday double stamps' }), mult = sel([[2, '2x'], [3, '3x']], b ? b.multiplier : 2);
    const days = new Set(b && b.weekdays ? b.weekdays.split(',').map(Number) : []);
    const st = inp({ type: 'time', value: b && b.start_time ? b.start_time.slice(0, 5) : '' }), en = inp({ type: 'time', value: b && b.end_time ? b.end_time.slice(0, 5) : '' });
    const dayRow = h('div.chips', [0, 1, 2, 3, 4, 5, 6].map(i => h('button.chip', { type: 'button', 'aria-pressed': String(days.has(i)), onclick: e => { days.has(i) ? days.delete(i) : days.add(i); e.currentTarget.setAttribute('aria-pressed', String(days.has(i))); } }, wd(i))));
    const err = h('div.err');
    const m = modal(t(b ? 'Edit boost' : 'New boost'), h('div.stack', field('Name', title), field('Multiplier', mult), h('div.field', h('span', t('Days')), dayRow, h('small', t('Leave empty for every day.'))), h('div.g2', field('From', st), field('Until', en)), h('small.muted', t('Boosts apply to visit and item stamps, not to spend totals.')), err,
      h('button.btn', { onclick: e => busy(e.target, async () => {
        try { const body = { title: title.value.trim(), multiplier: +mult.value, weekdays: [...days].sort().join(','), start_time: st.value || null, end_time: en.value || null };
          await api(b ? 'boosts/' + b.id + '/' : 'b/' + code() + '/boosts/', b ? 'PATCH' : 'POST', body); m.close(); onDone(); } catch (x) { err.textContent = x.message; }
      }) }, t('Save boost'))));
  }
  async function socialFollowRequests() {
    const data = await api('b/' + code() + '/social-follow/claims/');
    if (!data.enabled) return null;
    const review = (id, action) => async e => {
      if (action === 'approve' && !await confirmBox(t('Confirm you saw this customer follow a shop profile?'), t('Approve reward'))) return;
      await busy(e.target, async () => {
        await api('b/' + code() + '/social-follow/claims/' + id + '/', 'POST', { action });
        toast(t(action === 'approve' ? 'Reward approved and added to the customer wallet.' : 'Follow request rejected.'));
        FX.render(true);
      });
    };
    return h('div.card.stack', h('div.hd', h('h3', t('Social follow requests')), data.claims.length ? pill(data.claims.length, 'warn') : null),
      data.reward_configured ? h('p.small.muted', t('Check the customer follows a listed profile before approving.')) :
        h('p.small.muted', t('Configure the social follow reward before approving requests.')),
      data.claims.length ? data.claims.map(claim => h('div.li',
        h('div.grow', h('b', claim.name), h('div.small.muted', t('Mobile ending in {digits} · {time}', { digits: claim.mobile_last4, time: FX.fmtDT(claim.requested_at) }))),
        h('div.row.wrap', data.reward_configured ? h('button.btn.sm', { onclick: review(claim.id, 'approve') }, t('Approve and issue reward')) : null,
          h('button.btn.danger.sm', { onclick: review(claim.id, 'reject') }, t('Reject'))))) :
        empty('No social follow requests', 'Customer requests to verify a social follow appear here.'));
  }

  function perkEditor(trig, cur, onDone) {
    const title = inp({ value: cur ? cur.title : '', maxlength: 120, ph: 'e.g. Free cookie' }), type = sel(REWARD_TYPES, cur ? cur.type : 'gift'), val = inp({ type: 'number', min: '0', value: cur ? cur.value : 0 }), days = inp({ type: 'number', min: '1', max: '365', value: cur ? cur.expiry_days : 30 });
    const label = trig === 'welcome' ? 'Welcome gift' : trig === 'referral' ? 'Referral reward' : 'Social follow reward';
    const description = trig === 'welcome' ? 'Given after a new customer\'s first approved purchase.' :
      trig === 'referral' ? 'Given to the customer who invited a friend, after the friend\'s first purchase.' :
        'Issued once after staff verify a customer follows one of your social profiles.';
    const m = modal(t(label), h('div.stack', h('p.muted', t(description)),
      field('Reward', title), h('div.g2', field('Type', type), field('Value (₹ or %)', val)), field('Valid for (days)', days),
      h('div.row', cur ? h('button.btn.danger', { onclick: e => busy(e.target, async () => { await api('b/' + code() + '/perks/', 'PUT', { [trig]: null }); m.close(); onDone(); }) }, t('Turn off')) : null,
        h('button.btn.grow', { onclick: e => busy(e.target, async () => { await api('b/' + code() + '/perks/', 'PUT', { [trig]: { title: title.value, type: type.value, value: val.value, expiry_days: days.value } }); m.close(); onDone(); }) }, t('Save')))));
  }
  R.rewards = async function () {
    const [boosts, perks, act] = await Promise.all([api('b/' + code() + '/boosts/'), api('b/' + code() + '/perks/'), api('b/' + code() + '/reward-activity/').catch(() => ({ rewards: [] }))]);
    const followRequests = await socialFollowRequests();
    const stats = {}; act.rewards.forEach(r => { stats[r.id] = r.stats; });
    const biz = S.biz, done = () => FX.render(true);
    const silver = inp({ type: 'number', min: '0', value: biz.tier_silver_visits }), gold = inp({ type: 'number', min: '0', value: biz.tier_gold_visits }), sp = inp({ value: biz.silver_perk, maxlength: 120, ph: 'e.g. Free size upgrade' }), gp = inp({ value: biz.gold_perk, maxlength: 120, ph: 'e.g. Priority service' });
    const perkCard = (trig, label, hint) => h('div.card.stack', h('b', t(label)), perks[trig] ? h('p', '🎁 ' + perks[trig].title) : h('p.muted', t(hint)), h('button.btn.soft.sm', { onclick: () => perkEditor(trig, perks[trig], done) }, t(perks[trig] ? 'Edit' : 'Set up')));
    return h('div.stack.l', h('div.hd', h('div', h('h1', t('Rewards')), h('p.muted', t('Give customers a reason to come back'))), h('div.row.wrap', h('button.btn.ghost', { onclick: () => blueprintPicker(done) }, t('Use a template')), h('button.btn.ghost', { onclick: () => programBuilder(done) }, '+ ' + t('New program')), h('button.btn', { onclick: () => quickReward(done) }, '⚡ ' + t('Quick add a reward')))),
      biz.programs.length ? h('div.g2', biz.programs.map(p => programCard(p, done, stats))) : empty('No programs yet', 'Start from a template or build your own.'),
      h('div.section', h('div.hd', h('h2', t('Boosts')), h('button.btn.soft.sm', { onclick: () => boostEditor(null, done) }, '+ ' + t('Add boost'))), h('p.muted.small', t('Double stamps on slow days or hours bring customers in when you need them.')),
        h('div.card', boosts.length ? boosts.map(b => h('div.li', h('div.grow', h('b', b.title + ' (' + b.multiplier + 'x)'), h('div.small.muted', (b.weekdays ? b.weekdays.split(',').map(i => wd(+i)).join(', ') : t('Every day')) + (b.start_time ? ' · ' + b.start_time.slice(0, 5) + '-' + b.end_time.slice(0, 5) : ''))),
          h('button.btn.ghost.sm', { onclick: e => busy(e.target, async () => { await api('boosts/' + b.id + '/', 'PATCH', { active: !b.active }); done(); }) }, t(b.active ? 'Pause' : 'Resume')),
          h('button.btn.ghost.sm', { onclick: () => boostEditor(b, done) }, t('Edit')),
          h('button.btn.danger.sm', { onclick: e => busy(e.target, async () => { await api('boosts/' + b.id + '/', 'DELETE'); done(); }) }, t('Delete')))) : empty('No boosts yet'))),
      followRequests,
      h('div.section', h('h2', { style: 'margin-bottom:12px' }, t('Welcome, referral and social rewards')), h('div.g2', perkCard('welcome', 'Welcome gift', 'Make new customers feel welcome on their first purchase.'), perkCard('referral', 'Referral reward', 'Reward customers who bring friends.'), perkCard('social', 'Social follow reward', 'Reward customers after staff confirm they follow a social profile.'))),
      h('div.section', h('h2', { style: 'margin-bottom:12px' }, t('Membership tiers')), h('div.card.stack', h('p.muted.small', t('Tiers are based on total visits. Perks are things you honour at the counter.')),
        h('div.g2', field('Silver after (visits)', silver), field('Gold after (visits)', gold)), h('div.g2', field('Silver perk', sp), field('Gold perk', gp)),
        h('button.btn.sm', { style: 'justify-self:start', onclick: e => busy(e.target, async () => { await api('b/' + code() + '/settings/', 'PATCH', { tier_silver_visits: +silver.value, tier_gold_visits: +gold.value, silver_perk: sp.value, gold_perk: gp.value }); await FX.reloadShops(); toast(t('Saved')); }) }, t('Save tiers')))));
  };
})(window.FX);
