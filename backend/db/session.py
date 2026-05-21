import os
from urllib.parse import unquote, quote
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()


def _normalize_db_url(raw: str) -> str:
    """
    Normalize DATABASE_URL so it always uses the asyncpg driver and
    the password is properly percent-encoded.

    Handles the common Railway issue where a password containing '@'
    (e.g. Investing123@123) causes two '@' signs in the URL, which
    SQLAlchemy cannot parse.  We always split on the LAST '@' so the
    everything before it is treated as credentials regardless of how
    many literal '@' signs the password contains.
    """
    if not raw:
        raise ValueError("DATABASE_URL environment variable is not set")

    # 1. Normalise the driver prefix → always postgresql+asyncpg://
    for prefix in ("postgres://", "postgresql://"):
        if raw.startswith(prefix):
            raw = "postgresql+asyncpg://" + raw[len(prefix):]
            break

    # 2. Split scheme from the rest
    scheme_end = raw.index("://") + 3
    scheme = raw[:scheme_end]          # e.g. "postgresql+asyncpg://"
    rest   = raw[scheme_end:]          # e.g. "user:pass@host:5432/db"

    # 3. Split credentials from host on the LAST '@'
    at_pos = rest.rfind("@")
    if at_pos == -1:
        # No credentials in the URL — return as-is
        return raw

    credentials = rest[:at_pos]        # "user:maybe@broken@pass"
    hostpath    = rest[at_pos + 1:]    # "host:5432/db"

    # 4. Split user from password on the FIRST ':'
    colon_pos = credentials.index(":")
    user     = credentials[:colon_pos]
    password = credentials[colon_pos + 1:]

    # 5. Decode any existing percent-encoding first, then re-encode cleanly
    #    so we never end up with double-encoding (%2540 etc.)
    password_clean   = unquote(password)          # %40 → @
    password_encoded = quote(password_clean, safe="")  # @ → %40

    return f"{scheme}{user}:{password_encoded}@{hostpath}"


DATABASE_URL = _normalize_db_url(os.getenv("DATABASE_URL", ""))

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
