/**
 * Gestión de API Keys — para vender acceso al rotador.
 */
import React, { useState, useEffect, useCallback } from 'react';
import { IcKey, IcCopy, IcCheck, IcPause, IcPlay, IcX } from './Icons.jsx';

export default function ApiKeys({ keys, reloadKeys, adminHeaders }) {
  const [label, setLabel] = useState('');
  const [rateLimit, setRateLimit] = useState(0);
  const [creating, setCreating] = useState(false);
  const [newKey, setNewKey] = useState('');
  const [copiedId, setCopiedId] = useState(null);

  useEffect(() => { reloadKeys(); }, []);

  const create = useCallback(async () => {
    setCreating(true);
    try {
      const r = await fetch('/api/keys', {
        method: 'POST', headers: { 'Content-Type': 'application/json', ...adminHeaders },
        body: JSON.stringify({ label, rate_limit: rateLimit }),
      });
      if (r.status === 403) { alert('Token de admin requerido o inválido'); return; }
      const d = await r.json();
      setNewKey(d.key); setLabel(''); setRateLimit(0); reloadKeys();
    } finally { setCreating(false); }
  }, [label, rateLimit, reloadKeys, adminHeaders]);

  const toggle = async (id) => { await fetch(`/api/keys/${id}/toggle`, { method: 'POST', headers: adminHeaders }); reloadKeys(); };
  const del = async (id) => {
    if (!window.confirm('¿Revocar esta API key? El cliente perderá acceso.')) return;
    await fetch(`/api/keys/${id}`, { method: 'DELETE', headers: adminHeaders }); reloadKeys();
  };
  const copy = async (k, id) => { await navigator.clipboard.writeText(k); setCopiedId(id); setTimeout(() => setCopiedId(null), 1500); };

  return (
    <section className="panel">
      <h2 className="tool-title"><IcKey size={20} /> API Keys — vende acceso a tu API de proxies</h2>
      <p className="tool-desc">
        Crea una key por cliente con su límite diario. Cada cliente usa su key contra el <b>rotador</b>
        (<span className="mono">/api/proxy</span>). Puedes pausar o revocar el acceso cuando quieras.
      </p>

      <div className="keys-create">
        <input className="quick-input" placeholder="Nombre del cliente / plan (ej: ACME - Pro)" value={label} onChange={(e) => setLabel(e.target.value)} disabled={creating} />
        <div className="field" style={{ minWidth: 160 }}>
          <label>Límite diario (0 = ∞)</label>
          <input type="number" min={0} step={100} value={rateLimit} onChange={(e) => setRateLimit(Number(e.target.value))} disabled={creating} />
        </div>
        <button className="btn btn-start" onClick={create} disabled={creating}><IcKey size={15} /> Generar key</button>
      </div>

      {newKey && (
        <div className="newkey-banner">
          <div>
            <b><IcCheck size={14} /> Nueva API key creada</b>
            <p>Cópiala ahora y entrégala al cliente:</p>
            <code className="newkey">{newKey}</code>
          </div>
          <button className="btn-sm" onClick={() => navigator.clipboard.writeText(newKey)}><IcCopy size={13} /> Copiar</button>
        </div>
      )}

      {keys.length > 0 && (
        <div className="table-wrap" style={{ marginTop: 18 }}>
          <table>
            <thead><tr><th>Estado</th><th>Etiqueta</th><th>Key</th><th>Hoy / Límite</th><th>Total</th><th>Último uso</th><th></th></tr></thead>
            <tbody>
              {keys.map((k) => (
                <tr key={k.id} style={{ opacity: k.active ? 1 : 0.5 }}>
                  <td><span className={k.active ? 'badge-on' : 'badge-off'}>{k.active ? 'Activa' : 'Pausada'}</span></td>
                  <td>{k.label}</td>
                  <td className="mono key-cell">{k.key.slice(0, 14)}…{k.key.slice(-4)}
                    <button className="mini" onClick={() => copy(k.key, k.id)}>{copiedId === k.id ? <IcCheck size={12} /> : <IcCopy size={12} />}</button>
                  </td>
                  <td className="mono">{k.requests_today || 0} / {k.rate_limit ? k.rate_limit : '∞'}</td>
                  <td className="mono">{k.requests}</td>
                  <td className="mono">{k.last_used ? new Date(k.last_used).toLocaleString() : '—'}</td>
                  <td>
                    <button className="mini" onClick={() => toggle(k.id)} title={k.active ? 'Pausar' : 'Activar'}>{k.active ? <IcPause size={12} /> : <IcPlay size={12} />}</button>
                    <button className="mini del" onClick={() => del(k.id)} title="Revocar"><IcX size={12} /></button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="callout">
        <b>Antes de exponer en internet:</b> define la variable de entorno <span className="mono">ADMIN_TOKEN</span> en el
        servidor y pégala arriba (campo "admin token") para proteger este panel. Sin ella, está abierto solo para uso local.
      </div>
    </section>
  );
}
