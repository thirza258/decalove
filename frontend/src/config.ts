/**
 * Decalove web client configuration — the port of `game/decalove/00_config.rpy`.
 *
 * The backend owns the story; this client owns presentation (PRD §20). Names and
 * defaults deliberately match the Ren'Py client's, so the two builds can be reasoned
 * about together and a number tuned in one is findable in the other.
 */

/**
 * Deployment settings, resolved at *runtime* rather than baked into the bundle.
 *
 * Vite substitutes `import.meta.env.VITE_*` at build time, which is the wrong lifetime
 * for a self-hosted image: you would need one build per environment. So the container
 * writes `/config.js` from its own environment at start-up and the bundle reads that
 * first, falling back to the build-time value and then to a local default. One image,
 * configured where it runs.
 *
 * Only what genuinely differs per deployment lives here. The tuning below (WAIT_MS,
 * AMBIENT_LIMIT, TEXT_SPEED_CPS) stays with the build: each runtime knob is another
 * thing the entrypoint can get wrong, and another way to drift from 00_config.rpy.
 */
declare global {
  interface Window {
    __DECALOVE__?: { apiBase?: string; apiPrefix?: string };
  }
}

const runtime = (typeof window !== "undefined" && window.__DECALOVE__) || {};

/**
 * Where the Decalove API lives.
 *
 * An empty string is a meaningful value, not a missing one: it means same-origin, which
 * is how the container is configured by default — nginx proxies `/api/` to the backend,
 * so there is no CORS to satisfy and no http/https pair for the browser to reject.
 * Hence `??` throughout; `||` would swallow it.
 */
export const API_BASE = (
  runtime.apiBase ??
  import.meta.env.VITE_API_BASE ??
  "http://localhost:8000"
).replace(/\/+$/, "");

export const API_PREFIX =
  runtime.apiPrefix ?? import.meta.env.VITE_API_PREFIX ?? "/api/v1";

/**
 * Added to every request's own timeout budget.
 *
 * The Ren'Py comment is load-bearing and applies verbatim here: a client timeout
 * shorter than the window the server was asked to hold the connection for turns a
 * slow-but-successful response into an abort, and the loop mistakes success for
 * failure. Every long poll gets WAIT_MS + this.
 */
export const HTTP_MARGIN_MS = 5000;

/**
 * How long GET /steps/batch may hold the connection waiting for the next beat.
 * This is the whole latency-hiding trick (PRD §11): the beat arrives the moment it
 * exists instead of on the next poll tick.
 */
export const WAIT_MS = 4000;

/**
 * Ambient in-world lines shown while a batch is still generating. After this many the
 * client stops pretending and says something honest. Never a spinner.
 */
export const AMBIENT_LIMIT = 6;

/** Give up on a game that has been pending for this many consecutive polls. */
export const MAX_PENDING_POLLS = 90;

/** Consecutive transport failures before the offline screen. */
export const MAX_OFFLINE_STREAK = 3;

/** Steps fetched per batch, then played from memory with no network at all. */
export const BATCH_LIMIT = 20;

/**
 * When the buffer drops to this many steps, a background fetch fires to load the next
 * batch before the player exhausts the current one. This eliminates the 4-second
 * long-poll gap that would otherwise appear between batches.
 */
export const PREFETCH_THRESHOLD = 5;

/**
 * The design canvas, from `gui.init(1280, 720)`. The stage is letterboxed to this
 * ratio and every position below is expressed as a fraction of it, so the layout is
 * the Ren'Py one at any window size.
 */
export const STAGE_WIDTH = 1280;
export const STAGE_HEIGHT = 720;

/**
 * Typewriter reveal, characters per second. Ren'Py leaves text speed to preferences;
 * this client has no preferences screen, so it picks one and lets a click complete
 * the line — the behaviour a player actually uses.
 */
export const TEXT_SPEED_CPS = 45;
