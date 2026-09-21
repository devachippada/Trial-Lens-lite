"""ORM models. Importing this package registers every model on
``Base.metadata`` so Alembic autogenerate (and ``Base.metadata.create_all``
in tests) can see them all.
"""

from app.models.chunk import Chunk
from app.models.citation import Citation
from app.models.document import Document
from app.models.publication import Publication
from app.models.trial import Trial

__all__ = ["Trial", "Publication", "Document", "Chunk", "Citation"]
