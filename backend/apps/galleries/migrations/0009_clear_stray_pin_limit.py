# backend/apps/galleries/migrations/0009_clear_stray_pin_limit.py
"""
Data migration (Task 1R.6-C): clears a stray ``design_settings.privacy.pin_limit``
of exactly 1.

WHY: "Limit PIN usage" shipped only on the 1R.6 work branch (it is not on main
and has never been released), so every stored value comes from development/QA.
The old Privacy-tab field autosaved while the photographer was still typing,
so "10" or "5" could be stored as "1" -- and a limit of 1 silently blocks the
whole gallery once the PIN has been entered a single time. 1R.6-A removed that
field, leaving no way to clear the value. 1R.6-C commits number fields on
blur/Enter only (no more half-typed values) and shows the limit again, but an
already-stored 1 must not keep blocking downloads unseen.

Only a limit of exactly 1 is cleared; any other stored limit is a deliberate
number and is left untouched. ``pin_use_count`` is kept. Rows are updated with
``.update()`` so ``updated_at`` is not touched. Not reversible by design: the
cleared value was never a meaningful setting.
"""
from django.db import migrations


def clear_stray_pin_limit(apps, schema_editor):
    Gallery = apps.get_model('galleries', 'Gallery')
    for gallery in Gallery.objects.only('id', 'design_settings').iterator():
        design = gallery.design_settings if isinstance(gallery.design_settings, dict) else {}
        privacy = design.get('privacy')
        if not isinstance(privacy, dict):
            continue
        limit = privacy.get('pin_limit')
        if limit == 1 and not isinstance(limit, bool):
            fixed = dict(design, privacy=dict(privacy, pin_limit=None))
            Gallery.objects.filter(pk=gallery.pk).update(design_settings=fixed)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('galleries', '0008_backfill_trashed_at'),
    ]

    operations = [
        migrations.RunPython(clear_stray_pin_limit, noop_reverse),
    ]
