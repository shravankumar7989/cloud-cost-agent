import React from 'react';
import { Activity, Cloud } from 'lucide-react';

export default function DashboardHeader() {
  return (
    <div className="glass-panel flex justify-between items-center" style={{ padding: '16px 24px', marginBottom: '24px' }}>
      <div className="flex items-center gap-4">
        <div style={{ background: 'rgba(59, 130, 246, 0.2)', padding: '12px', borderRadius: '12px' }}>
          <Cloud color="var(--accent-blue)" size={28} />
        </div>
        <div>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 700 }}>Cloud Cost Optimization Agent</h1>
          <div className="text-muted flex items-center gap-2">
            <Activity size={14} color="var(--accent-green)" />
            <span>Real-time autonomous cloud operations</span>
          </div>
        </div>
      </div>
      <div>
        <span className="badge badge-success">Agent Active</span>
      </div>
    </div>
  );
}
