import uuid

from sqlalchemy import ForeignKey, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from services.task.database.connector import SqlAlchemyBase


class Executors(SqlAlchemyBase):
    __tablename__ = 'executors'

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

    task: Mapped['TaskModel'] = relationship(back_populates="executor_associations")