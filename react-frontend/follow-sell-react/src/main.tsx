import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import ReactApp from "./ReactApp";

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ReactApp  />
  </StrictMode>,
)
