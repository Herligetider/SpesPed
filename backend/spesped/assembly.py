"""Explicit context adapters; no user-selected endpoints or source provenance flags."""
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import select

from spesped.auth import require_learner_access
from spesped.contexts.evidence import service as evidence
from spesped.contexts.evidence.models import SourceSubjectLink
from spesped.contexts.evidence.processing import ClamdScanner, LocalStorage, TesseractOCR
from spesped.contexts.platform.contracts import (
    DOCUMENT_PURPOSES, EvaluationCase, GatewayRuntime, ProviderSpec, Purpose, SourceInput, SourceRef,
)
from spesped.contexts.platform.providers import ProviderFailure, validate_provider
from spesped.errors import DomainError, access_denied


class ConfigurationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SyntheticAttestation(ConfigurationModel):
    fixture_name: str = Field(min_length=1, max_length=100)
    school_id: UUID
    learner_id: UUID | None = None
    reference: SourceRef
    purposes: list[Purpose] = Field(min_length=1, max_length=10)
    content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def document_basis_scope(self):
        if self.reference.kind == "document_basis":
            if (self.learner_id is None or self.reference.revision != 1
                    or any(purpose not in DOCUMENT_PURPOSES for purpose in self.purposes)):
                raise ValueError("Document basis attestations require a learner, revision 1 and document purposes")
        elif any(purpose in DOCUMENT_PURPOSES for purpose in self.purposes):
            raise ValueError("Document drafting attestations require document basis")
        return self


class SyntheticManifest(ConfigurationModel):
    version: Literal[1]
    entries: list[SyntheticAttestation] = Field(max_length=1000)


class EvaluationFixture(ConfigurationModel):
    name: str = Field(min_length=1, max_length=100)
    purpose: Purpose
    text: str | None = Field(default=None, min_length=1, max_length=20000)
    file: Path | None = None
    media_type: Literal["text/plain", "image/png", "image/jpeg", "audio/wav", "audio/mpeg", "audio/webm"] = "text/plain"
    required_substrings: list[str] = Field(default_factory=list, max_length=20)
    forbidden_substrings: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def compatible_fixture(self):
        if (self.text is None) == (self.file is None):
            raise ValueError("An evaluation case requires either text or a synthetic media file")
        if self.purpose in {"teaching_suggestion", "document_draft", "embedding", "intake_structuring", "session_planning", "iep_drafting", *DOCUMENT_PURPOSES}:
            if self.text is None or self.media_type != "text/plain":
                raise ValueError("This evaluation purpose requires plain text")
        elif self.file is None or not self.media_type.startswith("image/" if self.purpose == "evidence_extraction" else "audio/"):
            raise ValueError("This evaluation purpose requires matching synthetic media")
        if self.file is not None and (self.file.is_absolute() or ".." in self.file.parts):
            raise ValueError("Synthetic assets must be relative to the evaluation configuration")
        return self


class EvaluationConfiguration(ConfigurationModel):
    version: Literal[1]
    suites: dict[str, list[EvaluationFixture]]


def read_operator_configuration(path: Path, model):
    """Only deployment-owned local JSON. Never read a source upload as configuration."""
    try:
        stat = path.stat()
        if not path.is_file() or stat.st_size > 1_000_000 or stat.st_mode & 0o022:
            raise ValueError()
        data = path.read_bytes()
        if len(data) > 1_000_000:
            raise ValueError()
        return model.model_validate_json(data)
    except (OSError, ValueError, ValidationError):
        raise ValueError("Invalid or writable-by-others AI operator configuration") from None


def content_digest(content):
    return hashlib.sha256(content.encode() if isinstance(content, str) else content).hexdigest()


class EvidenceSourceResolver:
    def __init__(self, storage=None, attestations=()):
        self.storage = storage
        self.attestations = tuple(attestations)

    def resolve(self, db, actor, school_id, learner_id, purpose, references):
        if purpose in DOCUMENT_PURPOSES:
            if learner_id is None or len(references) != 1 or references[0].kind != "document_basis" or references[0].revision != 1:
                raise access_denied()
            require_learner_access(db, actor, school_id, learner_id)
            try:
                from spesped.contexts.documents.generation import resolve_generation_source
            except ModuleNotFoundError as exc:
                if exc.name not in {"spesped.contexts.documents", "spesped.contexts.documents.generation"}:
                    raise
                raise DomainError("document_generation_unavailable", "Document source validation is not installed.", 503) from None
            return [self._attest(resolve_generation_source(db, actor, school_id, learner_id, purpose, references[0]))]
        if any(reference.kind == "document_basis" for reference in references):
            raise access_denied()
        if purpose == "iep_drafting":
            if learner_id is None or len(references) != 1 or references[0].kind != "plan_basis" or references[0].revision != 1:
                raise access_denied()
            require_learner_access(db, actor, school_id, learner_id)
            from spesped.contexts.plans import service as plans
            resolve_plan = getattr(plans, "resolve_generation_source", None)
            if not callable(resolve_plan):
                raise DomainError("plan_generation_unavailable", "Plan source validation is not installed.", 503)
            return [self._attest(resolve_plan(db, actor, school_id, learner_id, purpose, references[0]))]
        if any(reference.kind == "plan_basis" for reference in references):
            raise access_denied()
        if purpose == "session_planning":
            if learner_id is None or len(references) != 1 or references[0].kind != "teaching_basis":
                raise access_denied()
            require_learner_access(db, actor, school_id, learner_id)
            try:
                from spesped.contexts.teaching.service import resolve_generation_source
            except ModuleNotFoundError as exc:
                if exc.name not in {"spesped.contexts.teaching", "spesped.contexts.teaching.service"}:
                    raise
                raise DomainError("teaching_context_unavailable", "Teaching source validation is not installed.", 503) from None
            return [self._attest(resolve_generation_source(db, actor, school_id, learner_id, purpose, references[0]))]
        if any(reference.kind == "teaching_basis" for reference in references):
            raise access_denied()
        if purpose == "intake_structuring":
            if learner_id is not None or len(references) != 1 or references[0].kind != "intake":
                raise access_denied()
            evidence.intake_access(db, actor, school_id)
        else:
            require_learner_access(db, actor, school_id, learner_id)
        result = []
        for reference in references:
            if reference.kind == "evidence":
                item = evidence.evidence(db, actor, school_id, str(reference.source_id))
                if item.learner_id != learner_id or item.current_revision != reference.revision:
                    raise DomainError("source_revision_changed", "Select the current authorized evidence revision.", 409)
                revision = evidence.current(db, item)
                if revision is None:
                    raise access_denied()
                excerpt = evidence.excerpt_view(db, actor, school_id, revision.link_id)
                # Preserve attribution and uncertainty. No original document text,
                # source metadata or sibling excerpts are fetched for this path.
                value = evidence.evidence_view(db, item)
                value["controlled_excerpt"] = excerpt["excerpt"]
                content = json.dumps(value, default=lambda v: v.isoformat(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                resolved = SourceInput(reference, school_id, learner_id, purpose, content)
            else:
                if purpose == "intake_structuring":
                    source = evidence.source(db, actor, school_id, str(reference.source_id))
                    if source.current_revision != reference.revision:
                        raise DomainError("source_revision_changed", "Select the current source revision.", 409)
                    inspected = evidence.inspection(db, source)
                    if inspected is None or inspected.extraction_state != "ready" or inspected.scan_state not in {"clean", "not_required_note"}:
                        raise DomainError("source_not_ready", "The source must pass scanning and extraction.", 409)
                    version = evidence.source_revision(db, school_id, source.id, reference.revision)
                    if self.storage is None:
                        raise DomainError("source_storage_unavailable", "Source storage is not configured.", 503)
                    evidence.read_original(self.storage, version)
                    content = json.dumps({"pages": inspected.pages, "source_digest": version.digest}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                    resolved = SourceInput(reference, school_id, None, purpose, content)
                    result.append(self._attest(resolved))
                    continue
                if purpose != "evidence_extraction":
                    raise access_denied()
                source = evidence.source(db, actor, school_id, str(reference.source_id))
                if source.current_revision != reference.revision:
                    raise DomainError("source_revision_changed", "Select the current source revision.", 409)
                # Original-image OCR remains an intake-authority operation. A
                # confirmed current subject link is additionally required; it is
                # not inferred from a filename or a caller's learner identifier.
                links = db.scalars(select(SourceSubjectLink).where(
                    SourceSubjectLink.school_id == school_id,
                    SourceSubjectLink.source_id == source.id,
                    SourceSubjectLink.source_revision == reference.revision,
                    SourceSubjectLink.learner_id == learner_id,
                    SourceSubjectLink.revoked_at.is_(None),
                )).all()
                if not links:
                    raise access_denied()
                evidence.excerpt_view(db, actor, school_id, links[0].id)
                inspection = evidence.inspection(db, source)
                version = evidence.source_revision(db, school_id, source.id, reference.revision)
                if inspection is None or inspection.scan_state != "clean":
                    raise DomainError("source_not_clean", "The original must pass file inspection.", 409)
                if version.media_type not in {"image/png", "image/jpeg"}:
                    raise DomainError("source_media_type", "AI image extraction requires a PNG or JPEG original.", 422)
                if self.storage is None:
                    raise DomainError("source_storage_unavailable", "Source storage is not configured.", 503)
                resolved = SourceInput(reference, school_id, learner_id, purpose, evidence.read_original(self.storage, version), version.media_type)
            result.append(self._attest(resolved))
        return result


    def _attest(self, resolved):
        for entry in self.attestations:
            learner = str(entry.learner_id) if entry.learner_id is not None else None
            if (str(entry.school_id) == resolved.school_id and learner == resolved.learner_id
                    and entry.reference == resolved.reference and resolved.purpose in entry.purposes
                    and entry.content_digest == content_digest(resolved.content)):
                return replace(resolved, provenance="synthetic_fixture", provenance_reference=entry.fixture_name)
        return resolved

    def attestation_is_current(self, school_id, learner_id, purpose, manifest):
        """Metadata-only operator attestation check; grants no source access."""
        if manifest.get("provenance") != "synthetic_fixture":
            return False
        reference = SourceRef.model_validate(manifest["reference"])
        return any(
            str(entry.school_id) == school_id
            and (str(entry.learner_id) if entry.learner_id is not None else None) == learner_id
            and entry.reference == reference and purpose in entry.purposes
            and entry.content_digest == manifest.get("content_digest")
            and entry.fixture_name == manifest.get("provenance_reference")
            for entry in self.attestations
        )


def load_evaluation_suites(path):
    if path is None:
        return {}
    configuration = read_operator_configuration(path, EvaluationConfiguration)
    if not configuration.suites or len(configuration.suites) > 20:
        raise ValueError("Configure between one and twenty synthetic evaluation suites")
    suites = {}
    # Evaluation examples have fixed non-pupil identities and are never resolved
    # through school data. The operator supplies synthetic fixture text only.
    fixture_school = "00000000-0000-4000-8000-000000000001"
    fixture_learner = "00000000-0000-4000-8000-000000000002"
    for name, fixtures in configuration.suites.items():
        if not name.strip() or len(name) > 100 or not 1 <= len(fixtures) <= 20:
            raise ValueError("Invalid evaluation suite name or size")
        if len({f.name for f in fixtures}) != len(fixtures):
            raise ValueError("Evaluation case names must be unique within a suite")
        cases = []
        for index, fixture in enumerate(fixtures, 1):
            source_kind = {"intake_structuring": "intake", "session_planning": "teaching_basis", "iep_drafting": "plan_basis", "report_drafting": "document_basis", "guardian_email_drafting": "document_basis"}.get(fixture.purpose, "evidence")
            ref = SourceRef(kind=source_kind, source_id=UUID(int=index), revision=1)
            content = fixture.text
            if fixture.file is not None:
                asset = (path.parent / fixture.file).resolve()
                try:
                    stat = asset.stat()
                    if (not asset.is_relative_to(path.parent.resolve()) or not asset.is_file()
                            or not 0 < stat.st_size <= 2_000_000 or stat.st_mode & 0o022):
                        raise ValueError()
                    content = asset.read_bytes()
                    if not 0 < len(content) <= 2_000_000:
                        raise ValueError()
                except (ValueError, OSError):
                    raise ValueError("Invalid synthetic evaluation asset") from None
            if fixture.purpose == "intake_structuring":
                # Fixed fixture configuration supplies literal extracted pages.
                content = json.dumps({"pages": [content]}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            source = SourceInput(ref, fixture_school, None if fixture.purpose == "intake_structuring" else fixture_learner, fixture.purpose, content, fixture.media_type,
                                 provenance="synthetic_fixture", provenance_reference=f"{name}/{fixture.name}")
            cases.append(EvaluationCase(fixture.name, fixture.purpose, (source,),
                                        tuple(fixture.required_substrings), tuple(fixture.forbidden_substrings)))
        suites[name] = tuple(cases)
    return suites


def governance_evidence_validator(db, actor, school_id, learner_id, case_id, reference_id):
    from spesped.contexts.governance.ports import ValidatedEvidenceReference
    if case_id is not None:
        from spesped.contexts.safeguarding.service import validate_evidence_reference
        return validate_evidence_reference(db, actor, school_id, learner_id, case_id, reference_id)
    if learner_id is None:
        raise access_denied()
    item = evidence.evidence(db, actor, school_id, reference_id)
    if item.learner_id != learner_id:
        raise access_denied()
    ref = SourceRef(source_id=reference_id, revision=item.current_revision)
    source = EvidenceSourceResolver().resolve(db, actor, school_id, learner_id, "document_draft", [ref])[0]
    return ValidatedEvidenceReference(reference_id, school_id, learner_id, None, item.current_revision, content_digest(source.content))


def safeguarding_rule_context(db, actor, school_id, learner_id, case_id):
    from spesped.contexts.governance.projections import case_requirements
    from spesped.contexts.safeguarding.ports import ReviewedRuleContext
    projection = case_requirements(db, actor, school_id, learner_id, case_id)
    return ReviewedRuleContext.model_validate(asdict(projection))


def configure_contexts(app, settings):
    storage = LocalStorage(settings.evidence_storage_root) if settings.evidence_storage_root is not None else None
    app.state.evidence_storage = storage
    app.state.evidence_scanner = ClamdScanner(str(settings.evidence_clamd_socket)) if settings.evidence_clamd_socket else None
    app.state.evidence_ocr = TesseractOCR(
        tesseract=settings.evidence_tesseract, pdftoppm=settings.evidence_pdftoppm,
        language=settings.evidence_ocr_language,
        tessdata_dir=str(settings.evidence_tessdata_dir) if settings.evidence_tessdata_dir else None,
    ) if settings.evidence_ocr_enabled else None
    attestations = ()
    if settings.ai_synthetic_manifest is not None:
        attestations = read_operator_configuration(settings.ai_synthetic_manifest, SyntheticManifest).entries
    runtime = GatewayRuntime(
        environment=settings.environment,
        providers={p.key: ProviderSpec(p.key, p.endpoint, frozenset(p.capabilities), p.kind,
                                     p.api_key.get_secret_value() if p.api_key else None) for p in settings.ai_providers},
        private_networks=tuple(settings.ai_private_networks),
        remote_synthetic_development=settings.ai_remote_synthetic_development,
        source_resolver=EvidenceSourceResolver(storage, attestations),
        evaluation_suites=load_evaluation_suites(settings.ai_evaluation_suites),
    )
    for provider in runtime.providers.values():
        # The remote boundary is rechecked with real source attestations before
        # any network request. Here a fixed fixture validates operator settings.
        fixture = SourceInput(SourceRef(source_id=UUID(int=1), revision=1), "fixture", "fixture", "embedding", "synthetic",
                              provenance="synthetic_fixture", provenance_reference="startup-boundary-check")
        try:
            validate_provider(runtime, provider, [fixture])
        except ProviderFailure:
            raise ValueError("AI provider does not match the configured processing boundary") from None
    app.state.ai_gateway = runtime
    app.state.governance_evidence_validator = governance_evidence_validator
    from spesped.contexts.safeguarding.service import resolve_case_learner
    from spesped.contexts.plans.service import validate_goal_reference
    app.state.governance_case_scope_resolver = resolve_case_learner
    app.state.safeguarding_rule_context = safeguarding_rule_context
    app.state.evidence_goal_validator = validate_goal_reference
    from spesped.contexts.administration.adapters import (
        NativeAssessmentAuthorityPort, NativeQualificationReadPort,
    )
    app.state.teaching_qualification_port = NativeQualificationReadPort()
    app.state.assessment_authority_port = NativeAssessmentAuthorityPort()
