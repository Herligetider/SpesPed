"""Static BC09 schema proof on isolated SQLite and PostgreSQL namespaces."""
from pathlib import Path
from uuid import uuid4
import os
import pytest
from sqlalchemy import create_engine,text,inspect
from sqlalchemy.engine import make_url
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.autogenerate import compare_metadata
from spesped.db import Base
from spesped.contexts.assessment import models as m
from assessment_fixtures import assessment_env,curriculum_env,teaching_env,env,login,instrument,planned

@pytest.fixture(params=['sqlite','postgres'])
def empty_database(request,tmp_path):
    schema=None;admin=None
    if request.param=='postgres':
        url=os.environ.get('SPESPED_TEST_POSTGRES_URL')
        if not url:pytest.skip('An isolated PostgreSQL URL is required')
        if make_url(url).database=='spesped_demo':pytest.fail('Demo database forbidden')
        schema='j10_'+uuid4().hex;admin=create_engine(url)
        with admin.begin() as db:db.execute(text(f'CREATE SCHEMA "{schema}"'))
        url=make_url(url).update_query_dict({'options':f'-csearch_path={schema}'}).render_as_string(hide_password=False)
    else:url=f'sqlite:///{tmp_path}/assessment_migration.db'
    config=Config(str(Path(__file__).resolve().parents[1]/'alembic.ini'));config.attributes['database_url']=url
    engine=create_engine(url)
    try:yield config,engine
    finally:
        engine.dispose()
        if schema:
            with admin.begin() as db:db.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            admin.dispose()

def test_static_alignment_and_empty_upgrade_downgrade_roundtrip(empty_database):
    config,engine=empty_database;command.upgrade(config,'j10_assessment_events')
    with engine.connect() as connection:
        context=MigrationContext.configure(connection,opts={'include_object':lambda obj,name,kind,reflected,compare_to:(name.startswith('assessment_') if kind=='table' else True)})
        differences=compare_metadata(context,Base.metadata)
        assert differences==[],differences
        assert len([t for t in inspect(connection).get_table_names() if t.startswith('assessment_')])==16
    command.downgrade(config,'j09_curriculum')
    with engine.connect() as connection:assert not any(t.startswith('assessment_') for t in inspect(connection).get_table_names())
    command.upgrade(config,'j10_assessment_events')
    with engine.connect() as connection:assert len([t for t in inspect(connection).get_table_names() if t.startswith('assessment_')])==16

def test_retained_assessment_data_refuses_downgrade(assessment_env):
    client,factory,app,ids=assessment_env;h=login(client);ins,_=instrument(client,ids,h);row=planned(client,ids,h,ins)
    config=Config(str(Path(__file__).resolve().parents[1]/'alembic.ini'));config.attributes['database_url']=factory.kw['bind'].url.render_as_string(hide_password=False)
    with pytest.raises(RuntimeError,match='retained'):command.downgrade(config,'j09_curriculum')
    with factory() as db:assert db.get(m.Administration,row['id']) is not None

def test_forward_envelope_migration_preserves_retained_legacy_rows(empty_database):
    from datetime import datetime,timezone
    from sqlalchemy import MetaData,Table,select
    from spesped.db import make_session_factory
    from spesped.cli import provision_school
    config,engine=empty_database;command.upgrade(config,'j10_assessment')
    factory=make_session_factory(engine.url.render_as_string(hide_password=False))
    occurred=datetime(2026,10,1,8,30,tzinfo=timezone.utc)
    event_id=str(uuid4());correlation_aggregate=str(uuid4())
    with factory.begin() as db:
        school,user=provision_school(db,school_name='Synthetic retained migration school',kind='public',timezone='Europe/Oslo',email='retained-envelope@example.invalid',display_name='Synthetic reviewer',password='synthetic-migration-password')
        school_id=school.id;user_id=user.id
    legacy=Table('assessment_outbox',MetaData(),autoload_with=engine)
    with engine.begin() as connection:
        connection.execute(legacy.insert().values(id=event_id,school_id=school_id,created_at=occurred,aggregate_id=correlation_aggregate,aggregate_version=3,actor_id=user_id,event_type='assessment.legacy.recorded',payload={'result_revision_id':str(uuid4())},causation_id='synthetic-retained-command'))
        before=dict(connection.execute(select(legacy).where(legacy.c.id==event_id)).mappings().one())
    command.upgrade(config,'j10_assessment_events')
    current=Table('assessment_outbox',MetaData(),autoload_with=engine)
    with engine.connect() as connection:
        after=dict(connection.execute(select(current).where(current.c.id==event_id)).mappings().one())
        assert {name:after[name] for name in before}==before
        assert after['schema_version']==0 and after['correlation_id']==event_id
    with factory() as db:
        row=db.get(m.AssessmentEvent,event_id)
        assert row.occurred_at==row.recorded_at==row.created_at==occurred
        assert row.occurred_at.tzinfo and row.recorded_at.tzinfo
    with pytest.raises(RuntimeError,match='retained event'):command.downgrade(config,'j10_assessment')
    with factory() as db:assert db.get(m.AssessmentEvent,event_id).schema_version==0
    factory.kw['bind'].dispose()
