/**
 * Baúl de proxies — guardadas de forma persistente.
 */
import React, { useState, useEffect, useMemo, useCallback } from 'react';

const QUALITY_COLOR = { '⭐ PREMIUM': '#10b981', '🟢 HIGH': '#3b82f6', '🟡 MEDIUM': '#f59e0b', '🔴 LOW': '#ef4444' };

export default function Vault({ vault, reloadVault }) {
  const [fProto, setFProto] = useState('all');
  const [search, setSearch] = useState('');

  useEffect(() => { reloadVault(); }, []);

  const del = useCallback(async (id) => {
    await fetch(`/api/vault/${id}`, { method: 'DELETE' });
    reloadVault();
  }, [reloadVault]);

  const clearAll = useCallback(async () => {
    if (!window.confirm('¿Vaciar todo el baúl? No se puede deshacer.')) return;
    await fetch('/api/vault', { method: 'DELETE' });
    reloadVault();
  }, [reloadVault]);

  const filtered = useMemo(() => vault.filter((r) => {
    if (fProto !== 'all' && r.protocol !== fProto) return false;
    if (search && !r.address.includes(search)) return false;
    return true;
  }), [vault, fProto, search]);

  const download = (fmt) => {
    let content;
    if (fmt === 'txt') content = filtered.map((r) => r.address).join('\n');
    else if (fmt === 'prefixed') content = filtered.map((r) => `${r.protocol}://${r.address}`).join('\n');
    else content = JSON.stringify(filtered, null, 2);
    const url = URL.createObjectURL(new Blob([content], { type: 'text/plain' }));
    const a = document.createElement('a'); a.href = url;
    a.download = fmt === 'json' ? 'baul_proxies.json' : 'baul_proxies.txt'; a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <section className="panel">
      <div className="results-header">
        <h2 className="tool-title">🗄️ Baúl de proxies <span className="count">{vault.length}</span></h2>
        <div className="filters">
          <input className="search" placeholder="Buscar IP..." value={search} onChange={(e) => setSearch(e.target.value)} />
          <select value={fProto} onChange={(e) => setFProto(e.target.value)}>
            <option value="all">Protocolo</option>
            <option value="http">HTTP</option><option value="https">HTTPS</option>
            <option value="socks4">SOCKS4</option><option value="socks5">SOCKS5</option>
          </select>
          <button className="btn-sm" onClick={() => download('txt')}>TXT</button>
          <button className="btn-sm" onClick={() => download('prefixed')}>TXT+</button>
          <button className="btn-sm" onClick={() => download('json')}>JSON</button>
          {vault.length > 0 && <button className="btn-sm danger" onClick={clearAll}>Vaciar</button>}
        </div>
      </div>

      {vault.length === 0 ? (
        <div className="empty-dash">🗄️<br />Baúl vacío<br /><span>Guarda proxies desde el Checker o el Test rápido</span></div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Score</th><th>Proxy</th><th>Protocolo</th><th>Calidad</th><th>País</th><th>Latencia</th><th></th></tr>
            </thead>
            <tbody>
              {filtered.map((r) => (
                <tr key={r.id}>
                  <td><span className="score" style={{ background: `hsl(${Math.min(r.score,100)*1.2},70%,45%)` }}>{r.score}</span></td>
                  <td className="mono">{r.address}</td>
                  <td><span className="proto-tag">{r.protocol}</span></td>
                  <td><span style={{ color: QUALITY_COLOR[r.quality] || '#94a3b8' }}>{r.quality}</span></td>
                  <td>{r.country}</td>
                  <td className="mono">{Math.round(r.latency_ms)}ms</td>
                  <td><button className="row-del" onClick={() => del(r.id)} title="Quitar">✕</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
