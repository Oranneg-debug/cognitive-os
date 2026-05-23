"""Test governance unit of work."""

from src.workflow_models import ValidatedProposal, ApprovalRecord, Severity, WorkflowPhase
from src.governance_unit_of_work import governance_unit_of_work
from datetime import datetime

def test_governance_uow():
    """Test governance unit of work."""
    p = ValidatedProposal(
        proposal_id='TEST-002',
        severity=Severity.HIGH,
        origin='test',
        workflow_version='1.0',
        phase=WorkflowPhase.PROPOSAL,
        status='draft',
        body='# Test Body'
    )
    
    r = ApprovalRecord(
        proposal_id='TEST-002',
        approver='alice',
        decision='APPROVE',
        reason='Looks good',
        timestamp=datetime.now(),
        state_hash='abc123'
    )
    
    with governance_unit_of_work() as uow:
        a = uow.snapshot_proposal(p, WorkflowPhase.PROPOSAL)
        print(f'Snapshot queued: {a.proposal_id}')
        
        uow.log_decision(r)
        print('Decision logged')
    
    print('Unit of work committed successfully')

if __name__ == '__main__':
    test_governance_uow()