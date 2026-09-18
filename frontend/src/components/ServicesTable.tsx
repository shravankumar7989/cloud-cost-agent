import React from 'react';
import { ServiceState, WorkflowReport } from '../types/schemas';
import { AlertTriangle, Server, CheckCircle2, Clock } from 'lucide-react';

interface Props {
  initialState: Record<string, ServiceState>;
  workflow: WorkflowReport;
}

export default function ServicesTable({ initialState, workflow }: Props) {
  const targetServiceId = workflow.initial_observation.service_id;
  const isStale = workflow.final_verification.decision.investigation.summary.includes('stale');
  
  return (
    <div className="glass-panel" style={{ overflow: 'hidden' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
        <thead>
          <tr style={{ background: 'rgba(255,255,255,0.05)', borderBottom: '1px solid var(--panel-border)' }}>
            <th style={{ padding: '16px', fontWeight: 600, fontSize: '0.875rem', color: 'var(--text-secondary)' }}>Service</th>
            <th style={{ padding: '16px', fontWeight: 600, fontSize: '0.875rem', color: 'var(--text-secondary)' }}>Metrics (CPU/Mem/RPM)</th>
            <th style={{ padding: '16px', fontWeight: 600, fontSize: '0.875rem', color: 'var(--text-secondary)' }}>Instances</th>
            <th style={{ padding: '16px', fontWeight: 600, fontSize: '0.875rem', color: 'var(--text-secondary)' }}>Latency</th>
            <th style={{ padding: '16px', fontWeight: 600, fontSize: '0.875rem', color: 'var(--text-secondary)' }}>Version</th>
            <th style={{ padding: '16px', fontWeight: 600, fontSize: '0.875rem', color: 'var(--text-secondary)' }}>Status</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(initialState).map(([id, state]) => {
            const isTarget = id === targetServiceId;
            const rowBg = isTarget ? 'rgba(59, 130, 246, 0.05)' : 'transparent';
            
            // Highlight metrics if it's the target and has issues
            let cpuColor = state.cpu_utilization_percent > 80 ? 'var(--accent-red)' : 'var(--text-primary)';
            let memColor = state.memory_utilization_percent > 80 ? 'var(--accent-red)' : 'var(--text-primary)';
            let latColor = state.latency_ms > state.max_latency_ms ? 'var(--accent-red)' : 'var(--text-primary)';

            if (isTarget && isStale) {
               cpuColor = 'var(--text-secondary)';
               memColor = 'var(--text-secondary)';
            }

            return (
              <tr key={id} style={{ background: rowBg, borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                <td style={{ padding: '16px' }}>
                  <div className="flex items-center gap-2">
                    <Server size={16} color="var(--text-secondary)" />
                    <span style={{ fontWeight: 500 }}>{id}</span>
                  </div>
                  {isTarget && <div style={{ fontSize: '0.75rem', color: 'var(--accent-blue)', marginTop: '4px' }}>Targeted</div>}
                </td>
                <td style={{ padding: '16px', fontSize: '0.875rem' }}>
                  <div style={{ color: cpuColor }}>CPU: {state.cpu_utilization_percent}%</div>
                  <div style={{ color: memColor }}>Mem: {state.memory_utilization_percent}%</div>
                  <div>Trf: {isTarget && isStale ? <span style={{ color: 'var(--accent-red)' }}>5200 (Spiking)</span> : state.traffic_rpm} RPM</div>
                </td>
                <td style={{ padding: '16px', fontSize: '0.875rem' }}>
                  {state.current_instances} (Min: {state.min_instances}, Max: {state.max_instances})
                </td>
                <td style={{ padding: '16px', fontSize: '0.875rem', color: latColor }}>
                  {state.latency_ms}ms <span className="text-muted">/ {state.max_latency_ms}ms</span>
                </td>
                <td style={{ padding: '16px' }}>
                  <span className="badge badge-neutral">{state.state_version}</span>
                </td>
                <td style={{ padding: '16px' }}>
                  {isTarget && isStale ? (
                    <span className="badge badge-warning flex items-center gap-1"><Clock size={12}/> Stale Data</span>
                  ) : state.healthy ? (
                    <span className="badge badge-success flex items-center gap-1"><CheckCircle2 size={12}/> Healthy</span>
                  ) : (
                    <span className="badge badge-error flex items-center gap-1"><AlertTriangle size={12}/> Unhealthy</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
