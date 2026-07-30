import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, RouterProvider, Navigate } from 'react-router-dom'
import './index.css'

import { Shell } from './components/Shell'
import { Landing } from './pages/Landing'
import { Home } from './pages/Home'
import { Dashboard } from './pages/Dashboard'
import { Settings } from './pages/Settings'

// The landing page sits OUTSIDE the shell: it has its own brand bar and no app
// navigation, so it reads as a front door rather than a fourth tab.
const router = createBrowserRouter([
  { path: '/', element: <Landing /> },
  {
    element: <Shell />,
    children: [
      { path: '/home', element: <Home /> },
      { path: '/dashboard', element: <Dashboard /> },
      { path: '/settings', element: <Settings /> },
    ],
  },
  { path: '*', element: <Navigate to="/" replace /> },
])

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
)
