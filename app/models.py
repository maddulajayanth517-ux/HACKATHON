from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, String, Float, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all ORM models."""


class ComplaintStatus(str, Enum):
    """Lifecycle states for a reported pothole complaint."""

    PENDING_VERIFICATION = "PENDING_VERIFICATION"
    ASSIGNED_TO_CONTRACTOR = "ASSIGNED_TO_CONTRACTOR"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"


class Authority(Base):
    """Municipal authority account used to verify and assign complaints."""

    __tablename__ = "authorities"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    department: Mapped[str | None] = mapped_column(String(120), nullable=True)

    complaints: Mapped[list["Complaint"]] = relationship(
        back_populates="authority",
        cascade="all, delete-orphan",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class Contractor(Base):
    """Contractor company account assigned to fix resolved defects."""

    __tablename__ = "contractors"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    company_name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    complaints: Mapped[list["Complaint"]] = relationship(
        back_populates="contractor",
        cascade="all, delete-orphan",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class Complaint(Base):
    """Citizen-submitted pothole report that moves through validation and repair workflow."""

    __tablename__ = "complaints"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    reporter_phone: Mapped[str] = mapped_column(String(30), nullable=False)
    location_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    location_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    manual_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity_level: Mapped[str] = mapped_column(String(50), nullable=False)
    estimated_depth_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[ComplaintStatus] = mapped_column(
        default=ComplaintStatus.PENDING_VERIFICATION,
        nullable=False,
    )

    authority_id: Mapped[int | None] = mapped_column(
        ForeignKey("authorities.id"), nullable=True, index=True
    )
    assigned_contractor_id: Mapped[int | None] = mapped_column(
        ForeignKey("contractors.id"), nullable=True, index=True
    )

    authority: Mapped[Authority | None] = relationship(back_populates="complaints")
    contractor: Mapped[Contractor | None] = relationship(back_populates="complaints")

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
