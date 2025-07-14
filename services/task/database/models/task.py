import uuid
from datetime import datetime

from sqlalchemy import Enum, Index, String, UUID, text
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.orm import Mapped, mapped_column, relationship

from services.auth.database.connector import SqlAlchemyBase
from services.task.enums import Status


class TaskModel(SqlAlchemyBase):
    __tablename__ = 'tasks'
    __table_args__ = (
        Index('title_index', 'title'),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4, unique=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(nullable=True)
    status: Mapped[Status] = mapped_column(Enum(Status, name='task_status'), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=text("TIMEZONE('utc', now())"), nullable=False)
    author_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    assignee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=True)

    watcher_associations: Mapped[list['Watcher']] = relationship(
        back_populates="task",
        cascade="all, delete-orphan"
    )

    watchers: Mapped[list[uuid.UUID]] = association_proxy(
        "watcher_associations",
        "user_id"
    )

    executor_associations: Mapped[list['Executors']] = relationship(
        back_populates="task",
        cascade="all, delete-orphan"
    )
    executors: Mapped[list[uuid.UUID]] = association_proxy(
        "executor_associations",
        "user_id"
    )
