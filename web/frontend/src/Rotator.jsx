/**
 * Rotador en vivo — endpoint que entrega una proxy fresca por petición.
 */
import React, { useState, useMemo, useCallback } from 'react';
import { IcRotate, IcRefresh, IcCopy } from './Icons.jsx';

export default function Rotator({ keys, vaultCount, reloadVault, adminHeaders }) {
  const activeKeys = keys.filter((k) => k.active);
  const [selKey, setSelKey] = useState('');
  const [protocol, setProtocol] = useState('');
  const [minScore, setMinScore] = useState(0);
  const [last, setLast] = useState(null);
  const [err, setErr] = useState('');
  const [refreshing, setRefreshing] = useState(false);
  const [refreshMsg, setRefreshMsg] = useState('');

  const keyVal = selKey || (activeKeys[0]?.key || '');
  const base = `${window.location.origin}/api/proxy`;

  const params = useMemo(() => {
    const p = new URLSearchParams();
    if (protocol) p.set('protocol', protocol);
    if (minScore) p.set('min_score', String(minScore));
    return p.toString();
  }, [protocol, minScore]);

  const fullUrl = `${base}?key=${keyVal || 'TU_API_KEY'}${params ? '&' + params : ''}`;

  const getNext = useCallback(async () => {
    setErr(''); setLast(null);
    if (!keyVal) { setErr('Crea o selecciona una API key primero (pestaña API Keys)'); return; }
    try {
      const r = await fetch(`${base}?key=${keyVal}${params ? '&' + params : ''}`);
      const d = await r.json();
      if (!r.ok) { setErr(d.detail || 'Error'); return; }
      setLast(d);
    } catch (e) { setErr(e.message); }
  }, [keyVal, params, base]);

  const refresh = useCallback(async () => {
    setRefreshing(true); setRefreshMsg('');
    try {
      const r = await fetch('/api/vault/refresh', {
        method: 'POST', headers: { 'Content-Type': 'application/json', ...(adminHeaders || {}) }, body: JSON.stringify({ limit: 600 }),
      });
      if (r.status === 403) { setRefreshMsg('Token de admin requerido'); return; }
      const d = await r.json();
      setRefreshMsg(`${d.alive} vivas (${d.added} nuevas) · baúl: ${d.total}`);
      reloadVault?.();
    } catch (e) { setRefreshMsg('Error: ' + e.message); }
    finally { setRefreshing(false); }
  }, [reloadVault, adminHeaders]);

  const snippets = {
    cURL: `curl "${fullUrl}"`,
    Python: `import requests
r = requests.get("${base}", params={"key": "${keyVal || 'TU_API_KEY'}"${protocol ? `, "protocol": "${protocol}"` : ''}${minScore ? `, "min_score": ${minScore}` : ''}})
proxy = r.json()["proxy"]   # ej: socks5://1.2.3.4:1080`,
    'Texto plano': `curl "${fullUrl}&format=text"`,
  };

  return (
    <section className="panel">
      <h2 className="tool-title"><IcRotate size={20} /> Rotador en vivo</h2>
      <p className="tool-desc">
        Un endpoint que entrega <b>una proxy distinta en cada petición</b> (round-robin) desde tu baúl.
        Ideal para scrapers y bots — y para <b>vender acceso</b> con API keys.
      </p>

      <div className="rotator-bar">
        <div className="field">
          <label>API key</label>
          <select value={keyVal} onChange={(e) => setSelKey(e.target.value)}>
            {activeKeys.length === 0 && <option value="">— crea una en API Keys —</option>}
            {activeKeys.map((k) => <option key={k.id} value={k.key}>{k.label} ({k.key.slice(0, 12)}…)</option>)}
          </select>
        </div>
        <div className="field">
          <label>Protocolo</label>
          <select value={protocol} onChange={(e) => setProtocol(e.target.value)}>
            <option value="">Cualquiera</option>
            <option value="http">HTTP</option><option value="https">HTTPS</option>
            <option value="socks4">SOCKS4</option><option value="socks5">SOCKS5</option>
          </select>
        </div>
        <div className="field">
          <label>Score mínimo</label>
          <input type="number" min={0} max={100} step={10} value={minScore} onChange={(e) => setMinScore(Number(e.target.value))} />
        </div>
      </div>

      <div className="endpoint-box">
        <span className="ep-label">ENDPOINT</span>
        <code className="mono">{fullUrl}</code>
        <button className="btn-sm" onClick={() => navigator.clipboard.writeText(fullUrl)}>Copiar</button>
      </div>

      <div className="actions">
        <button className="btn btn-start" onClick={getNext}><IcRotate size={16} /> Obtener siguiente</button>
        <button className="btn-sm" onClick={refresh} disabled={refreshing}>
          <IcRefresh size={13} /> {refreshing ? 'Refrescando baúl...' : 'Refrescar baúl (escaneo rápido)'}
        </button>
        <span className="status">Baúl: {vaultCount} proxies {refreshMsg && `· ${refreshMsg}`}</span>
      </div>

      {err && <div className="tool-error">❌ {err}</div>}

      {last && (
        <div className="result-card alive" style={{ marginTop: 16 }}>
          <div className="rc-head">
            <span className="big-status mono">{last.proxy}</span>
            <span className="score-big" style={{ background: `hsl(${Math.min(last.score,100)*1.2},70%,45%)` }}>{last.score}</span>
          </div>
          <div className="rc-grid">
            <div><label>Protocolo</label><span className="proto-tag">{last.protocol}</span></div>
            <div><label>Calidad</label><span>{last.quality}</span></div>
            <div><label>Anonimato</label><span>{last.anon_level}</span></div>
            <div><label>País</label><span>{last.country}</span></div>
            <div><label>Latencia</label><span className="mono">{Math.round(last.latency_ms)}ms</span></div>
            <div><label>Pool</label><span>{last.pool_size} proxies</span></div>
          </div>
        </div>
      )}

      <h3 className="guide-h" style={{ marginTop: 24 }}>Cómo lo usa tu cliente</h3>
      {Object.entries(snippets).map(([name, code]) => (
        <div className="code-block" key={name}>
          <div className="code-head">{name}</div>
          <pre>{code}</pre>
        </div>
      ))}
    </section>
  );
}
