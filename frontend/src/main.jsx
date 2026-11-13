import { StrictMode, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import Riport from './Riport.jsx'

// A Beállításokból visszalépve: ha közben új verzió került élesbe, újratöltünk (a riporton landol),
// mert ebben a nézetben a riport verziófigyelője nem fut.
async function hasNewVersion() {
  const mine = document.querySelector('script[type="module"][src*="assets/index-"]')?.getAttribute('src')
  if (!mine) return false
  try {
    const html = await (await fetch('/', { cache: 'no-store', signal: AbortSignal.timeout(3000) })).text()
    const live = html.match(/assets\/index-[^"']+\.js/)?.[0]
    return !!live && !mine.endsWith(live)
  } catch { return false }
}

function Root() {
  const [view, setView] = useState('riport')
  const back = async () => {
    if (await hasNewVersion()) { window.location.reload(); return }
    setView('riport')
  }
  if (view === 'riport') return <Riport onOpenSettings={() => setView('beallitasok')} />
  return <App onBack={back} />
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <Root />
  </StrictMode>,
)
