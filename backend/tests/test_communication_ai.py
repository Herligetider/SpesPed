"""A recalled local model blocks an already queued, human approved package."""
from communication_fixtures import *
from documents_fixtures import generated_documents,document_wire,path as document_path
from test_documents_generation import generate,diff,selection as generated_selection
from spesped.contexts.platform.models import ModelRelease

def test_actual_local_generation_release_recall_blocks_queued_package(communication_env,generated_documents):
    e=generated_documents;client,factory,app,ids=communication_env;h=e.h
    _,_,_,_,chosen=setup(client,ids,h)
    job=generate(e);proposal=diff(e,job)
    response=client.post(document_path(ids)+f'/cases/{e.row["id"]}/suggestion-review',headers=h,json=generated_selection(e,proposal));assert response.status_code==200,response.text
    doc=revised(client,ids,h,response.json());doc=transition(client,ids,h,doc,'review');doc=transition(client,ids,h,doc,'approve')
    chosen={**chosen,'document_revision_id':doc['revision_id'],'section_keys':['body']}
    package=post(client,ids,h,'/packages',retry(selection=chosen),201);package=authorize(client,ids,h,package);_,dispatch=queued(client,ids,h,package)
    with factory() as db:version=db.get(ModelRelease,e.release).version
    response=client.post(base(ids)+f'/ai/configuration/release/{e.release}/revoke',headers=h,json={'expected_version':version});assert response.status_code==200,response.text
    assert client.get(path(ids)+f'/packages/{package["id"]}/preview').status_code==409
    assert client.post(path(ids)+f'/dispatches/{dispatch["id"]}/prepare',headers=h,json=expected(dispatch,reason='Synthetic recalled model must block current release')).status_code==409
