from django.contrib import admin
from django.http import FileResponse
from django.urls import path, reverse
from django.utils.html import format_html
import mimetypes
from . import models
from .billing import mark_paid, revoke_period
from .notify import push
for m in (models.User, models.Business, models.Program, models.Task, models.Reward,
          models.CustomerProfile, models.PurchaseEntry, models.RewardGrant, models.AuditLog):
    admin.site.register(m)


@admin.register(models.Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "owner", "plan", "amount", "method", "status", "utr", "proof_link", "created_at")
    list_filter = ("status", "method")
    actions = ["approve", "reject", "refund"]
    exclude = ("proof",)
    readonly_fields = ("proof_preview",)

    def get_urls(self):
        return [path("<int:payment_id>/proof/", self.admin_site.admin_view(self.payment_proof),
                     name="core_payment_proof")] + super().get_urls()

    def payment_proof(self, request, payment_id):
        payment = self.get_object(request, str(payment_id))
        if not payment or payment.method != "upi" or not payment.proof:
            from django.http import Http404
            raise Http404
        response = FileResponse(payment.proof.open("rb"),
            content_type=mimetypes.guess_type(payment.proof.name)[0] or "application/octet-stream")
        response["Content-Disposition"] = "inline"
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response

    @admin.display(description="Payment screenshot")
    def proof_link(self, payment):
        if not payment.proof:
            return "—"
        url = reverse("admin:core_payment_proof", args=[payment.pk])
        return format_html('<a href="{}" target="_blank" rel="noopener">View screenshot</a>', url)

    @admin.display(description="Payment screenshot")
    def proof_preview(self, payment):
        return self.proof_link(payment)

    @admin.action(description="Approve selected UPI payments (review screenshot and verify bank UTR first)")
    def approve(self, request, qs):
        n = 0
        for p in qs.filter(method="upi", status="pending"):
            mark_paid(p.pk)  # notifies the owner and creates the invoice
            n += 1
        if request is not None:
            self.message_user(request, f"{n} payment(s) approved and the owners notified.")

    @admin.action(description="Reject selected pending UPI payments (owner is told to resubmit)")
    def reject(self, request, qs):
        n = 0
        for p in qs.filter(method="upi", status="pending"):
            p.status = "rejected"
            p.save(update_fields=["status"])
            push(p.owner, f"We could not verify your UPI payment (ref {p.utr or '-'}). Please check the amount and reference "
                          "and submit it again from Billing, or contact support.", link="/app/#/billing")
            n += 1
        if request is not None:
            self.message_user(request, f"{n} pending UPI payment(s) rejected and the owners notified. Other statuses were left alone.")

    @admin.action(description="Mark refunded (removes the paid period, reverses vendor commission, notifies the owner)")
    def refund(self, request, qs):
        n = 0
        for p in qs.filter(status="paid"):
            revoke_period(p.pk)
            n += 1
        if request is not None:
            self.message_user(request, f"{n} payment(s) refunded. Remember to send the money back through Razorpay or UPI.")


@admin.register(models.Donation)
class DonationAdmin(admin.ModelAdmin):
    list_display = ("id", "donor", "amount", "status", "order_id", "payment_id", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("donor__username", "order_id", "payment_id")
    readonly_fields = ("donor", "amount", "status", "order_id", "payment_id", "created_at")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(models.Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ("code", "user", "status", "rate", "applied_at", "upi_id")
    list_filter = ("status",)
    search_fields = ("code", "user__username", "user__first_name")
    readonly_fields = ("code", "applied_at")
    actions = ["approve", "suspend"]

    @admin.action(description="Approve selected applications (activates referral links and earning)")
    def approve(self, request, qs):
        vendors = list(qs.filter(status__in=("pending", "suspended")).select_related("user"))
        qs.filter(pk__in=[vendor.pk for vendor in vendors]).update(status="approved")
        for vendor in vendors:
            push(vendor.user, "Your vendor profile is approved. Your referral link is now active in your dashboard.")

    @admin.action(description="Suspend selected vendors (pause referral attribution and access)")
    def suspend(self, request, qs): qs.update(status="suspended")


@admin.register(models.Commission)
class CommissionAdmin(admin.ModelAdmin):
    list_display = ("id", "vendor", "amount", "rate", "status", "payable_on")
    list_filter = ("status", "vendor")


@admin.register(models.Payout)
class PayoutAdmin(admin.ModelAdmin):
    list_display = ("id", "vendor", "amount", "tds", "status", "reference", "paid_at", "created_at")
    list_filter = ("status",)
    readonly_fields = ("tds", "paid_at")
    actions = ["paid"]

    @admin.action(description="Mark paid (withholds TDS automatically if VENDOR_TDS_RATE is set; transfer the net amount to the vendor)")
    def paid(self, request, qs):
        from .vendors import mark_payout_paid
        for po in qs.filter(status="pending"):
            mark_payout_paid(po)


@admin.register(models.Subscription)
class SubscriptionAdmin(admin.ModelAdmin):  # use for win-back calls: sort by paid_until
    list_display = ("owner", "trial_ends", "paid_until", "state_now")
    search_fields = ("owner__username", "owner__first_name")
    ordering = ("-paid_until",)

    @admin.display(description="state")
    def state_now(self, o):
        return o.state
