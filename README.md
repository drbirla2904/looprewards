> **v2:** see [UPGRADE.md](UPGRADE.md) for the new growth layer, frontend and upgrade steps.

# OFFLet

## Deploy
OFFLet runs directly on Ubuntu without Docker. See **[GUIDE.md](GUIDE.md)** for step-by-step Contabo setup for `offlet.in`, Nginx/HTTPS, backups, upgrades, and rollback. Once installed, upgrade with `bash ./deploy/deploy.sh`.

## Local development
Create and activate a virtual environment, install `requirements.txt`, then use `make verify-local` to run Django checks, migration checks, and tests. For individual steps, see `make check-local`, `make migrations-check`, and `make test-local`. Start the development server with `make run-local`.

The production Gunicorn configuration distributes traffic across configurable worker processes and threads. See the [deployment guide](GUIDE.md#worker-sizing-and-load-distribution) before increasing worker counts or adding app servers.


## QR card (My shop)
My shop shows **one** QR card: shop logo/initial, name, real customer-rating stars when reviews exist, tagline, customer-facing stamp rewards, Spin & Win, offers and referral benefits, a scannable QR code, and compact shop details. It never invents a rating. The card uses the shop's brand colour and Hindi text when the shop language is Hindi. It has only two actions: **Download** (PNG) and **Share** (WhatsApp/any app via the phone's share sheet; falls back to sharing the shop link). It is drawn in the browser, so it fits any phone and needs no extra server work. The older A6/A5/A4/table-tent print pages still exist at `/print/<shop_code>/?size=...` only for the classic fallback UI (`/app/classic/`); they are no longer linked from the app.

## Smart Spin & Win
Owners can create wheels from **Spin & Win** with 2–12 free-item or percentage-off rewards. Add multiple rewards and their chances are divided equally automatically; optionally set a minimum purchase. Campaigns run every day. The most recently updated matching audience-specific wheel takes precedence over an all-customer wheel.

The Spin & Win QR and share link stay the same as campaigns change; customers see the campaign selected for their audience. Each wheel configures a 1–10 daily spin limit per customer and shop. Owners can delete an individual wheel; existing spin history remains, but the deleted campaign and its analytics are removed. Winning coupons are added to the existing customer rewards wallet. Customers can request redemption in the app; shop staff approve or decline from the dashboard, and the customer can still reveal the reward code as a fallback. Minimum-purchase conditions are shown to staff for verification; OFFLet does not automatically validate a separate point-of-sale order.

## Shop offers
Owners can add multiple items to percentage-off, fixed-price and buy-one-get-one offers. Each offer can be turned off or permanently deleted individually; deleting an offer also removes its uploaded item images.

## Launch readiness
Before production, follow **[GUIDE.md](GUIDE.md)**, complete the pilot checklist, and test payments,
notifications, backups, and restore on a staging domain. External provider integrations require
your own credentials and end-to-end verification; passing the local tests does not verify them.

## Billing
- 14-day trial (no card), then ₹99/mo or ₹999/yr (edit `PLANS` in settings). 30-day grace: profile/QR paused, print kit + progress kept.
- Online: Razorpay Checkout (UPI/cards/netbanking); payment is verified by signature and activated immediately. Add webhook `https://<domain>/api/billing/webhook/`, events `payment.captured` + `order.paid`.
- If `RAZORPAY_PLAN_MONTHLY` or `RAZORPAY_PLAN_YEARLY` is configured, point it to a Razorpay plan priced at the new amount. Existing AutoPay subscriptions retain their Razorpay terms until canceled and set up again.
- Manual UPI: set `PLATFORM_UPI_ID`; owner pays the displayed amount and submits the UTR plus a JPEG/PNG/WebP screenshot (max 5 MB). An admin checks the bank statement and screenshot in /admin -> Payments, then approves the submission. Screenshots are stored privately and included in protected backups.

## Invoices and reminders
- Each paid payment gets invoice no. `LR/<yy>/<id>` and a printable GST invoice (price treated as GST-inclusive; set SELLER_* in .env). Have your CA confirm the format (CGST/SGST vs IGST split by state is not done).
- `python manage.py send_reminders` (run daily by the `offlet-daily.timer` systemd timer): trial ends in 2 days, renewal in 7 days, paused notice. Point NOTIFY_WEBHOOK_URL at your SMS/WhatsApp bridge, else it only logs.
- Database migrations are committed in `core/migrations/`; create and commit a reviewed migration whenever a model change requires one.

## Vendors / agents
- **Account and approval:** create an account in the app and choose **agent / reseller**. Sign in, submit the partner application using your PAN and payout UPI ID, then wait for an administrator to review it under `/admin` -> **Vendors**. The dashboard shows **Application received — review in progress** while pending. Approval sends an in-app notification, activates referrals, and shows the partner dashboard; refreshing the page checks the latest status.
- **No application / no earnings:** a vendor login without an application is not yet a partner account. Submit the application first. Pending or suspended vendors cannot refer owners or earn. New signups alone do not create commissions: an attributed owner must successfully pay for a subscription.
- The approved vendor dashboard shows the referral link, referred owners/shops, commission activity, on-hold versus payout-processing totals, payout minimum, monthly schedule, and transfer history. Only new shop-owner registrations made while the vendor is approved are attributed; attribution is permanent after signup.
- Vendors can also create an owner and shop from the dashboard. The returned one-time password is set on that account; share it securely and have the owner change it after signing in.
- Commission = rate × subscription price excluding GST, created only on a real paid payment (never trial), 30-day hold, single level, every renewal (set `COMMISSION_FIRST_YEAR_ONLY=1` for year one only).
- Refund: /admin -> Payments -> "Mark refunded" reverses a held commission.
- Monthly (1st) `run_payouts` bundles ripe commissions ≥ ₹500 into Payouts; you transfer via UPI/bank (deduct TDS as required) and mark "paid" in /admin.
- Blocked: self-referral (same UPI), duplicate shop UPI IDs. Agents see shop names/status only, never customer data or passwords. Confirm commission, TDS and GST on commission with your CA.

## Refer and earn for businesses (owner wallet)
- Any **shop owner** can also refer other businesses: **Refer & Earn** in the owner menu -> enter PAN + payout UPI ID -> an admin approves it under `/admin` -> **Vendors** (or set `OWNER_REFERRAL_AUTO_APPROVE=1` in `.env` to approve owners instantly). Owners reuse the vendor engine, so rates, tiers, 30-day hold, monthly payouts, TDS, statements and the marketing kit all work the same way.
- The owner gets a referral link/QR (`/app/?ref=<code>`). When a business that signed up through it pays for a plan, the commission lands in the owner's **wallet** (`GET /api/vendor/wallet/`): *in hold period* -> *ready for payout* -> *payout processing* -> *paid*, plus a ledger of credits and payouts. The owner is notified on every credit.
- Money is paid out by UPI on the monthly `run_payouts` cycle (minimum `MIN_PAYOUT_PAISE`); there is no on-demand withdrawal and wallet balance is not spendable inside the app.
- Guards: no earnings on your own accounts (the payer's shop UPI IDs must not match the referrer's payout UPI or any of the referrer's own shop UPI IDs), pending/suspended partners earn nothing, attribution is only set at signup, refunds reverse a held commission. No database migration is needed.

## Staff accounts and counter code
- Owner adds staff per shop (dashboard -> Add staff). Staff can approve/reject and redeem only; they cannot edit the shop, rewards or billing.
- **Counter code screen** (`/app/?screen=<shop_code>`, open on a counter tablet/phone): 6-digit code + QR, changes every 60s. After paying, the customer scans the QR (or types the code); the purchase is then auto-approved, with no owner tap. The cooldown and daily cap still apply, each customer can use a code once, and a code works at most 20 times.
- Weak spot: a customer could WhatsApp the code to a friend who is not at the shop. Add the GPS proximity check (PRD 7.5) next if you see this.

## Reports and notifications
- Owner dashboard (per shop): customers, repeat-customer rate, top customers, rewards issued vs redeemed, peak hours, approved today, and a customers CSV (signed link valid 10 min). Customer name and mobile are visible only to the shop they joined.
- In-app notifications: customer gets approved/rejected, reward unlocked, reward expiring (3 days, from the daily `send_reminders`); owner and staff get "new purchase pending". Set `NOTIFY_SMS=1` + `NOTIFY_WEBHOOK_URL` to also send reward unlocked/expiring by SMS/WhatsApp. Broadcast offers are delivered in-app only to customers who opted in to marketing.
- **Account center:** every signed-in role can update their display name, change their password, and verify an optional recovery email from Account. Customers can also manage their profile photo; mobile numbers remain read-only.
- Customers can hide past purchase history from their account or hide a shop from their profile; shop records, membership, progress, and rewards are preserved. Hidden shops can be restored from Account, and reopening a live shop QR restores it automatically.

## Hindi
- The app has an English/हिन्दी button (top right), remembered per phone; it defaults to the shop's language (set when creating the shop) or the phone language. Owner/staff/customer/agent screens, common error messages and notifications are translated; the print card is Hindi when the shop language is Hindi (or `?lang=hi`).
- To add a string or language, edit the `EX` (whole-text) and `PT` (phrase) tables at the end of `core/web/app.html`. Please have a native Hindi speaker proofread the wording. Invoices stay in English (GST).

## Safety, renewal and privacy features
- **GPS check (soft):** the customer's phone sends its location with each entry; shops set their location once (Settings -> "Set shop location"). Beyond `max_distance_m` (default 300 m) the entry is flagged "far from shop", never auto-approved (even with a counter code), and the owner sees a warning.
- **Bill photo:** optional per shop (Settings -> Require bill photo). Files get random names and are served from `/media/`; Nginx serves the configured media directory as described in GUIDE.md.
- **Undo + block:** "Recent approvals" has Undo (reverses progress and revokes an unredeemed reward); pending entries have "Block customer".
- **Pause/resume** a program from the dashboard; `PATCH /api/tasks/<id>/` edits a task. Customers already in progress keep the target they started with (snapshot), new cycles use the new target.
- **Auto-renew:** Razorpay Subscriptions (UPI AutoPay/cards). Create two plans in Razorpay, set `RAZORPAY_PLAN_MONTHLY/YEARLY`, and add `subscription.charged` to the webhook. The first charge is after the trial / current period; each charge creates a payment, invoice and commission automatically. Owners can cancel in the dashboard.
- **Offers (broadcast):** only to customers who ticked "Send me offers from this shop"; one per shop per day; delivered in-app.
- **Forgot password:** sign in with mobile number + password. Password-reset OTPs use `NOTIFY_WEBHOOK_URL` when an SMS bridge is configured; otherwise they go to the account's verified recovery email through SMTP. Configure `EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` and `DEFAULT_FROM_EMAIL` in `.env` (a provider's free SMTP tier may be used). Codes expire after 10 minutes, allow 5 attempts, and unknown accounts receive the same response.
- **Delete my account (DPDP):** customers are erased; owners/agents are anonymised and their shops closed (invoices and commissions must be kept for accounts).
- **Platform stats:** `GET /api/admin/stats/` with a staff user's token (create one with `createsuperuser`, then log in via `/api/auth/login/`).
