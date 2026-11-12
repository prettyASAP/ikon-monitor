import { StrictMode, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import Riport from './Riport.jsx'

function Root() {
  const [view, setView] = useState('riport')
  if (view === 'riport') return <Riport onOpenSettings={() => setView('beallitasok')} />
  return <App onBack={() => setView('riport')} />
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <Root />
  </StrictMode>,
)
