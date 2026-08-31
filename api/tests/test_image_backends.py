"""IMAGE_BACKEND as a preference chain — one backend, several, or a fallback.

The two backends fail for unrelated reasons: a GPU box loses SDXL to a driver upgrade or
an OOM, a hosted model rate-limits or goes down. Either alone leaves the player on
placeholder art for the length of the outage while the other one was sitting right there.
"""

from __future__ import annotations

import sys
import types

import pytest

from app.config import IMAGE_BACKENDS, Settings
from app.llm.base import ImageError
from app.llm.fallback_image import FallbackImageProvider
from app.runtime import _build_image_chain

PNG = (b"\x89PNG\r\n\x1a\n", "image/png")


class Stub:
    """An image provider that either answers or raises, on demand."""

    def __init__(self, name: str, *, fails: bool = False) -> None:
        self.name = name
        self.fails = fails
        self.calls = 0
        self.closed = False
        self.seen: list[dict] = []

    async def generate(
        self,
        prompt: str,
        *,
        width: int = 1024,
        height: int = 576,
        seed: int | None = None,
        negative: str | None = None,
    ):
        self.calls += 1
        self.seen.append({"prompt": prompt, "seed": seed, "negative": negative})
        if self.fails:
            raise ImageError(f"{self.name} is down")
        return (f"{self.name}:{prompt}".encode(), "image/png")

    async def aclose(self) -> None:
        self.closed = True


class TestSettingsParsing:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("openrouter", ("openrouter",)),
            ("sdxl", ("sdxl",)),
            ("sdxl,openrouter", ("sdxl", "openrouter")),
            # Whitespace and case are what a hand-edited .env actually looks like.
            (" SDXL , OpenRouter ", ("sdxl", "openrouter")),
            # De-duplicated, first occurrence wins: it is a preference order.
            ("sdxl,openrouter,sdxl", ("sdxl", "openrouter")),
        ],
    )
    def test_the_chain_is_parsed_in_order(self, raw, expected):
        assert Settings(IMAGE_BACKEND=raw).image_backends == expected

    @pytest.mark.parametrize("raw", ["sdlx", "", "sdxl,nope", ","])
    def test_an_unknown_backend_fails_at_boot(self, raw):
        """A typo used to be silent: it matched neither branch, so the deployment simply
        never produced art -- hours later, with nothing in the log pointing at the cause.
        """
        with pytest.raises(ValueError) as caught:
            Settings(IMAGE_BACKEND=raw)
        # The error has to name the valid set, or it just moves the guessing earlier.
        assert all(name in str(caught.value) for name in IMAGE_BACKENDS)


class TestFallbackChain:
    async def test_the_first_backend_that_answers_wins(self):
        first, second = Stub("first"), Stub("second")
        chain = FallbackImageProvider([first, second])

        data, content_type = await chain.generate("a rooftop")

        assert data == b"first:a rooftop"
        assert content_type == "image/png"
        assert second.calls == 0, "the fallback ran even though the primary answered"

    async def test_a_failing_backend_hands_over_to_the_next(self):
        gpu, api = Stub("sdxl-local", fails=True), Stub("openrouter-image")
        chain = FallbackImageProvider([gpu, api])

        data, _ = await chain.generate("a rooftop")

        assert data == b"openrouter-image:a rooftop"
        assert gpu.calls == 1, "the failing backend was skipped rather than tried"

    async def test_when_every_backend_fails_the_error_names_all_of_them(self):
        gpu, api = Stub("sdxl-local", fails=True), Stub("openrouter-image", fails=True)

        with pytest.raises(ImageError) as caught:
            await FallbackImageProvider([gpu, api]).generate("a rooftop")

        # AssetService turns this into status="unavailable" and the client draws its own
        # placeholder, so the story is never blocked -- but the log has to say why.
        message = str(caught.value)
        assert "sdxl-local is down" in message
        assert "openrouter-image is down" in message

    async def test_the_seed_and_negatives_reach_the_backend_that_serves(self):
        """Consistency is carried by these two, so a link that drops them is a link that
        draws a different person. The fallback is the easiest place to lose them.
        """
        gpu, api = Stub("sdxl-local", fails=True), Stub("openrouter-image")

        await FallbackImageProvider([gpu, api]).generate(
            "Aiko", seed=1234, negative="multiple people"
        )

        for stub in (gpu, api):
            assert stub.seen[-1]["seed"] == 1234
            assert stub.seen[-1]["negative"] == "multiple people"

    async def test_closing_the_chain_closes_every_link(self):
        first, second = Stub("first"), Stub("second")
        await FallbackImageProvider([first, second]).aclose()
        assert first.closed and second.closed

    def test_the_chain_names_itself_after_its_links(self):
        """/health answers "which backend am I actually on"; a wrapper name would hide it."""
        assert FallbackImageProvider([Stub("sdxl-local"), Stub("openrouter-image")]).name == (
            "sdxl-local+openrouter-image"
        )

    def test_an_empty_chain_is_rejected(self):
        with pytest.raises(ValueError):
            FallbackImageProvider([])


class TestChainAssembly:
    """What ``_build_image_chain`` makes of a given IMAGE_BACKEND."""

    @staticmethod
    def _settings(backend: str, *, key: str = "") -> Settings:
        return Settings(
            IMAGE_BACKEND=backend, OPENROUTER_API_KEY=key, IMAGE_GENERATION_ENABLED=True
        )

    @staticmethod
    def _openrouter(key: str) -> dict:
        return {
            "api_key": key,
            "base_url": "https://openrouter.ai/api/v1",
            "timeout": 1.0,
            "max_retries": 0,
            "referer": "",
            "title": "test",
        }

    def test_a_chain_of_one_is_not_wrapped(self):
        """So /health keeps naming the backend rather than a wrapper."""
        chain = _build_image_chain(self._settings("sdxl"), {})
        assert chain.name == "sdxl-local"
        assert not isinstance(chain, FallbackImageProvider)

    def test_two_backends_become_a_chain_in_order(self):
        chain = _build_image_chain(
            self._settings("sdxl,openrouter", key="k"), self._openrouter("k")
        )
        assert chain.name == "sdxl-local+openrouter-image"

    def test_openrouter_is_dropped_when_there_is_no_key(self):
        """Otherwise every single image pays a round-trip to rediscover it."""
        chain = _build_image_chain(self._settings("sdxl,openrouter"), {})
        assert chain.name == "sdxl-local"

    def test_a_chain_with_nothing_usable_falls_back_to_the_placeholder(self):
        """IMAGE_GENERATION_ENABLED=true with no key keeps the asset pipeline exercisable
        offline -- the contract /health reports as images="placeholder".
        """
        assert _build_image_chain(self._settings("openrouter"), {}).name == "placeholder"


def _fake_torch(*, cuda: bool):
    """A stand-in for torch, so the device check is testable without a 2 GB install.

    Enough of the surface for _load_pipeline's fast path: the dtype lookup and the
    availability probe. It never reaches diffusers, which is the point of the check
    sitting where it does.
    """
    module = types.ModuleType("torch")
    module.float16 = "float16"
    module.float32 = "float32"
    module.cuda = types.SimpleNamespace(is_available=lambda: cuda)
    return module


LOAD_ARGS = ("stabilityai/stable-diffusion-xl-base-1.0", "models/sdxl")


class TestSdxlDeviceIsARequirement:
    def test_asking_for_cuda_without_cuda_fails_rather_than_using_the_cpu(self, monkeypatch):
        """An SDXL pass on CPU is minutes per image -- past the image queue's time limit and
        indistinguishable from a hang. Failing is what lets the next backend take over.
        """
        from app.llm import sdxl_image

        monkeypatch.setitem(sys.modules, "torch", _fake_torch(cuda=False))

        with pytest.raises(ImageError) as caught:
            sdxl_image._load_pipeline(*LOAD_ARGS, "cuda", "float16", True, False, True)

        assert "SDXL_DEVICE=cpu" in str(caught.value), "the error must say how to opt in"

    def test_the_failure_is_not_cached_so_a_later_gpu_still_works(self, monkeypatch):
        """_get_or_load_pipeline holds the load lock across the load. A cached failure
        would mean a driver coming back never takes effect until the worker restarts.
        """
        from app.llm import sdxl_image

        monkeypatch.setitem(sys.modules, "torch", _fake_torch(cuda=False))
        monkeypatch.setattr(sdxl_image, "_PIPELINES", {})

        for _ in range(2):
            with pytest.raises(ImageError):
                sdxl_image._get_or_load_pipeline(
                    ("key",), *LOAD_ARGS, "cuda", "float16", True, False, True
                )

        assert sdxl_image._PIPELINES == {}
        # The lock has to be free, or the next attempt deadlocks instead of retrying.
        assert sdxl_image._PIPELINE_LOCK.acquire(blocking=False)
        sdxl_image._PIPELINE_LOCK.release()

    def test_asking_for_the_cpu_is_honoured(self, monkeypatch):
        """SDXL_DEVICE=cpu is a deliberate opt-in, so it must get past the check and on to
        the real load -- which fails here only because diffusers is not installed.
        """
        from app.llm import sdxl_image

        monkeypatch.setitem(sys.modules, "torch", _fake_torch(cuda=False))

        with pytest.raises(Exception) as caught:
            sdxl_image._load_pipeline(*LOAD_ARGS, "cpu", "float32", True, False, True)

        assert "SDXL_DEVICE" not in str(caught.value), "the device check rejected cpu"
