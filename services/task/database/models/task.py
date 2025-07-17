import uuid
from datetime import datetime

from sqlalchemy import Enum, Index, String, UUID, text
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.orm import Mapped, mapped_column, relationship

from services.task.database.connector import SqlAlchemyBase
from services.task.enums import Status
from services.task.schemas import TaskDB


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

    def to_schema(self) -> TaskDB:
        try:
            return TaskDB(
                id=self.id,
                title=self.title,
                description=self.description,
                status=self.status,
                author_id=self.author_id,
                assignee_id=self.assignee_id,
                watchers=self.watchers,
                executors=self.executors,
                created_at=self.created_at
            )
        except Exception:
            return TaskDB(
                id=self.id,
                title=self.title,
                description=self.description,
                status=self.status,
                author_id=self.author_id,
                assignee_id=self.assignee_id,
                watchers=[],
                executors=[],
                created_at=self.created_at
            )

