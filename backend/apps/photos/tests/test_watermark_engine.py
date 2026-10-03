# backend/apps/photos/tests/test_watermark_engine.py
"""
Watermark rendering engine (apps/core/watermark.py) — pure image tests.

Covers: text and logo marks, opacity, position (all nine), size scaling across
image dimensions, margin, portrait/landscape/tiny images, a missing font, the
no-mutation guarantee, the fail-safe fallback (with a logged error), and
configuration validation.
"""
from unittest import mock

from django.test import SimpleTestCase
from PIL import Image, ImageChops, ImageStat

from apps.core import watermark as wm


def _photo(size, color=(40, 90, 150)):
    return Image.new('RGB', size, color)


def _spec(**overrides):
    config = {**wm.DEFAULTS, 'text': 'KYAPTURE STUDIO', **overrides}
    return wm.make_spec(config)


def _diff_bbox(before, after):
    """Bounding box of the pixels the watermark actually changed (None if identical)."""
    return ImageChops.difference(before.convert('RGB'), after.convert('RGB')).getbbox()


def _mean_diff(before, after):
    diff = ImageChops.difference(before.convert('RGB'), after.convert('RGB'))
    return sum(ImageStat.Stat(diff).mean) / 3


def _logo(size=(200, 100), color=(255, 0, 0, 255)):
    return Image.new('RGBA', size, color)


class TextWatermarkTests(SimpleTestCase):
    def test_default_mark_changes_only_the_bottom_right_region(self):
        img = _photo((1200, 800))
        out = wm.apply_watermark(img, _spec())
        left, top, right, bottom = _diff_bbox(img, out)
        self.assertGreater(left, 1200 * 0.5)      # right half only
        self.assertGreater(top, 800 * 0.6)        # lower part only
        self.assertEqual(out.mode, 'RGB')
        self.assertEqual(out.size, img.size)

    def test_input_image_is_never_mutated(self):
        img = _photo((600, 400))
        snapshot = img.copy()
        wm.apply_watermark(img, _spec())
        self.assertIsNone(_diff_bbox(img, snapshot))

    def test_no_spec_returns_the_image_unchanged(self):
        img = _photo((300, 200))
        self.assertIsNone(_diff_bbox(img, wm.apply_watermark(img, None)))

    def test_mark_is_visible_but_does_not_swallow_the_photo(self):
        img = _photo((2000, 1333))
        out = wm.apply_watermark(img, _spec())
        left, top, right, bottom = _diff_bbox(img, out)
        covered = ((right - left) * (bottom - top)) / (2000 * 1333)
        self.assertGreater(covered, 0.002)        # actually visible
        self.assertLess(covered, 0.05)            # nowhere near covering the photo

    def test_nothing_is_drawn_over_the_centre_by_default(self):
        img = _photo((1000, 800))
        out = wm.apply_watermark(img, _spec())
        centre = (400, 300, 600, 500)
        self.assertIsNone(_diff_bbox(img.crop(centre), out.crop(centre)))


class SizeScalingTests(SimpleTestCase):
    def test_mark_width_tracks_image_width_on_small_and_large_images(self):
        for width in (640, 1280, 2048, 4000):
            img = _photo((width, int(width * 2 / 3)))
            out = wm.apply_watermark(img, _spec(size=20, margin=0))
            left, _, right, _ = _diff_bbox(img, out)
            ratio = (right - left) / width
            self.assertAlmostEqual(ratio, 0.20, delta=0.04, msg=f'width={width}')

    def test_size_setting_changes_the_mark_width(self):
        img = _photo((1600, 1000))
        small = _diff_bbox(img, wm.apply_watermark(img, _spec(size=10)))
        large = _diff_bbox(img, wm.apply_watermark(img, _spec(size=40)))
        self.assertGreater(large[2] - large[0], (small[2] - small[0]) * 3)

    def test_a_long_caption_is_capped_by_height_not_allowed_to_balloon(self):
        img = _photo((400, 400))
        out = wm.apply_watermark(img, _spec(text='W' * 60, size=50))
        _, top, _, bottom = _diff_bbox(img, out)
        self.assertLessEqual(bottom - top, 400 * 0.25 + 2)


class PositionTests(SimpleTestCase):
    EXPECTED = {
        'top-left': ('left', 'top'), 'top-center': ('center', 'top'), 'top-right': ('right', 'top'),
        'center-left': ('left', 'center'), 'center': ('center', 'center'), 'center-right': ('right', 'center'),
        'bottom-left': ('left', 'bottom'), 'bottom-center': ('center', 'bottom'), 'bottom-right': ('right', 'bottom'),
    }

    def test_all_nine_positions_land_in_the_right_third(self):
        width, height = 1500, 1000
        img = _photo((width, height))
        for position, (horizontal, vertical) in self.EXPECTED.items():
            out = wm.apply_watermark(img, _spec(position=position, size=15))
            left, top, right, bottom = _diff_bbox(img, out)
            cx, cy = (left + right) / 2, (top + bottom) / 2
            col = 0 if cx < width / 3 else 1 if cx < 2 * width / 3 else 2
            row = 0 if cy < height / 3 else 1 if cy < 2 * height / 3 else 2
            self.assertEqual(('left', 'center', 'right')[col], horizontal, position)
            self.assertEqual(('top', 'center', 'bottom')[row], vertical, position)


class MarginTests(SimpleTestCase):
    def test_margin_is_a_percentage_of_the_shorter_edge(self):
        img = _photo((2000, 1000))
        out = wm.apply_watermark(img, _spec(margin=10, position='bottom-right'))
        _, _, right, bottom = _diff_bbox(img, out)
        expected = round(0.10 * 1000)                      # shorter edge = 1000
        self.assertAlmostEqual(2000 - right, expected, delta=4)
        self.assertAlmostEqual(1000 - bottom, expected, delta=4)

    def test_margin_zero_sits_on_the_edge_and_larger_margin_moves_inward(self):
        img = _photo((1200, 900))
        flush = _diff_bbox(img, wm.apply_watermark(img, _spec(margin=0)))
        inset = _diff_bbox(img, wm.apply_watermark(img, _spec(margin=12)))
        self.assertLessEqual(1200 - flush[2], 4)
        self.assertGreater(1200 - inset[2], 60)

    def test_top_left_margin_insets_from_the_top_left(self):
        img = _photo((1000, 1000))
        left, top, _, _ = _diff_bbox(img, wm.apply_watermark(img, _spec(margin=8, position='top-left')))
        self.assertAlmostEqual(left, 80, delta=4)
        self.assertAlmostEqual(top, 80, delta=4)


class OpacityTests(SimpleTestCase):
    def test_higher_opacity_changes_pixels_more(self):
        img = _photo((1200, 800))
        deltas = [
            _mean_diff(img, wm.apply_watermark(img, _spec(opacity=value)))
            for value in (10, 40, 70, 100)
        ]
        self.assertEqual(deltas, sorted(deltas))
        self.assertGreater(deltas[-1], deltas[0] * 3)

    def test_low_opacity_is_subtle_and_full_opacity_is_solid_white_text(self):
        img = _photo((1200, 800), color=(0, 0, 0))
        faint = wm.apply_watermark(img, _spec(opacity=10, margin=0))
        solid = wm.apply_watermark(img, _spec(opacity=100, margin=0))
        self.assertLess(max(faint.getdata())[0], 60)
        self.assertEqual(max(solid.getdata()), (255, 255, 255))


class OrientationAndSmallImageTests(SimpleTestCase):
    def test_portrait_and_landscape_both_get_an_inset_mark(self):
        for size in ((800, 1200), (1200, 800), (1000, 1000)):
            img = _photo(size)
            out = wm.apply_watermark(img, _spec(margin=5))
            left, top, right, bottom = _diff_bbox(img, out)
            self.assertGreaterEqual(left, 0, size)
            self.assertLessEqual(right, size[0], size)
            self.assertLessEqual(bottom, size[1], size)
            self.assertGreater(size[1] - bottom, 0, size)        # inset from the bottom edge

    def test_tiny_images_do_not_crash(self):
        for size in ((1, 1), (8, 8), (40, 30), (100, 20)):
            out = wm.apply_watermark(_photo(size), _spec())
            self.assertEqual(out.size, size)

    def test_rgba_and_palette_inputs_are_handled(self):
        for mode in ('RGBA', 'L', 'P'):
            img = Image.new(mode, (300, 200))
            self.assertEqual(wm.apply_watermark(img, _spec()).mode, 'RGB')


class LogoWatermarkTests(SimpleTestCase):
    def test_logo_is_composited_at_the_requested_position_and_size(self):
        img = _photo((1200, 800), color=(0, 0, 0))
        spec = wm.make_spec({**wm.DEFAULTS, 'type': 'logo', 'size': 20, 'opacity': 100,
                             'margin': 0, 'position': 'top-left'}, logo=_logo())
        out = wm.apply_watermark(img, spec)
        left, top, right, bottom = _diff_bbox(img, out)
        self.assertEqual((left, top), (0, 0))
        self.assertAlmostEqual((right - left) / 1200, 0.20, delta=0.01)
        # aspect ratio (2:1) preserved
        self.assertAlmostEqual((right - left) / (bottom - top), 2.0, delta=0.1)
        self.assertEqual(out.getpixel((10, 10)), (255, 0, 0))

    def test_logo_respects_opacity(self):
        img = _photo((1000, 700), color=(0, 0, 0))
        half = wm.make_spec({**wm.DEFAULTS, 'type': 'logo', 'opacity': 50, 'margin': 0,
                             'position': 'top-left'}, logo=_logo())
        out = wm.apply_watermark(img, half)
        self.assertAlmostEqual(out.getpixel((5, 5))[0], 128, delta=3)

    def test_transparent_logo_pixels_leave_the_photo_untouched(self):
        logo = Image.new('RGBA', (100, 100), (0, 0, 0, 0))
        for x in range(50):
            for y in range(100):
                logo.putpixel((x, y), (255, 255, 255, 255))     # left half opaque, right half clear
        img = _photo((1000, 1000), color=(10, 20, 30))
        spec = wm.make_spec({**wm.DEFAULTS, 'type': 'logo', 'size': 20, 'opacity': 100, 'margin': 0,
                             'position': 'top-left'}, logo=logo)
        out = wm.apply_watermark(img, spec)
        self.assertEqual(out.getpixel((10, 50)), (255, 255, 255))
        self.assertEqual(out.getpixel((150, 50)), (10, 20, 30))

    def test_tall_logo_is_capped_by_height(self):
        img = _photo((1000, 500))
        spec = wm.make_spec({**wm.DEFAULTS, 'type': 'logo', 'size': 40}, logo=_logo((50, 400)))
        _, top, _, bottom = _diff_bbox(img, wm.apply_watermark(img, spec))
        self.assertLessEqual(bottom - top, 500 * 0.25 + 2)


class FontAndFailureTests(SimpleTestCase):
    def test_missing_fonts_fall_back_to_a_readable_scaled_mark(self):
        img = _photo((1200, 800), color=(0, 0, 0))
        with mock.patch.object(wm, '_FONT_CANDIDATES', ('/no/such/font.ttf',)), \
                mock.patch.object(wm.ImageFont, 'load_default', side_effect=[TypeError('no size kw'), wm.ImageFont.load_default()]):
            out = wm.apply_watermark(img, _spec(opacity=100))
        left, _, right, _ = _diff_bbox(img, out)
        self.assertAlmostEqual((right - left) / 1200, 0.20, delta=0.04)     # scaled up, not 8px wide

    def test_render_failure_returns_the_unwatermarked_image_and_logs_an_error(self):
        img = _photo((600, 400))
        with mock.patch.object(wm, '_scaled_mark', side_effect=RuntimeError('boom')):
            with self.assertLogs('apps.core.watermark', level='ERROR') as logs:
                out = wm.apply_watermark(img, _spec())
        self.assertIsNone(_diff_bbox(img, out))
        self.assertTrue(any('Watermark rendering failed' in line for line in logs.output))

    def test_logo_spec_without_a_logo_image_degrades_to_unwatermarked(self):
        img = _photo((600, 400))
        spec = wm.make_spec({**wm.DEFAULTS, 'type': 'logo'}, logo=None)
        self.assertIsNone(_diff_bbox(img, wm.apply_watermark(img, spec)))


class ConfigValidationTests(SimpleTestCase):
    def test_defaults_are_valid_and_complete(self):
        config, errors = wm.validate_watermark_config({})
        self.assertEqual(errors, {})
        self.assertEqual(config, wm.DEFAULTS)

    def test_unknown_keys_are_dropped(self):
        config, _ = wm.validate_watermark_config({'type': 'text', 'evil': '<script>'})
        self.assertNotIn('evil', config)

    def test_out_of_range_and_wrong_types_are_rejected(self):
        for payload in (
            {'type': 'video'}, {'position': 'middle'}, {'opacity': 0}, {'opacity': 101},
            {'opacity': 'high'}, {'opacity': True}, {'size': 4}, {'size': 51}, {'margin': -1},
            {'margin': 21}, {'text': 'x' * 61}, {'text': 123}, {'text': '<b>hi</b>'},
        ):
            config, errors = wm.validate_watermark_config(payload)
            self.assertIsNone(config, payload)
            self.assertTrue(errors, payload)

    def test_non_object_is_rejected(self):
        for payload in (None, 'text', 5, ['a']):
            self.assertTrue(wm.validate_watermark_config(payload)[1])

    def test_text_whitespace_is_collapsed(self):
        config, _ = wm.validate_watermark_config({'text': '  My \n  Studio  '})
        self.assertEqual(config['text'], 'My Studio')

    def test_signature_changes_with_every_setting_and_is_stable_otherwise(self):
        base = _spec()
        self.assertEqual(base.signature, _spec().signature)
        for change in ({'text': 'Other'}, {'position': 'top-left'}, {'opacity': 30},
                       {'size': 30}, {'margin': 9}):
            self.assertNotEqual(base.signature, _spec(**change).signature, change)
        a = wm.make_spec({**wm.DEFAULTS, 'type': 'logo'}, logo=_logo(), logo_key='logos/a.png')
        b = wm.make_spec({**wm.DEFAULTS, 'type': 'logo'}, logo=_logo(), logo_key='logos/b.png')
        self.assertNotEqual(a.signature, b.signature)           # replacing the logo re-keys it

    def test_versioned_url(self):
        asset = mock.Mock(watermark_signature='abc123')
        self.assertEqual(wm.versioned_url('http://x/a.webp', asset), 'http://x/a.webp?v=abc123')
        self.assertEqual(wm.versioned_url('http://x/a.webp?sig=1', asset), 'http://x/a.webp?sig=1&v=abc123')
        self.assertEqual(wm.versioned_url('http://x/a.webp', mock.Mock(watermark_signature='')), 'http://x/a.webp?v=0')
        self.assertIsNone(wm.versioned_url(None, asset))
