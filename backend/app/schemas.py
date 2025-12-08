from pydantic import BaseModel
from typing import Optional, Literal, List
from datetime import datetime


# ---- Campaign ----

class CampaignBase(BaseModel):
    name: str
    description: Optional[str] = None


class CampaignCreate(CampaignBase):
    pass


class CampaignRead(CampaignBase):
    id: int
    created_at: datetime

    class Config:
        orm_mode = True


# ---- Location ----

class LocationBase(BaseModel):
    name: str
    description: Optional[str] = None


class LocationCreate(LocationBase):
    campaign_id: int


class LocationRead(LocationBase):
    id: int
    campaign_id: int

    class Config:
        orm_mode = True


# ---- Scene ----

SceneType = Literal["social", "investigation", "combat"]
SceneStatus = Literal["pending", "active", "done"]


class SceneBase(BaseModel):
    name: str
    description: Optional[str] = None
    scene_type: SceneType = "social"
    status: SceneStatus = "pending"


class SceneCreate(SceneBase):
    campaign_id: int
    location_id: Optional[int] = None


class SceneRead(SceneBase):
    id: int
    campaign_id: int
    location_id: Optional[int]

    class Config:
        orm_mode = True


# ---- NPC ----

class NPCCreate(BaseModel):
    campaign_id: int
    name: str
    role: Optional[str] = None
    faction: Optional[str] = None
    description: Optional[str] = None


class NPCRead(BaseModel):
    id: int
    campaign_id: int
    name: str
    role: Optional[str]
    faction: Optional[str]
    description: Optional[str]
    status: str

    class Config:
        orm_mode = True


# ---- Encounter ----

EncounterOutcome = Literal["victory", "draw", "defeat", "retreat"]


class EncounterCreate(BaseModel):
    scene_id: int
    layout_scheme: Optional[str] = None
    npc_summary: Optional[str] = None
    objective_victory: Optional[str] = None
    objective_draw: Optional[str] = None
    objective_defeat: Optional[str] = None
    objective_retreat: Optional[str] = None


class EncounterRead(BaseModel):
    id: int
    scene_id: int
    layout_scheme: Optional[str]
    npc_summary: Optional[str]
    objective_victory: Optional[str]
    objective_draw: Optional[str]
    objective_defeat: Optional[str]
    objective_retreat: Optional[str]
    status: str
    outcome: Optional[str]

    class Config:
        orm_mode = True


class EncounterResolve(BaseModel):
    outcome: EncounterOutcome
    defeated_npc_ids: Optional[List[int]] = None
    gm_notes: Optional[str] = None


class EncounterGenerateRequest(BaseModel):
    difficulty: Optional[str] = "medium"   # easy/medium/hard/deadly - как подсказка модели
    theme: Optional[str] = None           # "засада культистов в доках"
    max_enemies: Optional[int] = 8        # потолок по количеству врагов


# ---- Check ----

CheckResult = Literal["success", "failure"]


class CheckCreate(BaseModel):
    scene_id: int
    actor_name: str
    check_type: str
    difficulty_label: Optional[str] = None
    difficulty_value: Optional[int] = None
    result: CheckResult
    degrees: Optional[int] = None
    note: Optional[str] = None


class CheckRead(BaseModel):
    id: int
    scene_id: int
    actor_name: str
    check_type: str
    difficulty_label: Optional[str]
    difficulty_value: Optional[int]
    result: str
    degrees: Optional[int]
    note: Optional[str]

    class Config:
        orm_mode = True


# ---- Log ----

class LogEntryRead(BaseModel):
    id: int
    campaign_id: int
    scene_id: Optional[int]
    entry_type: str
    text: str
    created_at: datetime

    class Config:
        orm_mode = True


# ---- Auto Adventure ----

class AutoAdventureRequest(BaseModel):
    num_players: int
    exp_level: int  # XP на персонажа (просто масштаб сложности)
    world: Optional[str] = None  # "hive_world", "forge_world", "feudal_world" и т.п.
    random_world: bool = True    # если True и world не задан — мир выбирает модель сама


class AutoAdventureSummary(BaseModel):
    campaign: CampaignRead
    locations: List[LocationRead]
    scenes: List[SceneRead]

