from django.db import migrations, models


def create_business_referral_settings(apps, schema_editor):
    settings_model = apps.get_model("core", "BusinessReferralSettings")
    settings_model.objects.get_or_create(pk=1, defaults={"enabled": True})


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0018_donation"),
    ]

    operations = [
        migrations.CreateModel(
            name="BusinessReferralSettings",
            fields=[
                ("id", models.PositiveSmallIntegerField(default=1, editable=False, primary_key=True, serialize=False)),
                ("enabled", models.BooleanField(
                    default=True,
                    help_text="Allow business owners to earn referral commissions. Owners also need an active yearly plan.",
                )),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.RunPython(create_business_referral_settings, migrations.RunPython.noop),
    ]
