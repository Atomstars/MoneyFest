import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, RouterProvider, Navigate } from 'react-router-dom'
import './index.css'
import './app.css'
import './identity.css'
import './workspace.css'

import { Shell } from './components/Shell'
import { Landing } from './pages/Landing'
import { Home } from './pages/Home'
import { Dashboard } from './pages/Dashboard'
import { Settings } from './pages/Settings'
import { News } from './pages/News'
import { Funds } from './pages/Funds'
import { Research } from './pages/Research'
import { StockResearchPage } from './pages/StockResearch'
import { PortfolioLab } from './pages/PortfolioLab'
import { USStocks } from './pages/USStocks'
import { SessionGate } from './components/SessionGate'

// The landing page sits OUTSIDE the shell: it has its own brand bar and no app
// navigation, so it reads as a front door rather than a fourth tab.
const router = createBrowserRouter([
  { path: '/', element: <Landing /> },
  {
    element: <SessionGate />,
    children: [{ element: <Shell />, children: [
      { path: '/home', element: <Home /> },
      { path: '/dashboard', element: <Dashboard /> },
      { path: '/us-stocks', element: <USStocks /> },
      { path: '/stock-research', element: <StockResearchPage /> },
      { path: '/portfolio-lab', element: <PortfolioLab /> },
      { path: '/settings', element: <Settings /> },
      { path: '/news', element: <News /> },
      { path: '/funds', element: <Funds /> },
      { path: '/research', element: <Research /> },
    ] }],
  },
  { path: '*', element: <Navigate to="/" replace /> },
])

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
)
