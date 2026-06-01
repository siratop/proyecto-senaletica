from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [
        ('flota', '0005_unidad_modelo_unidad_placa'), 
    ]

    operations = [
        migrations.RemoveField(
            model_name='unidad',
            name='modelo',
        ),
        migrations.RemoveField(
            model_name='unidad',
            name='placa',
        ),
    ]