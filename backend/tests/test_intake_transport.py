"""Browser-safe headers and authorized, searchable intake owner choices."""
from datetime import timedelta
import json
from urllib.parse import quote
from uuid import uuid4

from sqlalchemy import func, select

from spesped.auth import school_today
from spesped.contexts.evidence.models import SourceItem, SourceRevision
from spesped.contexts.identity.models import AuthorityGrant, School, SchoolMembership, UserAccount
from test_evidence import env, login, base, metadata


def test_unicode_upload_revision_and_single_decode(env):
    client, factory, app, ids = env
    headers = login(client)
    values = metadata(sender="Foresatt Åse – 李 🌻", external_id="🌻" * 320)
    original = "Kartlegging – ÆØÅ 李 🌻 %20.txt"
    encoded = {**headers, "X-Evidence-Filename": quote(original, safe=""),
               "X-Evidence-Filename-Encoding": "percent", "X-Evidence-Metadata": json.dumps(values)}
    assert len(encoded["X-Evidence-Metadata"]) > 4000
    result = client.post(base(ids) + "/intake/files", content="Syntetisk observasjon æøå".encode(), headers=encoded)
    assert result.status_code == 201, result.text
    source = result.json()
    assert source["filename"] == original and source["sender"] == values["sender"]
    values["request_key"] = str(uuid4())
    revised_name = "Revidert økt – 李 🌻.txt"
    result = client.post(base(ids) + f'/intake/{source["id"]}/revisions', content=b"Synthetic revised text",
        headers={**encoded, "X-Evidence-Filename": quote(revised_name, safe=""),
                 "X-Evidence-Metadata": json.dumps(values), "X-Expected-Version": str(source["version"])})
    assert result.status_code == 201, result.text
    assert result.json()["filename"] == revised_name and result.json()["revision"] == 2
    # Old callers and literal percent sequences retain their original identity.
    plain = client.post(base(ids) + "/intake/files", content=b"Synthetic plain percent filename", headers={
        **headers, "X-Evidence-Filename": "literal%20%ZZ.txt", "X-Evidence-Metadata": json.dumps(metadata())})
    assert plain.status_code == 201 and plain.json()["filename"] == "literal%20%ZZ.txt", plain.text
    with factory() as db:
        revisions = db.scalars(select(SourceRevision).where(SourceRevision.source_id == source["id"]).order_by(SourceRevision.revision)).all()
        assert [r.filename for r in revisions] == [original, revised_name]
        assert [r.sender for r in revisions] == [values["sender"], values["sender"]]


def test_invalid_filename_headers_do_not_create_sources_or_revisions(env):
    client, factory, app, ids = env
    headers = login(client)
    values = metadata()
    common = {**headers, "X-Evidence-Metadata": json.dumps(values)}
    created = client.post(base(ids) + "/intake/files", content=b"Synthetic original", headers={**common, "X-Evidence-Filename": "original.txt"})
    assert created.status_code == 201, created.text
    source = created.json()
    for filename, encoding in [("bad%.txt", "percent"), ("bad%ZZ.txt", "percent"), ("bad%C0%AF.txt", "percent"),
                               ("bad%ED%A0%80.txt", "percent"), ("bad%00.txt", "percent"), ("bad%0A.txt", "percent"),
                               ("bad%C2%85.txt", "percent"), ("%2Ftmp%2Ffile.txt", "percent"),
                               ("folder%5Cfile.txt", "percent"), ("valid.txt", "base64")]:
        for path in ("/intake/files", f'/intake/{source["id"]}/revisions'):
            bad = client.post(base(ids) + path, content=b"Synthetic bad filename", headers={**common,
                "X-Evidence-Filename": filename, "X-Evidence-Filename-Encoding": encoding, "X-Expected-Version": str(source["version"])})
            assert bad.status_code == 422, (filename, path, bad.text)
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(SourceItem)) == 1
        assert db.scalar(select(func.count()).select_from(SourceRevision)) == 1
    assert client.get(base(ids) + f'/intake/{source["id"]}/revisions/1/original').content == b"Synthetic original"


def test_assignees_scope_dates_search_paging_and_revocation(env):
    client, factory, app, ids = env
    login(client)
    with factory.begin() as db:
        today = school_today(db.get(School, ids["school"]))
        existing = db.get(UserAccount, ids["reviewer"])
        eligible = []
        for index, kind in enumerate(("first", "second", "revoked", "expired", "future", "learner", "case", "disabled", "membership", "foreign")):
            school = ids["other_school"] if kind == "foreign" else ids["school"]
            user = UserAccount(email=f"choice-{kind}@example.invalid", display_name=f"Choice {index:02} {kind}", password_hash=existing.password_hash,
                               state="disabled" if kind == "disabled" else "active")
            db.add(user); db.flush()
            db.add(SchoolMembership(school_id=school, user_id=user.id, role="teacher", valid_from=today,
                                    state="revoked" if kind == "membership" else "active")); db.flush()
            grant = dict(school_id=school, user_id=user.id, action="evidence.intake", valid_from=today, granted_by=ids["leader"])
            if kind == "revoked": grant["state"] = "revoked"
            if kind == "expired": grant.update(valid_from=today - timedelta(days=2), valid_until=today - timedelta(days=1))
            if kind == "future": grant["valid_from"] = today + timedelta(days=1)
            if kind == "learner": grant["learner_id"] = ids["a"]
            if kind == "case": grant["case_id"] = str(uuid4())
            db.add(AuthorityGrant(**grant))
            if kind in {"first", "second"}:
                eligible.append(user.id)
                db.add(AuthorityGrant(**grant))  # Multiple grants must not duplicate choices.
        literal = db.get(UserAccount, eligible[1]); literal.display_name = "Choice 01 second_100%"
    choices = client.get(base(ids) + "/intake/assignees")
    assert choices.status_code == 200, choices.text
    assert choices.json()["total"] == 3
    assert {x["id"] for x in choices.json()["items"]} == {ids["reviewer"], *eligible}
    assert all(set(x) == {"id", "display_name"} for x in choices.json()["items"])
    page = client.get(base(ids) + "/intake/assignees?query=CHOICE&offset=1&limit=1").json()
    assert page["total"] == 2 and [x["id"] for x in page["items"]] == eligible[1:]
    literal = client.get(base(ids) + "/intake/assignees", params={"query": "_100%"}).json()
    assert literal["total"] == 1 and literal["items"][0]["id"] == eligible[1]
    empty = client.get(base(ids) + "/intake/assignees?offset=100").json()
    assert empty == {"items": [], "total": 3}
    assert client.get(base(ids) + "/intake/assignees?limit=101").status_code == 422
    with factory.begin() as db:
        grant = db.scalar(select(AuthorityGrant).where(AuthorityGrant.user_id == ids["reviewer"], AuthorityGrant.action == "evidence.intake"))
        grant.state = "revoked"
    assert client.get(base(ids) + "/intake/assignees").status_code == 403
    login(client, "tech")
    assert client.get(base(ids) + "/intake/assignees").status_code == 403
