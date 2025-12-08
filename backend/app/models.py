from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime

from .database import Base


class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    locations = relationship(
        "Location", back_populates="campaign", cascade="all, delete-orphan"
    )
    scenes = relationship(
        "Scene", back_populates="campaign", cascade="all, delete-orphan"
    )
    npcs = relationship(
        "NPC", back_populates="campaign", cascade="all, delete-orphan"
    )
    logs = relationship(
        "LogEntry", back_populates="campaign", cascade="all, delete-orphan"
    )


class Location(Base):
    __tablename__ = "locations"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=False)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)

    campaign = relationship("Campaign", back_populates="locations")
    scenes = relationship("Scene", back_populates="location")


class Scene(Base):
    __tablename__ = "scenes"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=False)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    scene_type = Column(String(50), default="social")  # social / investigation / combat
    status = Column(String(50), default="pending")     # pending / active / done

    campaign = relationship("Campaign", back_populates="scenes")
    location = relationship("Location", back_populates="scenes")
    encounter = relationship("Encounter", back_populates="scene", uselist=False)
    checks = relationship("Check", back_populates="scene")
    logs = relationship("LogEntry", back_populates="scene")


class NPC(Base):
    __tablename__ = "npcs"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=False)
    name = Column(String(200), nullable=False)
    role = Column(String(200), nullable=True)
    faction = Column(String(200), nullable=True)
    description = Column(Text, nullable=True)
    status = Column(String(50), default="alive")  # alive / dead / missing

    campaign = relationship("Campaign", back_populates="npcs")


class Encounter(Base):
    __tablename__ = "encounters"

    id = Column(Integer, primary_key=True, index=True)
    scene_id = Column(Integer, ForeignKey("scenes.id"), nullable=False)

    # 1.1 – планировка схемой с расположением NPC и геометрией
    layout_scheme = Column(Text, nullable=True)  # текст или условный JSON

    # Краткое текстовое описание групп NPC (например: "3 культиста, 1 псайкер, 2 гвардейца")
    npc_summary = Column(Text, nullable=True)

    # Цели / последствия для разных исходов боя
    objective_victory = Column(Text, nullable=True)
    objective_draw = Column(Text, nullable=True)
    objective_defeat = Column(Text, nullable=True)
    objective_retreat = Column(Text, nullable=True)

    status = Column(String(50), default="pending")  # pending / resolved
    outcome = Column(String(50), nullable=True)     # victory / draw / defeat / retreat

    scene = relationship("Scene", back_populates="encounter")


class Check(Base):
    __tablename__ = "checks"

    id = Column(Integer, primary_key=True, index=True)
    scene_id = Column(Integer, ForeignKey("scenes.id"), nullable=False)
    actor_name = Column(String(200), nullable=False)
    check_type = Column(String(200), nullable=False)  # Intimidate, Charm, Awareness и т.п.
    difficulty_label = Column(String(100), nullable=True)
    difficulty_value = Column(Integer, nullable=True)  # +10, -20 и т.п.
    result = Column(String(50), nullable=False)        # success / failure
    degrees = Column(Integer, nullable=True)           # количество степеней (+/-)
    note = Column(Text, nullable=True)

    scene = relationship("Scene", back_populates="checks")


class LogEntry(Base):
    __tablename__ = "log_entries"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=False)
    scene_id = Column(Integer, ForeignKey("scenes.id"), nullable=True)
    entry_type = Column(String(50), nullable=False)  # system / gm_note / check / encounter
    text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    campaign = relationship("Campaign", back_populates="logs")
    scene = relationship("Scene", back_populates="logs")

