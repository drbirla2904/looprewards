import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0016_verified_recovery_email"),
    ]

    operations = [
        migrations.AddField(
            model_name="business",
            name="instagram_url",
            field=models.URLField(blank=True, max_length=300),
        ),
        migrations.AddField(
            model_name="business",
            name="facebook_url",
            field=models.URLField(blank=True, max_length=300),
        ),
        migrations.AddField(
            model_name="business",
            name="youtube_url",
            field=models.URLField(blank=True, max_length=300),
        ),
        migrations.AddField(
            model_name="business",
            name="tiktok_url",
            field=models.URLField(blank=True, max_length=300),
        ),
        migrations.AddField(
            model_name="business",
            name="x_url",
            field=models.URLField(blank=True, max_length=300),
        ),
        migrations.AlterField(
            model_name="reward",
            name="trigger",
            field=models.CharField(
                choices=[
                    ("task", "task"),
                    ("welcome", "welcome"),
                    ("referral", "referral"),
                    ("retired", "retired"),
                    ("winback", "winback"),
                    ("spin", "spin"),
                    ("social", "social"),
                ],
                default="task",
                max_length=10,
            ),
        ),
        migrations.CreateModel(
            name="SocialFollowClaim",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "status",
                    models.CharField(
                        choices=[("pending", "pending"), ("approved", "approved"), ("rejected", "rejected")],
                        default="pending",
                        max_length=10,
                    ),
                ),
                ("requested_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "profile",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="social_follow_claim",
                        to="core.customerprofile",
                    ),
                ),
                (
                    "reviewed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="reviewed_social_follow_claims",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "reward_grant",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="social_follow_claim",
                        to="core.rewardgrant",
                    ),
                ),
            ],
        ),
    ]
