/* OFFLet landing page for logged-out visitors: hero + sign-in, how it works, features by audience, pricing, FAQ.
   FX.authScreen stays the hero so referral links (?ref=) and partner sign-ups behave exactly as before. */
(function (FX) {
  'use strict';
  const { h, t, api } = FX;

  const HOW = [['Print the QR', 'Pick your business type. A ready reward program is created in one tap, then print the counter card.'],
    ['Customers scan and collect', 'No app to install. A customer joins with a mobile number and taps once after each purchase.'],
    ['They come back for more', 'Approve from your phone, send win-back offers and watch your repeat customers grow.']];
  const FEATURES = {
    shops: [['⚡', 'One-tap setup', 'A ready program, welcome gift and referral reward for cafes, salons, grocery, fitness and more.'],
      ['✅', 'Approve with undo', 'A simple queue for you and your staff. Counter codes approve honest customers instantly.'],
      ['👥', 'Know your customers', 'New, regular, slipping away or lapsed. Search, add notes, call or WhatsApp in a tap.'],
      ['📣', 'Win-back offers', 'Send a message to customers who stopped visiting. Only to those who opted in.'],
      ['⚡', 'Double-stamp boosts', 'Fill your quiet hours with Tuesday or 2 to 5 pm boosts. Undo reverses exactly what was given.'],
      ['📅', 'Bookings', 'Salons and studios take appointment requests. Completed visits credit stamps automatically.'],
      ['📊', 'Honest insights', 'Come-back rate, busiest hours, rewards redeemed, ratings and a plain-language tip each day.'],
      ['🖨️', 'Print kit', 'Counter card, A5 and A4 posters, and a table tent with your logo, colours and QR.'],
      ['🔒', 'Private by design', 'Customers are visible only to the shop they joined. Delete-my-account is built in.']],
    customers: [['🎟️', 'Digital stamp cards', 'One wallet for every shop. See exactly how close your next reward is.'],
      ['👆', 'One-tap check-in', 'Tap after you buy. Get approved instantly with the counter code, or in minutes by the shop.'],
      ['🎁', 'Reward pass with QR', 'Show a code the staff can scan. No screenshots, no arguments at the counter.'],
      ['🔥', 'Streaks and tiers', 'Visit every week to keep your streak. Reach Silver and Gold for extra perks.'],
      ['👫', 'Invite friends', 'Share your link on WhatsApp. When a friend makes a first purchase you both win.'],
      ['🇮🇳', 'हिन्दी and English', 'Switch language any time. Works on any phone, no download.']],
    partners: [['💸', 'Earn on every renewal', 'A commission on each subscription payment from the shops you bring.'],
      ['🏅', 'Partner tiers', 'Bring more paying shops to reach Silver, Gold and Platinum for a higher rate.'],
      ['📄', 'Ready marketing kit', 'A printable flyer with your own QR, WhatsApp messages and a 30-second pitch.'],
      ['🧾', 'Clear statements', 'Monthly payouts, TDS and a financial-year statement you can download.']]
  };
  const FAQ = [['Do my customers need to install an app?', 'No. Customers scan your QR code and use OFFLet in their phone browser. They can add it to the home screen if they like.'],
    ['How does the free trial work?', 'You get {d} days free with no card needed. Everything works. Choose a plan any time before it ends.'],
    ['What if I stop paying?', 'Your shop page pauses, but your customers, progress and rewards are kept safe. Renew and everything comes back instantly.'],
    ['How do I pay?', 'Pay online with Razorpay (UPI, cards, netbanking), turn on AutoPay, or pay by UPI and upload the screenshot. Invoices include GST.'],
    ['Can customers cheat the system?', 'Entries need your approval or the rotating counter code. A location check, daily limits and cooldowns add protection, and you can block anyone.'],
    ['Is it available in Hindi?', 'Yes. Owners, staff, customers and partners can all switch between English and हिन्दी.']];

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
      h('section#how', h('div.wrapw', h('h2.sec', t('Up and running in a minute')), h('p.sec', t('No hardware, no app, no training.')),
        h('div.how', HOW.map(([title, text], i) => h('div', h('span.n', i + 1), h('h3', t(title)), h('p.muted', t(text))))))),
      h('section.alt#features', h('div.wrapw', h('h2.sec', t('Everything to bring customers back')), h('p.sec', t('Built for the way local shops, salons and studios really work.')), h('div.tabs3', seg), grid)),
      price,
      h('section#faq', h('div.wrapw', h('h2.sec', t('Questions, answered')), h('div.faq', FAQ.map(([q, a]) => h('details', h('summary', t(q)), h('p', t(a, { d: plans ? plans.trial_days : 14 }))))))),
      h('section.cta', h('h2', t('Give customers a reason to come back.')), h('p', t('Create your free account in 30 seconds.')), h('button.btn.lg.gold', { onclick: toStart }, t('Start free trial'))));
  };
})(window.FX);
