import uuid

from sqlalchemy import ForeignKey, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from services.auth.database.connector import SqlAlchemyBase


class Watcher(SqlAlchemyBase):
    __tablename__ = 'watchers'

    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey('tasks.id', ondelete='CASCADE', onupdate='CASCADE'),
        primary_key=True,
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        nullable=False,
    )

    task: Mapped['TaskModel'] = relationship(back_populates="watcher_associations")
