import { Routes, Route, NavLink } from 'react-router-dom';
import NavigationPage from '@/pages/NavigationPage';
import DashboardPage from '@/pages/DashboardPage';
import { Map, LayoutDashboard } from 'lucide-react';
import clsx from 'clsx';

export default function App() {
  return (
    <div className="flex flex-col h-screen bg-gray-950 text-white">
      {/* Top Navigation Bar */}
      <header className="flex items-center gap-6 px-6 py-3 bg-gray-900 border-b border-gray-800 z-50 shrink-0">
        <div className="flex items-center gap-2">
          <Map className="w-5 h-5 text-blue-400" />
          <span className="font-semibold text-sm tracking-wide text-white">Road Intelligence</span>
        </div>
        <nav className="flex gap-1 ml-4">
          <NavLink
            to="/"
            end
            className={({ isActive }) =>
              clsx(
                'flex items-center gap-2 px-3 py-1.5 rounded text-sm font-medium transition-colors',
                isActive
                  ? 'bg-blue-600 text-white'
                  : 'text-gray-400 hover:text-white hover:bg-gray-800'
              )
            }
          >
            <Map className="w-4 h-4" />
            Navigation
          </NavLink>
          <NavLink
            to="/dashboard"
            className={({ isActive }) =>
              clsx(
                'flex items-center gap-2 px-3 py-1.5 rounded text-sm font-medium transition-colors',
                isActive
                  ? 'bg-blue-600 text-white'
                  : 'text-gray-400 hover:text-white hover:bg-gray-800'
              )
            }
          >
            <LayoutDashboard className="w-4 h-4" />
            Dashboard
          </NavLink>
        </nav>
        <div className="ml-auto flex items-center gap-2">
          <span className="inline-flex items-center gap-1.5 text-xs text-green-400">
            <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
            Live
          </span>
        </div>
      </header>

      {/* Page Content */}
      <main className="flex-1 overflow-hidden">
        <Routes>
          <Route path="/" element={<NavigationPage />} />
          <Route path="/dashboard" element={<DashboardPage />} />
        </Routes>
      </main>
    </div>
  );
}
