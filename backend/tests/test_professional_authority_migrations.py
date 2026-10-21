"""Static J19 migration, scoped isolated databases and retained-data refusal."""
from pathlib import Path
from uuid import uuid4
import os
import pytest
from sqlalchemy import create_engine,text,inspect,select
from sqlalchemy.engine import make_url
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.autogenerate import compare_metadata
from spesped.db import Base,make_session_factory
from spesped.cli import provision_school
from spesped.contexts.administration import models as m
from administration_fixtures import *

@pytest.fixture(params=['sqlite','postgres'])
def professional_database(request,tmp_path):
    schema=None;admin=None
    if request.param=='postgres':
        url=os.environ.get('SPESPED_TEST_POSTGRES_URL')
        if not url:pytest.skip('An isolated PostgreSQL URL is required')
        if make_url(url).database=='spesped_demo':pytest.fail('Demo database forbidden')
        schema='j19_'+uuid4().hex;admin=create_engine(url)
        with admin.begin() as db:db.execute(text(f'CREATE SCHEMA "{schema}"'))
        url=make_url(url).update_query_dict({'options':f'-csearch_path={schema}'}).render_as_string(hide_password=False)
    else:url=f'sqlite:///{tmp_path}/professional_migration.db'
    config=Config(str(Path(__file__).resolve().parents[1]/'alembic.ini'));config.attributes['database_url']=url
    engine=create_engine(url)
    try:yield config,engine
    finally:
        engine.dispose()
        if schema:
            with admin.begin() as db:db.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            admin.dispose()

def test_professional_static_schema_roundtrip_and_retained_prior_context(professional_database):
    config,engine=professional_database;command.upgrade(config,'j10_assessment_events')
    factory=make_session_factory(engine.url.render_as_string(hide_password=False))
    with factory.begin() as db:
        school,user=provision_school(db,school_name='Synthetic retained source',kind='public',timezone='Europe/Oslo',email='migration@example.invalid',display_name='Synthetic migration staff',password='synthetic-migration-password')
        school_id=school.id
    with engine.connect() as db:before=dict(db.execute(text('SELECT * FROM identity_schools WHERE id=:id'),{'id':school_id}).mappings().one())
    command.upgrade(config,'j19_professional_authority')
    with engine.connect() as connection:
        context=MigrationContext.configure(connection,opts={'include_object':lambda obj,name,kind,reflected,compare_to:name.startswith('administration_') if kind=='table' else True})
        assert compare_metadata(context,Base.metadata)==[]
        assert len([t for t in inspect(connection).get_table_names() if t.startswith('administration_')])==6
        assert dict(connection.execute(text('SELECT * FROM identity_schools WHERE id=:id'),{'id':school_id}).mappings().one())==before
    command.downgrade(config,'j10_assessment_events')
    with engine.connect() as db:assert not any(t.startswith('administration_') for t in inspect(db).get_table_names())
    command.upgrade(config,'j19_professional_authority')
    with engine.connect() as db:assert dict(db.execute(text('SELECT * FROM identity_schools WHERE id=:id'),{'id':school_id}).mappings().one())==before
    factory.kw['bind'].dispose()

def test_professional_retained_reviews_refuse_downgrade(administration_env):
    client,factory,app,ids=administration_env;h=login(client);q,r=prerequisites(client,ids,h)
    config=Config(str(Path(__file__).resolve().parents[1]/'alembic.ini'));config.attributes['database_url']=factory.kw['bind'].url.render_as_string(hide_password=False)
    with pytest.raises(RuntimeError,match='Retained professional'):command.downgrade(config,'j10_assessment_events')
    with factory() as db:
        assert db.get(m.ProfessionalRecord,q['id']).state=='reviewed'
        assert db.scalar(select(m.ProfessionalCheck).where(m.ProfessionalCheck.revision_id==q['revision_id'])).outcome=='eligible'
