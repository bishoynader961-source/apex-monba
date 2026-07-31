"""
db.py — Database Abstraction Layer for PharmacyPro.

Provides SQLAlchemy ORM models and a session factory for the pharmacy
database. Designed as a drop-in migration path from raw sqlite3 queries
in database.py.

Supports both SQLite (local dev) and PostgreSQL (networked deployment)
via a single DATABASE_URL configuration. Multiple pharmacy PCs can sync
to a central PostgreSQL server by setting DATABASE_URL in config.json.

Usage:
    from db import init_db, get_session, Product, SoldItem, Receipt

    # Initialize tables
    init_db()

    # Context-managed session
    with get_session() as session:
        products = session.query(Product).filter(Product.name.ilike("%ibuprofen%")).all()
        for p in products:
            print(p.name, p.price)

Configuration:
    Set DATABASE_URL env var or pass via config.json. Defaults to SQLite:
        sqlite:///pharmacy.db
    For PostgreSQL:
        postgresql://user:pass@host:5432/pharmacy?sslmode=require

Note: Requires `sqlalchemy>=2.0`. Install via: pip install sqlalchemy
"""
import os
import json
import logging
from contextlib import contextmanager
from typing import Optional

try:
    from sqlalchemy import (
        create_engine,
        Column,
        Integer,
        Float,
        String,
        Text,
        ForeignKey,
        DateTime,
        Boolean,
        event,
        text,
    )
    from sqlalchemy.orm import (
        declarative_base,
        sessionmaker,
        relationship,
        Session,
    )
    HAS_SQLALCHEMY = True
except ImportError:
    HAS_SQLALCHEMY = False

from path_utils import get_resource_path

log = logging.getLogger(__name__)

# ── Database URL Resolution ────────────────────────────────────────────

def _resolve_database_url() -> str:
    """Resolve the DATABASE_URL from env var, config.json, or SQLite fallback."""
    # 1. Environment variable (highest priority)
    env_url = os.environ.get("DATABASE_URL")
    if env_url:
        return env_url

    # 2. config.json (for multi-PC PostgreSQL setups)
    try:
        config_path = get_resource_path("config.json")
        if os.path.isfile(config_path):
            with open(config_path, "r") as f:
                config = json.load(f)
            pg_url = config.get("database_url", "")
            if pg_url:
                return pg_url
    except Exception:
        pass

    # 3. Default SQLite fallback
    return f"sqlite:///{get_resource_path('pharmacy.db')}"


DATABASE_URL = _resolve_database_url()

# ── Engine & Session Factory ───────────────────────────────────────────

engine = None
SessionLocal = None
Base = None
_Product = SoldItem = Template = ReceivingLog = None
Receipt = ReceiptItem = Patient = PatientField = AuditLog = None


def _build_engine(url: str):
    """Create an SQLAlchemy engine with appropriate settings for the backend."""
    if "sqlite" in url:
        return create_engine(
            url,
            echo=False,
            pool_pre_ping=True,
            connect_args={"check_same_thread": False},
        )
    else:
        # PostgreSQL: connection pooling for multi-PC concurrent access
        return create_engine(
            url,
            echo=False,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
            pool_timeout=30,
            pool_recycle=1800,
        )


def reconnect_db(new_url: Optional[str] = None):
    """Switch the database engine at runtime (e.g. from SQLite to PostgreSQL).

    Args:
        new_url: New DATABASE_URL. If None, re-reads from config.json.
    """
    global engine, SessionLocal, DATABASE_URL

    if new_url is None:
        DATABASE_URL = _resolve_database_url()
    else:
        DATABASE_URL = new_url

    if engine is not None:
        engine.dispose()

    engine = _build_engine(DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    # Enable WAL mode for SQLite
    if "sqlite" in DATABASE_URL:
        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_conn, _):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    log.info("Database reconnected to: %s", DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL)


def test_connection(url: str) -> dict:
    """Test a database connection string.

    Returns:
        {"ok": bool, "error": str|None, "backend": str}
    """
    backend = "postgresql" if "postgresql" in url else "sqlite"
    try:
        test_eng = create_engine(url, pool_pre_ping=True, connect_args={"check_same_thread": False} if "sqlite" in url else {})
        with test_eng.connect() as conn:
            if "postgresql" in url:
                conn.execute(text("SELECT 1"))
            else:
                conn.execute(text("SELECT 1"))
        test_eng.dispose()
        return {"ok": True, "error": None, "backend": backend}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "backend": backend}


if not HAS_SQLALCHEMY:
    # Graceful degradation: module can be imported but ORM features unavailable
    engine = None
    SessionLocal = None
    Base = None
    Product = SoldItem = Template = ReceivingLog = None
    Receipt = ReceiptItem = Patient = PatientField = AuditLog = None

    def init_db():
        raise ImportError("SQLAlchemy is required for db.py ORM features. Run: pip install sqlalchemy")

    def get_session():
        raise ImportError("SQLAlchemy is required for db.py ORM features. Run: pip install sqlalchemy")

    def reconnect_db(new_url=None):
        raise ImportError("SQLAlchemy is required for db.py ORM features. Run: pip install sqlalchemy")

    def test_connection(url):
        return {"ok": False, "error": "SQLAlchemy not installed", "backend": "unknown"}

    def find_product_by_barcode(barcode):
        raise ImportError("SQLAlchemy is required")

    def search_products(query):
        raise ImportError("SQLAlchemy is required")

    def get_all_products():
        raise ImportError("SQLAlchemy is required")

    def get_expiring_products(days=30):
        raise ImportError("SQLAlchemy is required")

    def add_product_to_db(*a, **kw):
        raise ImportError("SQLAlchemy is required")
else:
    engine = _build_engine(DATABASE_URL)

    # Enable WAL mode for SQLite
    if "sqlite" in DATABASE_URL:
        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_conn, _):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base = declarative_base()

    @contextmanager
    def get_session():
        """Yield a transactional session, auto-committing on success."""
        session = SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


    # ── ORM Models ─────────────────────────────────────────────────────

    class Product(Base):
        __tablename__ = "products"

        id = Column(Integer, primary_key=True, autoincrement=True)
        name = Column(String, nullable=False)
        price = Column(Float, nullable=False)
        manufacturer_barcode = Column(String, nullable=False, default="")
        internal_unique_barcode = Column(String, nullable=False, unique=True)
        status = Column(String, default="In Stock")
        expiry_date = Column(String, default="")
        manufacture_date = Column(String, default="")
        vendor_name = Column(String, default="N/A")

        sold_items = relationship("SoldItem", back_populates="product", lazy="dynamic")
        receiving_logs = relationship("ReceivingLog", back_populates="product", lazy="dynamic")

        def __repr__(self):
            return f"<Product(id={self.id}, name='{self.name}', barcode='{self.internal_unique_barcode}')>"


    class SoldItem(Base):
        __tablename__ = "sold_items"

        id = Column(Integer, primary_key=True, autoincrement=True)
        product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
        barcode = Column(String, nullable=False)
        sale_date = Column(String, default="")
        sale_time = Column(String, default="")
        price = Column(Float, default=0.0)
        status = Column(String, default="sold")
        receipt_id = Column(Integer, ForeignKey("receipts.id"), nullable=True)
        patient_id = Column(Integer, ForeignKey("patients.id"), nullable=True)

        product = relationship("Product", back_populates="sold_items")
        receipt = relationship("Receipt", back_populates="items")
        patient = relationship("Patient", back_populates="sales")

        def __repr__(self):
            return f"<SoldItem(id={self.id}, barcode='{self.barcode}')>"


    class Template(Base):
        __tablename__ = "templates"

        id = Column(Integer, primary_key=True, autoincrement=True)
        name = Column(String, nullable=False)
        price = Column(Float, nullable=False)

        def __repr__(self):
            return f"<Template(id={self.id}, name='{self.name}')>"


    class ReceivingLog(Base):
        __tablename__ = "receiving_log"

        id = Column(Integer, primary_key=True, autoincrement=True)
        product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
        vendor_name = Column(String, default="")
        product_name = Column(String, default="")
        date_received = Column(String, default="")
        quantity = Column(Integer, default=0)
        total_cost = Column(Float, default=0.0)
        barcode = Column(String, default="")

        product = relationship("Product", back_populates="receiving_logs")

        def __repr__(self):
            return f"<ReceivingLog(id={self.id}, vendor='{self.vendor_name}')>"


    class Receipt(Base):
        __tablename__ = "receipts"

        id = Column(Integer, primary_key=True, autoincrement=True)
        payment_method = Column(String, default="Cash")
        total = Column(Float, default=0.0)
        created_at = Column(String, default="")
        patient_id = Column(Integer, ForeignKey("patients.id"), nullable=True)

        items = relationship("ReceiptItem", back_populates="receipt", lazy="dynamic")
        patient = relationship("Patient", back_populates="receipts")

        def __repr__(self):
            return f"<Receipt(id={self.id}, total={self.total})>"


    class ReceiptItem(Base):
        __tablename__ = "receipt_items"

        id = Column(Integer, primary_key=True, autoincrement=True)
        receipt_id = Column(Integer, ForeignKey("receipts.id"), nullable=False)
        product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
        product_name = Column(String, default="")
        barcode = Column(String, default="")
        quantity = Column(Integer, default=1)
        unit_price = Column(Float, default=0.0)
        total_price = Column(Float, default=0.0)
        status = Column(String, default="sold")
        patient_id = Column(Integer, ForeignKey("patients.id"), nullable=True)

        receipt = relationship("Receipt", back_populates="items")
        product = relationship("Product")

        def __repr__(self):
            return f"<ReceiptItem(id={self.id}, name='{self.product_name}')>"


    class Patient(Base):
        __tablename__ = "patients"

        id = Column(Integer, primary_key=True, autoincrement=True)
        name = Column(String, nullable=False)
        phone = Column(String, default="")
        email = Column(String, default="")
        created_at = Column(String, default="")

        sales = relationship("SoldItem", back_populates="patient", lazy="dynamic")
        receipts = relationship("Receipt", back_populates="patient", lazy="dynamic")
        custom_fields = relationship("PatientField", back_populates="patient", lazy="dynamic")

        def __repr__(self):
            return f"<Patient(id={self.id}, name='{self.name}')>"


    class PatientField(Base):
        __tablename__ = "patient_fields"

        id = Column(Integer, primary_key=True, autoincrement=True)
        patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
        field_name = Column(String, nullable=False)
        field_value = Column(String, default="")

        patient = relationship("Patient", back_populates="custom_fields")


    class AuditLog(Base):
        __tablename__ = "audit_logs"

        id = Column(Integer, primary_key=True, autoincrement=True)
        timestamp = Column(String, default="")
        action = Column(String, default="")
        user_pin = Column(String, default="")
        details = Column(Text, default="")


    # ── Initialization ─────────────────────────────────────────────────

    def init_db():
        """Create all tables if they don't exist."""
        Base.metadata.create_all(engine)


    # ── Query Helpers ──────────────────────────────────────────────────

    def find_product_by_barcode(barcode: str):
        """Look up a product by internal or manufacturer barcode."""
        with get_session() as s:
            p = s.query(Product).filter_by(internal_unique_barcode=barcode).first()
            if p:
                return p
            return s.query(Product).filter_by(manufacturer_barcode=barcode).first()


    def search_products(query: str):
        """Fuzzy search products by name, barcode, or vendor."""
        q = f"%{query}%"
        with get_session() as s:
            return s.query(Product).filter(
                (Product.name.ilike(q))
                | (Product.internal_unique_barcode.ilike(q))
                | (Product.manufacturer_barcode.ilike(q))
                | (Product.vendor_name.ilike(q))
            ).all()


    def get_all_products():
        """Return all products ordered by name."""
        with get_session() as s:
            return s.query(Product).order_by(Product.name).all()


    def get_expiring_products(days: int = 30):
        """Return products expiring within the given number of days."""
        from datetime import date, timedelta
        cutoff = (date.today() + timedelta(days=days)).isoformat()
        today = date.today().isoformat()
        with get_session() as s:
            return s.query(Product).filter(
                Product.expiry_date != "",
                Product.expiry_date <= cutoff,
                Product.expiry_date >= today,
                Product.status == "In Stock",
            ).order_by(Product.expiry_date).all()


    def add_product_to_db(
        name: str,
        price: float,
        manufacturer_barcode: str,
        internal_unique_barcode: str,
        expiry_date: str = "",
        manufacture_date: str = "",
        vendor_name: str = "N/A",
    ):
        """Insert a new product and return the ORM object."""
        with get_session() as s:
            p = Product(
                name=name,
                price=price,
                manufacturer_barcode=manufacturer_barcode,
                internal_unique_barcode=internal_unique_barcode,
                expiry_date=expiry_date,
                manufacture_date=manufacture_date,
                vendor_name=vendor_name,
            )
            s.add(p)
            s.flush()
            return p
