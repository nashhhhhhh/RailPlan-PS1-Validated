"""Typed SQLAlchemy 2.0 projections of the SQL-authoritative schema.
Do not call create_all(): use Alembic so triggers, views and constraints are installed.
Foreign keys/defaults/types are mapped; SQL owns composite checks and indexes.
"""
from __future__ import annotations
from datetime import datetime, date
from decimal import Decimal
from typing import Any
from uuid import UUID
from sqlalchemy import Boolean, Date, DateTime, Integer, Numeric, Text, ForeignKey, Computed, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB, TSTZRANGE, Range
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from geoalchemy2 import Geometry
from geoalchemy2.elements import WKBElement

class Base(DeclarativeBase):
    pass

class Operators(Base):
    __tablename__ = "operators"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class Departments(Base):
    __tablename__ = "departments"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    operator_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.operators.id", ondelete="RESTRICT"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class Users(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    department_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.departments.id", ondelete="RESTRICT"), nullable=False)
    auth_subject: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class Roles(Base):
    __tablename__ = "roles"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class UserRoles(Base):
    __tablename__ = "user_roles"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.users.id", ondelete="RESTRICT"), nullable=False)
    role_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.roles.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class Networks(Base):
    __tablename__ = "networks"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    operator_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.operators.id", ondelete="RESTRICT"), nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class Lines(Base):
    __tablename__ = "lines"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    network_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.networks.id", ondelete="RESTRICT"), nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class Stations(Base):
    __tablename__ = "stations"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    network_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.networks.id", ondelete="RESTRICT"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    geom: Mapped[WKBElement | None] = mapped_column(Geometry("POINT", srid=4326, spatial_index=False), nullable=True)
    geometry_source: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'unverified'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class LineStations(Base):
    __tablename__ = "line_stations"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    line_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.lines.id", ondelete="RESTRICT"), nullable=False)
    station_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.stations.id", ondelete="RESTRICT"), nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class TrackSectors(Base):
    __tablename__ = "track_sectors"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    line_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.lines.id", ondelete="RESTRICT"), nullable=False)
    from_station_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.stations.id", ondelete="RESTRICT"), nullable=False)
    to_station_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.stations.id", ondelete="RESTRICT"), nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    geom: Mapped[WKBElement | None] = mapped_column(Geometry("MULTILINESTRING", srid=4326, spatial_index=False), nullable=True)
    geometry_source: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'unverified'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class Tracks(Base):
    __tablename__ = "tracks"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    sector_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.track_sectors.id", ondelete="RESTRICT"), nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    direction: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class TrackSegments(Base):
    __tablename__ = "track_segments"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    track_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.tracks.id", ondelete="RESTRICT"), nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    geom: Mapped[WKBElement | None] = mapped_column(Geometry("LINESTRING", srid=4326, spatial_index=False), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class Workzones(Base):
    __tablename__ = "workzones"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    network_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.networks.id", ondelete="RESTRICT"), nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    geom: Mapped[WKBElement | None] = mapped_column(Geometry("MULTIPOLYGON", srid=4326, spatial_index=False), nullable=True)
    geometry_source: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'unverified'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class WorkzoneSectors(Base):
    __tablename__ = "workzone_sectors"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    workzone_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.workzones.id", ondelete="RESTRICT"), nullable=False)
    sector_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.track_sectors.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class IsolationZones(Base):
    __tablename__ = "isolation_zones"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    network_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.networks.id", ondelete="RESTRICT"), nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    geom: Mapped[WKBElement | None] = mapped_column(Geometry("MULTIPOLYGON", srid=4326, spatial_index=False), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class IsolationZoneSectors(Base):
    __tablename__ = "isolation_zone_sectors"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    isolation_zone_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.isolation_zones.id", ondelete="RESTRICT"), nullable=False)
    sector_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.track_sectors.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class EngineeringWindows(Base):
    __tablename__ = "engineering_windows"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    line_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.lines.id", ondelete="RESTRICT"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    service_date: Mapped[date] = mapped_column(Date, nullable=False)
    timezone: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'Asia/Singapore'"))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period: Mapped[Range[datetime]] = mapped_column(TSTZRANGE, Computed("tstzrange(starts_at, ends_at, '[)')", persisted=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class WindowPeriods(Base):
    __tablename__ = "window_periods"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    window_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.engineering_windows.id", ondelete="RESTRICT"), nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period: Mapped[Range[datetime]] = mapped_column(TSTZRANGE, Computed("tstzrange(starts_at, ends_at, '[)')", persisted=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class SectorAvailability(Base):
    __tablename__ = "sector_availability"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    window_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.engineering_windows.id", ondelete="RESTRICT"), nullable=False)
    sector_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.track_sectors.id", ondelete="RESTRICT"), nullable=False)
    available: Mapped[bool] = mapped_column(Boolean, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period: Mapped[Range[datetime]] = mapped_column(TSTZRANGE, Computed("tstzrange(starts_at, ends_at, '[)')", persisted=True), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class WorkTypes(Base):
    __tablename__ = "work_types"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class RequestStatuses(Base):
    __tablename__ = "request_statuses"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    code: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class MaintenanceRequests(Base):
    __tablename__ = "maintenance_requests"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    request_code: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("('MR-' || lpad(nextval('request_code_seq')::text,6,'0'))"))
    window_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.engineering_windows.id", ondelete="RESTRICT"), nullable=False)
    department_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.departments.id", ondelete="RESTRICT"), nullable=False)
    work_type_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.work_types.id", ondelete="RESTRICT"), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    priority: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'normal'"))
    status_code: Mapped[str] = mapped_column(Text, ForeignKey("railplan.request_statuses.code", ondelete="RESTRICT"), nullable=False, server_default=text("'draft'"))
    requested_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    requested_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    requested_period: Mapped[Range[datetime]] = mapped_column(TSTZRANGE, Computed("tstzrange(requested_start,requested_end,'[)')", persisted=True), nullable=False)
    min_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    max_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    earliest_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    latest_finish: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    flexibility: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'flexible'"))
    operational_impact: Mapped[str | None] = mapped_column(Text, nullable=True)
    safety_classification: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'unreviewed'"))
    created_by: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.users.id", ondelete="RESTRICT"), nullable=False)
    submitted_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.users.id", ondelete="RESTRICT"), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class RequestSectors(Base):
    __tablename__ = "request_sectors"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    request_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.maintenance_requests.id", ondelete="RESTRICT"), nullable=False)
    sector_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.track_sectors.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class RequestWorkzones(Base):
    __tablename__ = "request_workzones"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    request_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.maintenance_requests.id", ondelete="RESTRICT"), nullable=False)
    workzone_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.workzones.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class Teams(Base):
    __tablename__ = "teams"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    department_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.departments.id", ondelete="RESTRICT"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class Engineers(Base):
    __tablename__ = "engineers"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    department_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.departments.id", ondelete="RESTRICT"), nullable=False)
    user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.users.id", ondelete="RESTRICT"), nullable=True)
    employee_code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class Skills(Base):
    __tablename__ = "skills"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class EngineerSkills(Base):
    __tablename__ = "engineer_skills"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    engineer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.engineers.id", ondelete="RESTRICT"), nullable=False)
    skill_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.skills.id", ondelete="RESTRICT"), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period: Mapped[Range[datetime]] = mapped_column(TSTZRANGE, Computed("tstzrange(starts_at, ends_at, '[)')", persisted=True), nullable=False)
    certificate_reference: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class TeamMemberships(Base):
    __tablename__ = "team_memberships"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    team_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.teams.id", ondelete="RESTRICT"), nullable=False)
    engineer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.engineers.id", ondelete="RESTRICT"), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period: Mapped[Range[datetime]] = mapped_column(TSTZRANGE, Computed("tstzrange(starts_at, ends_at, '[)')", persisted=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class Shifts(Base):
    __tablename__ = "shifts"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    department_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.departments.id", ondelete="RESTRICT"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period: Mapped[Range[datetime]] = mapped_column(TSTZRANGE, Computed("tstzrange(starts_at, ends_at, '[)')", persisted=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class EngineerAvailability(Base):
    __tablename__ = "engineer_availability"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    engineer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.engineers.id", ondelete="RESTRICT"), nullable=False)
    shift_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.shifts.id", ondelete="RESTRICT"), nullable=True)
    available: Mapped[bool] = mapped_column(Boolean, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period: Mapped[Range[datetime]] = mapped_column(TSTZRANGE, Computed("tstzrange(starts_at, ends_at, '[)')", persisted=True), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class TeamAvailability(Base):
    __tablename__ = "team_availability"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    team_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.teams.id", ondelete="RESTRICT"), nullable=False)
    shift_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.shifts.id", ondelete="RESTRICT"), nullable=True)
    available: Mapped[bool] = mapped_column(Boolean, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period: Mapped[Range[datetime]] = mapped_column(TSTZRANGE, Computed("tstzrange(starts_at, ends_at, '[)')", persisted=True), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class RequestTeams(Base):
    __tablename__ = "request_teams"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    request_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.maintenance_requests.id", ondelete="RESTRICT"), nullable=False)
    team_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.teams.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class RequestEngineers(Base):
    __tablename__ = "request_engineers"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    request_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.maintenance_requests.id", ondelete="RESTRICT"), nullable=False)
    engineer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.engineers.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class RequestSkills(Base):
    __tablename__ = "request_skills"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    request_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.maintenance_requests.id", ondelete="RESTRICT"), nullable=False)
    skill_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.skills.id", ondelete="RESTRICT"), nullable=False)
    required_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1 CHECK(required_count > 0)"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class EquipmentTypes(Base):
    __tablename__ = "equipment_types"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class EquipmentAssets(Base):
    __tablename__ = "equipment_assets"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    department_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.departments.id", ondelete="RESTRICT"), nullable=False)
    type_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.equipment_types.id", ondelete="RESTRICT"), nullable=False)
    asset_code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class EquipmentCapabilities(Base):
    __tablename__ = "equipment_capabilities"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class AssetCapabilities(Base):
    __tablename__ = "asset_capabilities"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    asset_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.equipment_assets.id", ondelete="RESTRICT"), nullable=False)
    capability_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.equipment_capabilities.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class EquipmentAvailability(Base):
    __tablename__ = "equipment_availability"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    asset_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.equipment_assets.id", ondelete="RESTRICT"), nullable=False)
    available: Mapped[bool] = mapped_column(Boolean, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period: Mapped[Range[datetime]] = mapped_column(TSTZRANGE, Computed("tstzrange(starts_at, ends_at, '[)')", persisted=True), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class RequestEquipmentRequirements(Base):
    __tablename__ = "request_equipment_requirements"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    request_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.maintenance_requests.id", ondelete="RESTRICT"), nullable=False)
    type_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.equipment_types.id", ondelete="RESTRICT"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1 CHECK(quantity > 0)"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class RequestEquipmentAssets(Base):
    __tablename__ = "request_equipment_assets"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    request_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.maintenance_requests.id", ondelete="RESTRICT"), nullable=False)
    asset_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.equipment_assets.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class RequestCapabilities(Base):
    __tablename__ = "request_capabilities"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    request_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.maintenance_requests.id", ondelete="RESTRICT"), nullable=False)
    capability_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.equipment_capabilities.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class RequestIsolations(Base):
    __tablename__ = "request_isolations"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    request_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.maintenance_requests.id", ondelete="RESTRICT"), nullable=False)
    isolation_zone_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.isolation_zones.id", ondelete="RESTRICT"), nullable=False)
    required_state: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class CompatibilityRules(Base):
    __tablename__ = "compatibility_rules"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    first_work_type_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.work_types.id", ondelete="RESTRICT"), nullable=False)
    second_work_type_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.work_types.id", ondelete="RESTRICT"), nullable=False)
    compatible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    minimum_separation_metres: Mapped[Decimal] = mapped_column(Numeric, nullable=False, server_default=text("0 CHECK(minimum_separation_metres >= 0)"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class RuleDefinitions(Base):
    __tablename__ = "rule_definitions"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    code: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    blocking: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'"))
    authority_reference: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'SYNTHETIC - not an operational rule'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class DependencyTypes(Base):
    __tablename__ = "dependency_types"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class RequestDependencies(Base):
    __tablename__ = "request_dependencies"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    predecessor_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.maintenance_requests.id", ondelete="RESTRICT"), nullable=False)
    successor_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.maintenance_requests.id", ondelete="RESTRICT"), nullable=False)
    dependency_type_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.dependency_types.id", ondelete="RESTRICT"), nullable=False)
    lag_minutes: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0 CHECK(lag_minutes >= 0)"))
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class TravelTimes(Base):
    __tablename__ = "travel_times"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    from_sector_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.track_sectors.id", ondelete="RESTRICT"), nullable=False)
    to_sector_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.track_sectors.id", ondelete="RESTRICT"), nullable=False)
    minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class OptimisationObjectives(Base):
    __tablename__ = "optimisation_objectives"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    weights: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class OptimisationRuns(Base):
    __tablename__ = "optimisation_runs"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    window_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.engineering_windows.id", ondelete="RESTRICT"), nullable=False)
    objective_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.optimisation_objectives.id", ondelete="RESTRICT"), nullable=False)
    requested_by: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.users.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'queued'"))
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'"))
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    solver_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    runtime_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class Scenarios(Base):
    __tablename__ = "scenarios"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.optimisation_runs.id", ondelete="RESTRICT"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'draft'"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    validation_status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'unvalidated'"))
    provenance: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'solver'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class ScenarioAssignments(Base):
    __tablename__ = "scenario_assignments"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    scenario_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.scenarios.id", ondelete="RESTRICT"), nullable=False)
    request_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.maintenance_requests.id", ondelete="RESTRICT"), nullable=False)
    request_version: Mapped[int] = mapped_column(Integer, nullable=False)
    original_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    original_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period: Mapped[Range[datetime]] = mapped_column(TSTZRANGE, Computed("tstzrange(starts_at, ends_at, '[)')", persisted=True), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    feasible: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    locked: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class ScenarioSectors(Base):
    __tablename__ = "scenario_sectors"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    assignment_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.scenario_assignments.id", ondelete="RESTRICT"), nullable=False)
    sector_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.track_sectors.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class ScenarioTeams(Base):
    __tablename__ = "scenario_teams"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    assignment_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.scenario_assignments.id", ondelete="RESTRICT"), nullable=False)
    team_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.teams.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class ScenarioEngineers(Base):
    __tablename__ = "scenario_engineers"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    assignment_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.scenario_assignments.id", ondelete="RESTRICT"), nullable=False)
    engineer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.engineers.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class ScenarioEquipment(Base):
    __tablename__ = "scenario_equipment"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    assignment_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.scenario_assignments.id", ondelete="RESTRICT"), nullable=False)
    asset_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.equipment_assets.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class Possessions(Base):
    __tablename__ = "possessions"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    scenario_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.scenarios.id", ondelete="RESTRICT"), nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    exclusive: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period: Mapped[Range[datetime]] = mapped_column(TSTZRANGE, Computed("tstzrange(starts_at, ends_at, '[)')", persisted=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class PossessionSectors(Base):
    __tablename__ = "possession_sectors"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    possession_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.possessions.id", ondelete="RESTRICT"), nullable=False)
    sector_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.track_sectors.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class PossessionAssignments(Base):
    __tablename__ = "possession_assignments"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    possession_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.possessions.id", ondelete="RESTRICT"), nullable=False)
    assignment_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.scenario_assignments.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class IsolationPlans(Base):
    __tablename__ = "isolation_plans"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    scenario_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.scenarios.id", ondelete="RESTRICT"), nullable=False)
    isolation_zone_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.isolation_zones.id", ondelete="RESTRICT"), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period: Mapped[Range[datetime]] = mapped_column(TSTZRANGE, Computed("tstzrange(starts_at, ends_at, '[)')", persisted=True), nullable=False)
    restored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    handback_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class ScenarioMetrics(Base):
    __tablename__ = "scenario_metrics"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    scenario_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.scenarios.id", ondelete="RESTRICT"), nullable=False)
    conflicts_resolved: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0 CHECK(conflicts_resolved>=0)"))
    unresolved_conflicts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0 CHECK(unresolved_conflicts>=0)"))
    requests_moved: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0 CHECK(requests_moved>=0)"))
    total_movement_minutes: Mapped[Decimal] = mapped_column(Numeric, nullable=False, server_default=text("0 CHECK(total_movement_minutes>=0)"))
    possession_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0 CHECK(possession_count>=0)"))
    disruption_score: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    resource_utilisation: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    unscheduled_requests: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0 CHECK(unscheduled_requests>=0)"))
    solver_status: Mapped[str] = mapped_column(Text, nullable=False)
    solver_runtime_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class ScoringPolicies(Base):
    __tablename__ = "scoring_policies"
    __table_args__ = {"schema": "railplan"}
    operator_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.operators.id", ondelete="RESTRICT"), nullable=True)
    definition: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    code: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    weights: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    is_validated: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class AnalysisRuns(Base):
    __tablename__ = "analysis_runs"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    window_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.engineering_windows.id", ondelete="RESTRICT"), nullable=False)
    scenario_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.scenarios.id", ondelete="RESTRICT"), nullable=True)
    requested_by: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.users.id", ondelete="RESTRICT"), nullable=False)
    scoring_policy_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.scoring_policies.id", ondelete="RESTRICT"), nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'queued'"))
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    rule_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class Conflicts(Base):
    __tablename__ = "conflicts"
    __table_args__ = {"schema": "railplan"}
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    conflict_code: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("('CF-' || lpad(nextval('conflict_code_seq')::text,6,'0'))"))
    analysis_run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.analysis_runs.id", ondelete="RESTRICT"), nullable=False)
    rule_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.rule_definitions.id", ondelete="RESTRICT"), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    risk_score: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    resolution_status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'open'"))
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    detection_method: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'automatic'"))
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class ConflictRequests(Base):
    __tablename__ = "conflict_requests"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    conflict_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.conflicts.id", ondelete="RESTRICT"), nullable=False)
    request_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.maintenance_requests.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class ConflictTeams(Base):
    __tablename__ = "conflict_teams"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    conflict_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.conflicts.id", ondelete="RESTRICT"), nullable=False)
    team_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.teams.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class ConflictEngineers(Base):
    __tablename__ = "conflict_engineers"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    conflict_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.conflicts.id", ondelete="RESTRICT"), nullable=False)
    engineer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.engineers.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class ConflictEquipment(Base):
    __tablename__ = "conflict_equipment"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    conflict_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.conflicts.id", ondelete="RESTRICT"), nullable=False)
    asset_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.equipment_assets.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class ConflictSectors(Base):
    __tablename__ = "conflict_sectors"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    conflict_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.conflicts.id", ondelete="RESTRICT"), nullable=False)
    sector_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.track_sectors.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class ConflictIsolations(Base):
    __tablename__ = "conflict_isolations"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    conflict_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.conflicts.id", ondelete="RESTRICT"), nullable=False)
    isolation_zone_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.isolation_zones.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class ConflictScoreComponents(Base):
    __tablename__ = "conflict_score_components"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    conflict_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.conflicts.id", ondelete="RESTRICT"), nullable=False)
    component: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class RequestLocks(Base):
    __tablename__ = "request_locks"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    request_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.maintenance_requests.id", ondelete="RESTRICT"), nullable=False)
    scenario_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.scenarios.id", ondelete="RESTRICT"), nullable=True)
    locked_by: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.users.id", ondelete="RESTRICT"), nullable=False)
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    locked_values: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    released_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.users.id", ondelete="RESTRICT"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class LockFields(Base):
    __tablename__ = "lock_fields"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    lock_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.request_locks.id", ondelete="RESTRICT"), nullable=False)
    field: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class ApprovalWorkflows(Base):
    __tablename__ = "approval_workflows"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    operator_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.operators.id", ondelete="RESTRICT"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class ApprovalStages(Base):
    __tablename__ = "approval_stages"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    workflow_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.approval_workflows.id", ondelete="RESTRICT"), nullable=False)
    required_role_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.roles.id", ondelete="RESTRICT"), nullable=False)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class ApprovalRequests(Base):
    __tablename__ = "approval_requests"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    scenario_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.scenarios.id", ondelete="RESTRICT"), nullable=False)
    workflow_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.approval_workflows.id", ondelete="RESTRICT"), nullable=False)
    submitted_by: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.users.id", ondelete="RESTRICT"), nullable=False)
    scenario_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'pending_review'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class ApprovalDecisions(Base):
    __tablename__ = "approval_decisions"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    approval_request_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.approval_requests.id", ondelete="RESTRICT"), nullable=False)
    stage_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.approval_stages.id", ondelete="RESTRICT"), nullable=False)
    approver_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.users.id", ondelete="RESTRICT"), nullable=False)
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    comment: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class ScheduleVersions(Base):
    __tablename__ = "schedule_versions"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    window_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.engineering_windows.id", ondelete="RESTRICT"), nullable=False)
    scenario_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.scenarios.id", ondelete="RESTRICT"), nullable=False)
    approval_request_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.approval_requests.id", ondelete="RESTRICT"), nullable=False)
    approved_by: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.users.id", ondelete="RESTRICT"), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class ActiveSchedules(Base):
    __tablename__ = "active_schedules"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    window_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.engineering_windows.id", ondelete="RESTRICT"), nullable=False)
    schedule_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.schedule_versions.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class AuditLogs(Base):
    __tablename__ = "audit_logs"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    actor_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.users.id", ondelete="RESTRICT"), nullable=True)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    before_state: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    after_state: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    correlation_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class ActivityEvents(Base):
    __tablename__ = "activity_events"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    actor_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.users.id", ondelete="RESTRICT"), nullable=True)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    entity_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class EventReads(Base):
    __tablename__ = "event_reads"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    event_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.activity_events.id", ondelete="RESTRICT"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.users.id", ondelete="RESTRICT"), nullable=False)
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class CopilotConversations(Base):
    __tablename__ = "copilot_conversations"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.users.id", ondelete="RESTRICT"), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class CopilotMessages(Base):
    __tablename__ = "copilot_messages"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    conversation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.copilot_conversations.id", ondelete="RESTRICT"), nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class CopilotToolCalls(Base):
    __tablename__ = "copilot_tool_calls"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    message_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.copilot_messages.id", ondelete="RESTRICT"), nullable=False)
    actor_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.users.id", ondelete="RESTRICT"), nullable=False)
    tool_name: Mapped[str] = mapped_column(Text, nullable=False)
    arguments: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    correlation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class CopilotRequestRefs(Base):
    __tablename__ = "copilot_request_refs"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    message_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.copilot_messages.id", ondelete="RESTRICT"), nullable=False)
    request_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.maintenance_requests.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class CopilotConflictRefs(Base):
    __tablename__ = "copilot_conflict_refs"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    message_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.copilot_messages.id", ondelete="RESTRICT"), nullable=False)
    conflict_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.conflicts.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

class CopilotScenarioRefs(Base):
    __tablename__ = "copilot_scenario_refs"
    __table_args__ = {"schema": "railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()"))
    message_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.copilot_messages.id", ondelete="RESTRICT"), nullable=False)
    scenario_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("railplan.scenarios.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
