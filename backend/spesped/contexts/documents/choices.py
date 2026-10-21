"""Bounded, current owner inventories and metadata-only practitioner recovery."""
from datetime import date, datetime, timedelta
from typing import Literal
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, func
from spesped.errors import DomainError
from spesped.contexts.identity import document_choices as identity
from . import models as m, schemas as s, service as svc, adapters as a

Category = Literal['guardians','owners','contributors','templates','obligations','sources','goals','actuals','future_plans']
class Value(BaseModel): model_config = ConfigDict(extra='forbid')
class ChoicePeriod(Value):
    starts_on:date
    ends_on:date
    timezone:str
    starts_at:datetime
    ends_at_exclusive:datetime
class GuardianChoice(Value):
    relationship_id:str
    guardian_user_id:str
    display_name:str
    version:int
    state:Literal['eligible_proposal','unresolved']
    disclosure:Literal['not_authorized']
class StaffChoice(Value):
    user_id:str
    display_name:str
    purpose:Literal['owner','contributor']
    action:Literal['documents.write','documents.contribute']
    state:Literal['eligible']
    assignment_purpose:str|None
class TemplateChoice(Value):
    template_id:str
    revision_id:str
    revision:int
    content_digest:str
    title:str
    kind:s.Kind
    sections:list[s.SectionSpec]
    requirement_version_id:str|None
    effective_from:date
    effective_until:date
    state:Literal['reviewed_current']
class ReportPeriod(Value):
    starts_on:date
    ends_on:date
class ObligationChoice(Value):
    obligation_id:str
    label:str
    requirement_version_id:str
    period_key:str
    state:Literal['applicable','unresolved']
    report_period:ReportPeriod|None
    unresolved_inputs:list[str]
class SourceChoice(Value):
    reference:s.EvidenceRef
    label:str
    source_type:Literal['evidence','observation','assessment_result','progress_review','assessment_statement']
    occurred_at:datetime
    classification:Literal['interval_fact','background_reference']
    state:Literal['current','review_required']
class EffectivePeriod(Value):
    starts_at:datetime
    ends_at_exclusive:datetime
class GoalChoice(Value):
    goal_revision_id:str
    goal_id:str
    plan_revision_id:str
    title:str
    kind:Literal['ordinary_teaching','individual_education']
    effective_period:EffectivePeriod
    applicable_at:datetime
class PupilParticipationChoice(Value):
    category:str
    status:str
    minutes:int
class ActualChoice(Value):
    delivery_revision_id:str
    revision:int
    label:str
    occurred_at:datetime
    state:str
    participation:list[PupilParticipationChoice]
    classification:Literal['actual_delivery_not_learning_progress']
class FutureChoice(Value):
    session_revision_id:str
    revision:int
    title:str
    planned_at:datetime
    state:str
    classification:Literal['future_plan_not_actual']
class ChoicePage(Value):
    category:Category
    items:list[GuardianChoice|StaffChoice|TemplateChoice|ObligationChoice|SourceChoice|GoalChoice|ActualChoice|FutureChoice]
    total:int
    offset:int
    limit:int
    period:ChoicePeriod
class ProposalSelection(Value):
    sections:list[str]
    subject:bool
class ProposalReviewMetadata(Value):
    revision_id:str
    outcome:Literal['applied','rejected','discarded']
    selection:ProposalSelection
    reviewer_id:str
    created_at:datetime
class SuggestionMetadata(Value):
    id:str
    version:int
    state:str
    attempts:int
    created_at:datetime
    updated_at:datetime
    basis_id:str
    availability:Literal['current','review_required']
    reviews:list[ProposalReviewMetadata]
class SuggestionPage(Value):
    items:list[SuggestionMetadata]
    total:int
    offset:int
    limit:int
    manual_fallback_available:Literal[True]
class AssignedSectionMetadata(Value):
    key:str
    label:str
    required:bool
class ContributionMetadata(Value):
    document_id:str
    revision_id:str
    version:int
    kind:s.Kind
    title:str
    sections:list[AssignedSectionMetadata]
class ContributionPage(Value):
    items:list[ContributionMetadata]
    total:int
    offset:int
    limit:int
class RecoveryMetadata(Value):
    document_id:str
    learner_id:str
    kind:s.Kind
    state:Literal['draft','waiting_contributions','in_review','approved','discarded']
    version:int
    revision_id:str
    revision:int
    content_digest:s.Digest
    section_keys:list[s.Tag]
    generated_fields:list[s.Tag]

def calendar_bounds(db,school_id,starts_on,ends_on):
    try: return a.period(db,school_id,starts_on,ends_on)
    except (OverflowError,ValueError):
        raise DomainError('document_period','Choose calendar dates that resolve to real bounded school-timezone instants.',422) from None

def inventory_bounds(category,source_mode,start,end,lower,upper):
    """Narrow inventory selection without changing the report's actual period."""
    if category in {'actuals','goals'} or (category == 'sources' and source_mode == 'interval'):
        if (lower is not None and not start <= lower < end) or (upper is not None and not start < upper <= end):
            raise DomainError('choice_period','Interval facts and historical goals must be narrowed within the report period.',422)
        return lower or start,upper or end
    if category == 'sources' and source_mode == 'background':
        if (lower is not None and lower >= start) or (upper is not None and upper > start):
            raise DomainError('choice_period','Background source narrowing must precede the report period.',422)
        return lower,upper or start
    if category == 'future_plans':
        if (lower is not None and lower < end) or (upper is not None and upper <= end):
            raise DomainError('choice_period','Future plan narrowing must follow the inclusive report period.',422)
        horizon = end+timedelta(days=366) if end.year < 9998 else datetime.max.replace(tzinfo=end.tzinfo)
        selected_start,selected_end = lower or end,upper or horizon
        if selected_start >= selected_end:
            raise DomainError('choice_period','Choose an end after the narrowed future plan start.',422)
        return selected_start,selected_end
    if lower is not None or upper is not None:
        raise DomainError('choice_period','Source narrowing dates apply only to sources, goals, actuals and future plans.',422)
    return None,None

def page(items, offset, limit):
    if offset < 0 or not 1 <= limit <= 100:
        raise DomainError('choice_pagination','Use offset >= 0 and limit between 1 and 100.',422)
    return dict(items=items[offset:offset+limit], total=len(items), offset=offset, limit=limit)

def templates(db, actor, school_id, kind, starts_on, ends_on, query=None):
    statement = select(m.TemplateRevision).join(m.Template, m.Template.id == m.TemplateRevision.template_id).join(
        m.TemplateReview,m.TemplateReview.revision_id == m.TemplateRevision.id).where(
        m.Template.school_id == school_id, m.Template.state == 'active', m.TemplateRevision.number == m.Template.current_revision,
        m.TemplateReview.digest == m.TemplateRevision.digest,
        m.TemplateRevision.content['kind'].as_string() == kind,
        m.TemplateRevision.content['effective_from'].as_string() <= starts_on.isoformat(),
        m.TemplateRevision.content['effective_until'].as_string() >= ends_on.isoformat())
    if query: statement = statement.where(m.TemplateRevision.content['title'].as_string().icontains(query, autoescape=True))
    rows = identity.bounded(db, statement.order_by(m.TemplateRevision.created_at, m.TemplateRevision.id))
    items = []
    for (revision,) in rows:
        try:
            value = svc.template_basis(db,actor,school_id,revision.id,kind,starts_on,ends_on)
            if value['state'] != 'reviewed_current': continue
        except DomainError as exc:
            if exc.status_code not in {403,409}: raise
            continue
        c = value['content']
        items.append(dict(template_id=revision.template_id,revision_id=revision.id,revision=revision.number,
            content_digest=revision.digest,title=c['title'],kind=c['kind'],sections=c['sections'],
            requirement_version_id=c['requirement_version_id'],effective_from=c['effective_from'],effective_until=c['effective_until'],state='reviewed_current'))
    return items

def evidence_sources(db, actor, school_id, learner_id, start, end):
    from spesped.contexts.evidence.service import timeline
    items = []; offset = 0
    while True:
        result = timeline(db,actor,school_id,learner_id,start=start,end=end,certainty='confirmed',offset=offset,limit=100)
        if result['total'] > identity.MAX_CANDIDATES:
            raise DomainError('choice_limit','Narrow source_starts_on/source_ends_on to at most 1000 source candidates.',422)
        for item in result['items']:
            ref = s.EvidenceRef(kind='evidence',id=item['id'],revision=item['revision'],link_id=item['source']['link_id'])
            try: value = a.reference(db,actor,school_id,learner_id,ref)
            except DomainError as exc:
                if exc.status_code not in {403,409}: raise
                continue
            excerpt = value['value'].get('controlled_excerpt')
            label = excerpt if isinstance(excerpt,str) else value['value'].get('topic') or 'Confirmed evidence'
            items.append(dict(reference={**value['reference'],'digest':value['digest']},label=label[:200],
                source_type='evidence',occurred_at=value['value']['occurred_at'],state='current'))
        offset += len(result['items'])
        if offset >= result['total']: break
    return items

@svc.read_contract
def choices(db, actor, school_id, learner_id, category, kind, starts_on, ends_on, *,
            offset=0, limit=50, requirement_version_id=None, source_mode='interval', source_starts_on=None, source_ends_on=None, query=None):
    svc.access(db,actor,school_id,learner_id,'documents.write')
    if ends_on < starts_on or ends_on == date.max:
        raise DomainError('document_period','Choose an ordered, bounded calendar interval.',422)
    start,end,tz = calendar_bounds(db,school_id,starts_on,ends_on)
    if source_starts_on and source_ends_on and source_starts_on > source_ends_on:
        raise DomainError('document_period','Source narrowing dates must be ordered.',422)
    if source_starts_on == date.max or source_ends_on == date.max:
        raise DomainError('document_period','Choose bounded source narrowing dates.',422)
    if query and category not in {'guardians','owners','contributors','templates','obligations'}:
        raise DomainError('choice_query','Use source narrowing dates for this category.',422)
    lower = calendar_bounds(db,school_id,source_starts_on,source_starts_on)[0] if source_starts_on else None
    upper = calendar_bounds(db,school_id,source_ends_on,source_ends_on)[1] if source_ends_on else None
    lower,upper = inventory_bounds(category,source_mode,start,end,lower,upper)
    if category == 'guardians': items = identity.guardians(db,actor,school_id,learner_id,query)
    elif category in {'owners','contributors'}: items = identity.staff(db,actor,school_id,learner_id,'owner' if category == 'owners' else 'contributor',query)
    elif category == 'templates': items = templates(db,actor,school_id,kind,starts_on,ends_on,query)
    elif category == 'obligations':
        from spesped.contexts.governance.document_choices import obligations
        items = obligations(db,actor,school_id,learner_id,kind,starts_on,ends_on,requirement_version_id,query)
    elif category == 'goals':
        from spesped.contexts.plans.document_choices import goals
        items = goals(db,actor,school_id,learner_id,lower,upper)
    elif category in {'actuals','future_plans'}:
        from spesped.contexts.teaching.document_choices import actuals, future_plans
        items = actuals(db,actor,school_id,learner_id,lower,upper) if category == 'actuals' else future_plans(db,actor,school_id,learner_id,lower,upper)
    elif category == 'sources':
        from spesped.contexts.teaching.document_choices import observations
        from spesped.contexts.assessment.document_choices import sources
        if source_mode not in {'interval','background'}: raise DomainError('source_mode','Choose interval or background.',422)
        items = []
        if lower is None or lower < upper:
            for port in (evidence_sources,observations,sources):
                try: items.extend(port(db,actor,school_id,learner_id,lower,upper))
                except DomainError as exc:
                    if exc.status_code != 403: raise
        for item in items: item['classification'] = 'interval_fact' if source_mode == 'interval' else 'background_reference'
        items.sort(key=lambda v:(str(v['occurred_at']),v['source_type'],str(v['reference']['id'])))
    else: raise DomainError('choice_category','Unknown document choice category.',422)
    return ChoicePage.model_validate(dict(category=category,**page(items,offset,limit),period=dict(
        starts_on=starts_on,ends_on=ends_on,timezone=tz,starts_at=start,ends_at_exclusive=end))).model_dump(mode='json')

@svc.read_contract
def suggestions(db, actor, school_id, identity, runtime, offset=0, limit=50):
    from spesped.contexts.platform.service import source_job_summaries
    row = svc.get(db,m.DocumentCase,school_id,identity)
    svc.access(db,actor,school_id,row.learner_id,'documents.write')
    page([],offset,limit)
    revision = svc.current(db,row)
    result = source_job_summaries(db,actor,school_id,row.learner_id,
        'guardian_email_drafting' if row.kind == 'guardian_email' else 'report_drafting',
        [revision.snapshot_id],runtime,offset=offset,limit=limit)
    for item in result['items']:
        reviews = db.scalars(select(m.ProposalReview).where(m.ProposalReview.school_id == school_id,
            m.ProposalReview.document_id == row.id,m.ProposalReview.job_id == item['id']).order_by(m.ProposalReview.created_at,m.ProposalReview.id))
        item['reviews'] = [dict(revision_id=r.revision_id,outcome=r.outcome,selection=r.selection,
            reviewer_id=r.reviewer_id,created_at=r.created_at) for r in reviews]
    return a.encode({**result,'offset':offset,'limit':limit})

@svc.read_contract
def contribution_inbox(db, actor, school_id, learner_id, offset=0, limit=50):
    svc.access(db,actor,school_id,learner_id,'documents.contribute')
    page([],offset,limit)
    assigned = select(m.ContributionAssignment.revision_id).where(m.ContributionAssignment.school_id == school_id,
        m.ContributionAssignment.contributor_id == actor.user_id)
    statement = select(m.DocumentCase,m.DocumentRevision).join(m.DocumentRevision,m.DocumentRevision.document_id == m.DocumentCase.id).where(
        m.DocumentCase.school_id == school_id,m.DocumentCase.learner_id == learner_id,m.DocumentCase.state != 'discarded',
        m.DocumentRevision.number == m.DocumentCase.current_revision,m.DocumentRevision.id.in_(assigned))
    total = db.scalar(select(func.count()).select_from(statement.subquery()))
    rows = db.execute(statement.order_by(m.DocumentCase.created_at,m.DocumentCase.id).offset(offset).limit(limit))
    items = []
    for row,rev in rows:
        assignment = list(db.scalars(select(m.ContributionAssignment).where(m.ContributionAssignment.school_id == school_id,
            m.ContributionAssignment.revision_id == rev.id,m.ContributionAssignment.contributor_id == actor.user_id).order_by(m.ContributionAssignment.section_key)))
        # The inbox exposes only assignment metadata; source/text validation
        # occurs on opening the established curated contribution workspace.
        items.append(dict(document_id=row.id,revision_id=rev.id,version=row.version,kind=row.kind,
            title=row.kind.replace('_',' '),sections=[dict(key=v.section_key,label=v.section_key,required=v.required) for v in assignment]))
    return dict(items=items,total=total,offset=offset,limit=limit)
