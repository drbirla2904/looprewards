import core.models
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0014_reward_catalog_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="ShopOffer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("offer_type", models.CharField(choices=[("percent_off", "Percentage off"), ("fixed_price", "Fixed price"), ("bogo", "Buy one get one")], max_length=15)),
                ("value", models.DecimalField(decimal_places=2, default=0, max_digits=5)),
                ("active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("business", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="offers", to="core.business")),
            ],
            options={
                "ordering": ("-created_at", "-id"),
            },
        ),
        migrations.CreateModel(
            name="ShopOfferItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("price", models.DecimalField(decimal_places=2, max_digits=10)),
                ("offer_price", models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ("image", models.ImageField(blank=True, upload_to=core.models._offer_image_path)),
                ("offer", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="items", to="core.shopoffer")),
            ],
            options={
                "ordering": ("id",),
            },
        ),
    ]
