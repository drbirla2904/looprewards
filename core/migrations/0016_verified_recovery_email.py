from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0015_shop_offers"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="email_verified",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="otpcode",
            name="purpose",
            field=models.CharField(
                choices=[("password_reset", "Password reset"), ("email_verify", "Recovery email verification")],
                default="password_reset",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="otpcode",
            name="target_email",
            field=models.EmailField(blank=True, max_length=254),
        ),
    ]
