import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import IntakeWorkspace from './IntakeWorkspace';
import { ApiClient, ApiError } from './api';
import type { IntakeSource } from './types';

const source:IntakeSource={id:'source-1',version:3,state:'needs_clarification',current_revision:2,revision:2,sender:'Synthetic sender',document_type:'notat',received_at:'2026-10-21T08:00:00Z',original_at:null,filename:'synthetic.txt',media_type:'text/plain',digest:'a'.repeat(64),byte_size:32,scan_state:'not_required_note',extraction_state:'ready',issue:null,page_count:1,review_progress:{pending:0,accepted:0,edited:0,rejected:0,confirmed:0},pagination:'source_pages'};
const ok=(items:unknown[]=[])=>({items,total:items.length});
const apiError=(status:number,code:string)=>new ApiError('Try again against current source.',status,code);

describe('document intake source review',()=>{
  it('keeps a restricted inbox error visible and does not fall back to a learner dossier',async()=>{
    const client={intake:vi.fn().mockRejectedValue(apiError(403,'access_denied')),learners:vi.fn().mockResolvedValue(ok()),setSessionExpiredHandler:vi.fn()} as unknown as ApiClient;
    render(<IntakeWorkspace client={client} schoolId="school-1" formatError={e=>e instanceof Error?e.message:'error'}/>);
    expect((await screen.findAllByRole('alert')).some(element=>element.textContent?.includes('Try again against current source.'))).toBe(true);
    expect(client.intake).toHaveBeenCalledWith('school-1');
    expect(screen.queryByText(/elevprofil|dossier/i)).not.toBeInTheDocument();
  });

  it('offers exact-span manual recovery when model proposal access is recalled, and preserves 409 on a stale source',async()=>{
    const user=userEvent.setup();
    const client={
      intake:vi.fn().mockResolvedValue(ok([source])), intakeSource:vi.fn().mockResolvedValue(source),
      intakeProposals:vi.fn().mockRejectedValue(apiError(503,'gateway_unavailable')),
      intakeClarifications:vi.fn().mockResolvedValue(ok()), intakePage:vi.fn().mockResolvedValue({page:1,text:'Synthetic learner read three words.',source_revision:2}),
      recoveryCandidates:vi.fn().mockResolvedValue(ok([{id:'model-field-1',source_id:'source-1',source_revision:2,page:1,span_start:10,span_end:16,field_name:'content'}])),
      recoverManualField:vi.fn().mockRejectedValue(apiError(409,'source_revision_changed')),
      learners:vi.fn().mockResolvedValue(ok()), setSessionExpiredHandler:vi.fn(),
    } as unknown as ApiClient;
    render(<IntakeWorkspace client={client} schoolId="school-1" formatError={e=>e instanceof Error?e.message:'error'}/>);
    await user.click(await screen.findByRole('button',{name:/synthetic.txt/i}));
    expect(await screen.findByText(/Modellforslaget er utilgjengelig eller tilbakekalt/i)).toBeInTheDocument();
    const recovery=await screen.findByRole('heading',{name:'Manuell gjenoppretting av modellfelt'});
    const form=recovery.closest('form')!;
    await user.selectOptions(within(form).getByLabelText('Kildeplassering'),'model-field-1');
    await user.type(within(form).getByLabelText('Verdi kontrollert mot kildeteksten'),'tre ord');
    await user.click(within(form).getByRole('button',{name:'Lagre uavhengig manuelt felt'}));
    expect(client.recoverManualField).toHaveBeenCalledWith('school-1','source-1',expect.objectContaining({expected_version:3,source_revision:2,recovery_of_proposal_id:'model-field-1',page:1,span_start:10,span_end:16,field_name:'content',proposed_value:'tre ord'}));
    expect((await screen.findAllByRole('alert')).some(element=>element.textContent?.includes('Try again against current source.'))).toBe(true);
    expect(await screen.findByText('Synthetic learner read three words.')).toBeInTheDocument();
  });
});
