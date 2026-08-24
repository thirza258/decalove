## HTTP client for the Decalove API.
##
## Every call is made from a `python:` block, never from inside a screen or an
## interaction. Ren'Py documents that renpy.fetch called OUTSIDE an interaction
## repeatedly calls renpy.pause() so the game does not lock up, while inside one
## it blocks the display system. The playback loop honours that.

init -5 python:

    import json as _json


    def _decalove_is_control_flow(exc):
        """True for Ren'Py's own control-flow exceptions.

        Quit, jump, rollback and end-interaction all derive from Exception, so a
        bare `except Exception` around a fetch would swallow the player's attempt
        to quit mid-request. Everything from renpy.* is re-raised except the one
        exception we actually want to handle.
        """
        module = getattr(type(exc), "__module__", "") or ""
        return module.startswith("renpy") and type(exc).__name__ != "FetchError"


    class DecaloveAPI(object):
        """Thin wrapper over renpy.fetch. Never raises; returns None on failure."""

        def __init__(self, base, prefix):
            self.base = base.rstrip("/")
            self.prefix = prefix
            self.last_error = None

        def url(self, path):
            return self.base + self.prefix + path

        def _call(self, path, method=None, payload=None, params=None, wait_ms=0):
            timeout = (wait_ms / 1000.0) + DECALOVE_HTTP_MARGIN
            try:
                kwargs = {"result": "json", "timeout": timeout}
                if params:
                    kwargs["params"] = params
                if payload is not None:
                    kwargs["json"] = payload
                if method:
                    kwargs["method"] = method
                result = renpy.fetch(self.url(path), **kwargs)
                self.last_error = None
                return result
            except Exception as exc:
                if _decalove_is_control_flow(exc):
                    raise
                self.last_error = str(exc)
                return None

        def get(self, path, params=None, wait_ms=0):
            return self._call(path, params=params, wait_ms=wait_ms)

        def post(self, path, payload):
            return self._call(path, method="POST", payload=payload or {})

        def fetch_bytes(self, url):
            """Raw image bytes, for im.Data(). Handles relative and absolute URLs."""
            if not url:
                return None
            absolute = url if url.startswith("http") else self.base + url
            try:
                return renpy.fetch(absolute, result="bytes", timeout=DECALOVE_HTTP_MARGIN * 2)
            except Exception as exc:
                if _decalove_is_control_flow(exc):
                    raise
                self.last_error = str(exc)
                return None


    decalove_api = DecaloveAPI(DECALOVE_API_BASE, DECALOVE_API_PREFIX)
