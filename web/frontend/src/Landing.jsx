/**
 * Landing de ventas — hero, features, precios, CTA.
 */
import React from 'react';
import { IcZap, IcShield, IcArchive, IcRotate, IcKey, IcChart, IcCheck, IcSearch } from './Icons.jsx';

const FEATURES = [
  { Ic: IcSearch, t: 'Obtención masiva', d: '30+ fuentes, ~20.000 proxies descargadas y verificadas en paralelo.' },
  { Ic: IcShield, t: 'Doble verificación', d: 'Cada proxy se prueba 2 veces — cero falsos positivos.' },
  { Ic: IcChart, t: 'Scoring y dashboard', d: 'Puntaje 0–100, anonimato, país y gráficos en tiempo real.' },
  { Ic: IcArchive, t: 'Baúl persistente', d: 'Guarda tus mejores proxies y reúsalas cuando quieras.' },
  { Ic: IcRotate, t: 'Rotador en vivo', d: 'Un endpoint que entrega una proxy distinta por petición.' },
  { Ic: IcKey, t: 'API keys', d: 'Vende acceso por cliente con límites y control de uso.' },
];

const PLANS = [
  { name: 'Free', price: '$0', period: '/mes', highlight: false, features: ['100 requests/día', 'Checker masivo', 'Test rápido + limpiador', 'Export TXT/CSV/JSON'] },
  { name: 'Pro', price: '$19', period: '/mes', highlight: true, features: ['10.000 requests/día', 'Rotador en vivo', 'Auto-refresh del baúl', 'Dashboard + uptime', 'Soporte prioritario'] },
  { name: 'Business', price: '$99', period: '/mes', highlight: false, features: ['Requests ilimitadas', 'Múltiples API keys', 'White-label', 'SLA de disponibilidad', 'Despliegue dedicado'] },
];

export default function Landing({ onEnter }) {
  return (
    <div className="landing">
      <section className="hero">
        <div className="hero-badge">Proxy API · Motor async</div>
        <h1 className="hero-title">Proxies frescas y verificadas,<br /><span>listas para usar en segundos</span></h1>
        <p className="hero-sub">
          Obtén, verifica y rota miles de proxies HTTP / SOCKS desde una sola herramienta.
          Móntala como tu propia API de proxies y vende acceso con API keys.
        </p>
        <div className="hero-cta">
          <button className="btn btn-start big" onClick={onEnter}><IcZap size={18} /> Entrar a la app</button>
          <a className="btn-ghost" href="#precios">Ver precios</a>
        </div>
        <div className="hero-stats">
          <div><b>30+</b><span>fuentes</span></div>
          <div><b>~20k</b><span>proxies/escaneo</span></div>
          <div><b>4</b><span>protocolos</span></div>
          <div><b>0</b><span>falsos positivos*</span></div>
        </div>
      </section>

      <section className="features-sec">
        <h2 className="sec-h">Todo en una herramienta</h2>
        <div className="features-grid">
          {FEATURES.map(({ Ic, t, d }) => (
            <div className="feature" key={t}>
              <div className="feature-ic"><Ic size={22} /></div>
              <b>{t}</b><p>{d}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="pricing-sec" id="precios">
        <h2 className="sec-h">Planes</h2>
        <p className="sec-sub">Precios de ejemplo — ajústalos a tu mercado.</p>
        <div className="plans">
          {PLANS.map((pl) => (
            <div className={`plan ${pl.highlight ? 'plan-hl' : ''}`} key={pl.name}>
              {pl.highlight && <span className="plan-tag">Más popular</span>}
              <h3>{pl.name}</h3>
              <div className="plan-price">{pl.price}<span>{pl.period}</span></div>
              <ul>{pl.features.map((f) => <li key={f}><IcCheck size={14} /> {f}</li>)}</ul>
              <button className={pl.highlight ? 'btn btn-start' : 'btn-outline'} onClick={onEnter}>Empezar</button>
            </div>
          ))}
        </div>
      </section>

      <section className="cta-final">
        <h2>¿Listo para tu propia API de proxies?</h2>
        <button className="btn btn-start big" onClick={onEnter}><IcZap size={18} /> Entrar a la app</button>
      </section>
    </div>
  );
}
