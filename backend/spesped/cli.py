"""Local, explicit provisioning. No network or demo login bypass."""
import argparse
from datetime import date
import getpass
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from alembic import command
from alembic.config import Config
from sqlalchemy import select

from spesped.audit import record_audit
from spesped.auth import Actor, hash_password, school_today
from spesped.config import get_settings
from spesped.db import make_session_factory
from spesped.contexts.identity.models import AuthorityGrant, Enrollment, Learner, School, SchoolMembership, StaffAssignment, UserAccount

BOOTSTRAP_ACTIONS = ("membership.manage", "assignment.manage", "authority.manage", "authority.delegate", "guardian.manage", "learner.create", "learner.read", "learner.update")


def migrate(database_url=None):
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    if database_url:
        config.attributes["database_url"] = database_url
    command.upgrade(config, "head")


def provision_school(db, *, school_name, kind, timezone, email, display_name, password):
    ZoneInfo(timezone)
    if db.scalar(select(UserAccount).where(UserAccount.email == email.lower())):
        raise ValueError("This user already exists; use the authorized management workflow")
    school = School(name=school_name, kind=kind, timezone=timezone)
    user = UserAccount(email=email.lower(), display_name=display_name, password_hash=hash_password(password))
    db.add_all([school, user])
    db.flush()
    today = school_today(school)
    membership = SchoolMembership(school_id=school.id, user_id=user.id, role="school_leader", valid_from=today)
    db.add(membership)
    db.flush()
    for action in BOOTSTRAP_ACTIONS:
        db.add(AuthorityGrant(school_id=school.id, user_id=user.id, action=action, valid_from=today, granted_by=user.id))
    record_audit(db, Actor(user.id), school.id, "school.bootstrap", "school", school.id)
    return school, user


def demo(db, password):
    if db.scalar(select(School.id).limit(1)):
        raise ValueError("Synthetic fixtures require an empty database")
    first, leader = provision_school(db, school_name="Syntetisk eksempelskole", kind="public", timezone="Europe/Oslo", email="demo.leader@example.invalid", display_name="Syntetisk skoleleder", password=password)
    second, other = provision_school(db, school_name="Syntetisk annen skole", kind="montessori", timezone="Europe/Oslo", email="demo.other@example.invalid", display_name="Syntetisk annen skoleleder", password=password)
    today = school_today(first)
    for school, suffix, grade in ((first, "A", 4), (first, "B", 5), (second, "C", 6)):
        learner = Learner(school_id=school.id, display_name=f"Syntetisk elev {suffix}", grade=grade, group_name=f"Eksempelgruppe {grade}")
        db.add(learner)
        db.flush()
        db.add(Enrollment(school_id=school.id, learner_id=learner.id, valid_from=today))
        if suffix == "A":
            first_learner = learner
    for email, label, role, actions in (
        ("demo.teacher@example.invalid", "Syntetisk lærer", "teacher", ["learner.read", "learner.update", "document.contribute"]),
        ("demo.assistant@example.invalid", "Syntetisk assistent", "assistant", ["brief.read", "observation.create"]),
        ("demo.technical@example.invalid", "Syntetisk driftsbruker", "technical_administrator", []),
        ("demo.guardian@example.invalid", "Syntetisk foresatt", "guardian", []),
    ):
        user = UserAccount(email=email, display_name=label, password_hash=hash_password(password))
        db.add(user)
        db.flush()
        db.add(SchoolMembership(school_id=first.id, user_id=user.id, role=role, valid_from=today))
        db.flush()
        if actions:
            db.add(StaffAssignment(school_id=first.id, user_id=user.id, learner_id=first_learner.id, actions=actions, purpose="synthetic_teaching", valid_from=today))
    record_audit(db, Actor(leader.id), first.id, "synthetic_fixture.created", "school", first.id)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("migrate", help="Apply versioned database migrations")
    bootstrap = commands.add_parser("bootstrap", help="Create a school and explicitly authorized initial leader")
    bootstrap.add_argument("--school-name", required=True)
    bootstrap.add_argument("--kind", choices=["public", "montessori"], required=True)
    bootstrap.add_argument("--timezone", default="Europe/Oslo")
    bootstrap.add_argument("--email", required=True)
    bootstrap.add_argument("--display-name", required=True)
    bootstrap.add_argument("--password-env", help="Name of a private environment variable; otherwise prompt securely")
    fixture = commands.add_parser("demo", help="Explicitly opt into synthetic fixtures in an empty development database")
    fixture.add_argument("--confirm-synthetic", action="store_true", required=True)
    fixture.add_argument("--password-env", required=True)
    args = parser.parse_args()
    settings = get_settings()
    if args.command == "migrate":
        migrate()
        print("Migrations applied.")
        return
    if args.command == "demo" and settings.environment == "production":
        parser.error("Synthetic fixtures are disabled in production")
    password = os.environ.get(args.password_env) if args.password_env else getpass.getpass("Initial password: ")
    if not password:
        parser.error("Supply a private password through the selected environment variable")
    factory = make_session_factory(settings.database_url)
    try:
        with factory.begin() as db:
            if args.command == "demo":
                demo(db, password)
            else:
                provision_school(db, school_name=args.school_name, kind=args.kind, timezone=args.timezone, email=args.email, display_name=args.display_name, password=password)
    except ValueError as exc:
        parser.error(str(exc))
    print("Synthetic fixture created." if args.command == "demo" else "School and initial leader created.")


if __name__ == "__main__":
    main()
