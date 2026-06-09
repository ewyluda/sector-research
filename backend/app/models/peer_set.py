"""PeerSet — persisted, user-curated peer list per ticker.

Auto-seeded on first read from filing-extracted competitors
(competitor_landscape) + FMP stock-peers; user edits replace the list.
No FKs by design: peer sets are independent of themes/runs and survive
their deletion.
"""

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base, TimestampMixin


class PeerSet(Base, TimestampMixin):
    __tablename__ = "peer_sets"

    ticker: Mapped[str] = mapped_column(String(16), primary_key=True)
    peers: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
