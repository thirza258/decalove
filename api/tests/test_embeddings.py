"""Memory embeddings — the hashed default and the HTTP alternative."""

from __future__ import annotations

import math

import httpx
import pytest

from app.llm import embeddings as module
from app.llm.base import LLMError
from app.llm.embeddings import HashingEmbedding, HttpEmbedding, cosine


class TestCosine:
    def test_identical_vectors_score_one(self):
        assert cosine([1.0, 0.0, 1.0], [1.0, 0.0, 1.0]) == pytest.approx(1.0)

    def test_orthogonal_vectors_score_zero(self):
        assert cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_opposite_vectors_score_minus_one(self):
        assert cosine([1.0, 2.0], [-1.0, -2.0]) == pytest.approx(-1.0)

    def test_magnitude_does_not_matter(self):
        assert cosine([3.0, 4.0], [30.0, 40.0]) == pytest.approx(1.0)

    @pytest.mark.parametrize(
        ("a", "b"),
        [([], [1.0]), ([1.0], []), ([1.0, 2.0], [1.0]), ([0.0, 0.0], [1.0, 1.0])],
    )
    def test_degenerate_inputs_return_zero_rather_than_dividing_by_zero(self, a, b):
        assert cosine(a, b) == 0.0


class TestHashingEmbedding:
    def test_vectors_are_unit_length(self):
        vector = HashingEmbedding().embed_one("Aiko waited on the rooftop until sunset")
        assert math.sqrt(sum(v * v for v in vector)) == pytest.approx(1.0)

    def test_dimension_is_configurable(self):
        assert len(HashingEmbedding(64).embed_one("x")) == 64

    def test_empty_text_yields_a_zero_vector_not_a_crash(self):
        assert HashingEmbedding().embed_one("") == [0.0] * 256

    def test_hashing_is_stable_across_processes(self):
        """Python's built-in hash() is salted per process; a stored embedding must
        still be readable after a restart, so this uses blake2b instead."""
        import subprocess
        import sys

        script = (
            "import sys; sys.path.insert(0, '.');"
            "from app.llm.embeddings import HashingEmbedding;"
            "print(sum(HashingEmbedding().embed_one('Aiko defended the club')))"
        )
        runs = {
            subprocess.run(
                [sys.executable, "-c", script], capture_output=True, text=True, cwd="."
            ).stdout.strip()
            for _ in range(2)
        }
        assert len(runs) == 1 and runs != {""}

    def test_possessives_and_plurals_fold_together(self):
        """'brother' and "brother's" hashing apart made a query about someone's
        brother score exactly zero against the memory that mentions him."""
        embedder = HashingEmbedding()
        query = embedder.embed_one("Aiko's brother")
        related = embedder.embed_one("Aiko covers for her brother")
        unrelated = embedder.embed_one("Mika lost a race")

        assert cosine(query, related) > 0.2
        assert cosine(query, related) > cosine(query, unrelated)

    def test_word_order_matters_a_little(self):
        """Bigrams mean a reversal is similar but not identical."""
        embedder = HashingEmbedding()
        forward = embedder.embed_one("Aiko trusts Ren")
        backward = embedder.embed_one("Ren trusts Aiko")
        assert 0.3 < cosine(forward, backward) < 1.0

    async def test_embed_handles_a_batch(self):
        vectors = await HashingEmbedding().embed(["one", "two", "three"])
        assert len(vectors) == 3
        assert all(len(v) == 256 for v in vectors)


class TestHttpEmbedding:
    def wire(self, monkeypatch, handler):
        recorded: list[httpx.Request] = []

        def capture(request: httpx.Request) -> httpx.Response:
            recorded.append(request)
            return handler(request)

        real = httpx.AsyncClient
        transport = httpx.MockTransport(capture)
        monkeypatch.setattr(
            module.httpx, "AsyncClient", lambda **kwargs: real(transport=transport, **kwargs)
        )
        return recorded

    def provider(self):
        return HttpEmbedding(
            base_url="https://api.openai.com/v1",
            api_key="sk-test",
            model="text-embedding-3-small",
            dimensions=3,
        )

    async def test_it_calls_an_openai_compatible_endpoint(self, monkeypatch):
        import json

        recorded = self.wire(
            monkeypatch,
            lambda request: httpx.Response(
                200, json={"data": [{"embedding": [0.1, 0.2, 0.3]}, {"embedding": [1.0, 0.0, 0.0]}]}
            ),
        )

        vectors = await self.provider().embed(["a", "b"])
        assert vectors == [[0.1, 0.2, 0.3], [1.0, 0.0, 0.0]]

        request = recorded[0]
        assert str(request.url) == "https://api.openai.com/v1/embeddings"
        assert request.headers["Authorization"] == "Bearer sk-test"
        assert json.loads(request.content) == {"model": "text-embedding-3-small", "input": ["a", "b"]}

    async def test_a_transport_failure_becomes_an_llm_error(self, monkeypatch):
        self.wire(monkeypatch, lambda request: httpx.Response(500, text="down"))
        with pytest.raises(LLMError, match="embedding request failed"):
            await self.provider().embed(["a"])

    async def test_a_non_json_body_becomes_an_llm_error(self, monkeypatch):
        self.wire(monkeypatch, lambda request: httpx.Response(200, text="<html>oops</html>"))
        with pytest.raises(LLMError):
            await self.provider().embed(["a"])

    async def test_the_client_is_reused_and_closable(self, monkeypatch):
        recorded = self.wire(
            monkeypatch, lambda request: httpx.Response(200, json={"data": [{"embedding": [1.0]}]})
        )
        provider = self.provider()
        await provider.embed(["a"])
        await provider.embed(["b"])
        assert len(recorded) == 2

        await provider.aclose()
        assert provider._client is None
        await provider.aclose()  # idempotent
