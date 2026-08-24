## Decalove client configuration.
##
## The backend owns the story; this client owns presentation (PRD §20).

init -10 python:

    ## Where the Decalove API lives. For a web build served from another origin the
    ## API must send CORS headers -- it does, but the browser will still block a
    ## mixed http/https pair, so serve both over the same scheme.
    DECALOVE_API_BASE = "http://localhost:8000"
    DECALOVE_API_PREFIX = "/api/v1"

    ## renpy.fetch defaults to a 5 second timeout. Every long-poll must be given
    ## MORE than it asks the server to hold the connection for, or a slow-but-
    ## successful response arrives as a FetchError and the loop mistakes success
    ## for failure.
    DECALOVE_HTTP_MARGIN = 5.0

    ## How long GET /steps/next is allowed to hold the connection waiting for the
    ## next beat. This is the whole latency-hiding trick (PRD §11): the beat
    ## arrives the moment it exists instead of on the next poll tick.
    DECALOVE_WAIT_MS = 4000

    ## Ambient in-world lines played while a batch is still generating. After this
    ## many, the client stops pretending and says something honest.
    DECALOVE_AMBIENT_LIMIT = 6

    ## Give up on a game that has been pending for this many consecutive polls.
    DECALOVE_MAX_PENDING_POLLS = 30


## Rollback is disabled on purpose.
##
## The server's step cursor only moves forward. If a player rolled back three
## beats and then advanced, the client would ask for "the next step" and receive
## step N+1, not the one they rewound past -- the transcript and the world state
## would quietly disagree from then on. Turning rollback off is the honest fix;
## a rewind feature would need the server to support replay.
define config.rollback_enabled = False

## Skip is likewise meaningless when the next beat may not exist yet.
define config.allow_skipping = False
