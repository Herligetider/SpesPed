from alembic import context
from sqlalchemy import create_engine, pool

from spesped.config import get_settings
from spesped.db import Base
from spesped.contexts.identity import models  # noqa: F401
from spesped.contexts.evidence import models as evidence_models  # noqa: F401
from spesped.contexts.platform import models as platform_models  # noqa: F401
from spesped.contexts.governance import models as governance_models  # noqa: F401
from spesped.contexts.entitlements import models as entitlement_models  # noqa: F401
from spesped.contexts.plans import models as plan_models  # noqa: F401
from spesped.contexts.safeguarding import models as safeguarding_models  # noqa: F401
from spesped.contexts.teaching import models as teaching_models  # noqa: F401
from spesped.contexts.curriculum import models as curriculum_models  # noqa: F401
from spesped.contexts.assessment import models as assessment_models  # noqa: F401
from spesped.contexts.administration import models as administration_models  # noqa: F401
from spesped.contexts.documents import models as document_models  # noqa: F401
from spesped.contexts.communication import models as communication_models  # noqa: F401

config = context.config
target_metadata = Base.metadata
url = config.attributes.get("database_url") or get_settings().database_url

if context.is_offline_mode():
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
