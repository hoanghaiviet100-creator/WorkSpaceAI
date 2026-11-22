"""
backend/database/init_db.py
Database Initialization & Seeding Script for WorkspaceAI (SQLite / MySQL).
Usage:
    python -m backend.database.init_db
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import date

logger = logging.getLogger("init_db")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def init_database() -> bool:
    """Creates all database tables and seeds default requirements and tasks."""
    try:
        from backend.database.connection import get_engine, check_db_connection
        from backend.database.models import Base
    except ImportError as err:
        logger.error(
            "Missing database dependencies: %s. Please run: pip install sqlalchemy",
            err,
        )
        return False

    logger.info("Checking database connection...")
    if not check_db_connection():
        logger.error(
            "Cannot connect to the database. Please verify your configuration in .env."
        )
        return False

    engine = get_engine()
    logger.info("Connected to database successfully. Creating schema tables...")
    Base.metadata.create_all(bind=engine)
    logger.info("All 12 tables created or already exist.")

    # Seed initial demo requirements and tasks
    seed_demo_data()
    return True


def seed_demo_data() -> None:
    """Seeds initial requirements and tasks from default domain services if empty."""
    from backend.database.connection import get_session_factory
    from backend.database.models import RequirementModel, TaskModel, DocumentModel
    from backend.services.reconciliation_service import get_default_requirements, get_default_tasks

    factory = get_session_factory()
    db = factory()
    try:
        # Ensure default document exists for foreign key references
        doc = db.query(DocumentModel).filter_by(doc_id="Project_Brief.pdf").first()
        if not doc:
            logger.info("Seeding default document 'Project_Brief.pdf'...")
            doc = DocumentModel(
                doc_id="Project_Brief.pdf",
                doc_name="Project_Brief.pdf",
                file_type="pdf",
                file_size_bytes=10240,
                file_hash="demo_hash_project_brief_seed",
                version_id="v1",
                total_pages=10,
                total_lines=500,
                total_chunks=15,
                is_selected=True,
                mime_type="application/pdf",
            )
            db.add(doc)
            db.commit()

        req_count = db.query(RequirementModel).count()
        if req_count == 0:
            logger.info("Seeding default requirements...")
            for req in get_default_requirements():
                model = RequirementModel(
                    req_id=req.req_id,
                    doc_id="Project_Brief.pdf",
                    title=req.title,
                    description=None,
                    keywords=req.keywords,
                    official_deadline=req.official_deadline,
                    mandatory_flag=req.mandatory_flag,
                    source_ref=req.source_ref,
                )
                db.add(model)
            db.commit()
            logger.info("Seeded %d default requirements.", len(get_default_requirements()))

        task_count = db.query(TaskModel).count()
        if task_count == 0:
            logger.info("Seeding default tasks...")
            for t in get_default_tasks():
                model = TaskModel(
                    task_id=t.task_id,
                    mapped_req_id=t.mapped_req_id,
                    title=t.title,
                    owner=t.owner,
                    status=t.status,
                    logged_deadline=t.logged_deadline,
                    completion_pct=t.completion_pct,
                    source_ref=t.source_ref,
                )
                db.add(model)
            db.commit()
            logger.info("Seeded %d default tasks.", len(get_default_tasks()))

    except Exception as err:
        db.rollback()
        logger.warning("Seeding demo data skipped or encountered issue: %s", err)
    finally:
        db.close()


if __name__ == "__main__":
    success = init_database()
    sys.exit(0 if success else 1)
