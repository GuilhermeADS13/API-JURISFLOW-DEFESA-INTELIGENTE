/*
=========================================================
SETOR 1 — INICIALIZAÇÃO DO REACT
Esse arquivo conecta o React ao HTML.
=========================================================
*/

import React from 'react'
import ReactDOM from 'react-dom/client'
import 'bootstrap/dist/css/bootstrap.min.css'
import './styles.css'
import App from './App'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)