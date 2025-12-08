from fastapi import FastAPI, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from typing import List

from .database import Base, engine, SessionLocal
from . import models, schemas
from .ollama_client import generate_json, OllamaError

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Dark Heresy Sandbox API")


# ---- зависимость для БД ----

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---- healthcheck ----

@app.get("/health")
def health():
    return {"status": "ok"}


# ---- Campaigns ----

@app.post("/campaigns", response_model=schemas.CampaignRead)
def create_campaign(campaign: schemas.CampaignCreate, db: Session = Depends(get_db)):
    db_obj = models.Campaign(name=campaign.name, description=campaign.description)
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj


@app.get("/campaigns", response_model=List[schemas.CampaignRead])
def list_campaigns(db: Session = Depends(get_db)):
    return db.query(models.Campaign).all()


@app.get("/campaigns/{campaign_id}", response_model=schemas.CampaignRead)
def get_campaign(campaign_id: int, db: Session = Depends(get_db)):
    campaign = db.query(models.Campaign).get(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


# ---- Locations ----

@app.post("/locations", response_model=schemas.LocationRead)
def create_location(location: schemas.LocationCreate, db: Session = Depends(get_db)):
    campaign = db.query(models.Campaign).get(location.campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    db_obj = models.Location(
        campaign_id=location.campaign_id,
        name=location.name,
        description=location.description,
    )
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj


@app.get("/campaigns/{campaign_id}/locations", response_model=List[schemas.LocationRead])
def list_locations(campaign_id: int, db: Session = Depends(get_db)):
    return db.query(models.Location).filter_by(campaign_id=campaign_id).all()


# ---- Scenes ----

@app.post("/scenes", response_model=schemas.SceneRead)
def create_scene(scene: schemas.SceneCreate, db: Session = Depends(get_db)):
    campaign = db.query(models.Campaign).get(scene.campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if scene.location_id:
        loc = db.query(models.Location).get(scene.location_id)
        if not loc or loc.campaign_id != scene.campaign_id:
            raise HTTPException(status_code=400, detail="Invalid location for this campaign")

    db_obj = models.Scene(
        campaign_id=scene.campaign_id,
        location_id=scene.location_id,
        name=scene.name,
        description=scene.description,
        scene_type=scene.scene_type,
        status=scene.status,
    )
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj


@app.get("/campaigns/{campaign_id}/scenes", response_model=List[schemas.SceneRead])
def list_scenes(campaign_id: int, db: Session = Depends(get_db)):
    return db.query(models.Scene).filter_by(campaign_id=campaign_id).all()


# ---- NPC ----

@app.post("/npcs", response_model=schemas.NPCRead)
def create_npc(npc: schemas.NPCCreate, db: Session = Depends(get_db)):
    campaign = db.query(models.Campaign).get(npc.campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    db_obj = models.NPC(
        campaign_id=npc.campaign_id,
        name=npc.name,
        role=npc.role,
        faction=npc.faction,
        description=npc.description,
    )
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj


@app.get("/campaigns/{campaign_id}/npcs", response_model=List[schemas.NPCRead])
def list_npcs(campaign_id: int, db: Session = Depends(get_db)):
    return db.query(models.NPC).filter_by(campaign_id=campaign_id).all()


# ---- Encounters ----

@app.post("/encounters", response_model=schemas.EncounterRead)
def create_encounter(enc: schemas.EncounterCreate, db: Session = Depends(get_db)):
    scene = db.query(models.Scene).get(enc.scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")

    if scene.scene_type != "combat":
        raise HTTPException(status_code=400, detail="Encounter can only be attached to combat scene")

    db_obj = models.Encounter(
        scene_id=enc.scene_id,
        layout_scheme=enc.layout_scheme,
        npc_summary=enc.npc_summary,
        objective_victory=enc.objective_victory,
        objective_draw=enc.objective_draw,
        objective_defeat=enc.objective_defeat,
        objective_retreat=enc.objective_retreat,
    )
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj


@app.get("/scenes/{scene_id}/encounter", response_model=schemas.EncounterRead)
def get_encounter_for_scene(scene_id: int, db: Session = Depends(get_db)):
    scene = db.query(models.Scene).get(scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    if not scene.encounter:
        raise HTTPException(status_code=404, detail="Encounter not found")
    return scene.encounter


@app.post("/encounters/{encounter_id}/resolve")
def resolve_encounter(
    encounter_id: int,
    payload: schemas.EncounterResolve,
    db: Session = Depends(get_db),
):
    enc = db.query(models.Encounter).get(encounter_id)
    if not enc:
        raise HTTPException(status_code=404, detail="Encounter not found")

    scene = enc.scene
    campaign = scene.campaign

    enc.status = "resolved"
    enc.outcome = payload.outcome

    # помечаем убитых NPC
    if payload.defeated_npc_ids:
        npcs = (
            db.query(models.NPC)
            .filter(models.NPC.id.in_(payload.defeated_npc_ids))
            .all()
        )
        for n in npcs:
            n.status = "dead"

    # выбираем текст-указание по исходу
    if payload.outcome == "victory":
        text = enc.objective_victory or "Вы одержали победу. Решите, куда двигаться дальше."
    elif payload.outcome == "draw":
        text = enc.objective_draw or "Бой закончился ничьей. Ситуация остаётся напряжённой."
    elif payload.outcome == "defeat":
        text = enc.objective_defeat or "Вы потерпели поражение. Подумайте, как вы сможете выбраться из этого."
    else:  # retreat
        text = enc.objective_retreat or "Вы отступили. Нужно найти обходной путь или перегруппироваться."

    if payload.gm_notes:
        text += f"\n\nЗаметки ведущего: {payload.gm_notes}"

    log = models.LogEntry(
        campaign_id=campaign.id,
        scene_id=scene.id,
        entry_type="encounter",
        text=text,
    )
    db.add(log)
    db.commit()

    return {"message": text}


# ---- Генерация Encounter через Ollama ----

@app.post("/scenes/{scene_id}/generate_encounter", response_model=schemas.EncounterRead)
async def generate_encounter_for_scene(
    scene_id: int,
    payload: schemas.EncounterGenerateRequest,
    db: Session = Depends(get_db),
):
    scene = db.query(models.Scene).get(scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")

    if scene.scene_type != "combat":
        raise HTTPException(status_code=400, detail="Encounter can only be generated for combat scenes")

    campaign = scene.campaign
    location = scene.location

    world_context = []
    if campaign.description:
        world_context.append(f"Описание кампании: {campaign.description}")
    if location:
        world_context.append(f"Локация: {location.name}. {location.description or ''}")

    world_text = "\n".join(world_context) if world_context else "Обычный мир-улей Империума."

    difficulty = payload.difficulty or "medium"
    max_enemies = payload.max_enemies or 8
    theme_text = payload.theme or "боестолкновение аколитов Инквизиции с врагами Императора"

    system_prompt = (
        "Ты — помощник ведущего для настольной ролевой игры Dark Heresy во вселенной Warhammer 40,000. "
        "Генерируй только сцены в духе grimdark, Инквизиции, ереси, культа Императора. "
        "НЕ используй современный сленг, телефоны, интернет и т.п. "
        "Ответ ДОЛЖЕН быть валидным JSON без комментариев и текста вне JSON."
    )

    user_prompt = f"""
Сейчас идёт подготовка боевой сцены (Encounter) для аколитов Инквизиции.

Контекст мира и ситуации:
{world_text}

Тема столкновения:
{theme_text}

Сложность: {difficulty}
Максимальное количество врагов, которые должны участвовать: {max_enemies}.

Нужно сгенерировать объект JSON со следующими полями:
- "layout_scheme": строка. Краткое, но насыщенное описание планировки локации
  (геометрия помещения/территории, уровни, укрытия, опасные зоны), а также
  расположения групп врагов. Можно использовать маркеры зон (например: сектор А, Б и т.д.).
- "npc_summary": строка. Краткое описание типов и количества врагов
  (например: "3 культиста с автопистолетами, 1 псайкер-еретик, 2 бойца PDF").
- "objective_victory": строка. Что произойдёт и какие варианты дальнейших действий логичны,
  если аколиты одержат победу.
- "objective_draw": строка. Что произойдёт, если бой закончился ничьей
  (обе стороны тяжело потрёпаны, цели выполнены частично).
- "objective_defeat": строка. Что произойдёт, если аколиты проиграли,
  но не обязательно умерли (плен, ранение, потеря контроля над ситуацией).
- "objective_retreat": строка. Что происходит, если аколиты отступили
  (куда они отступают, какие у них варианты дальше).

Важные требования:
- Используй стилистику вселенной Warhammer 40,000 и игры Dark Heresy.
- Не упоминай правила, кубики или проценты — только сюжет и описание.
- Все поля должны быть строками.
"""

    try:
        data = await generate_json(prompt=user_prompt, system_prompt=system_prompt)
    except OllamaError as e:
        raise HTTPException(status_code=500, detail=f"Ollama error: {e}")

    layout_scheme = data.get("layout_scheme") or "Простая локация без подробного описания."
    npc_summary = data.get("npc_summary") or "Несколько врагов Императора."
    objective_victory = data.get("objective_victory") or "Вы одержали победу и можете двигаться дальше."
    objective_draw = data.get("objective_draw") or "Ничья. Ситуация остаётся напряжённой."
    objective_defeat = data.get("objective_defeat") or "Поражение. Аколиты оказываются в тяжёлом положении."
    objective_retreat = data.get("objective_retreat") or "Отступление. Нужно искать обходной путь или перегруппироваться."

    if scene.encounter:
        enc = scene.encounter
        enc.layout_scheme = layout_scheme
        enc.npc_summary = npc_summary
        enc.objective_victory = objective_victory
        enc.objective_draw = objective_draw
        enc.objective_defeat = objective_defeat
        enc.objective_retreat = objective_retreat
    else:
        enc = models.Encounter(
            scene_id=scene.id,
            layout_scheme=layout_scheme,
            npc_summary=npc_summary,
            objective_victory=objective_victory,
            objective_draw=objective_draw,
            objective_defeat=objective_defeat,
            objective_retreat=objective_retreat,
        )
        db.add(enc)

    log_text = (
        f"Сгенерировано боевое столкновение для сцены '{scene.name}'\n\n"
        f"Планировка:\n{layout_scheme}\n\n"
        f"Враги:\n{npc_summary}\n"
    )
    log = models.LogEntry(
        campaign_id=scene.campaign_id,
        scene_id=scene.id,
        entry_type="system",
        text=log_text,
    )
    db.add(log)

    db.commit()
    db.refresh(enc)
    return enc


# ---- Checks ----

@app.post("/checks", response_model=schemas.CheckRead)
def create_check(check: schemas.CheckCreate, db: Session = Depends(get_db)):
    scene = db.query(models.Scene).get(check.scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")

    db_obj = models.Check(
        scene_id=check.scene_id,
        actor_name=check.actor_name,
        check_type=check.check_type,
        difficulty_label=check.difficulty_label,
        difficulty_value=check.difficulty_value,
        result=check.result,
        degrees=check.degrees,
        note=check.note,
    )
    db.add(db_obj)

    text = f"Проверка: {check.actor_name} — {check.check_type}, результат: {check.result}"
    if check.degrees is not None:
        text += f", степени: {check.degrees}"
    if check.difficulty_label or check.difficulty_value:
        text += f" (сложность: {check.difficulty_label or ''} {check.difficulty_value or ''})"
    if check.note:
        text += f"\nЗаметка: {check.note}"

    log = models.LogEntry(
        campaign_id=scene.campaign_id,
        scene_id=scene.id,
        entry_type="check",
        text=text,
    )
    db.add(log)

    db.commit()
    db.refresh(db_obj)
    return db_obj


# ---- Logs ----

@app.get("/campaigns/{campaign_id}/logs", response_model=List[schemas.LogEntryRead])
def list_logs(campaign_id: int, db: Session = Depends(get_db)):
    return (
        db.query(models.LogEntry)
        .filter_by(campaign_id=campaign_id)
        .order_by(models.LogEntry.created_at.asc())
        .all()
    )


# ---- Auto Adventure (одна кнопка) ----

@app.post("/adventures/autogenerate", response_model=schemas.AutoAdventureSummary)
async def autogenerate_adventure(
    payload: schemas.AutoAdventureRequest,
    db: Session = Depends(get_db),
):
    if payload.random_world and not payload.world:
        world_hint = "выбери подходящий тип мира самостоятельно (улей, агромир, мир-куз forge_world и т.п.)"
    elif payload.world:
        world_hint = f"тип мира: {payload.world}"
    else:
        world_hint = "обычный мир-улей Империума"

    system_prompt = (
        "Ты — генератор приключений для настольной ролевой игры Dark Heresy "
        "во вселенной Warhammer 40,000. "
        "Твоя задача — создавать кампании в стиле grimdark, Инквизиции, ереси, культа Императора. "
        "Не используй современный сленг, телефоны, интернет и т.п. "
        "Ответ ДОЛЖЕН быть валидным JSON строго указанной структуры, "
        "без комментариев и лишнего текста."
    )

    user_prompt = f"""
Создай концепцию кампании Dark Heresy для группы из {payload.num_players} аколитов
с уровнем развития примерно {payload.exp_level} XP (это просто ориентир для масштаба опасностей).

Мир / сеттинг: {world_hint}.

Нужно вернуть JSON со следующей структурой:

{{
  "campaign": {{
    "name": "строка, название кампании в духе 40k",
    "description": "строка, 2-5 абзацев с общим описанием заговора, настроением и ордо Инквизиции",
    "world_type": "строка, тип мира (например, hive_world, forge_world, feudal_world)",
    "tone": "строка, тон кампании (investigative, horror, military, mixed)"
  }},
  "locations": [
    {{
      "name": "строка, название локации (например, Нижние доки Сигма-9)",
      "description": "строка, 1-3 абзаца описания места, его атмосферы и важности"
    }}
  ],
  "scenes": [
    {{
      "name": "строка, название сцены",
      "description": "строка, краткое описание сцены для ведущего (без правил)",
      "scene_type": "строка, одно из: social, investigation, combat",
      "location_index": 0,
      "encounter": {{
        "layout_scheme": "строка, если scene_type == 'combat' — планировка и расположение врагов, иначе можно пустую строку",
        "npc_summary": "строка, краткий перечень врагов в этом бою",
        "objective_victory": "строка, что происходит и какие варианты продолжения при победе аколитов",
        "objective_draw": "строка, что при ничьей",
        "objective_defeat": "строка, что при поражении (плен, бегство, потеря контроля)",
        "objective_retreat": "строка, что при отступлении"
      }}
    }}
  ],
  "npcs": [
    {{
      "name": "строка, имя значимого NPC",
      "role": "строка, роль (информатор, клирик, инквизитор, культ-лидер)",
      "faction": "строка, фракция (Эклезиархия, Адептус Арбитес, PDF, Механикус, культ Хаоса и т.п.)",
      "description": "строка, краткое описание характера и мотивации"
    }}
  ]
}}

Требования:
- Все поля должны присутствовать. Если для сцены нет боя, поле "encounter" всё равно должно быть,
  но можно заполнить его пустыми строками.
- scene_type должен быть только из списка: social, investigation, combat.
- location_index — целое число, индекс в массиве "locations", начиная с 0.
- Не пиши ничего вне JSON.
"""

    try:
        data = await generate_json(prompt=user_prompt, system_prompt=system_prompt)
    except OllamaError as e:
        raise HTTPException(status_code=500, detail=f"Ollama error: {e}")

    campaign_data = data.get("campaign")
    locations_data = data.get("locations", [])
    scenes_data = data.get("scenes", [])
    npcs_data = data.get("npcs", [])

    if not campaign_data:
        raise HTTPException(status_code=500, detail="Ollama response missing 'campaign' object")

    campaign = models.Campaign(
        name=campaign_data.get("name") or "Безымянная кампания",
        description=campaign_data.get("description") or "",
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)

    location_id_map: List[int] = []
    for loc in locations_data:
        loc_obj = models.Location(
            campaign_id=campaign.id,
            name=loc.get("name") or "Безымянная локация",
            description=loc.get("description") or "",
        )
        db.add(loc_obj)
        db.flush()
        location_id_map.append(loc_obj.id)

    created_scenes: List[models.Scene] = []

    for sc in scenes_data:
        loc_index = sc.get("location_index", 0)
        if not isinstance(loc_index, int) or loc_index < 0 or loc_index >= len(location_id_map):
            loc_index = 0
        location_id = location_id_map[loc_index] if location_id_map else None

        scene_type = sc.get("scene_type") or "social"
        if scene_type not in ("social", "investigation", "combat"):
            scene_type = "social"

        scene_obj = models.Scene(
            campaign_id=campaign.id,
            location_id=location_id,
            name=sc.get("name") or "Безымянная сцена",
            description=sc.get("description") or "",
            scene_type=scene_type,
            status="pending",
        )
        db.add(scene_obj)
        db.flush()

        enc_data = sc.get("encounter") or {}
        if scene_type == "combat":
            enc = models.Encounter(
                scene_id=scene_obj.id,
                layout_scheme=enc_data.get("layout_scheme") or "",
                npc_summary=enc_data.get("npc_summary") or "",
                objective_victory=enc_data.get("objective_victory") or "",
                objective_draw=enc_data.get("objective_draw") or "",
                objective_defeat=enc_data.get("objective_defeat") or "",
                objective_retreat=enc_data.get("objective_retreat") or "",
            )
            db.add(enc)

        created_scenes.append(scene_obj)

    for npc in npcs_data:
        npc_obj = models.NPC(
            campaign_id=campaign.id,
            name=npc.get("name") or "Безымянный NPC",
            role=npc.get("role") or None,
            faction=npc.get("faction") or None,
            description=npc.get("description") or "",
        )
        db.add(npc_obj)

    log_text = (
        f"Автоматически сгенерирована кампания '{campaign.name}' "
        f"для {payload.num_players} игроков (XP ~ {payload.exp_level}).\n"
        f"Сцен: {len(created_scenes)}, локаций: {len(location_id_map)}, NPC: {len(npcs_data)}."
    )
    log = models.LogEntry(
        campaign_id=campaign.id,
        scene_id=None,
        entry_type="system",
        text=log_text,
    )
    db.add(log)

    db.commit()

    locations = db.query(models.Location).filter_by(campaign_id=campaign.id).all()
    scenes = db.query(models.Scene).filter_by(campaign_id=campaign.id).all()

    return schemas.AutoAdventureSummary(
        campaign=campaign,
        locations=locations,
        scenes=scenes,
    )


# ---- STATIC UI ----

app.mount(
    "/ui",
    StaticFiles(directory="app/static", html=True),
    name="ui",
)

