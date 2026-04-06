import { Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout.jsx';
import VesselMap from './components/VesselMap.jsx';
import PortDashboard from './components/PortDashboard.jsx';
import ChokepointView from './components/ChokepointView.jsx';
import ReroutingTab from './components/ReroutingTab.jsx';
import AIAdvisor from './components/AIAdvisor.jsx';

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="/vessels" replace />} />
        <Route path="/vessels" element={<VesselMap />} />
        <Route path="/ports" element={<PortDashboard />} />
        <Route path="/chokepoints" element={<ChokepointView />} />
        <Route path="/rerouting" element={<ReroutingTab />} />
        <Route path="/advisor" element={<AIAdvisor />} />
        <Route path="*" element={<Navigate to="/vessels" replace />} />
      </Route>
    </Routes>
  );
}
