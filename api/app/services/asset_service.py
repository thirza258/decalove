"""Generated-image lifecycle — PRD §18/§19/§26.

Cache first, generate second, degrade third. A cache miss is never an error: the step is
served with ``status="pending"`` or ``"unavailable"`` and the Ren'Py client draws its
built-in placeholder, so art always trails the story instead of blocking it.
"""

from __future__ import annotations

import logging
import random
import uuid

from app.agents.visual import AssetSpec
from app.assets.base import AssetStore, AssetStoreError
from app.assets.transparency import make_transparent_character_png
from app.domain.asset import AssetRecord
from app.domain.enums import AssetStatus
from app.domain.story import AssetRef
from app.llm.base import ImageError, ImageProvider
from app.repositories.base import AssetRepository

log = logging.getLogger(__name__)


class AssetService:
    def __init__(
        self,
        repository: AssetRepository,
        store: AssetStore,
        image: ImageProvider | None,
        *,
        api_prefix: str = "/api/v1",
        enabled: bool = False,
        generation_probability: float = 1.0,
        width: int = 1024,
        height: int = 576,
    ) -> None:
        self.repository = repository
        self.store = store
        self.image = image
        self.api_prefix = api_prefix
        self.enabled = enabled and image is not None
        self.generation_probability = generation_probability
        self.width = width
        self.height = height

    async def reference(self, spec: AssetSpec) -> AssetRef:
        """Non-blocking lookup used while assembling a batch."""
        record = await self.repository.by_cache_key(spec.cache_key)
        if record is not None:
            return await self.to_ref(record)
        return AssetRef(
            cache_key=spec.cache_key,
            status=AssetStatus.pending if self.enabled else AssetStatus.unavailable,
        )

    async def to_ref(self, record: AssetRecord) -> AssetRef:
        url = None
        try:
            url = await self.store.url(record.object_key)
        except AssetStoreError as exc:  # pragma: no cover - store-specific
            log.warning("could not build a direct URL for %s: %s", record.object_key, exc)
        return AssetRef(
            cache_key=record.cache_key,
            status=AssetStatus.ready,
            asset_id=record.id,
            # A relative path when the API has to proxy; the client joins it to its base URL.
            url=url or f"{self.api_prefix}/assets/{record.id}/view",
        )

    def wants_generation(self, spec: AssetSpec) -> bool:
        """Whether an uncached spec is worth generating at all.

        The sampling gate that keeps the story mostly text (PRD §19). Public so it can be
        rolled at *dispatch* time rather than inside ``ensure``: at the default 5%, gating
        in the worker meant nineteen of every twenty image jobs claimed a queue slot,
        built a whole runtime and connected to MongoDB purely to decide to do nothing --
        while a real image job waited behind them.
        """
        if not self.enabled or self.image is None:
            return False
        if self.generation_probability >= 1.0:
            return True
        if self.generation_probability <= 0.0:
            return False
        return random.random() <= self.generation_probability

    async def ensure(self, spec: AssetSpec, world_id: str, *, gated: bool = True) -> AssetRef:
        """Return the cached asset, generating it first if necessary.

        ``gated=False`` skips the sampling gate, for callers that have already rolled it
        (or that mean it unconditionally, like the asset pre-generation scripts). Rolling
        it twice would square the probability.
        """
        record = await self.repository.by_cache_key(spec.cache_key)
        if record is not None:
            return await self.to_ref(record)
        if not self.enabled or self.image is None:
            return AssetRef(cache_key=spec.cache_key, status=AssetStatus.unavailable)

        if gated and not self.wants_generation(spec):
            log.debug("skipping new image generation for %s (probability gate)", spec.cache_key)
            return AssetRef(cache_key=spec.cache_key, status=AssetStatus.unavailable)

        try:
            data, content_type = await self.image.generate(
                spec.prompt, width=self.width, height=self.height
            )
            if spec.kind == "character":
                data = make_transparent_character_png(data)
                content_type = "image/png"
        except ImageError as exc:
            log.warning("image generation failed for %s: %s", spec.cache_key, exc)
            return AssetRef(cache_key=spec.cache_key, status=AssetStatus.unavailable)

        asset_id = uuid.uuid4().hex
        extension = "png" if "png" in content_type else content_type.rsplit("/", 1)[-1]
        object_key = f"{spec.kind}s/{spec.cache_key}.{extension}"
        try:
            await self.store.put(object_key, data, content_type)
        except AssetStoreError as exc:
            log.warning("could not store asset %s: %s", object_key, exc)
            return AssetRef(cache_key=spec.cache_key, status=AssetStatus.unavailable)

        record = AssetRecord(
            id=asset_id,
            cache_key=spec.cache_key,
            kind=spec.kind,
            world_id=world_id,
            object_key=object_key,
            content_type=content_type,
            size_bytes=len(data),
            prompt=spec.prompt,
            provider=getattr(self.image, "name", "unknown"),
        )
        await self.repository.put(record)
        return await self.to_ref(record)

    async def read(self, asset_id: str) -> tuple[bytes, str] | None:
        record = await self.repository.get(asset_id)
        if record is None:
            return None
        try:
            return await self.store.get(record.object_key)
        except AssetStoreError as exc:
            log.warning("asset %s missing from the store: %s", asset_id, exc)
            return None

    async def metadata(self, asset_id: str) -> AssetRecord | None:
        return await self.repository.get(asset_id)
