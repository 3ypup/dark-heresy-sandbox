from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
)
from sqlalchemy.orm import relationship

from .database import Base


class SceneType(str, PyEnum):
    INTRO = "intro"
    SOCIAL = "social"
    INVESTIGATION = "investigation"
    COMBAT = "combat"
    FINAL = "final"


class LogEntryType(str, PyEnum):
    INFO = "info"
    CHECK = "check"
    CHOICE = "choice"
    COMBAT_RESULT = "combat_result"


class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    world = Column(String(255), nullable=True)
    premise = Column(Text, nullable=True)      # краткое описание кампании
    intro_text = Column(Text, nullable=True)   # вступление

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    locations = relationship("Location", back_populates="campaign", cascade="all, delete-orphan")
    scenes = relationship("Scene", back_populates="campaign", cascade="all, delete-orphan")
    npcs = relationship("NPC", back_populates="campaign", cascade="all, delete-orphan")
    logs = relationship("LogEntry", back_populates="campaign", cascade="all, delete-orphan")
    state = relationship("CampaignState", back_populates="campaign", uselist=False, cascade="all, delete-orphan")


class Location(Base):
    __tablename__ = "locations"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    ascii_map = Column(Text, nullable=True)  # ASCII-схема локации

    campaign = relationship("Campaign", back_populates="locations")
    scenes = relationship("Scene", back_populates="location")


class NPC(Base):
    __tablename__ = "npcs"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=False)
    name = Column(String(255), nullable=False)
    role = Column(String(255), nullable=True)         # кто он по отношению к кампании
    faction = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)               # подсказки мастеру

    campaign = relationship("Campaign", back_populates="npcs")


class Scene(Base):
    __tablename__ = "scenes"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=False)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)

    name = Column(String(255), nullable=False)
    scene_type = Column(String(32), nullable=False, default=SceneType.SOCIAL.value)
    order_index = Column(Integer, nullable=True)  # для сортировки по умолчанию

    # то, что мастер рассказывает игрокам
    player_text = Column(Text, nullable=True)
    # заметки мастеру (секреты, крючки, варианты развития)
    gm_notes = Column(Text, nullable=True)
    # JSON со списком диалогов (как текст)
    dialogues_json = Column(Text, nullable=True)

    campaign = relationship("Campaign", back_populates="scenes")
    location = relationship("Location", back_populates="scenes")
    encounter = relationship("Encounter", back_populates="scene", uselist=False, cascade="all, delete-orphan")

    # ВАЖНО: явно указываем, какие foreign keys использовать
    choices = relationship(
        "SceneChoice",
        back_populates="scene",
        cascade="all, delete-orphan",
        foreign_keys="SceneChoice.scene_id",
    )


class SceneChoice(Base):
    __tablename__ = "scene_choices"

    id = Column(Integer, primary_key=True, index=True)
    scene_id = Column(Integer, ForeignKey("scenes.id"), nullable=False)
    label = Column(String(255), nullable=False)       # короткое название выбора
    description = Column(Text, nullable=True)         # подробность
    result_hint = Column(Text, nullable=True)         # к чему ориентировочно приведет
    to_scene_id = Column(Integer, ForeignKey("scenes.id"), nullable=True)
    condition_json = Column(Text, nullable=True)      # на будущее: условия (по флагам)

    # Здесь тоже указываем foreign_keys, чтобы убрать двусмысленность
    scene = relationship(
        "Scene",
        back_populates="choices",
        foreign_keys=[scene_id],
    )
    to_scene = relationship(
        "Scene",
        foreign_keys=[to_scene_id],
    )


class Encounter(Base):
    __tablename__ = "encounters"

    id = Column(Integer, primary_key=True, index=True)
    scene_id = Column(Integer, ForeignKey("scenes.id"), nullable=False)

    objectives = Column(Text, nullable=True)   # условия победы/ничьей/поражения
    npc_summary = Column(Text, nullable=True)  # краткое описание врагов / сил
    victory_text = Column(Text, nullable=True)
    defeat_text = Column(Text, nullable=True)
    escape_text = Column(Text, nullable=True)

    scene = relationship("Scene", back_populates="encounter")


class CampaignState(Base):
    __tablename__ = "campaign_state"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), unique=True, nullable=False)
    current_scene_id = Column(Integer, ForeignKey("scenes.id"), nullable=True)
    flags_json = Column(Text, nullable=True)  # {"писарь_помог": true, ...}

    campaign = relationship("Campaign", back_populates="state")
    current_scene = relationship("Scene")


class LogEntry(Base):
    __tablename__ = "log_entries"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    entry_type = Column(String(32), nullable=False, default=LogEntryType.INFO.value)
    content = Column(Text, nullable=False)
    metadata_json = Column(Text, nullable=True)

    campaign = relationship("Campaign", back_populates="logs")
