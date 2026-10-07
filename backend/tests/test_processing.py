"""
Background receipt reading: results land on the document, failures don't
leave it stuck, and interrupted reads are found again.
"""

import asyncio
import uuid

from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.user import User
from app.services import processing
from tests.conftest import TestingSessionLocal


def processing_receipt(db: Session) -> str:
    user = User(clerk_id=f"test-user-{uuid.uuid4().hex[:8]}", email="")
    db.add(user)
    db.commit()
    document = Document(
        user_id=user.id, status="processing", storage_key=f"{user.clerk_id}/r.jpg",
        original_filename="r.jpg", mime_type="image/jpeg",
    )
    db.add(document)
    db.commit()
    return document.id


def test_mock_read_fills_the_receipt(db: Session):
    document_id = processing_receipt(db)
    asyncio.run(processing.read_receipt(TestingSessionLocal, document_id))
    db.expire_all()
    document = db.get(Document, document_id)
    assert document.status in ("ready", "needs_review")
    assert document.gross_amount is not None


def test_a_crash_marks_the_receipt_failed_instead_of_stuck(db: Session, monkeypatch):
    document_id = processing_receipt(db)

    async def boom(*args):
        raise RuntimeError("tesseract died")

    monkeypatch.setattr(processing, "_read_into", boom)
    asyncio.run(processing.read_receipt(TestingSessionLocal, document_id))
    db.expire_all()
    assert db.get(Document, document_id).status == "failed"


def test_interrupted_reads_are_found(db: Session):
    document_id = processing_receipt(db)
    assert document_id in processing.stuck_document_ids(db)
