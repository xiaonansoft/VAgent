import React, { useState } from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Header from './components/Header';
import Dashboard from './src/pages/Dashboard';
import History from './src/pages/History';
import SelfLearning from './src/pages/SelfLearning';
import Settings from './src/pages/Settings';
import { LanguageProvider } from './src/contexts/LanguageContext';

const AppLayout: React.FC = () => {
  const [processContext, setProcessContext] = useState({
    iron_temp_c: 1340,
    si_content_pct: 0.28,
    is_one_can: true,
  });

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-[#0b1116] text-white">
      <Header />
      <Routes>
        <Route path="/" element={<Dashboard processContext={processContext} setProcessContext={setProcessContext} />} />
        <Route path="/history" element={<History />} />
        <Route path="/learning" element={<SelfLearning />} />
        <Route path="/settings" element={<Settings />} />
      </Routes>
    </div>
  );
};

const App: React.FC = () => {
  return (
    <LanguageProvider>
      <Router>
        <AppLayout />
      </Router>
    </LanguageProvider>
  );
};

export default App;
