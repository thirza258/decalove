"""Asset storage and the placeholder PNG encoder."""

from __future__ import annotations

import struct
import zlib

import pytest

from app.assets.base import AssetStoreError
from app.assets.local_store import LocalAssetStore
from app.assets.png import encode_png, gradient_png


class TestLocalStore:
    async def test_round_trip_preserves_bytes_and_content_type(self, tmp_path):
        store = LocalAssetStore(tmp_path)
        await store.put("backgrounds/rooftop.png", b"\x89PNG payload", "image/png")

        assert await store.exists("backgrounds/rooftop.png")
        assert await store.get("backgrounds/rooftop.png") == (b"\x89PNG payload", "image/png")

    async def test_content_type_survives_a_restart(self, tmp_path):
        await LocalAssetStore(tmp_path).put("a/b.webp", b"x", "image/webp")
        # A fresh instance, as if the process had been restarted.
        _, content_type = await LocalAssetStore(tmp_path).get("a/b.webp")
        assert content_type == "image/webp"

    async def test_a_missing_key_raises_rather_than_returning_empty_bytes(self, tmp_path):
        with pytest.raises(AssetStoreError):
            await LocalAssetStore(tmp_path).get("nope.png")
        assert not await LocalAssetStore(tmp_path).exists("nope.png")

    @pytest.mark.parametrize(
        "key",
        ["../escaped.png", "backgrounds/../../escaped.png", "/etc/passwd", "a/../../b.png"],
    )
    async def test_keys_cannot_escape_the_asset_root(self, tmp_path, key):
        """Cache keys are derived from model output, so treat them as untrusted."""
        root = tmp_path / "assets"
        store = LocalAssetStore(root)
        try:
            await store.put(key, b"x", "image/png")
        except AssetStoreError:
            pass  # rejected outright is fine
        outside = [p for p in tmp_path.rglob("*") if p.is_file() and root not in p.parents and p.parent != root]
        assert not outside, f"{key!r} wrote outside the asset root: {outside}"

    async def test_the_store_never_offers_a_direct_url(self, tmp_path):
        """Local files are proxied by the API, so the client gets a path, not a URL."""
        assert await LocalAssetStore(tmp_path).url("anything.png") is None

    async def test_nested_keys_create_their_directories(self, tmp_path):
        store = LocalAssetStore(tmp_path)
        await store.put("deep/er/still/x.png", b"y", "image/png")
        assert (tmp_path / "deep" / "er" / "still" / "x.png").read_bytes() == b"y"


class TestPngEncoder:
    def test_output_is_a_structurally_valid_png(self):
        data = gradient_png(16, 8, "#ff0000", "#0000ff", seed="t")

        assert data[:8] == b"\x89PNG\r\n\x1a\n"
        # IEND is 12 bytes: length(4) + tag(4) + crc(4).
        assert data[-12:] == struct.pack(">I", 0) + b"IEND" + struct.pack(
            ">I", zlib.crc32(b"IEND") & 0xFFFFFFFF
        )

        length, tag = struct.unpack(">I", data[8:12])[0], data[12:16]
        assert tag == b"IHDR" and length == 13
        width, height, depth, colour = struct.unpack(">IIBB", data[16:26])
        assert (width, height, depth, colour) == (16, 8, 8, 2)  # 8-bit truecolour

    def test_every_chunk_crc_checks_out(self):
        data = gradient_png(8, 4, "#123456", "#abcdef", seed="crc")
        offset = 8
        seen = []
        while offset < len(data):
            length = struct.unpack(">I", data[offset : offset + 4])[0]
            tag = data[offset + 4 : offset + 8]
            body = data[offset + 8 : offset + 8 + length]
            crc = struct.unpack(">I", data[offset + 8 + length : offset + 12 + length])[0]
            assert crc == zlib.crc32(tag + body) & 0xFFFFFFFF, tag
            seen.append(tag)
            offset += 12 + length
        assert seen == [b"IHDR", b"IDAT", b"IEND"]

    def test_pixel_data_decompresses_to_the_expected_scanlines(self):
        width, height = 6, 3
        data = gradient_png(width, height, "#000000", "#ffffff", seed="x", grain=0)

        offset = 8
        while data[offset + 4 : offset + 8] != b"IDAT":
            offset += 12 + struct.unpack(">I", data[offset : offset + 4])[0]
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        raw = zlib.decompress(data[offset + 8 : offset + 8 + length])

        assert len(raw) == height * (1 + width * 3)
        # Every scanline carries filter type 0.
        assert all(raw[row * (1 + width * 3)] == 0 for row in range(height))
        # With no grain the gradient runs dark to light.
        assert raw[1] == 0 and raw[-1] == 255

    def test_the_seed_changes_the_bytes_but_not_the_shape(self):
        a = gradient_png(32, 18, "#ff9e7d", "#2b3a67", seed="rooftop:sunset")
        b = gradient_png(32, 18, "#ff9e7d", "#2b3a67", seed="rooftop:sunset")
        c = gradient_png(32, 18, "#ff9e7d", "#2b3a67", seed="library:evening")

        assert a == b, "the same scene must produce the same file"
        assert a != c, "different scenes must not collide"
        assert len(a) == len(b)

    @pytest.mark.parametrize("colour", ["#f00", "f00", "#ff0000", "not-a-colour", ""])
    def test_malformed_colours_degrade_instead_of_raising(self, colour):
        """Palettes come from authored content; a typo should not take a scene down."""
        assert gradient_png(4, 2, colour, colour, seed="s")[:8] == b"\x89PNG\r\n\x1a\n"

    def test_a_row_count_mismatch_is_rejected(self):
        with pytest.raises(ValueError, match="expected 3 rows"):
            encode_png(2, 3, [b"\x00" * 6])


class TestAssetServiceProbability:
    async def test_cached_assets_always_reused_regardless_of_probability(self, tmp_path):
        from app.agents.visual import AssetSpec
        from app.domain.enums import AssetStatus
        from app.llm.placeholder_image import PlaceholderImageProvider
        from app.repositories.memory_repo import InMemoryAssetRepository
        from app.services.asset_service import AssetService

        repo = InMemoryAssetRepository()
        store = LocalAssetStore(tmp_path)
        service = AssetService(
            repo, store, PlaceholderImageProvider(), enabled=True, generation_probability=0.0
        )
        spec = AssetSpec(kind="background", cache_key="bg_known", prompt="classroom")

        # First when prob=0.0 and uncached -> skips generation
        ref1 = await service.ensure(spec, "w")
        assert ref1.status is AssetStatus.unavailable

        # Now pre-fill asset in repo
        service_active = AssetService(
            repo, store, PlaceholderImageProvider(), enabled=True, generation_probability=1.0
        )
        ref2 = await service_active.ensure(spec, "w")
        assert ref2.status is AssetStatus.ready

        # Now with prob=0.0 -> already generated image is 100% reused
        ref3 = await service.ensure(spec, "w")
        assert ref3.status is AssetStatus.ready
        assert ref3.asset_id == ref2.asset_id
