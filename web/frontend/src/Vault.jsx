/**
 * Baúl de proxies — guardadas de forma persistente, con uptime.
 */
import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { IcArchive, IcDownload, IcTrash, IcCheck2, IcX } from './Icons.jsx';

const QUALITY_COLOR = { PREMIUM: '#10b981', HIGH: '#3b82f6', MEDIUM: '#f59e0b', LOW: '#ef4444' };
const cleanQ = (q) => (q || '').replace(/[^A-Za-z ]/g, '').trim();

export default function Vault({ vault, reloadVault, adminHeaders }) {
  const [fProto, setFProto] = useState('all');
  const [search, setSearch] = useState('');
  const [verifying, setVerifying] = useState(false);
  const [msg, setMsg] = useState('');

  useEffect(() => { reloadVault(); }, []);

  const del = useCallback(async (id) => { await fetch(`/api/vault/${id}`, { method: 'DELETE' }); reloadVault(); }, [reloadVault]);
  const clearAll = useCallback(async () => {
    if (!window.confirm('¿Vaciar todo el baúl?')) return;
    const r = await fetch('/api/vault', { method: 'DELETE', headers: adminHeaders });
    if (r.status === 403) { alert('Token de admin requerido'); return; }
    reloadVault();
  }, [reloadVault, adminHeaders]);

  const verify = useCallback(async () => {
    setVerifying(true); setMsg('');
    try {
      const r = await fetch('/api/vault/verify', {
        method: 'POST', headers: { 'Content-Type': 'application/json', ...adminHeaders },
        body: JSON.stringify({ prune: true }),
      });
      if (r.status === 403) { setMsg('Token de admin requerido'); return; }
      const d = await r.json();
      setMsg(`${d.alive}/${d.checked} vivas · ${d.removed} eliminadas`);
      reloadVault();
    } finally { setVerifying(false); }
  }, [reloadVault, adminHeaders]);

  const filtered = useMemo(() => vault.filter((r) => {
    if (fProto !== 'all' && r.protocol !== fProto) return false;
    if (search && !r.address.includes(search)) return false;
    return true;
  }), [vault, fProto, search]);

  const download = (fmt) => {
    const content = fmt === 'prefixed' ? filtered.map((r) => `${r.protocol}://${r.address}`).join('\n')
      : fmt === 'json' ? JSON.stringify(filtered, null, 2) : filtered.map((r) => r.address).join('\n');
    const url = URL.createObjectURL(new Blob([content], { type: 'text/plain' }));
    const a = document.createElement('a'); a.href = url; a.download = fmt === 'json' ? 'baul.json' : 'baul.txt'; a.click(); URL.revokeObjectURL(url);
  };

  const uptime = (r) => (r.checks ? Math.round(((r.checks - (r.fails || 0)) / r.checks) * 100) : null);

  return (
    <section className="panel">
      <div className="results-header">
        <h2 className="tool-title"><IcArchive size={20} /> Baúl de proxies <span className="count">{vault.length}</span></h2>
        <div className="filters">
          <input className="search" placeholder="Buscar IP..." value={search} onChange={(e) => setSearch(e.target.value)} />
          <select value={fProto} onChange={(e) => setFProto(e.target.value)}>
            <option value="all">Protocolo</option><option value="http">HTTP</option><option value="https">HTTPS</option>
            <option value="socks4">SOCKS4</option><option value="socks5">SOCKS5</option>
          </select>
          <button className="btn-sm" onClick={() => download('txt')}><IcDownload size={13} /> TXT</button>
          <button className="btn-sm" onClick={() => download('prefixed')}>TXT+</button>
          <button className="btn-sm" onClick={() => download('json')}>JSON</button>
          {vault.length > 0 && <button className="btn-sm" onClick={verify} disabled={verifying}><IcCheck2 size={13} /> {verifying ? 'Verificando…' : 'Re-verificar'}</button>}
          {vault.length > 0 && <button className="btn-sm danger" onClick={clearAll}>Vaciar</button>}
        </div>
      </div>
      {msg && <div className="saved-msg" style={{ marginBottom: 10 }}>{msg}</div>}

      {vault.length === 0 ? (
        <div className="empty-dash"><IcArchive size={40} /><br />Baúl vacío<br /><span>Guarda proxies desde el Checker, el Test rápido o el Auto-refresh</span></div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead><tr><th>Score</th><th>Proxy</th><th>Protocolo</th><th>Calidad</th><th>País</th><th>Latencia</th><th>Uptime</th><th></th></tr></thead>
            <tbody>
              {filtered.map((r) => (
                <tr key={r.id}>
                  <td><span className="score" style={{ background: `hsl(${Math.min(r.score,100)*1.2},70%,45%)` }}>{r.score}</span></td>
                  <td className="mono">{r.address}</td>
                  <td><span className="proto-tag">{r.protocol}</span></td>
                  <td><span style={{ color: QUALITY_COLOR[cleanQ(r.quality)] || '#94a3b8' }}>{cleanQ(r.quality)}</span></td>
                  <td>{r.country}</td>
                  <td className="mono">{Math.round(r.latency_ms)}ms</td>
                  <td className="mono">{uptime(r) === null ? '—' : `${uptime(r)}%`}</td>
                  <td><button className="mini del" onClick={() => del(r.id)} title="Quitar"><IcX size={13} /></button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
