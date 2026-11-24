# OFFLet v2 upgrade

Goal: turn the loyalty tool into a SaaS platform that helps **local shops and service businesses bring customers back**,
using rewards, tasks, boosts, referrals and bookings. The existing API is unchanged (everything is additive), so old
clients, print kits, billing, vendors and legal pages keep working.

## What is new

### For owners
| Area | What it does |
|---|---|
| One-tap setup | Pick a business type (cafe, restaurant, grocery, retail, salon, fitness, services, other). A ready program, slow-hour boost, welcome gift, referral reward, tier perks and (for service types) a service menu are created. `core/blueprints.py` |
| Today screen | Approval queue first (approve/decline with Undo), booking requests, reward redeem box, KPIs, 30-day chart and plain-language tips ("12 customers have not visited in 30 days"). |
| Customers (CRM) | Segments computed live: new, regular, slipping away (31-60 days), lapsed (60+), not yet bought. Search, sort, private notes, block, call/WhatsApp, CSV export. |
| Offers | Segment-targeted messages to opted-in customers. Limits: 1 per audience per day, 3 per day. |
| Boosts | "Double stamps on Tuesdays / 2-5pm". Applies to visit and item tasks, never to spend totals. Undo reverses exactly what was credited. |
| Welcome + referral gifts | Welcome gift on a customer's first approved purchase; referral reward for the inviter after the friend's first purchase. Exactly once, even after an undo. |
| Membership tiers | Member / Silver / Gold from lifetime visit days, with perks you set. |
| Services and bookings | Customers request a slot, staff confirm, and "Completed" credits the visit to every live program (visit +1, spend += price). |
| Insights | Come-back rate, returning-visit share, tracked sales, busiest days/hours, customer groups, redeem rate, ratings. |
| Reviews | Customers rate approved visits and completed bookings; 1-2 star ratings alert the owner privately. |
| Branding | Logo, brand colour, about, phone, WhatsApp, maps link. Shop links show a proper preview card on WhatsApp. |
| Team | Staff list (was add/remove only). Staff get a focused queue, bookings and counter-code screens. |

### For customers
Wallet home with one stamp card per shop (brand colour, tier, week streak, active boost, next booking), shop page tabs
(Earn, Rewards, Book, History, Invite), ticket-style reward codes, referral link with WhatsApp share, ratings.

### Frontend
Rebuilt as a small modular app (`core/static/app/`): design system `app.css`, `core.js` (router, API, layout, auth),
`customer.js`, `owner.js`, `owner2.js`, `partner.js`, Hindi in `i18n-hi.js` (+ the classic tables reused for server
messages). No build step. The previous single-file UI is kept at `/app/classic/` for one release.

## Upgrade steps
```
pip install -r requirements.txt          # no new dependencies
python manage.py makemigrations --check  # must say "No changes detected" (0007 and 0008 are hand-written to match models.py)
python manage.py migrate
python manage.py test                    # existing suite + core/tests_growth.py + core/tests_vendor.py
python manage.py collectstatic --noinput # deploy.sh already does this
```
Bump `ASSET_VERSION` in `core/pages.py` on every frontend release (busts browser + service-worker cache).


## Partners (vendors who refer shops and earn from subscriptions)
Existing behaviour is unchanged: a partner is approved by you, owners who register through `/app/?ref=CODE` are attributed
permanently, and every paid subscription payment accrues a commission (on the ex-GST amount) that is held, bundled monthly
into a payout, and marked paid by you in the admin.

| New | What it does |
|---|---|
| Tiers | Bonus percentage points on top of the base rate, based on referred shops that are **currently paid up** (default: 5 = Silver +2, 15 = Gold +4, 40 = Platinum +6; edit `VENDOR_TIERS` in settings). The rate is frozen on each commission when it is created, so a later tier drop never changes past earnings. These defaults are placeholders: check them against your margins. |
| Shop activity | For every referred shop the partner sees customers, visits in 30 days, last activity and a health label (new / active / quiet / inactive) with a next step ("help them print the QR code"). Aggregate numbers only; a partner never sees a shop's customers. |
| Marketing kit | Printable A4 flyer (English and Hindi) carrying the partner's own referral QR at `/kit/<code>/`, ready-to-send WhatsApp messages, a 30-second pitch, answers to common objections and the prices to quote. |
| TDS on payouts | Migration `0008` adds `paid_at` and `tds` to payouts. **Off by default.** Set `VENDOR_TDS_RATE` (percent) and `VENDOR_TDS_THRESHOLD_PAISE` with your accountant. When the yearly total crosses the threshold, TDS is withheld on the whole year's total (earlier payouts are caught up). "Mark paid" in the admin now records the date, the TDS and notifies the partner of the net amount. This is a bookkeeping aid, not tax advice. |
| Earnings statements | Per financial year (Apr-Mar): commissions, payouts, gross / TDS / net totals, and a CSV download for the partner's records and ITR / Form 26AS reconciliation. |
| Assisted onboarding | A shop a partner creates for an owner now starts with the same ready-made program as the owner wizard (it used to start empty). |

Partner leaderboards were deliberately not built: they would expose other partners' earnings and encourage spam.
The new partner code (`core/tests_vendor.py`, about 20 tests) has not been run either; see the verification note above.

## Verification status (please read)
The sandbox this was built in had no network, so **Django could not be installed and the Python test suite was not run**.
What *was* done: every Python file compiles, a static undefined-name check passes, the frontend was executed in Node
against a fake DOM with mocked API data across all 43 screen/role/language combinations (no errors, no
"undefined"/"NaN"), and API field names were cross-checked against the backend. Migration `0007` is written by hand;
run `makemigrations --check` first and, if it reports differences, regenerate it (`makemigrations core`) - the model
code is the source of truth. `core/tests_growth.py` (about 40 tests) has not been executed yet, so expect to fix small
test-side details on first run. Not verified: real browser rendering, Razorpay checkout in the new UI, image upload of
logos.

## Needs a human
* **Hindi review.** All new Hindi strings were machine-written; have a native speaker proof them.
* **Secrets.** The zip you sent contained `.env`, `.superuser-credentials.txt` and `db.sqlite3` (not in git history, which
  is good). They are excluded from the upgraded package. Treat them as exposed: rotate `SECRET_KEY`, Razorpay keys and
  the superuser password.
* Fonts load from Google Fonts (Bricolage Grotesque, Hind); self-host them if you need offline/privacy guarantees.

## Suggested next steps
Plan tiers with limits (e.g. Free / Starter / Pro) and feature flags; WhatsApp Business API for offers and booking
reminders (extend `send_reminders`); multi-location with per-branch staff roles (cashier vs manager); gift cards and
prepaid packages; customer birthday rewards (needs DOB consent under DPDP); owner mobile app wrapper (the PWA
manifest is ready); automated win-back campaigns on a schedule; webhook/Zapier export.

## v2.1.0 (this release)

**Reward click (customers):** one big claim button with ripple + haptics; bottom-sheet with quantity stepper and quick amounts; live cooldown
countdown and daily allowance (`cooldown_seconds`, `entries_left_today` on `me/shop/<code>/`); the app now watches a pending purchase and
celebrates the moment the shop approves it; "reward unlocked" confetti; full-screen reward pass with a QR (`/api/rewards/qr/<code>.png`).
**Reward click (staff):** redeem is now two steps, `POST /api/rewards/lookup/` previews customer + reward, then Redeem. Scanning the customer's QR
with a phone camera opens `/app/?redeem=CODE` and pre-fills the check.
**Involvement:** "almost there" push at one step from a reward, Saturday streak nudge (`send_reminders`, `--force-streaks` to test), next-reward
focus card with progress ring, streak flames, welcome-gift celebration on joining.
**Subscription fixes:** admin Reject only touches *pending UPI* and notifies the owner; Approve/Refund notify; Refund now removes the paid period
(`billing.revoke_period`) and reverses vendor commission; payment-success notification; `payment.failed` webhook notifies; duplicate
`subscription.charged` deliveries are now serialised; bad webhook JSON returns 400; Razorpay outages return a friendly 400 instead of a 500;
AutoPay owners get "renews automatically" instead of "renew now"; billing API adds payment history, rejection state, yearly saving, next charge.
Fixed an admin bug where `reverse` was shadowed by `vendors.reverse`, which broke the screenshot link in the Payments list.
**UI:** new design layer at the end of `app.css`, skeleton loaders, page entrance, offline strip, redesigned billing screen, owner "Get set up"
checklist, landing page with features / pricing / FAQ (`landing.js`, `GET /api/plans/`).
**Hindi:** `i18n-hi2.js` (machine-written, needs native review).
Tests: 110 pass (`core/tests_upgrade.py` adds 13).

## v2.1.1
**Owners can now edit rewards and see who is involved.** Rewards screen: `Edit` (name, target, repeat limit, and the reward itself: name, type, value,
validity, terms), `Add reward` to a running program, `Rename and dates`, and `Who` which opens the reward-activity data (the API existed but no screen
used it): collecting / ready / redeemed counts, filters (close to reward, ready, redeemed), Call, WhatsApp, and `Send reminder`.
API: `PATCH /api/rewards/<id>/`, `POST /api/programs/<id>/tasks/`, `POST /api/b/<code>/customers/<pid>/nudge/` (consent only, 1 per customer per
3 days, 20 a day), task edits are now validated.
**Bring customers back:** the Offers screen leads with a Win-back gift (`GET/POST /api/b/<code>/winback/`): real reward codes for a chosen group
(slipping / lapsed / new / regular), short validity (3 to 60 days), shares the daily campaign limits and the consent rule.
**Notification taps:** `Notification.link` (migration 0010). Tapping opens the right screen (reward unlocked, purchase pending for owners, billing,
bookings...) and marks just that item read; "Mark all read" added. Links are restricted to in-app paths on both server and client.
Tests: 119 pass.

## v2.2.0 — new look for every role
UPI-app design language: violet brand (#5e35b1), Inter + Noto Sans Devanagari, one type scale (24/20/16.5/15/12.5), solid 48px pill buttons,
22px cards with soft shadows, violet header, white bottom tabs with an active bar, icon-tile quick actions (customer home, owner Today),
and a header "Aa" control that scales text (normal / large / extra large). All colours are tokens at the top of the v2.2 block in `app.css`.
New default shop colour is violet; migration 0011 moves only shops still on the old default teal (reversible). Razorpay popup and PWA theme follow.
Not copied: any third-party logo, name, exact brand colour or proprietary font. OFFLet name and mark are kept.

## v2.2.1 — print, invoice and public pages in the new style
Shop print card (A6/A5/A4/table tent): violet brand mark, accent band, pill "Scan" button, Inter type; each business category keeps its own accent
colour (the generic category now uses violet). QR codes stay black on white so they always scan. Invoice: violet header, From / Billed to columns,
PAID stamp, big total, print-ready A4. Partner flyer, legal/policy pages, and the app icon follow the same palette.

## v2.3.0
**AutoPay for subscription plans:** works with only RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET. OFFLet creates the Razorpay monthly + yearly plans itself on first
use (`GatewayPlan`, migration 0012) and re-creates one if the price changes; `python manage.py sync_razorpay_plans` pre-creates them. Plan IDs in the
environment still win. Webhooks map auto-created plans too. Billing screen leads with a "Never miss a renewal" AutoPay card (no charge before the
trial/period ends). In the Razorpay dashboard, enable webhook events: subscription.charged, subscription.halted, subscription.cancelled, payment.captured, payment.failed.
**Partner sets the owner's password:** `POST /api/vendor/assist/` now requires `password` (6+ chars, not the mobile number) and `owner_name`; it is never
echoed back. The partner form has Show / Generate and a share message with the login. The old random temp password is gone.
**Quick add a reward:** `POST /api/b/<code>/rewards/quick/`. Three steps on one screen (buy-and-get / spend-and-get / visit-and-get, a number, what they get),
live preview, category-based gift ideas, adds into the running program, blocks exact duplicates.


## v2.4: refer and earn for businesses
Shop owners can refer other businesses and earn commission in a wallet (see README, "Refer and earn for businesses").
Files: `core/vendors.py` (owners may apply, `wallet` endpoint, stronger self-referral guard, earning notification),
`core/urls.py` (`vendor/wallet/`), `core/static/app/partner.js` (owner **Refer & Earn** screen), `core.js`/`owner.js` (menu + tile),
`i18n-hi3.js` (Hindi), `core/tests_owner_referral.py`. No migration. Optional env: `OWNER_REFERRAL_AUTO_APPROVE=1`.

### v2.4: single QR card
My shop now has one QR card (download / share only) instead of the A6/A5/A4/table-tent links. Mobile layout fixes in `app.css`
(`.stack` columns can shrink, long buttons wrap) remove sideways scrolling on phones from 320 px wide. Files: `owner2.js` (`drawQrCard`, `qrCard`),
`owner.js` (tile label), `app.css`, `i18n-hi3.js`.
