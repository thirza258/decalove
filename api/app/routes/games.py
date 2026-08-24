"""Game API — PRD §22.

Every route that could involve a model returns immediately. ``POST /actions`` and
``POST /choices`` answer 202 with a batch id; the story arrives through
``GET /steps/next``, which the client polls (and which can hold the connection briefly so
the first beat arrives the instant it exists).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.dependencies import RuntimeDep
from app.domain.state import PlayerProfile, SaveGame
from app.models.game import (
    AcceptedOut,
    ActionRequest,
    CharacterOut,
    ChoiceRequest,
    GameStateOut,
    IntentOut,
    LocationOut,
    NewGameRequest,
    NextStepOut,
    WorldOut,
)
from app.runtime import Runtime
from app.services.game_service import GameNotFound, InvalidAction

router = APIRouter(tags=["games"])


def _not_found(game_id: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"game {game_id} not found")


@router.get("/worlds", response_model=WorldOut)
async def get_world(runtime: Runtime = RuntimeDep) -> WorldOut:
    """The authored world.

    Fetched once at boot so the client can draw consistent placeholder sprites and
    backgrounds when generated art is unavailable (PRD §26).
    """
    world = runtime.world
    return WorldOut(
        id=world.id,
        title=world.title,
        premise=world.premise,
        tone=world.tone,
        rating=world.rating,
        opening_location=world.opening_location,
        characters=[
            CharacterOut(
                id=character.id,
                name=character.name,
                pronouns=character.pronouns,
                role=character.role,
                expressions=list(character.expressions),
                palette=list(character.palette),
            )
            for character in world.characters
        ],
        locations=[
            LocationOut(
                id=location.id,
                name=location.name,
                description=location.description,
                palette=list(location.palette),
                ambience=list(location.ambience),
            )
            for location in world.locations
        ],
    )


@router.post("/games", response_model=GameStateOut, status_code=status.HTTP_201_CREATED)
async def create_game(request: NewGameRequest, runtime: Runtime = RuntimeDep) -> GameStateOut:
    profile = PlayerProfile(
        name=request.player_name.strip() or "You",
        pronouns=request.pronouns,
        tone=request.tone,
        romance_focus=runtime.world.resolve_character(request.romance_focus),
    )
    session = await runtime.game_service.create_game(profile, request.world_id)
    return runtime.game_service.to_state(session)


@router.get("/games", response_model=list[str])
async def list_games(limit: int = Query(default=50, ge=1, le=200), runtime: Runtime = RuntimeDep) -> list[str]:
    return await runtime.game_service.list_ids(limit)


@router.get("/games/{game_id}", response_model=GameStateOut)
async def get_game(game_id: str, runtime: Runtime = RuntimeDep) -> GameStateOut:
    try:
        session = await runtime.game_service.get(game_id)
    except GameNotFound as exc:
        raise _not_found(game_id) from exc
    return runtime.game_service.to_state(session)


@router.get("/games/{game_id}/save", response_model=SaveGame)
async def get_save(game_id: str, runtime: Runtime = RuntimeDep) -> SaveGame:
    """The PRD §27 save payload, for the client to stash in a Ren'Py save slot."""
    try:
        session = await runtime.game_service.get(game_id)
    except GameNotFound as exc:
        raise _not_found(game_id) from exc
    return runtime.game_service.to_save(session)


@router.delete("/games/{game_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_game(game_id: str, runtime: Runtime = RuntimeDep) -> Response:
    if not await runtime.game_service.delete(game_id):
        raise _not_found(game_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/games/{game_id}/steps/next", response_model=NextStepOut)
async def next_step(
    game_id: str,
    wait_ms: int = Query(default=0, ge=0, le=30000, description="hold the request briefly for the next step"),
    runtime: Runtime = RuntimeDep,
) -> NextStepOut:
    try:
        return await runtime.game_service.next_step(game_id, wait_ms)
    except GameNotFound as exc:
        raise _not_found(game_id) from exc


@router.post("/games/{game_id}/actions", response_model=AcceptedOut, status_code=status.HTTP_202_ACCEPTED)
async def submit_action(
    game_id: str, request: ActionRequest, runtime: Runtime = RuntimeDep
) -> AcceptedOut:
    """Natural-language input — PRD §8 Method B."""
    try:
        batch, intent = await runtime.game_service.submit_action(game_id, request.input)
    except GameNotFound as exc:
        raise _not_found(game_id) from exc
    except InvalidAction as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return AcceptedOut(
        game_id=game_id,
        batch_id=batch.batch_id if batch else None,
        status=batch.status if batch else None,
        intent=IntentOut(
            action=intent.action,
            target=intent.target,
            emotion=intent.emotion,
            risk=intent.risk.value,
            meaningful=intent.meaningful,
        ),
    )


@router.post("/games/{game_id}/choices", response_model=AcceptedOut, status_code=status.HTTP_202_ACCEPTED)
async def submit_choice(
    game_id: str, request: ChoiceRequest, runtime: Runtime = RuntimeDep
) -> AcceptedOut:
    """Traditional visual-novel choice — PRD §8 Method A."""
    try:
        batch, intent = await runtime.game_service.submit_choice(
            game_id, request.step_id, request.choice_id
        )
    except GameNotFound as exc:
        raise _not_found(game_id) from exc
    except InvalidAction as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return AcceptedOut(
        game_id=game_id,
        batch_id=batch.batch_id if batch else None,
        status=batch.status if batch else None,
        intent=IntentOut(
            action=intent.action,
            target=intent.target,
            emotion=intent.emotion,
            risk=intent.risk.value,
            meaningful=intent.meaningful,
        ),
    )
