import { createContext, useContext } from 'react';
import { useDashboardState } from './useDashboardState';

const DashboardContext = createContext(null);

export function DashboardProvider({ children }) {
  const value = useDashboardState();
  return <DashboardContext.Provider value={value}>{children}</DashboardContext.Provider>;
}

export function useDashboard() {
  const value = useContext(DashboardContext);
  if (!value) {
    throw new Error('useDashboard must be used within DashboardProvider');
  }
  return value;
}
