import React from 'react';
import { Scenario } from '../types/schemas';
import { scenarios } from '../data/scenarios';
import { Play, RotateCcw } from 'lucide-react';

interface Props {
  scenario: Scenario | null;
  onRunScenario: (id: string) => void;
  onClear: () => void;
}

export default function SystemStatus({ scenario, onRunScenario, onClear }: Props) {
  // Compute some derived status metrics based on the current scenario
  const serviceCount = scenario ? Object.keys(scenario.initialState).length : 3;
  let totalCost = scenario 
    ? Object.values(scenario.initialState).reduce((acc, s) => acc + (s.cost_per_hour * s.current_instances), 0)
    : 154.5;
    
  if (scenario?.workflow.final_verification.is_successful && scenario.workflow.final_verification.execution?.action === 'scale_down') {
    // mock adjusting cost for UI display to show savings
    totalCost -= 6.0;
  }

  return (
    <div className="glass-panel" style={{ padding: '24px', marginBottom: '24px' }}>
      <div className="flex justify-between items-center" style={{ marginBottom: '24px' }}>
        <h2 style={{ fontSize: '1.25rem' }}>System Status</h2>
        
        <div className="flex gap-2">
          {scenarios.map(s => (
            <button 
              key={s.id}
              onClick={() => onRunScenario(s.id)}
              className={`btn ${scenario?.id === s.id ? 'btn-active animate-pulse-glow' : ''} flex items-center gap-2`}
            >
              <Play size={16} />
              {s.name}
            </button>
          ))}
          {scenario && (
            <button onClick={onClear} className="btn flex items-center gap-2" style={{ marginLeft: '12px' }}>
              <RotateCcw size={16} /> Reset
            </button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-4 gap-6">
        <div className="glass-card">
          <div className="text-muted" style={{ marginBottom: '4px' }}>Total Est. Cost</div>
          <div style={{ fontSize: '2rem', fontWeight: 700, color: 'var(--accent-green)' }}>
            ${totalCost.toFixed(2)}<span style={{ fontSize: '1rem', color: 'var(--text-secondary)' }}>/hr</span>
          </div>
        </div>
        <div className="glass-card">
          <div className="text-muted" style={{ marginBottom: '4px' }}>Services Monitored</div>
          <div style={{ fontSize: '2rem', fontWeight: 700 }}>{serviceCount}</div>
        </div>
        <div className="glass-card">
          <div className="text-muted" style={{ marginBottom: '4px' }}>Active Recommendations</div>
          <div style={{ fontSize: '2rem', fontWeight: 700, color: scenario ? 'var(--accent-blue)' : 'var(--text-primary)' }}>
            {scenario ? '1' : '0'}
          </div>
        </div>
        <div className="glass-card">
          <div className="text-muted" style={{ marginBottom: '4px' }}>Last Workflow Status</div>
          <div style={{ marginTop: '8px' }}>
            {!scenario && <span className="badge badge-neutral">Idle</span>}
            {scenario?.workflow.final_verification.is_successful && <span className="badge badge-success">Verified Success</span>}
            {scenario?.workflow.final_verification.is_successful === false && <span className="badge badge-error">Action Rejected / Failed</span>}
          </div>
        </div>
      </div>
    </div>
  );
}
