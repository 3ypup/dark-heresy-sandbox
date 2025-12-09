from datetime import datetime
from typing import List, Optional, Any

from pydantic import BaseModel

from .models import SceneType, LogEntryType


# -------- Basic read/create models --------

class LocationBase(BaseModel):
    name: str
    description: Optional[str] = None
    ascii_map: Optional[str] = None


class LocationCreate(LocationBase):
    pass


class LocationRead(LocationBase):
    id: int

    class Config:
        orm_mode = True


class NPCBase(BaseModel):
    name: str
    role: Optional[str] = None
    faction: Optional[str] = None
    description: Optional[str] = None
    notes: Optional[str] = None


class NPCCreate(NPCBase):
    pass


class NPCRead(NPCBase):
    id: int

    class Config:
        orm_mode = True


class EncounterBase(BaseModel):
    objectives: Optional[str] = None
    npc_summary: Optional[str] = None
    victory_text: Optional[str] = None
    defeat_text: Optional[str] = None
    escape_text: Optional[str] = None


class EncounterCreate(EncounterBase):
    pass


class EncounterRead(EncounterBase):
    id: int

    class Config:
        orm_mode = True


class SceneChoiceBase(BaseModel):
    label: str
    description: Optional[str] = None
    result_hint: Optional[str] = None
    to_scene_id: Optional[int] = None
    condition_json: Optional[str] = None


class SceneChoiceCreate(SceneChoiceBase):
    pass


class SceneChoiceRead(SceneChoiceBase):
    id: int

    class Config:
        orm_mode = True


class SceneBase(BaseModel):
    name: str
    scene_type: str = SceneType.SOCIAL.value
    order_index: Optional[int] = None
    location_id: Optional[int] = None

    player_text: Optional[str] = None
    gm_notes: Optional[str] = None
    dialogues_json: Optional[str] = None


class SceneCreate(SceneBase):
    encounter: Optional[EncounterCreate] = None
    choices: List[SceneChoiceCreate] = []


class SceneRead(SceneBase):
    id: int
    encounter: Optional[EncounterRead] = None
    choices: List[SceneChoiceRead] = []

    class Config:
        orm_mode = True


class CampaignBase(BaseModel):
    title: str
    world: Optional[str] = None
    premise: Optional[str] = None
    intro_text: Optional[str] = None


class CampaignCreate(CampaignBase):
    locations: List[LocationCreate] = []
    scenes: List[SceneCreate] = []
    npcs: List[NPCCreate] = []


class CampaignRead(CampaignBase):
    id: int
    created_at: datetime
    locations: List[LocationRead] = []
    scenes: List[SceneRead] = []
    npcs: List[NPCRead] = []

    class Config:
        orm_mode = True


class CampaignSummary(BaseModel):
    id: int
    title: str
    world: Optional[str] = None
    created_at: datetime

    class Config:
        orm_mode = True


class CampaignStateRead(BaseModel):
    current_scene_id: Optional[int] = None
    flags_json: Optional[str] = None
    current_scene: Optional[SceneRead] = None

    class Config:
        orm_mode = True


class LogEntryRead(BaseModel):
    id: int
    created_at: datetime
    entry_type: str = LogEntryType.INFO.value
    content: str
    metadata_json: Optional[str] = None

    class Config:
        orm_mode = True


# -------- Autogeneration --------

class AutoGenRequest(BaseModel):
    num_players: int
    avg_exp: int
    world: Optional[str] = None


class AutoGenResponse(BaseModel):
    campaign: CampaignRead


# -------- Choice / Checks API --------

class MakeChoiceRequest(BaseModel):
    choice_id: int


class CheckRequest(BaseModel):
    name: str
    skill: str
    difficulty: str
    success: bool
    degrees: Optional[int] = None
    notes: Optional[str] = None


class SimpleMessageResponse(BaseModel):
    message: str
    data: Optional[Any] = None
