# backend/apps/photos/tests/test_png_location_7f.py
"""
7F (reviewer 7R, F4): PNG location stripping must fail CLOSED.

Before 7F two ways of carrying GPS in a PNG were not read, so the original was
stored with its location:
  - an XMP packet in a COMPRESSED iTXt chunk (only zTXt was decompressed);
  - EXIF stored as hex text ("Raw profile type exif" / "Raw profile type APP1",
    the way ImageMagick 6 writes EXIF into a PNG), in tEXt, zTXt or iTXt.

Each kind is built here with GPS; strip_exif_gps must return a file with no
location left (other metadata kept), or refuse it (LocationStripError, which
the upload view answers with a 400).
"""
import io
import zlib

import piexif
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from PIL import Image

from apps.core.utils import LocationStripError, _png_chunk, strip_exif_gps

XMP_WITH_GPS = (
    b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
    b'<rdf:Description xmlns:exif="http://ns.adobe.com/exif/1.0/" exif:GPSLatitude="48,51.5N" '
    b'exif:GPSLongitude="2,17.4E"/></rdf:RDF></x:xmpmeta>'
)


def exif_with_gps():
    return piexif.dump({
        '0th': {piexif.ImageIFD.Make: b'Canon', piexif.ImageIFD.Model: b'EOS 7F'},
        'Exif': {},
        'GPS': {
            piexif.GPSIFD.GPSLatitudeRef: b'N',
            piexif.GPSIFD.GPSLatitude: ((48, 1), (51, 1), (30, 1)),
            piexif.GPSIFD.GPSLongitudeRef: b'E',
            piexif.GPSIFD.GPSLongitude: ((2, 1), (17, 1), (24, 1)),
        },
    })                                                  # b'Exif\0\0' + TIFF


def raw_profile(name, payload):
    """ImageMagick 6's text form of a binary profile: name, length, then hex in 72-character lines."""
    hexed = payload.hex()
    lines = '\n'.join(hexed[i:i + 72] for i in range(0, len(hexed), 72))
    return f'\n{name}\n{len(payload):8d}\n{lines}\n'.encode('latin-1')


def png_with(*chunks):
    buf = io.BytesIO()
    Image.new('RGB', (4, 4), (200, 30, 30)).save(buf, format='PNG')
    raw = buf.getvalue()
    iend = raw.rindex(b'IEND') - 4
    return raw[:iend] + b''.join(_png_chunk(kind, data) for kind, data in chunks) + raw[iend:]


def itxt(keyword, text, compressed):
    body = zlib.compress(text) if compressed else text
    return b'iTXt', keyword + b'\x00' + (b'\x01\x00' if compressed else b'\x00\x00') + b'\x00\x00' + body


def ztxt(keyword, text):
    return b'zTXt', keyword + b'\x00\x00' + zlib.compress(text)


def text_chunks(data):
    """{keyword: decoded text} of every tEXt/zTXt/iTXt chunk in a PNG."""
    pos, found = 8, {}
    while pos + 8 <= len(data):
        length = int.from_bytes(data[pos:pos + 4], 'big')
        kind, body = data[pos + 4:pos + 8], data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if kind == b'tEXt':
            key, text = body.split(b'\x00', 1)
        elif kind == b'zTXt':
            key, rest = body.split(b'\x00', 1)
            text = zlib.decompress(rest[1:])
        elif kind == b'iTXt':
            key, rest = body.split(b'\x00', 1)
            flag, rest = rest[0], rest[2:]
            _lang, rest = rest.split(b'\x00', 1)
            _translated, text = rest.split(b'\x00', 1)
            text = zlib.decompress(text) if flag else text
        else:
            continue
        found[key] = text
    return found


def exif_from_raw_profile(text):
    lines = text.decode('latin-1').strip().split('\n')
    return bytes.fromhex(''.join(lines[2:]))


class PngLocationTests(SimpleTestCase):
    def strip(self, data):
        return strip_exif_gps(SimpleUploadedFile('gps.png', data, content_type='image/png')).read()

    def assert_pixels_kept(self, original, cleaned):
        self.assertEqual(Image.open(io.BytesIO(original)).tobytes(), Image.open(io.BytesIO(cleaned)).tobytes())

    def test_compressed_itxt_xmp_with_gps_is_removed(self):
        original = png_with(itxt(b'XML:com.adobe.xmp', XMP_WITH_GPS, compressed=True))
        cleaned = self.strip(original)
        self.assertNotIn(b'XML:com.adobe.xmp', text_chunks(cleaned))
        self.assert_pixels_kept(original, cleaned)

    def test_uncompressed_itxt_xmp_with_gps_is_still_removed(self):
        cleaned = self.strip(png_with(itxt(b'XML:com.adobe.xmp', XMP_WITH_GPS, compressed=False)))
        self.assertNotIn(b'XML:com.adobe.xmp', text_chunks(cleaned))

    def _assert_raw_profile_gps_removed(self, chunk, keyword):
        original = png_with(chunk)
        cleaned = self.strip(original)
        exif = piexif.load(exif_from_raw_profile(text_chunks(cleaned)[keyword]))
        self.assertFalse(exif['GPS'])                                   # location gone
        self.assertEqual(exif['0th'][piexif.ImageIFD.Make], b'Canon')    # camera kept
        self.assert_pixels_kept(original, cleaned)

    def test_raw_profile_exif_in_text_chunk(self):
        keyword = b'Raw profile type exif'
        self._assert_raw_profile_gps_removed((b'tEXt', keyword + b'\x00' + raw_profile('exif', exif_with_gps())), keyword)

    def test_raw_profile_exif_in_ztxt_chunk(self):
        keyword = b'Raw profile type exif'
        self._assert_raw_profile_gps_removed(ztxt(keyword, raw_profile('exif', exif_with_gps())), keyword)

    def test_raw_profile_app1_in_ztxt_chunk(self):
        keyword = b'Raw profile type APP1'
        self._assert_raw_profile_gps_removed(ztxt(keyword, raw_profile('APP1', exif_with_gps())), keyword)

    def test_raw_profile_exif_without_the_exif_header(self):
        keyword = b'Raw profile type exif'
        tiff_only = exif_with_gps()[6:]
        self._assert_raw_profile_gps_removed(ztxt(keyword, raw_profile('exif', tiff_only)), keyword)

    def test_raw_profile_exif_in_compressed_itxt_chunk(self):
        keyword = b'Raw profile type exif'
        self._assert_raw_profile_gps_removed(itxt(keyword, raw_profile('exif', exif_with_gps()), compressed=True), keyword)

    def test_raw_profile_xmp_with_gps_is_removed(self):
        keyword = b'Raw profile type xmp'
        cleaned = self.strip(png_with(ztxt(keyword, raw_profile('xmp', XMP_WITH_GPS))))
        self.assertNotIn(keyword, text_chunks(cleaned))

    def test_raw_profile_8bim_with_an_exif_resource_is_removed(self):
        keyword = b'Raw profile type 8bim'
        exif = exif_with_gps()[6:]
        resource = b'8BIM\x04\x22\x00\x00' + len(exif).to_bytes(4, 'big') + exif
        cleaned = self.strip(png_with(ztxt(keyword, raw_profile('8bim', resource))))
        self.assertNotIn(keyword, text_chunks(cleaned))

    def test_a_text_chunk_naming_a_gps_field_is_removed(self):
        cleaned = self.strip(png_with((b'tEXt', b'exif:GPSLatitude\x0048/1, 51/1, 30/1')))
        self.assertNotIn(b'exif:GPSLatitude', text_chunks(cleaned))

    def test_a_png_without_location_is_returned_byte_for_byte(self):
        original = png_with((b'tEXt', b'Software\x00KYAPTURE'), itxt(b'Comment', b'no place here', compressed=True))
        self.assertEqual(self.strip(original), original)

    def test_unreadable_compressed_text_is_refused(self):
        broken = (b'iTXt', b'XML:com.adobe.xmp\x00\x01\x00\x00\x00' + b'not zlib at all')
        with self.assertRaises(LocationStripError):
            self.strip(png_with(broken))

    def test_unreadable_raw_profile_is_refused(self):
        with self.assertRaises(LocationStripError):
            self.strip(png_with((b'tEXt', b'Raw profile type exif\x00\nexif\n      10\nzz-not-hex\n')))

    def test_a_decompression_bomb_is_refused(self):
        bomb = itxt(b'Comment', b'\x00' * (40 * 1024 * 1024), compressed=True)
        with self.assertRaises(LocationStripError):
            self.strip(png_with(bomb))
