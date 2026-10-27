import { DashboardProvider } from './app/DashboardContext';
import { Shell } from './features/shell/Shell';

export default function App() {
  return (
    <DashboardProvider>
      <Shell />
    </DashboardProvider>
  );
}
