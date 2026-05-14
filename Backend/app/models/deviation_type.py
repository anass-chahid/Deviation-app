from sqlalchemy import Boolean, Enum as SqlEnum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import DeviationCategory, enum_values


class DeviationType(Base):
    __tablename__ = "deviation_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    category: Mapped[DeviationCategory] = mapped_column(
        SqlEnum(DeviationCategory, native_enum=False, values_callable=enum_values),
        nullable=False,
        default=DeviationCategory.yard,
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    deviations: Mapped[list["Deviation"]] = relationship(back_populates="deviation_type")
