import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.jsx'

// Inject global keyframes for spinner animation
const style = document.createElement('style');
style.textContent = '@keyframes analytics-spin { to { transform: rotate(360deg); } }';
document.head.appendChild(style);

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
