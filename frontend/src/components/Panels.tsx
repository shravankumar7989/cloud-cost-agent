import React from 'react';
import { WorkflowReport } from '../types/schemas';
import { Search, Brain, Shield, Zap, CheckSquare } from 'lucide-react';

interface Props {
  workflow: WorkflowReport;
}

export default function Panels({ workflow }: Props) {
  const fv = workflow.final_verification;
  const inv = fv.decision.investigation;
  const prop = fv.decision.proposal;
  const safe = fv.safety_check;
  const exec = fv.execution;

  return (
    <div className="flex-col gap-4">
      {/* Investigation Panel */}
      <div className="glass-card">
        <div className="flex items-center gap-2" style={{ marginBottom: '12px', color: 'var(--accent-blue)' }}>
          <Search size={20} />
          <h3 style={{ fontSize: '1.1rem' }}>Investigation</h3>
        </div>
        <div style={{ marginBottom: '8px' }}>
          <span className="text-muted">Target Service:</span> <span style={{ fontWeight: 600 }}>{inv.observation.service_id}</span>
        </div>
        <div style={{ marginBottom: '8px' }}>
          <span className="text-muted">Identified Issues:</span>
          <ul style={{ marginLeft: '24px', marginTop: '4px', fontSize: '0.875rem' }}>
            {inv.identified_issues.map((issue, idx) => (
              <li key={idx} style={{ color: issue.includes('Stale') || issue.includes('pressure') ? 'var(--accent-red)' : 'var(--text-primary)' }}>
                {issue}
              </li>
            ))}
          </ul>
        </div>
        <div style={{ background: 'rgba(0,0,0,0.2)', padding: '12px', borderRadius: '6px', fontSize: '0.875rem', borderLeft: inv.summary.includes('WARNING') ? '3px solid var(--accent-red)' : '3px solid var(--accent-blue)' }}>
          {inv.summary}
        </div>
      </div>

      {/* Decision Panel */}
      <div className="glass-card">
        <div className="flex items-center gap-2" style={{ marginBottom: '12px', color: 'var(--accent-blue)' }}>
          <Brain size={20} />
          <h3 style={{ fontSize: '1.1rem' }}>Decision</h3>
        </div>
        <div className="grid grid-cols-2 gap-4" style={{ fontSize: '0.875rem' }}>
          <div>
            <div className="text-muted">Proposed Action</div>
            <div style={{ fontWeight: 600, marginTop: '4px' }}>
              <span className={`badge ${prop.action === 'scale_down' ? 'badge-success' : 'badge-warning'}`}>{prop.action}</span>
            </div>
          </div>
          <div>
            <div className="text-muted">Confidence</div>
            <div style={{ fontWeight: 600, marginTop: '4px' }}>{(prop.confidence * 100).toFixed(0)}%</div>
          </div>
          <div style={{ gridColumn: 'span 2' }}>
            <div className="text-muted">Reasoning</div>
            <div style={{ marginTop: '4px' }}>{prop.reason}</div>
          </div>
          <div style={{ gridColumn: 'span 2' }}>
            <div className="text-muted">Expected Effect</div>
            <div style={{ marginTop: '4px' }}>{prop.expected_effect}</div>
          </div>
        </div>
      </div>

      {/* Safety Panel */}
      <div className="glass-card" style={{ borderLeft: safe.is_approved ? '4px solid var(--accent-green)' : '4px solid var(--accent-red)' }}>
        <div className="flex items-center gap-2" style={{ marginBottom: '12px', color: safe.is_approved ? 'var(--accent-green)' : 'var(--accent-red)' }}>
          <Shield size={20} />
          <h3 style={{ fontSize: '1.1rem' }}>Safety Engine</h3>
        </div>
        <div style={{ marginBottom: '12px' }}>
          {safe.is_approved ? (
            <span className="badge badge-success">Approved</span>
          ) : (
            <span className="badge badge-error">Rejected</span>
          )}
        </div>
        {!safe.is_approved && (
          <div>
            <div className="text-muted">Rejection Reasons:</div>
            <ul style={{ marginLeft: '24px', marginTop: '4px', fontSize: '0.875rem', color: '#f87171' }}>
              {safe.rejection_reasons.map((r, i) => <li key={i}>{r}</li>)}
            </ul>
          </div>
        )}
      </div>

      {/* Execution Panel (If active) */}
      {exec && (
        <div className="glass-card" style={{ borderLeft: exec.status === 'SUCCESS' ? '4px solid var(--accent-green)' : '4px solid var(--accent-red)' }}>
          <div className="flex items-center gap-2" style={{ marginBottom: '12px', color: exec.status === 'SUCCESS' ? 'var(--accent-green)' : 'var(--accent-red)' }}>
            <Zap size={20} />
            <h3 style={{ fontSize: '1.1rem' }}>Execution</h3>
          </div>
          <div className="flex items-center gap-4">
            <div>
              <span className={`badge ${exec.status === 'SUCCESS' ? 'badge-success' : 'badge-error'}`}>{exec.status}</span>
            </div>
            {exec.error_code && (
              <div style={{ fontSize: '0.875rem', color: '#f87171', fontWeight: 600 }}>
                Code: {exec.error_code}
              </div>
            )}
          </div>
          {exec.error_message && (
            <div style={{ marginTop: '8px', fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
              {exec.error_message}
            </div>
          )}
        </div>
      )}

      {/* Verification Panel */}
      <div className="glass-card" style={{ background: fv.is_successful ? 'rgba(16, 185, 129, 0.05)' : 'rgba(239, 68, 68, 0.05)' }}>
        <div className="flex items-center gap-2" style={{ marginBottom: '12px' }}>
          <CheckSquare size={20} color={fv.is_successful ? 'var(--accent-green)' : 'var(--accent-red)'} />
          <h3 style={{ fontSize: '1.1rem' }}>Verification</h3>
        </div>
        <div style={{ fontSize: '0.875rem', lineHeight: '1.6' }}>
          {fv.verification_notes}
        </div>
      </div>

    </div>
  );
}
