"""Static forward migration with retained pre-document rows on both databases."""
import os
from pathlib import Path
from uuid import uuid4
import pytest
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.autogenerate import compare_metadata
from sqlalchemy import create_engine,text,select,inspect
from sqlalchemy.engine import make_url
from spesped.db import Base,make_session_factory
from spesped.contexts.identity.models import School
from spesped.contexts.documents import models

@pytest.mark.parametrize('dialect',['sqlite','postgres'])
def test_static_forward_retained_rows_and_metadata(tmp_path,dialect):
    admin=None;schema=None
    if dialect=='postgres':
        raw=os.getenv('SPESPED_TEST_POSTGRES_URL')
        if not raw:pytest.skip('Set isolated PostgreSQL test URL')
        assert make_url(raw).database!='spesped_demo'
        admin=create_engine(raw);schema='j11_'+uuid4().hex
        with admin.begin() as connection:connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        url=make_url(raw).update_query_dict({'options':f'-csearch_path={schema}'}).render_as_string(hide_password=False)
    else:url=f'sqlite:///{tmp_path}/forward.db'
    config=Config(str(Path(__file__).parents[1]/'alembic.ini'));config.attributes['database_url']=url
    engine=create_engine(url);factory=make_session_factory(url)
    try:
        command.upgrade(config,'j19_professional_authority')
        with factory.begin() as db:
            school=School(name='Synthetic retained pre-BC10 school',kind='public',timezone='Europe/Oslo');db.add(school);db.flush();identity=school.id
        command.upgrade(config,'head')
        with factory() as db:assert db.get(School,identity).name=='Synthetic retained pre-BC10 school'
        with engine.connect() as connection:
            actual={name for name in inspect(connection).get_table_names() if name.startswith('documents_')}
            expected={name for name in Base.metadata.tables if name.startswith('documents_')};assert actual==expected
            context=MigrationContext.configure(connection,opts={'include_object':lambda obj,name,kind,reflected,compare_to: name.startswith('documents_') if kind=='table' else True})
            assert compare_metadata(context,Base.metadata)==[]
        content=Path(__file__).parents[1]/'migrations/versions/j11_documents.py'
        assert 'create_all' not in content.read_text() and 'metadata' not in content.read_text()
    finally:
        engine.dispose();factory.kw['bind'].dispose()
        if admin:
            with admin.begin() as connection:connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            admin.dispose()
