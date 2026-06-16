from sqlalchemy import String, Text

from app.extensions import db
from app.models.base import PrimaryKeyMixin, TimestampMixin


class Setting(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "settings"

    key: str = db.Column(String(120), unique=True, nullable=False, index=True)
    value: str = db.Column(Text, nullable=False, default="")
    description: str | None = db.Column(String(255), nullable=True)
    type: str = db.Column(String(20), nullable=False, default="string")

    def __repr__(self) -> str:
        return f"<Setting {self.key}={self.value}>"
