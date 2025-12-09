from __future__ import annotations

import json
from pathlib import Path
from typing import List

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from .database import Base, engine, get_db
from .models import (
    Campaign,
    Location,
    Scene,
    SceneChoice,
    Encounter,
    NPC,
    CampaignState,
    LogEntry,
    LogEntryType,
    SceneType,
)
from .schemas import (
    CampaignSummary,
    CampaignRead,
    AutoGenRequest,
    AutoGenResponse,
    CampaignStateRead,
    MakeChoiceRequest,
    LogEntryRead,
    CheckRequest,
    SimpleMessageResponse,
    SceneRead,
)
from .ollama_client import generate_json, OllamaError

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Dark Heresy AR GM")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)


# ---------- utils ----------


def campaign_to_read(campaign: Campaign) -> CampaignRead:
    return CampaignRead.from_orm(campaign)


def json_dumps_safe(obj) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return "[]"


# ---------- basic endpoints ----------


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/campaigns", response_model=List[CampaignSummary])
def list_campaigns(db: Session = Depends(get_db)) -> List[CampaignSummary]:
    campaigns = db.query(Campaign).order_by(Campaign.created_at.desc()).all()
    return [CampaignSummary.from_orm(c) for c in campaigns]


@app.get("/campaigns/{campaign_id}", response_model=CampaignRead)
def get_campaign(campaign_id: int, db: Session = Depends(get_db)) -> CampaignRead:
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign_to_read(campaign)


@app.get("/campaigns/{campaign_id}/state", response_model=CampaignStateRead)
def get_campaign_state(campaign_id: int, db: Session = Depends(get_db)) -> CampaignStateRead:
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    state = campaign.state
    if not state:
        return CampaignStateRead(current_scene_id=None, flags_json=None, current_scene=None)

    current_scene = state.current_scene
    scene_read = SceneRead.from_orm(current_scene) if current_scene else None

    return CampaignStateRead(
        current_scene_id=state.current_scene_id,
        flags_json=state.flags_json,
        current_scene=scene_read,
    )


@app.get("/campaigns/{campaign_id}/logs", response_model=List[LogEntryRead])
def get_logs(campaign_id: int, db: Session = Depends(get_db)) -> List[LogEntryRead]:
    logs = (
        db.query(LogEntry)
        .filter(LogEntry.campaign_id == campaign_id)
        .order_by(LogEntry.created_at.asc())
        .all()
    )
    return [LogEntryRead.from_orm(l) for l in logs]


# ---------- autogeneration ----------


SYSTEM_PROMPT = """
Ты мастер по Dark Heresy / Warhammer 40k. 
Твоя задача — сгенерировать одно самодостаточное приключение (кампанию) 
для 3–5 живых игроков, которое играется за 1–2 сессии.

Формат ответа: СТРОГО один JSON-объект со следующими полями:

{
  "campaign": {
    "title": "...",
    "world": "название мира или субсектора",
    "premise": "общее описание кампании",
    "intro_text": "вступительный текст, который мастер читает игрокам в начале"
  },
  "locations": [
    {
      "name": "название локации",
      "description": "описание обстановки",
      "ascii_map": "ASCII-карта, несколько строк, где # — стены, . — пол, D — двери, P — старт отряда, E — враги, N — NPC, X — цель. Строки разделены символом \\n"
    }
  ],
  "npcs": [
    {
      "name": "имя NPC",
      "role": "роль в сюжете",
      "faction": "фракция (Инквизиция, Адептус Механикус, культ ереси и т.п.)",
      "description": "как выглядит, что хочет",
      "notes": "секреты и подсказки мастеру"
    }
  ],
  "scenes": [
    {
      "name": "название сцены",
      "scene_type": "intro | social | investigation | combat | final",
      "location_index": 0,
      "order_index": 0,
      "player_text": "что мастер рассказывает игрокам",
      "gm_notes": "секретные заметки мастеру",
      "dialogues": [
        { "speaker": "NPC или Игроки", "text": "пример реплики" }
      ],
      "encounter": {
        "objectives": "кратко цель боя или конфликта",
        "npc_summary": "кто противостоит, без правил Dark Heresy",
        "victory_text": "что происходит при победе игроков",
        "defeat_text": "что происходит при поражении",
        "escape_text": "что происходит если они бегут"
      },
      "choices": [
        {
          "label": "короткое название выбора",
          "description": "что игроки делают",
          "result_hint": "к чему примерно ведет",
          "to_scene_index": 2   // индекс сцены в этом массиве (или null, если сцена финальная)
        }
      ]
    }
  ]
}

Требования:

- Приключение должно быть ветвистым: не менее 6–8 сцен, с несколькими развилками.
- Большая часть игры — на столе: социальные сцены, расследование, несколько боевых столкновений.
- Обязательно финальная сцена, где исход зависит от решений игроков.
- Вся атмосфера, имена и описания должны соответствовать сеттингу Warhammer 40 000 и Dark Heresy.
- Не используй правила механики, только художественные описания, понятные живому мастеру.
"""


@app.post("/adventures/autogenerate", response_model=AutoGenResponse)
async def autogenerate_adventure(payload: AutoGenRequest, db: Session = Depends(get_db)) -> AutoGenResponse:
    user_prompt = (
        f"Сгенерируй кампанию по Dark Heresy для {payload.num_players} игроков "
        f"с уровнем опыта примерно {payload.avg_exp}. "
    )
    if payload.world:
        user_prompt += f"Действие происходит в мире/секторе: {payload.world}. "
    user_prompt += "Соблюдай строго указанный JSON-формат."

    try:
        data = await generate_json(prompt=user_prompt, system_prompt=SYSTEM_PROMPT)
    except OllamaError as e:
        raise HTTPException(status_code=500, detail=f"Ollama error: {e}")

    # ----- создаем кампанию и связанные объекты -----

    campaign_data = data.get("campaign") or {}
    campaign = Campaign(
        title=campaign_data.get("title") or "Безымянная кампания",
        world=campaign_data.get("world"),
        premise=campaign_data.get("premise"),
        intro_text=campaign_data.get("intro_text"),
    )
    db.add(campaign)
    db.flush()

    # locations
    locations_data = data.get("locations") or []
    location_ids_by_index = []
    for idx, loc in enumerate(locations_data):
        location = Location(
            campaign_id=campaign.id,
            name=loc.get("name") or f"Локация {idx+1}",
            description=loc.get("description"),
            ascii_map=loc.get("ascii_map"),
        )
        db.add(location)
        db.flush()
        location_ids_by_index.append(location.id)

    # npcs
    for npc in data.get("npcs") or []:
        db.add(
            NPC(
                campaign_id=campaign.id,
                name=npc.get("name") or "Безымянный NPC",
                role=npc.get("role"),
                faction=npc.get("faction"),
                description=npc.get("description"),
                notes=npc.get("notes"),
            )
        )

    db.flush()

    # scenes (первый проход – создаем сцены и энкаунтеры, без связей choices.to_scene_id)
    scenes_data = data.get("scenes") or []
    scene_ids_by_index = []
    choices_temp = []  # (SceneChoice, to_scene_index)

    for idx, s in enumerate(scenes_data):
        loc_index = s.get("location_index")
        if loc_index is not None and 0 <= loc_index < len(location_ids_by_index):
            loc_id = location_ids_by_index[loc_index]
        else:
            loc_id = None

        scene = Scene(
            campaign_id=campaign.id,
            name=s.get("name") or f"Сцена {idx+1}",
            scene_type=s.get("scene_type") or SceneType.SOCIAL.value,
            order_index=s.get("order_index"),
            location_id=loc_id,
            player_text=s.get("player_text"),
            gm_notes=s.get("gm_notes"),
            dialogues_json=json_dumps_safe(s.get("dialogues")) if s.get("dialogues") else None,
        )
        db.add(scene)
        db.flush()
        scene_ids_by_index.append(scene.id)

        enc = s.get("encounter")
        if enc:
            encounter = Encounter(
                scene_id=scene.id,
                objectives=enc.get("objectives"),
                npc_summary=enc.get("npc_summary"),
                victory_text=enc.get("victory_text"),
                defeat_text=enc.get("defeat_text"),
                escape_text=enc.get("escape_text"),
            )
            db.add(encounter)

        for ch in s.get("choices") or []:
            choice = SceneChoice(
                scene_id=scene.id,
                label=ch.get("label") or "Выбор",
                description=ch.get("description"),
                result_hint=ch.get("result_hint"),
            )
            db.add(choice)
            db.flush()
            choices_temp.append((choice, ch.get("to_scene_index")))

    db.flush()

    # второй проход – проставляем to_scene_id
    for choice, to_index in choices_temp:
        if to_index is not None and 0 <= to_index < len(scene_ids_by_index):
            choice.to_scene_id = scene_ids_by_index[to_index]
    db.flush()

    # состояние кампании – текущая сцена = первая intro, иначе первая вообще
    current_scene_id = None
    intro_scene = (
        db.query(Scene)
        .filter(Scene.campaign_id == campaign.id, Scene.scene_type == SceneType.INTRO.value)
        .order_by(Scene.order_index.is_(None), Scene.order_index.asc())
        .first()
    )
    if intro_scene:
        current_scene_id = intro_scene.id
    else:
        any_scene = (
            db.query(Scene)
            .filter(Scene.campaign_id == campaign.id)
            .order_by(Scene.order_index.is_(None), Scene.order_index.asc())
            .first()
        )
        if any_scene:
            current_scene_id = any_scene.id

    state = CampaignState(campaign_id=campaign.id, current_scene_id=current_scene_id, flags_json=None)
    db.add(state)

    db.add(
        LogEntry(
            campaign_id=campaign.id,
            entry_type=LogEntryType.INFO.value,
            content="Кампания автоматически сгенерирована.",
        )
    )

    db.commit()
    db.refresh(campaign)

    return AutoGenResponse(campaign=campaign_to_read(campaign))


# ---------- выборы и проверки ----------


@app.post("/campaigns/{campaign_id}/choose", response_model=CampaignStateRead)
def make_choice(campaign_id: int, payload: MakeChoiceRequest, db: Session = Depends(get_db)) -> CampaignStateRead:
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    state = campaign.state
    if not state:
        raise HTTPException(status_code=400, detail="Campaign state not initialized")

    choice = db.query(SceneChoice).filter(SceneChoice.id == payload.choice_id).first()
    if not choice or choice.scene.campaign_id != campaign.id:
        raise HTTPException(status_code=404, detail="Choice not found for this campaign")

    if state.current_scene_id != choice.scene_id:
        raise HTTPException(status_code=400, detail="Choice does not belong to current scene")

    if choice.to_scene_id:
        state.current_scene_id = choice.to_scene_id

    db.add(
        LogEntry(
            campaign_id=campaign.id,
            entry_type=LogEntryType.CHOICE.value,
            content=f"Выбор: {choice.label}",
        )
    )

    db.commit()
    db.refresh(state)

    return get_campaign_state(campaign_id, db)


@app.post("/campaigns/{campaign_id}/checks", response_model=SimpleMessageResponse)
def register_check(campaign_id: int, payload: CheckRequest, db: Session = Depends(get_db)) -> SimpleMessageResponse:
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    result = "успешна" if payload.success else "провалена"
    degrees = f", степеней: {payload.degrees}" if payload.degrees is not None else ""
    log_text = (
        f"Проверка '{payload.name}' ({payload.skill}, сложность {payload.difficulty}) {result}{degrees}."
    )
    if payload.notes:
        log_text += f" Примечание: {payload.notes}"

    db.add(
        LogEntry(
            campaign_id=campaign.id,
            entry_type=LogEntryType.CHECK.value,
            content=log_text,
        )
    )
    db.commit()

    return SimpleMessageResponse(message="Проверка сохранена")


# ---------- статический UI ----------

static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/ui/", response_class=HTMLResponse)
async def ui_root() -> str:
    html_path = static_dir / "index.html"
    return html_path.read_text(encoding="utf-8")
