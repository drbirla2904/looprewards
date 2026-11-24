from django.db import migrations, models
import core.models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0013_reward_min_order_amount_reward_product_restrictions_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="reward",
            name="item_name",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="reward",
            name="original_price",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
        migrations.AddField(
            model_name="reward",
            name="offer_price",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
        migrations.AddField(
            model_name="reward",
            name="image",
            field=models.ImageField(blank=True, upload_to=core.models._offer_image_path),
        ),
    ]
