/* OFFLet v2 partner (sales agent) portal: apply, referral link, earnings, onboard a shop for an owner. */
(function (FX) {
  'use strict';
  const { h, api, field, inp, sel, pill, empty, kpi, toast, modal, busy } = FX;
  const t = FX.t, R = FX.routes.vendor;
  const paise = n => FX.rupee((n || 0) / 100);

  function applyForm(me, asOwner) {
    const pan = inp({ maxlength: 10, autocapitalize: 'characters', ph: 'ABCDE1234F' }), upi = inp({ ph: 'yourname@upi' }), err = h('div.err');
    return h('div.stack.l', { style: 'max-width:560px' }, h('div', h('h1', t(asOwner ? 'Refer and earn' : 'Become a partner')), h('p.muted', t(asOwner ? 'Refer other businesses to OFFLet and earn a commission in your wallet every time they pay.' : 'Earn a commission every time a shop you bring pays for OFFLet.'))),
      h('div.card.stack', field('PAN', pan, 'Needed for TDS and payouts.'), field('UPI ID for payouts', upi), err,
        h('button.btn.lg', { onclick: e => busy(e.target, async () => { try { const r = await api('vendor/apply/', 'POST', { pan: pan.value, upi_id: upi.value }); toast(t(r.detail)); FX.render(); } catch (x) { err.textContent = x.message; } }) }, t('Apply'))));
  }

  function assistModal(onDone) {
    const f = { owner_name: inp({ maxlength: 150 }), mobile: inp({ type: 'tel', inputmode: 'numeric', maxlength: 15 }), name: inp({ maxlength: 120 }), address: inp(), pay_upi_id: inp({ ph: 'optional' }) };
    const cat = sel([['cafe', 'Cafe'], ['restaurant', 'Restaurant'], ['grocery', 'Grocery'], ['retail', 'Retail'], ['salon', 'Salon'], ['fitness', 'Fitness'], ['services', 'Services'], ['other', 'Other']], 'other');
    /* the owner logs in with mobile + this password, so the partner sets it here (and tells the owner) */
    const pw = inp({ type: 'password', autocomplete: 'new-password', minlength: 6, maxlength: 64, ph: 'At least 6 characters' });
    const eye = h('button.btn.ghost.sm', { type: 'button', 'aria-label': t('Show password'), onclick: () => { pw.type = pw.type === 'password' ? 'text' : 'password'; eye.textContent = pw.type === 'password' ? t('Show') : t('Hide'); } }, t('Show'));
    const gen = h('button.btn.soft.sm', { type: 'button', onclick: () => {
      const a = 'abcdefghjkmnpqrstuvwxyz', n = '23456789', pick = s => s[crypto.getRandomValues(new Uint32Array(1))[0] % s.length];
      pw.value = Array.from({ length: 4 }, () => pick(a)).join('') + Array.from({ length: 4 }, () => pick(n)).join(''); pw.type = 'text'; eye.textContent = t('Hide');
    } }, t('Generate'));
    const err = h('div.err', { role: 'alert' });
    const m = modal(t('Set up a shop for an owner'), h('div.stack', field('Owner name', f.owner_name), field('Owner mobile', f.mobile), field('Shop name', f.name), field('Address', f.address), field('UPI ID', f.pay_upi_id), field('Business type', cat),
      h('div.card.stack', h('b', t('Owner login password')), h('small.muted', t('The owner logs in with their mobile number and this password. Tell it to them; they can change it later in Account.')),
        h('div.row', pw, eye, gen)), err,
      h('button.btn.lg', { onclick: e => busy(e.target, async () => {
        err.textContent = '';
        try {
          if (pw.value.length < 6) throw new Error(t('Set a password for the owner (at least 6 characters).'));
          const body = { category: cat.value, password: pw.value }; for (const [k, v] of Object.entries(f)) body[k] = v.value.trim();
          const r = await api('vendor/assist/', 'POST', body); m.close();
          const text = t('Your OFFLet account is ready. Mobile: {m}, password: {p}. Log in at {u}. You can change the password in Account.', { m: r.mobile, p: body.password, u: location.origin + '/app/' });
          modal(t('Account created'), h('div.stack', h('p', t('Share these login details with the owner now. For safety the password is not stored anywhere you can read it again.')),
            h('div.card', h('div.muted', t('Mobile')), h('b.num', { style: 'font-size:calc(20px * var(--font-scale, .8))' }, r.mobile), h('div.muted', { style: 'margin-top:8px' }, t('Password')), h('b.num', { style: 'font-size:calc(22px * var(--font-scale, .8))' }, body.password)),
            h('button.btn', { onclick: () => FX.share(text, '') }, t('Share on WhatsApp')), h('button.btn.ghost', { onclick: () => FX.copy(text) }, t('Copy'))));
          onDone();
        } catch (x) { err.textContent = x.message; }
      }) }, t('Create account'))));
  }

  const HEALTH = { new: ['No customers yet', 'warn'], live: ['Active', 'ok'], quiet: ['Quiet', 'warn'], idle: ['Inactive', 'bad'] };
  const NUDGE = {
    new: 'No customers yet. Help them print the QR code and put it at the counter.',
    quiet: 'Activity is slowing. Suggest a boost (double stamps) or a win-back offer.',
    idle: 'No recent visits. Visit or call the owner to restart their program.'
  };
  const ORDER = { idle: 0, new: 1, quiet: 2, live: 3 };

  function tierCard(d) {
    const tr = d.tier, pct = tr.next_at ? Math.min(100, Math.round(100 * tr.active_shops / tr.next_at)) : 100;
    return h('div.card.stack', h('div.hd', h('div', h('h3', t('{tier} partner', { tier: tr.name })), h('small.muted', t('{n} active paying shops', { n: tr.active_shops }))),
      pill(t('{r}% commission', { r: FX.num(d.effective_rate) }), 'ok')),
      h('div.bar', { style: 'height:8px;background:var(--bg);border-radius:9px;overflow:hidden' }, h('i', { style: { display: 'block', height: '100%', width: pct + '%', background: 'var(--brand)' } })),
      tr.next ? h('p.small', t('{n} more paying shops to reach {tier}: +{b}% on every payment.', { n: tr.to_next, tier: tr.next, b: tr.next_bonus })) : h('p.small', t('You are at the top tier. Thank you!')),
      h('div.chips', tr.ladder.map(l => h('span.chip' + (l.name === tr.name ? '.on' : ''), l.name + ' · ' + l.shops + '+ · +' + l.bonus + '%'))),
      h('small.muted', t('Only shops that are currently paid up count. Your rate on each payment is fixed when it is made.')));
  }
  function shopRow(b) {
    const hl = HEALTH[b.health], expired = b.state === 'expired' || b.state === 'grace';
    return h('div.li', { style: 'align-items:flex-start' }, h('div.grow', h('b', b.name), h('div.small.muted', (b.owner || '') + (b.owner ? ' · ' : '') + t('{c} customers', { c: b.customers }) + ' · ' + t('{v} visits in 30 days', { v: b.visits_30d }) + (b.last_activity ? ' · ' + t('Last activity {d}', { d: FX.ago(b.last_activity) }) : '')),
      expired ? h('div.small', { style: 'color:var(--red)' }, t('Plan ended. Ask them to renew so you keep earning.')) : (b.health !== 'live' ? h('div.small', NUDGE[b.health] ? t(NUDGE[b.health]) : '') : null)),
      h('div.stack.s', { style: 'justify-items:end' }, pill(t(hl[0]), hl[1]), pill(t(b.state), b.state === 'active' ? 'ok' : b.state === 'trial' ? 'info' : 'bad')));
  }

  R[''] = async function () {
    const d = await api('vendor/dashboard/');
    if (d.status === 'not_applied') return applyForm(d);
    if (d.status !== 'approved') return h('div.stack.l', h('h1', t('Application received')), h('div.banner.blue', t('We are reviewing your application. You will be notified once it is approved.')));
    const c = d.commission_paise, url = d.referral_url;
    const text = t('Grow your shop with repeat customers using OFFLet. Join here:');
    const shops = d.businesses.slice().sort((a, b) => (ORDER[a.health] - ORDER[b.health]));
    const needs = shops.filter(b => b.health !== 'live' || b.state === 'expired' || b.state === 'grace').length;
    return h('div.stack.l', h('div.hd', h('div', h('h1', t('Partner dashboard')), h('p.muted', t('Earn on every subscription payment from the shops you bring'))), h('button.btn', { onclick: () => assistModal(() => FX.render(true)) }, '+ ' + t('Onboard a shop'))),
      tierCard(d),
      h('div.card.stack', h('h3', t('Your referral link')), h('code', { style: 'word-break:break-all' }, url), h('div.row.wrap', h('button.btn', { onclick: () => FX.share(text, url) }, t('Share on WhatsApp')), h('button.btn.ghost', { onclick: () => FX.copy(url) }, t('Copy link')), h('a.btn.ghost', { href: '#/kit' }, t('Marketing kit')))),
      h('div.g4', kpi('Owners referred', d.referred_owner_count), kpi('Shops live', d.referred_shop_count), kpi('Ready to pay', paise(c.payable)), kpi('Paid so far', paise(c.paid), t('On hold: {a}', { a: paise(c.hold) }))),
      h('p.small.muted', t('Commissions are held for {n} days, then paid monthly once they reach {m}.', { n: d.commission_hold_days, m: paise(d.minimum_payout_paise) }) + ' ' + t('Details are in Earnings.')),
      h('div.card', h('div.hd', h('h3', t('Your shops')), needs ? pill(t('{n} need attention', { n: needs }), 'warn') : null), shops.length ? shops.map(shopRow) : empty('No shops yet', 'Share your link or onboard a shop yourself.')),
      d.recent_commissions.length ? h('div.card', h('h3', t('Recent commissions')), d.recent_commissions.map(x => h('div.li', h('div.grow', h('b', paise(x.amount)), h('div.small.muted', FX.fmtDate(x.date) + ' · ' + x.plan)), pill(t(x.status), x.status === 'paid' ? 'ok' : x.status === 'payable' ? 'info' : 'warn')))) : null,
      d.payouts.length ? h('div.card', h('h3', t('Payouts')), d.payouts.map(p => h('div.li', h('div.grow', h('b', paise(p.amount)), h('div.small.muted', FX.fmtDate(p.date) + (p.reference ? ' · ' + p.reference : ''))), pill(t(p.status), p.status === 'paid' ? 'ok' : 'warn')))) : null);
  };

  /* ---------- marketing kit ---------- */
  R.kit = async function () {
    const k = await api('vendor/kit/');
    const m = k.plans.monthly ? k.plans.monthly.price : 0;
    const en = 'Hi! I help local shops get repeat customers with OFFLet. Customers scan a QR code and collect stamps and rewards, and you can see who stopped coming and bring them back with an offer. Free ' + k.trial_days + '-day trial, then from ₹' + m + '/month. Try it here: ' + k.referral_url;
    const hi = 'नमस्ते! मैं OFFLet से दुकानों को दोबारा आने वाले ग्राहक दिलाने में मदद करता/करती हूँ। ग्राहक QR स्कैन करके स्टैम्प और रिवॉर्ड जमा करते हैं, और जो ग्राहक आना बंद कर दें उन्हें ऑफ़र भेजकर वापस ला सकते हैं। ' + k.trial_days + ' दिन फ़्री ट्रायल, फिर ₹' + m + '/महीने से। यहाँ आज़माएँ: ' + k.referral_url;
    const msg = (title, text) => h('div.card.stack', h('b', title), h('p.small', { style: 'white-space:pre-wrap' }, text), h('div.row.wrap', h('button.btn.sm', { onclick: () => FX.share(text, '') }, t('Share on WhatsApp')), h('button.btn.ghost.sm', { onclick: () => FX.copy(text) }, t('Copy'))));
    const faq = [['"I already have a punch card book."', 'Paper cards get lost and you cannot see who stopped coming. Here every customer is on your phone and you can message the ones who drift away.'],
      ['"Customers will not install an app."', 'They do not need to. They scan the QR code and join with their mobile number in 10 seconds.'],
      ['"Is it expensive?"', 'It is free for ' + k.trial_days + ' days, then from ₹' + m + ' a month. One returning customer a day usually pays for it.'],
      ['"I am not good with phones."', 'Pick your business type and a ready program is created for you. I will help you set it up.']];
    return h('div.stack.l', h('div', h('h1', t('Marketing kit')), h('p.muted', t('Everything you need to explain OFFLet and sign up shops'))),
      h('div.card.stack', h('h3', t('Printable flyer with your QR code')), h('p.muted.small', t('Shop owners scan it to start a free trial. It is linked to you, so you earn on their payments.')),
        h('div.row.wrap', h('a.btn', { href: k.flyer_url, target: '_blank', rel: 'noopener' }, t('Flyer in English')), h('a.btn.ghost', { href: k.flyer_url_hi, target: '_blank', rel: 'noopener' }, t('Flyer in Hindi')))),
      h('div.g2', msg(t('WhatsApp message (English)'), en), msg(t('WhatsApp message (Hindi)'), hi)),
      h('div.card.stack', h('h3', t('30-second pitch')), h('ol', { style: 'margin:0;padding-left:20px;display:grid;gap:6px' },
        ['Ask: "How do you make sure customers come back?"', 'Show: a customer scanning the QR code and getting a stamp.', 'Say: "You approve from your phone and see who stopped coming."', 'Offer: "Start free for ' + k.trial_days + ' days. I will set it up with you now."'].map(x => h('li', t(x))))),
      h('div.card.stack', h('h3', t('Common questions')), faq.map(([q, a]) => h('div.stack.s', h('b', t(q)), h('p.small.muted', t(a))))),
      h('div.card', h('h3', t('Prices to quote')), Object.values(k.plans).map(p => h('div.li', h('span.grow', t(p.label)), h('b.num', FX.rupee(p.price)), h('small.muted', t('GST included'))))));
  };

  /* ---------- earnings statements ---------- */
  async function downloadCsv(fy) {
    const r = await fetch('/api/vendor/statement/?fy=' + fy + '&download=csv', { headers: { Authorization: 'Token ' + FX.S.token } });
    if (!r.ok) throw new Error(t('Something went wrong. Please try again.'));
    const a = h('a', { href: URL.createObjectURL(await r.blob()), download: 'partner-statement-FY' + fy + '.csv' });
    document.body.appendChild(a); a.click(); a.remove();
  }
  R.statements = async function (args) {
    const q = args[0] ? '?fy=' + encodeURIComponent(args[0]) : '';
    const d = await api('vendor/statement/' + q), T = d.totals;
    return h('div.stack.l', h('div.hd', h('div', h('h1', t('Earnings')), h('p.muted', t('Financial year {a}-{b}', { a: d.fy, b: String(d.fy + 1).slice(2) }))),
      h('div.row.wrap', FX.sel(d.years.map(y => [y, y + '-' + String(y + 1).slice(2)]), d.fy, { style: 'width:auto', 'aria-label': t('Financial year'), onchange: e => FX.go('statements/' + e.target.value) }),
        h('button.btn.ghost', { onclick: e => busy(e.target, () => downloadCsv(d.fy)) }, t('Download CSV')))),
      h('div.g4', kpi('Commission earned', paise(T.earned)), kpi('Paid (before TDS)', paise(T.paid_gross)), kpi('TDS withheld', paise(T.tds)), kpi('Received in bank', paise(T.paid_net))),
      h('p.small.muted', t(d.tds_note)),
      h('div.card', h('h3', t('Commissions')), d.commissions.length ? d.commissions.map(c => h('div.li', h('div.grow', h('b', c.shop || '-'), h('div.small.muted', FX.fmtDate(c.date) + ' · ' + c.plan + ' · ' + t('{r}% of {b}', { r: FX.num(c.rate), b: paise(c.base) }))), h('b.num', paise(c.commission)),
        pill(t(c.status), c.status === 'paid' ? 'ok' : c.status === 'payable' ? 'info' : c.status === 'reversed' ? 'bad' : 'warn'))) : empty('No commissions in this year yet')),
      h('div.card', h('h3', t('Payouts')), d.payouts.length ? d.payouts.map(p => h('div.li', h('div.grow', h('b', t('Net {n}', { n: paise(p.net) })), h('div.small.muted', FX.fmtDate(p.date) + ' · ' + t('Gross {g}', { g: paise(p.gross) }) + (p.tds ? ' · ' + t('TDS {x}', { x: paise(p.tds) }) : '') + (p.reference ? ' · ' + p.reference : '')))) ) : empty('No payouts in this year yet')),
      h('p.small.muted', t('Commission is on the subscription amount excluding GST. Your PAN on file: {pan}.', { pan: d.pan })));
  };
  /* ---------- business owners: refer other businesses and earn in a wallet ---------- */
  const STATUS_PILL = { hold: ['On hold', 'warn'], payable: ['Payout processing', 'info'], paid: ['Paid out', 'ok'], reversed: ['Reversed', 'bad'], pending: ['Processing', 'info'] };
  function walletRow(r) {
    const st = STATUS_PILL[r.status] || [r.status, ''];
    if (r.kind === 'payout') {
      return h('div.li', h('div.grow', h('b', t('Payout to your UPI')), h('div.small.muted', FX.fmtDate(r.at) + (r.status === 'paid' ? ' · ' + t('Net {n}', { n: paise(r.net) }) + (r.tds ? ' · ' + t('TDS {x}', { x: paise(r.tds) }) : '') : '') + (r.reference ? ' · ' + r.reference : ''))),
        h('b.num', { style: 'color:var(--muted,#666)' }, '−' + paise(r.amount)), pill(t(st[0]), st[1]));
    }
    return h('div.li', h('div.grow', h('b', r.label || t('A business you referred')), h('div.small.muted', FX.fmtDate(r.at) + ' · ' + r.plan + (r.status === 'hold' ? ' · ' + t('Clears {d}', { d: FX.fmtDate(r.payable_on) }) : ''))),
      h('b.num', { style: r.status === 'reversed' ? 'text-decoration:line-through' : 'color:var(--green,#1b8a4b)' }, '+' + paise(r.amount)), pill(t(st[0]), st[1]));
  }
  function walletCard(w) {
    const note = w.meets_minimum ? t('{a} is ready and will be sent to your UPI on {d}.', { a: paise(w.ready), d: FX.fmtDate(w.next_payout) })
      : t('Earnings are held for {n} days, then paid monthly once they reach {m}.', { n: w.hold_days, m: paise(w.minimum_payout) });
    return h('div.card.stack', h('div.muted.small', t('Wallet balance')), h('div.num', { style: 'font-size:calc(34px * var(--font-scale, .8));font-weight:800' }, paise(w.balance)),
      h('div.g4', kpi('In hold period', paise(w.clearing)), kpi('Ready for payout', paise(w.ready)), kpi('Payout processing', paise(w.processing)), kpi('Paid to you', paise(w.paid_net), w.tds ? t('TDS withheld: {x}', { x: paise(w.tds) }) : '')),
      h('p.small.muted', note));
  }

  FX.routes.owner.kit = R.kit;
  FX.routes.owner.statements = R.statements;
  FX.routes.owner.refer = async function () {
    const [d, w] = await Promise.all([api('vendor/dashboard/'), api('vendor/wallet/')]);
    if (d.status === 'not_applied') return applyForm(d, true);
    if (d.status === 'suspended') return h('div.stack.l', h('h1', t('Refer and earn')), h('div.banner.blue', t('Your referral access is paused. Please contact support.')));
    if (d.status !== 'approved') return h('div.stack.l', h('h1', t('Application received')), h('div.banner.blue', t('We are reviewing your application. You will be notified once it is approved.')));
    const url = d.referral_url, text = t('I use OFFLet to bring customers back to my shop. Try it free:');
    const shops = d.businesses.slice().sort((a, b) => (ORDER[a.health] - ORDER[b.health]));
    return h('div.stack.l', h('div', h('h1', t('Refer and earn')), h('p.muted', t('Earn money in your wallet every time a business you refer pays for OFFLet'))),
      walletCard(w), tierCard(d),
      h('div.card.stack', h('h3', t('Your referral link')), h('code', { style: 'word-break:break-all' }, url),
        h('div.row.wrap', h('button.btn', { onclick: () => FX.share(text, url) }, t('Share on WhatsApp')), h('button.btn.ghost', { onclick: () => FX.copy(url) }, t('Copy link')), h('a.btn.ghost', { href: '#/kit' }, t('Marketing kit')), h('a.btn.ghost', { href: '#/statements' }, t('Earnings statement')))),
      h('div.g2', kpi('Businesses referred', d.referred_owner_count), kpi('Live shops', d.referred_shop_count)),
      h('div.card', h('h3', t('Businesses you referred')), shops.length ? shops.map(shopRow) : empty('No businesses yet', 'Share your link with other shop owners.')),
      h('div.card', h('h3', t('Wallet activity')), w.ledger.length ? w.ledger.map(walletRow) : empty('No earnings yet', 'You earn when a business you referred pays for a plan.')),
      h('p.small.muted', t('Commission is on the plan price excluding GST. You cannot earn on your own accounts or shops.')));
  };
})(window.FX);
