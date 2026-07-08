"""Salon maxsus funksiyalar — BOSQICH 23

Revision ID: n9o0p1q2r3s4
Revises: m8n9o0p1q2r3
Create Date: 2026-06-17

Yangi jadvallar:
  - staff_schedules  : Usta haftalik ish jadvali
  - client_photos    : Mijoz oldin/keyin fotosuratlari
"""

from alembic import op
import sqlalchemy as sa

revision     = 'n9o0p1q2r3s4'
down_revision = 'm8n9o0p1q2r3'
branch_labels = None
depends_on    = None


def upgrade():
    op.create_table(
        "staff_schedules",
        sa.Column("id",          sa.Integer(),    primary_key=True),
        sa.Column("tenant_id",   sa.Integer(),    sa.ForeignKey("cafes.id"),      nullable=True,  index=True),
        sa.Column("employee_id", sa.Integer(),    sa.ForeignKey("employees.id"),  nullable=False),
        sa.Column("weekday",     sa.Integer(),    nullable=False),
        sa.Column("work_start",  sa.String(5),    nullable=False, server_default="09:00"),
        sa.Column("work_end",    sa.String(5),    nullable=False, server_default="18:00"),
        sa.Column("is_working",  sa.Boolean(),    nullable=False, server_default=sa.true()),
        sa.Column("created_at",  sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at",  sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.UniqueConstraint("employee_id", "weekday", name="uq_employee_weekday"),
    )

    op.create_table(
        "client_photos",
        sa.Column("id",             sa.Integer(),    primary_key=True),
        sa.Column("tenant_id",      sa.Integer(),    sa.ForeignKey("cafes.id"),       nullable=True,  index=True),
        sa.Column("customer_id",    sa.Integer(),    sa.ForeignKey("customers.id"),   nullable=True),
        sa.Column("appointment_id", sa.Integer(),    sa.ForeignKey("appointments.id"), nullable=True),
        sa.Column("photo_type",     sa.String(10),   nullable=False),
        sa.Column("image_url",      sa.String(500),  nullable=False),
        sa.Column("service_name",   sa.String(100),  nullable=True),
        sa.Column("notes",          sa.Text(),       nullable=True),
        sa.Column("created_by",     sa.Integer(),    sa.ForeignKey("users.id"),       nullable=True),
        sa.Column("created_at",     sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("client_photos")
    op.drop_table("staff_schedules")
