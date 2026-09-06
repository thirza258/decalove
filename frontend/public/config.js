// Deployment settings, replaced at container start-up by docker-entrypoint.d.
//
// This committed copy is the development no-op: it defines nothing, so src/config.ts
// falls through to VITE_* from .env and then to the localhost default. The container
// overwrites this file wholesale, so a stale default here can never win over the
// environment the image was actually run with.
window.__DECALOVE__ = window.__DECALOVE__ || {};
