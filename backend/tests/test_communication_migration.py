"""Static forward-only retained history migration, against actual PostgreSQL too."""
import os
from pathlib import Path
from uuid import uuid4
import pytest
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.autogenerate import compare_metadata
from sqlalchemy import create_engine,text,inspect
from sqlalchemy.engine import make_url
from spesped.db import Base,make_session_factory
from spesped.contexts.identity.models import School
from spesped.contexts.communication import models
@pytest.mark.parametrize('dialect',['sqlite','postgres'])
def test_static_forward_metadata_and_retained_document_era_rows(tmp_path,dialect):
    admin=None;schema=None
    if dialect=='postgres':
        raw=os.getenv('SPESPED_TEST_POSTGRES_URL')
        if not raw:pytest.skip('Set isolated PostgreSQL URL')
        assert make_url(raw).database=='spesped_test'
        admin=create_engine(raw);schema='j12_'+uuid4().hex
        with admin.begin() as connection:connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        url=make_url(raw).update_query_dict({'options':f'-csearch_path={schema}'}).render_as_string(hide_password=False)
    else:url=f'sqlite:///{tmp_path}/communication-forward.db'
    config=Config(str(Path(__file__).parents[1]/'alembic.ini'));config.attributes['database_url']=url
    factory=make_session_factory(url);engine=factory.kw['bind']
    try:
        command.upgrade(config,'j11_documents')
        with factory.begin() as db:
            school=School(name='Synthetic retained document-era school',kind='public',timezone='Europe/Oslo');db.add(school);db.flush();identity=school.id
        command.upgrade(config,'j12_communication')
        with factory() as db:assert db.get(School,identity).name=='Synthetic retained document-era school'
        with engine.connect() as connection:
            actual={v for v in inspect(connection).get_table_names() if v.startswith('communication_')};expected={v for v in Base.metadata.tables if v.startswith('communication_')};assert actual==expected and len(actual)==20
            context=MigrationContext.configure(connection,opts={'include_object':lambda obj,name,kind,reflected,compare_to:name.startswith('communication_') if kind=='table' else True});assert compare_metadata(context,Base.metadata)==[]
        content=Path(__file__).parents[1]/'migrations/versions/j12_communication.py';assert 'create_all' not in content.read_text() and 'metadata' not in content.read_text()
        command.downgrade(config,'j13_report_period')
        with engine.connect() as connection:assert not any(v.startswith('communication_') for v in inspect(connection).get_table_names())
        command.upgrade(config,'j12_communication')
        with factory.begin() as db:db.add(models.ChannelPolicy(school_id=identity,state='active'))
        with pytest.raises(RuntimeError,match='retained'):command.downgrade(config,'j13_report_period')
        with engine.connect() as connection:assert len([v for v in inspect(connection).get_table_names() if v.startswith('communication_')])==20
    finally:
        engine.dispose()
        if admin:
            with admin.begin() as connection:connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            admin.dispose()
