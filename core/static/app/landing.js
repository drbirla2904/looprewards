/* OFFLet landing page for logged-out visitors: hero + sign-in, how it works, features by audience, pricing, FAQ.
   FX.authScreen stays the hero so referral links (?ref=) and partner sign-ups behave exactly as before. */
(function (FX) {
  'use strict';
  const { h, t, api } = FX;

  const HOW = [['Print the QR', 'Choose your business type. Get a ready-made rewards program and QR code.'],
    ['Customers scan and collect', 'Customers join with a mobile number and collect after each purchase.'],
    ['They come back for more', 'Approve visits and send offers that bring customers back.']];
  const FEATURES = {
    shops: [['⚡', 'One-tap setup', 'Ready-made rewards for cafes, salons, grocery shops and more.'],
      ['✅', 'Approve with undo', 'Review visits. Counter codes approve instantly.'],
      ['👥', 'Know your customers', 'Find regulars and customers who may need a reminder.'],
      ['📣', 'Win-back offers', 'Message customers who opted in.'],
      ['⚡', 'Double-stamp boosts', 'Reward visits during quiet hours. Undo changes safely.'],
      ['📅', 'Bookings', 'Take appointment requests and credit completed visits.'],
      ['📊', 'Honest insights', 'See return visits, busy hours, redemptions and ratings.'],
      ['🖨️', 'Print kit', 'Print branded counter cards and posters.'],
      ['🔒', 'Private by design', 'Each shop sees only its own customers.']],
    customers: [['🎟️', 'Digital stamp cards', 'Track rewards at every shop in one place.'],
      ['👆', 'One-tap check-in', 'Check in after a purchase; the shop confirms your visit.'],
      ['🎁', 'Reward pass with QR', 'Show a code staff can scan.'],
      ['🔥', 'Streaks and tiers', 'Build a weekly streak and unlock tier perks.'],
      ['👫', 'Invite friends', 'Invite a friend; both earn after their first purchase.'],
      ['🇮🇳', 'हिन्दी and English', 'Switch language any time. No download needed.']],
    partners: [['💸', 'Earn on subscriptions', 'Earn commission on shop subscriptions.'],
      ['🏅', 'Partner tiers', 'Refer more shops to unlock higher commission rates.'],
      ['📄', 'Ready marketing kit', 'Get a printable QR flyer and WhatsApp messages.'],
      ['🧾', 'Clear statements', 'View payouts, tax deductions and yearly statements.']]
  };
  const FAQ = [['Do my customers need to install an app?', 'No. Scan the shop QR code in your phone browser.'],
    ['How does the free trial work?', 'Get {d} days free. No card required. Choose a plan before it ends.'],
    ['What if I stop paying?', 'Your shop pauses, but its data stays safe. Renew to restore it.'],
    ['How do I pay?', 'Pay by UPI, card or netbanking. AutoPay is optional. GST invoices are available.'],
    ['Can customers cheat the system?', 'Visits need shop approval or a rotating counter code. Daily limits and location checks help prevent misuse.'],
    ['Is it available in Hindi?', 'Yes. Switch between English and हिन्दी any time.']];

  FX.landing = async function () {
    let plans = null;
    try { plans = await api('plans/'); } catch (e) { /* pricing section is simply hidden */ }
    const hero = FX.authScreen({});
    hero.id = 'start';
    const toStart = () => { document.getElementById('start').scrollIntoView({ behavior: 'smooth' }); };
    const jump = id => e => { e.preventDefault(); const el = document.getElementById(id); if (el) el.scrollIntoView({ behavior: 'smooth' }); };
    const grid = h('div.feat');
    const seg = h('div.seg', { role: 'tablist' });
    let who = 'shops';
    const draw = () => {
      seg.replaceChildren(...[['shops', 'For shops'], ['customers', 'For customers'], ['partners', 'For partners']].map(([k, l]) => h('button', { type: 'button', role: 'tab', 'aria-selected': String(k === who), onclick: () => { who = k; draw(); } }, t(l))));
      grid.replaceChildren(...FEATURES[who].map(([em, title, text]) => h('div', h('span.em', em), h('b', t(title)), h('p.muted.small', t(text)))));
    };
    draw();
    const price = plans && plans.plans ? h('section.alt#pricing', h('div.wrapw', h('h2.sec', t('Simple pricing')), h('p.sec', t('Start free for {d} days. No card needed.', { d: plans.trial_days })),
      h('div.plans', { style: 'max-width:760px;margin:0 auto' }, Object.keys(plans.plans).map(k => {
        const p = plans.plans[k], best = k === 'yearly', save = plans.plans.monthly ? plans.plans.monthly.amount * 12 - p.amount : 0;
        return h('div.plan' + (best ? '.best' : ''), best && save > 0 ? h('span.ribbon', t('Save {a}', { a: FX.rupee(save / 100) })) : null,
          h('h3', t(p.label)), h('div.price', FX.rupee(p.amount / 100), h('small', ' / ' + t(best ? 'year' : 'month'))), h('small.muted', t('Includes GST')),
          h('ul', ['Unlimited customers and rewards', 'Counter code and instant approvals', 'Offers, boosts and bookings', 'Hindi and English for your customers'].map(f => h('li', t(f)))),
          h('button.btn.lg' + (best ? '.gold' : ''), { onclick: toStart }, t('Start free trial')));
      })))) : null;
    return h('div.land',
      h('div.navbar', h('a.logo', { href: '/app/', style: 'padding:0' }, h('img', { src: '/icon.svg', alt: '' }), 'OFFLet'), h('div.grow'),
        h('a.l', { href: '#how', onclick: jump('how') }, t('How it works')), h('a.l', { href: '#features', onclick: jump('features') }, t('Features')),
        plans ? h('a.l', { href: '#pricing', onclick: jump('pricing') }, t('Pricing')) : null, h('a.l', { href: '#faq', onclick: jump('faq') }, t('FAQ')),
        h('button.btn.ghost.sm', { onclick: () => { FX.setLang(FX.lang === 'hi' ? 'en' : 'hi'); FX.start(true); } }, FX.lang === 'hi' ? 'English' : 'हिन्दी'),
        h('button.btn.sm', { onclick: toStart }, t('Get started'))),
      h('div.hero-wrap', hero),
      h('section#how', h('div.wrapw', h('h2.sec', t('Up and running in a minute')), h('p.sec', t('No hardware or app needed.')),
        h('div.how', HOW.map(([title, text], i) => h('div', h('span.n', i + 1), h('h3', t(title)), h('p.muted', t(text))))))),
      h('section.alt#features', h('div.wrapw', h('h2.sec', t('Everything to bring customers back')), h('p.sec', t('Simple tools for shops, salons and studios.')), h('div.tabs3', seg), grid)),
      price,
      h('section#faq', h('div.wrapw', h('h2.sec', t('Questions, answered')), h('div.faq', FAQ.map(([q, a]) => h('details', h('summary', t(q)), h('p', t(a, { d: plans ? plans.trial_days : 14 }))))))),
      h('section.cta', h('h2', t('Give customers a reason to come back.')), h('p', t('Create your free account in 30 seconds.')), h('button.btn.lg.gold', { onclick: toStart }, t('Start free trial'))));
  };
})(window.FX);
