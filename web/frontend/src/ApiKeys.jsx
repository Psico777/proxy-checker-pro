/**
 * Gestión de API Keys — para vender acceso al rotador.
 */
import React, { useState, useEffect, useCallback } from 'react';

export default function ApiKeys({ keys, reloadKeys }) {
  const [label, setLabel] = useState('');
  const [creating, setCreating] = useState(false);
  const [newKey, setNewKey] = useState('');
  const [copiedId, setCopiedId] = useState(null);

  useEffect(() => { reloadKeys(); }, []);

  const create = useCallback(async () => {
    setCreating(true);
    try {
      const r = await fetch('/api/keys', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ label }),
      });
      const d = await r.json();
      setNewKey(d.key);
      setLabel('');
      reloadKeys();
    } finally { setCreating(false); }
  }, [label, reloadKeys]);

  const toggle = async (id) => { await fetch(`/api/keys/${id}/toggle`, { method: 'POST' }); reloadKeys(); };
  const del = async (id) => {
    if (!window.confirm('¿Revocar esta API key? El cliente perderá acceso.')) return;
    await fetch(`/api/keys/${id}`, { method: 'DELETE' }); reloadKeys();
  };
  const copy = async (k, id) => {
    await navigator.clipboard.writeText(k); setCopiedId(id); setTimeout(() => setCopiedId(null), 1500);
  };

  return (
    <section className="panel">
      <h2 className="tool-title">🔑 API Keys — vende acceso a tu API de proxies</h2>
      <p className="tool-desc">
        Crea una key por cliente. Cada cliente usa su key contra el <b>rotador</b> (<span className="mono">/api/proxy</span>)
        para obtener proxies frescas. Puedes revocar o pausar el acceso cuando quieras.
      </p>

      <div className="quick-row">
        <input className="quick-input" placeholder="Nombre del cliente / plan (ej: Cliente ACME - Plan Pro)"
          value={label} onChange={(e) => setLabel(e.target.value)} disabled={creating} />
        <button className="btn btn-start" onClick={create} disabled={creating}>+ Generar key</button>
      </div>

      {newKey && (
        <div className="newkey-banner">
          <div>
            <b>✓ Nueva API key creada</b>
            <p>Cópiala ahora y entrégala al cliente:</p>
            <code className="newkey">{newKey}</code>
          </div>
          <button className="btn-sm" onClick={() => { navigator.clipboard.writeText(newKey); }}>Copiar</button>
        </div>
      )}

      {keys.length > 0 && (
        <div className="table-wrap" style={{ marginTop: 18 }}>
          <table>
            <thead>
              <tr><th>Estado</th><th>Etiqueta</th><th>Key</th><th>Requests</th><th>Último uso</th><th></th></tr>
            </thead>
            <tbody>
              {keys.map((k) => (
                <tr key={k.id} style={{ opacity: k.active ? 1 : 0.5 }}>
                  <td><span className={k.active ? 'badge-on' : 'badge-off'}>{k.active ? 'Activa' : 'Pausada'}</span></td>
                  <td>{k.label}</td>
                  <td className="mono key-cell">
                    {k.key.slice(0, 14)}…{k.key.slice(-4)}
                    <button className="mini" onClick={() => copy(k.key, k.id)}>{copiedId === k.id ? '✓' : '⧉'}</button>
                  </td>
                  <td className="mono">{k.requests}</td>
                  <td className="mono">{k.last_used ? new Date(k.last_used).toLocaleString() : '—'}</td>
                  <td>
                    <button className="mini" onClick={() => toggle(k.id)} title={k.active ? 'Pausar' : 'Activar'}>{k.active ? '⏸' : '▶'}</button>
                    <button className="mini del" onClick={() => del(k.id)} title="Revocar">✕</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="callout">
        ⚠️ <b>Antes de exponer en internet:</b> protege los endpoints <span className="mono">/api/keys*</span> (panel admin) con
        autenticación. Aquí están abiertos para uso local.
      </div>
    </section>
  );
}
