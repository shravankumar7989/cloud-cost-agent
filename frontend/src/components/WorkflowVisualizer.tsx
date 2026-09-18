import React from 'react';
import { WorkflowReport } from '../types/schemas';
import { CheckCircle2, XCircle, AlertCircle, Clock, ArrowRight } from 'lucide-react';

interface Props {
  workflow: WorkflowReport;
}

export default function WorkflowVisualizer({ workflow }: Props) {
  const fv = workflow.final_verification;
  const isScaleDown = fv.decision.proposal.action === 'scale_down';
  const isStale = fv.decision.investigation.summary.includes('stale');

  // Derive statuses
  const status = {
    observe: 'success',
    investigate: isStale ? 'warning' : 'success',
    decide: 'success',
    safety: fv.safety_check.is_approved ? 'success' : 'rejected',
    act: !fv.safety_check.is_approved ? 'pending' : (fv.execution?.status === 'SUCCESS' ? 'success' : 'failed'),
    verify: fv.is_successful ? 'success' : 'failed',
    recover: fv.is_successful ? 'pending' : (isStale ? 'pending' : 'active')
  };

  const stages = [
    { id: 'observe', label: 'Observe' },
    { id: 'investigate', label: 'Investigate' },
    { id: 'decide', label: 'Decide' },
    { id: 'safety', label: 'Safety' },
    { id: 'act', label: 'Act' },
    { id: 'verify', label: 'Verify' },
    { id: 'recover', label: 'Recover' },
  ];

  const getIcon = (s: string) => {
    switch(s) {
      case 'success': return <CheckCircle2 size={24} color="#34d399" />;
      case 'rejected': return <XCircle size={24} color="#f59e0b" />;
      case 'failed': return <XCircle size={24} color="#f87171" />;
      case 'warning': return <AlertCircle size={24} color="#fbbf24" />;
      case 'active': return <AlertCircle size={24} color="#60a5fa" />;
      default: return <Clock size={24} color="var(--text-secondary)" />;
    }
  };

  const getColor = (s: string) => {
    switch(s) {
      case 'success': return '#34d399';
      case 'rejected': return '#f59e0b';
      case 'failed': return '#f87171';
      case 'warning': return '#fbbf24';
      case 'active': return '#60a5fa';
      default: return 'var(--text-secondary)';
    }
  };

  return (
    <div className="glass-panel" style={{ padding: '32px', marginBottom: '24px' }}>
      <div className="flex items-center justify-between">
        {stages.map((stage, idx) => {
          const st = status[stage.id as keyof typeof status];
          return (
            <React.Fragment key={stage.id}>
              <div className="flex-col items-center gap-2" style={{ width: '80px', textAlign: 'center' }}>
                <div style={{ 
                  background: 'rgba(255,255,255,0.05)', 
                  padding: '12px', 
                  borderRadius: '50%',
                  border: `2px solid ${getColor(st)}`,
                  boxShadow: st !== 'pending' ? `0 0 15px ${getColor(st)}40` : 'none'
                }}>
                  {getIcon(st)}
                </div>
                <div style={{ fontSize: '0.875rem', fontWeight: 500, color: getColor(st) }}>
                  {stage.label}
                </div>
              </div>
              {idx < stages.length - 1 && (
                <div style={{ flex: 1, display: 'flex', justifyContent: 'center' }}>
                  <ArrowRight color="var(--text-secondary)" opacity={0.5} />
                </div>
              )}
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
}
