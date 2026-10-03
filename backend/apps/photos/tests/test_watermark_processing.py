# backend/apps/photos/tests/test_watermark_processing.py
"""
Watermark processing contract, on real assets.

THE DECISION UNDER TEST (also in apps/core/watermark.py and the task report):
  - the preserved ORIGINAL is never watermarked or rewritten;
  - the DOWNLOAD MASTER ("High Resolution") is never watermarked — it is the
    clean, authorized deliverable, built from the original;
  - display / medium / thumbnail (client-visible) ARE watermarked when the
    gallery has it enabled AND the photographer is entitled;
  - a "Web Size" download is the display derivative, so it carries the mark.
"""
import hashlib
import io
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase
from PIL import Image, ImageChops

from apps.core import watermark as wm
from apps.core.utils import process_image_pipeline, regenerate_display_derivatives
from apps.galleries.models import Gallery
from apps.photos import tasks
from apps.photos.models import MediaAsset
from apps.subscriptions.testing import grant_plan

User = get_user_model()


def _jpeg_bytes(size, color=(35, 85, 140)):
    img = Image.new('RGB', size, color)
    out = io.BytesIO()
    img.save(out, format='JPEG', quality=92)
    return out.getvalue()


def _png_bytes(size, color):
    out = io.BytesIO()
    Image.new('RGBA', size, color).save(out, format='PNG')
    return out.getvalue()


def _open(field):
    field.open('rb')
    try:
        img = Image.open(field)
        img.load()
        return img.convert('RGB')
    finally:
        field.close()


def _digest(field):
    field.open('rb')
    try:
        return hashlib.sha256(field.read()).hexdigest()
    finally:
        field.close()


def _bbox(a, b, threshold=0):
    """
    Bounding box of pixels that differ by more than `threshold`. WebP is lossy,
    so re-encoding a block that contains a mark nudges neighbouring pixels by
    a level or two; a small threshold isolates the visible mark itself.
    """
    diff = ImageChops.difference(a, b).convert('L')
    if threshold:
        diff = diff.point(lambda v: 255 if v > threshold else 0)
    return diff.getbbox()


class WatermarkProcessingBase(TestCase):
    username = 'wmproc'

    def setUp(self):
        self.photographer = User.objects.create_user(
            email=f'{self.username}@kyapture.com', password='SecurePassword123!',
            username=self.username, display_name='Aster Studio',
        )
        grant_plan(self.photographer)
        self.gallery = Gallery.objects.create(
            photographer=self.photographer, title='WM', slug='wm-gallery',
            is_published=True, is_active=True,
        )

    def enable(self, **config):
        self.gallery.watermark_enabled = True
        block = {**wm.DEFAULTS, 'text': 'ASTER', **config}
        self.gallery.design_settings = {'watermark': block}
        self.gallery.save(update_fields=['watermark_enabled', 'design_settings'])

    def disable(self):
        self.gallery.watermark_enabled = False
        self.gallery.save(update_fields=['watermark_enabled'])

    def make_asset(self, size=(1600, 1000), name='shot.jpg'):
        asset = MediaAsset(
            gallery=self.gallery, media_type=MediaAsset.MediaType.IMAGE, original_name=name,
            file_size=1024, processing_status=MediaAsset.ProcessingStatus.PENDING,
        )
        asset.original_file.save(name, ContentFile(_jpeg_bytes(size)), save=False)
        asset.save()
        return asset

    def process(self, asset):
        tasks.process_photo_asset(asset.id)
        asset.refresh_from_db()
        self.assertEqual(asset.processing_status, MediaAsset.ProcessingStatus.READY)
        return asset

    def clean_baseline(self, asset):
        """What display/medium/thumb/download look like with NO watermark."""
        asset.original_file.open('rb')
        try:
            display, medium, thumb, download, _ = process_image_pipeline(asset.original_file)
        finally:
            asset.original_file.close()
        return display, medium, thumb, download


class OriginalAndDownloadMasterAreNeverWatermarked(WatermarkProcessingBase):
    username = 'wmorig'

    def test_original_bytes_are_untouched_by_processing_with_a_watermark(self):
        self.enable()
        asset = self.make_asset()
        before = _digest(asset.original_file)
        name_before = asset.original_file.name
        asset = self.process(asset)
        self.assertEqual(asset.original_file.name, name_before)
        self.assertEqual(_digest(asset.original_file), before)

    def test_download_master_is_identical_to_the_unwatermarked_master(self):
        self.enable(opacity=100, size=40)
        asset = self.process(self.make_asset())
        _, _, _, clean_master = self.clean_baseline(asset)
        self.assertEqual(_open(asset.download_file).tobytes(),
                         Image.open(io.BytesIO(clean_master.read())).convert('RGB').tobytes())

    def test_watermark_applies_to_display_medium_and_thumbnail(self):
        self.enable(opacity=100, size=30)
        asset = self.process(self.make_asset())
        display, medium, thumb, _ = self.clean_baseline(asset)
        for stored, clean in ((asset.display_file, display), (asset.medium_file, medium),
                              (asset.thumbnail_file, thumb)):
            clean_img = Image.open(io.BytesIO(clean.read())).convert('RGB')
            marked = _open(stored)
            self.assertEqual(marked.size, clean_img.size)
            box = _bbox(clean_img, marked, threshold=20)
            self.assertIsNotNone(box, f'{stored.name} should carry the watermark')
            self.assertGreater(box[0], marked.width * 0.5)          # default bottom-right
            self.assertGreater(box[1], marked.height * 0.6)

    def test_signature_is_recorded_and_matches_the_applied_spec(self):
        self.enable()
        asset = self.process(self.make_asset())
        self.assertEqual(asset.watermark_signature, wm.current_signature(self.gallery))
        self.assertTrue(asset.watermark_signature)


class WatermarkRulesTests(WatermarkProcessingBase):
    username = 'wmrules'

    def test_disabled_gallery_gets_no_watermark(self):
        asset = self.process(self.make_asset())
        display, *_ = self.clean_baseline(asset)
        self.assertIsNone(_bbox(Image.open(io.BytesIO(display.read())).convert('RGB'), _open(asset.display_file)))
        self.assertEqual(asset.watermark_signature, '')

    def test_free_photographer_with_a_stale_enabled_flag_is_not_watermarked(self):
        # Entitlement is re-checked at processing time: a lapsed plan
        # cannot keep watermarking new derivatives through old settings.
        self.enable()
        self.photographer.subscription.delete()
        asset = self.process(self.make_asset())
        display, *_ = self.clean_baseline(asset)
        self.assertIsNone(_bbox(Image.open(io.BytesIO(display.read())).convert('RGB'), _open(asset.display_file)))
        self.assertEqual(asset.watermark_signature, '')

    def test_plan_without_the_feature_flag_is_not_watermarked(self):
        grant_plan(self.photographer, name='Basic', includes_branding_watermark=False)
        self.enable()
        self.assertIsNone(wm.build_watermark_spec(self.gallery))

    def test_expired_subscription_is_not_entitled(self):
        grant_plan(self.photographer, days=-1)
        self.enable()
        self.assertIsNone(wm.build_watermark_spec(self.gallery))

    def test_blank_text_defaults_to_a_copyright_line_with_the_photographer_name(self):
        self.gallery.watermark_enabled = True
        self.gallery.save(update_fields=['watermark_enabled'])
        spec = wm.build_watermark_spec(self.gallery)
        self.assertEqual(spec.text, '© Aster Studio')

    def test_portrait_and_landscape_assets_both_process_with_an_inset_mark(self):
        self.enable(opacity=100)
        for size in ((900, 1400), (1400, 900)):
            asset = self.process(self.make_asset(size=size, name=f'{size[0]}.jpg'))
            display, *_ = self.clean_baseline(asset)
            marked = _open(asset.display_file)
            box = _bbox(Image.open(io.BytesIO(display.read())).convert('RGB'), marked)
            self.assertIsNotNone(box, size)
            self.assertLessEqual(box[2], marked.width)
            self.assertLessEqual(box[3], marked.height)

    def test_small_source_image_processes_without_error(self):
        self.enable()
        asset = self.process(self.make_asset(size=(120, 80), name='tiny.jpg'))
        self.assertTrue(asset.display_file)

    def test_watermark_failure_still_produces_clean_derivatives_and_logs(self):
        self.enable()
        with mock.patch.object(wm, '_scaled_mark', side_effect=RuntimeError('font exploded')):
            with self.assertLogs('apps.core.watermark', level='ERROR'):
                asset = self.process(self.make_asset())
        display, *_ = self.clean_baseline(asset)
        self.assertIsNone(_bbox(Image.open(io.BytesIO(display.read())).convert('RGB'), _open(asset.display_file)))


class LogoWatermarkProcessingTests(WatermarkProcessingBase):
    username = 'wmlogo'

    def give_logo(self, color=(255, 0, 0, 255)):
        self.photographer.logo.save('logo.png', ContentFile(_png_bytes((300, 150), color)), save=True)

    def test_logo_watermark_is_composited_onto_derivatives(self):
        self.give_logo()
        self.enable(type='logo', opacity=100, size=25, position='top-left', margin=0)
        asset = self.process(self.make_asset())
        marked = _open(asset.display_file)
        self.assertEqual(marked.getpixel((6, 6))[0] > 200 and marked.getpixel((6, 6))[1] < 60, True)
        # download master stays clean
        self.assertNotEqual(_open(asset.download_file).getpixel((6, 6)), marked.getpixel((6, 6)))

    def test_logo_type_without_a_logo_falls_back_to_unwatermarked_and_warns(self):
        self.enable(type='logo')
        with self.assertLogs('apps.core.watermark', level='WARNING'):
            self.assertIsNone(wm.build_watermark_spec(self.gallery))

    def test_replacing_the_logo_changes_the_signature(self):
        self.give_logo()
        self.enable(type='logo')
        first = wm.current_signature(self.gallery)
        self.give_logo(color=(0, 255, 0, 255))
        self.gallery.refresh_from_db()
        self.assertNotEqual(wm.current_signature(self.gallery), first)

    def test_unreadable_logo_file_degrades_gracefully(self):
        self.give_logo()
        self.enable(type='logo')
        with mock.patch.object(wm.Image, 'open', side_effect=OSError('corrupt')):
            with self.assertLogs('apps.core.watermark', level='ERROR'):
                self.assertIsNone(wm.build_watermark_spec(self.gallery))


class RegenerationTests(WatermarkProcessingBase):
    """What happens to ALREADY-PROCESSED assets when the settings change."""
    username = 'wmregen'

    def test_existing_ready_assets_are_unchanged_until_regeneration_runs(self):
        asset = self.process(self.make_asset())
        before = _digest(asset.display_file)
        self.enable()                                    # settings change alone does nothing to files
        asset.refresh_from_db()
        self.assertEqual(_digest(asset.display_file), before)
        self.assertEqual(asset.watermark_signature, '')

    def test_regeneration_applies_the_new_watermark_without_touching_original_or_master(self):
        asset = self.process(self.make_asset())
        original_digest, master_digest = _digest(asset.original_file), _digest(asset.download_file)
        names = (asset.original_file.name, asset.download_file.name, asset.display_file.name)
        before_display = _digest(asset.display_file)

        self.enable(opacity=100)
        tasks.regenerate_asset_watermark(asset.id)
        asset.refresh_from_db()

        self.assertNotEqual(_digest(asset.display_file), before_display)
        self.assertEqual(asset.watermark_signature, wm.current_signature(self.gallery))
        self.assertEqual(_digest(asset.original_file), original_digest)
        self.assertEqual(_digest(asset.download_file), master_digest)
        # same storage keys: regenerated in place, no orphaned duplicates
        self.assertEqual((asset.original_file.name, asset.download_file.name, asset.display_file.name), names)
        self.assertEqual(asset.processing_status, MediaAsset.ProcessingStatus.READY)

    def test_disabling_the_watermark_regenerates_clean_derivatives(self):
        self.enable(opacity=100)
        asset = self.process(self.make_asset())
        original_digest = _digest(asset.original_file)
        self.disable()
        tasks.regenerate_asset_watermark(asset.id)
        asset.refresh_from_db()
        display, *_ = self.clean_baseline(asset)
        self.assertIsNone(_bbox(Image.open(io.BytesIO(display.read())).convert('RGB'), _open(asset.display_file)))
        self.assertEqual(asset.watermark_signature, '')
        self.assertEqual(_digest(asset.original_file), original_digest)

    def test_changing_position_and_opacity_changes_the_regenerated_pixels(self):
        self.enable(position='bottom-right', opacity=100)
        asset = self.process(self.make_asset())
        first = _open(asset.display_file)
        self.enable(position='top-left', opacity=100)
        tasks.regenerate_asset_watermark(asset.id)
        asset.refresh_from_db()
        second = _open(asset.display_file)
        box = _bbox(first, second)
        self.assertIsNotNone(box)
        # the mark moved: the new top-left mark region differs from the old image
        self.assertLess(_bbox(self.clean_display(asset), second)[0], second.width * 0.3)

    def clean_display(self, asset):
        display, *_ = self.clean_baseline(asset)
        return Image.open(io.BytesIO(display.read())).convert('RGB')

    def test_regeneration_is_idempotent(self):
        self.enable()
        asset = self.process(self.make_asset())
        with mock.patch.object(tasks, 'regenerate_display_derivatives',
                               wraps=tasks.regenerate_display_derivatives) as regen:
            tasks.regenerate_asset_watermark(asset.id)       # already current -> no work
            tasks.regenerate_asset_watermark(asset.id)
        regen.assert_not_called()

    def test_second_run_after_a_change_does_the_work_exactly_once(self):
        asset = self.process(self.make_asset())
        self.enable()
        with mock.patch.object(tasks, 'regenerate_display_derivatives',
                               wraps=tasks.regenerate_display_derivatives) as regen:
            tasks.regenerate_asset_watermark(asset.id)
            tasks.regenerate_asset_watermark(asset.id)
        self.assertEqual(regen.call_count, 1)

    def test_failure_leaves_existing_derivatives_and_status_intact_and_is_logged(self):
        asset = self.process(self.make_asset())
        before = _digest(asset.display_file)
        self.enable()
        with mock.patch.object(tasks, 'regenerate_display_derivatives', side_effect=RuntimeError('disk full')):
            with self.assertLogs('apps.photos.tasks', level='ERROR') as logs:
                with self.assertRaises(RuntimeError):         # called directly: retry re-raises
                    tasks.regenerate_asset_watermark(asset.id)
        asset.refresh_from_db()
        self.assertEqual(_digest(asset.display_file), before)
        self.assertEqual(asset.watermark_signature, '')       # still marked stale -> will be retried
        self.assertEqual(asset.processing_status, MediaAsset.ProcessingStatus.READY)
        self.assertTrue(any('regeneration failed' in line for line in logs.output))

    def test_gallery_task_queues_only_stale_ready_images(self):
        stale = self.process(self.make_asset(name='stale.jpg'))
        self.enable()
        current = self.process(self.make_asset(name='current.jpg'))       # built with the new settings
        pending = self.make_asset(name='pending.jpg')                     # not READY
        video = MediaAsset.objects.create(
            gallery=self.gallery, media_type=MediaAsset.MediaType.VIDEO, original_name='v.mp4',
            file_size=1, processing_status=MediaAsset.ProcessingStatus.READY,
        )
        with mock.patch.object(tasks.regenerate_asset_watermark, 'apply_async') as queue:
            queued = tasks.regenerate_gallery_watermarks(self.gallery.id)
        self.assertEqual(queued, 1)
        queue.assert_called_once()
        self.assertEqual(queue.call_args.kwargs['args'], [str(stale.id)])
        for other in (current, pending, video):
            self.assertNotIn(str(other.id), str(queue.call_args))

    def test_gallery_task_for_a_missing_gallery_is_a_noop(self):
        self.assertEqual(tasks.regenerate_gallery_watermarks('01a10000-0000-7000-8000-000000000000'), 0)

    def test_regenerated_url_version_changes_so_caches_cannot_serve_the_old_image(self):
        asset = self.process(self.make_asset())
        v_before = wm.versioned_url('http://x/d.webp', asset)
        self.enable()
        tasks.regenerate_asset_watermark(asset.id)
        asset.refresh_from_db()
        self.assertNotEqual(wm.versioned_url('http://x/d.webp', asset), v_before)

    def test_asset_finishing_after_a_settings_change_is_reconciled(self):
        asset = self.make_asset()
        original_build = wm.build_watermark_spec
        calls = {'n': 0}

        def flip(gallery):
            # first call (processing) sees "disabled"; the reconcile check sees the new settings
            calls['n'] += 1
            if calls['n'] == 1:
                return None
            return original_build(gallery)

        self.enable()
        with mock.patch.object(tasks, 'build_watermark_spec', side_effect=flip), \
                mock.patch.object(tasks, 'current_signature', side_effect=lambda g: original_build(g).signature), \
                mock.patch.object(tasks.regenerate_asset_watermark, 'delay') as delay:
            tasks.process_photo_asset(asset.id)
        delay.assert_called_once_with(str(asset.id))


class LegacyPipelineApiTests(WatermarkProcessingBase):
    username = 'wmlegacy'

    def test_legacy_watermark_text_argument_still_works(self):
        asset = self.make_asset()
        asset.original_file.open('rb')
        try:
            display, *_ = process_image_pipeline(asset.original_file, watermark_text='© legacy')
            clean, *_ = process_image_pipeline(asset.original_file)
        finally:
            asset.original_file.close()
        self.assertIsNotNone(_bbox(Image.open(io.BytesIO(display.read())).convert('RGB'),
                                   Image.open(io.BytesIO(clean.read())).convert('RGB')))

    def test_regenerate_display_derivatives_returns_three_webp_tiers_and_never_the_master(self):
        asset = self.make_asset()
        files = regenerate_display_derivatives(asset.original_file, None)
        self.assertEqual(len(files), 3)
        self.assertTrue(all(f.name.endswith('.webp') for f in files))
