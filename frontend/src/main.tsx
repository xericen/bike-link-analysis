import { createRoot } from 'react-dom/client'
import App from './App'
import './style.css'
// Analysis endpoints can run expensive graph algorithms. Avoid development-only StrictMode
// effect replays that issue identical API requests twice; backend tests cover side effects.
createRoot(document.getElementById('root')!).render(<App/>)
