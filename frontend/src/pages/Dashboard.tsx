import React from 'react';
import StaticSetup from '../../components/StaticSetup';
import DynamicMonitor from '../../components/DynamicMonitor';
import LanceControl from '../../components/LanceControl';
import AICopilot from '../../components/AICopilot';
import WhatIfSandbox from '../../components/WhatIfSandbox';

interface DashboardProps {
  processContext: any;
  setProcessContext: any;
}

const Dashboard: React.FC<DashboardProps> = ({ processContext, setProcessContext }) => {
  return (
      <main className="flex-1 overflow-hidden grid grid-cols-1 lg:grid-cols-12 gap-5 p-5 h-full">
        {/* Left Column: Static Setup */}
        <aside className="lg:col-span-3 lg:overflow-y-auto pr-1">
          <StaticSetup processContext={processContext} setProcessContext={setProcessContext} />
        </aside>

        {/* Center Column: Dynamic Monitor & Lance Recommendation */}
        <section className="lg:col-span-6 flex flex-col gap-4 lg:overflow-y-auto pr-1 custom-scrollbar">
          <DynamicMonitor />
          <WhatIfSandbox />
          <LanceControl processContext={processContext} />
        </section>

        {/* Right Column: AI Co-pilot */}
        <aside className="lg:col-span-3 flex flex-col gap-4 overflow-hidden">
          <AICopilot processContext={processContext} />
        </aside>
      </main>
  );
};

export default Dashboard;
