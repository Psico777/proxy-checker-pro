/**
 * Proxy Checker Pro - Web UI
 * Verificación de proxies en vivo vía WebSocket.
 */
import React, { useState, useRef, useCallback, useMemo, useEffect } from 'react';
import QuickTest from './QuickTest.jsx';
import CleanList from './CleanList.jsx';
import Dashboard from './Dashboard.jsx';
import Vault from './Vault.jsx';
import Guide from './Guide.jsx';

const SOURCES = [
  { v: 'all', label: '🌐 Todas las fuentes (~20k)' },
  { v: 'api', label: '⚡ Solo APIs (~8k)' },
  { v: 'github', label: '📦 Solo GitHub (~15k)' },
  { v: 'http', label: '🔌 Solo HTTP/HTTPS' },
  { v: 'socks', label: '🧦 Solo SOCKS4/5' },
  { v: 'paste', label: '📋 Pegar mi lista' },
];

const TESTS = [
  { v: 'hq', label: '🔬 HQ Riguroso (5 targets)' },
  { v: 'google', label: '🌍 Google + Cloudflare' },
  { v: 'alive', label: '⚡ Solo vida (rápido)' },
  { v: 'custom', label: '🎯 URL personalizada' },
];

const CONCURRENCY = [
  { v: 200, label: '🐢 200' },
  { v: 500, label: '⚡ 500' },
  { v: 800, label: '🚀 800' },
  { v: 1200, label: '💀 1200' },
];

const QUALITY_COLORS = {
  '⭐ PREMIUM': '#10b981', '🟢 HIGH': '#3b82f6',
  '🟡 MEDIUM': '#f59e0b', '🔴 LOW': '#ef4444',
};

function tierKey(q) { return (q || '').replace(/[^A-Z]/g, ''); }

export default function App() {
  const [source, setSource] = useState('all');
  const [tests, setTests] = useState('hq');
  const [concurrency, setConcurrency] = useState(500);
  const [limit, setLimit] = useState(2000);
  const [customUrl, setCustomUrl] = useState('');
  const [pasted, setPasted] = useState('');

  const [running, setRunning] = useState(false);
  const [status, setStatus] = useState('');
  const [progress, setProgress] = useState({ checked: 0, alive: 0, dead: 0, total: 0, speed: 0, premium: 0, high: 0 });
  const [results, setResults] = useState([]);
  const [summary, setSummary] = useState(null);

  // Filters
  const [fProto, setFProto] = useState('all');
  const [fQuality, setFQuality] = useState('all');
  const [fCountry, setFCountry] = useState('all');
  const [search, setSearch] = useState('');

  const [tab, setTab] = useState('checker');
  const [vault, setVault] = useState([]);
  const [savedMsg, setSavedMsg] = useState('');
  const wsRef = useRef(null);

  const reloadVault = useCallback(async () => {
    try {
      const r = await fetch('/api/vault');
      const d = await r.json();
      setVault(d.proxies || []);
    } catch {}
  }, []);

  useEffect(() => { reloadVault(); }, [reloadVault]);

  const saveToVault = useCallback(async (proxies) => {
    const list = Array.isArray(proxies) ? proxies : [proxies];
    if (!list.length) return;
    try {
      const r = await fetch('/api/vault', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ proxies: list }),
      });
      const d = await r.json();
      setVault(d.proxies || []);
      setSavedMsg(`✓ ${d.added} guardada(s) en el baúl`);
      setTimeout(() => setSavedMsg(''), 2500);
    } catch {}
  }, []);

  const start = useCallback(() => {
    setResults([]);
    setSummary(null);
    setProgress({ checked: 0, alive: 0, dead: 0, total: 0, speed: 0, premium: 0, high: 0 });
    setStatus('Conectando...');
    setRunning(true);

    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${proto}//${window.location.host}/api/ws/check`);
    wsRef.current = ws;

    ws.onopen = () => {
      ws.send(JSON.stringify({ source, tests, concurrency, limit, custom_url: customUrl, pasted }));
    };

    ws.onmessage = (ev) => {
      const m = JSON.parse(ev.data);
      switch (m.type) {
        case 'status': setStatus(m.msg); break;
        case 'started':
          setStatus(`Verificando ${m.total.toLocaleString()} proxies · ${m.concurrency} conexiones`);
          setProgress((p) => ({ ...p, total: m.total }));
          break;
        case 'progress':
          setProgress({ checked: m.checked, alive: m.alive, dead: m.dead, total: m.total, speed: m.speed, premium: m.premium, high: m.high });
          if (m.new?.length) setResults((prev) => [...prev, ...m.new]);
          break;
        case 'done':
          if (m.new?.length) setResults((prev) => [...prev, ...m.new]);
          setProgress((p) => ({ ...p, checked: m.checked, alive: m.alive, dead: m.dead, total: m.total }));
          setSummary(m.summary);
          setStatus(m.stopped ? `Detenido · ${m.alive} vivas en ${m.elapsed}s` : `✅ Completado · ${m.alive} vivas en ${m.elapsed}s`);
          setRunning(false);
          ws.close();
          break;
        case 'error':
          setStatus('❌ ' + m.msg);
          setRunning(false);
          ws.close();
          break;
        default: break;
      }
    };

    ws.onerror = () => { setStatus('❌ Error de conexión'); setRunning(false); };
    ws.onclose = () => { setRunning(false); };
  }, [source, tests, concurrency, limit, customUrl, pasted]);

  const stop = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ action: 'stop' }));
      setStatus('Deteniendo...');
    }
  }, []);

  useEffect(() => () => wsRef.current?.close(), []);

  // ── Filtros ──
  const countries = useMemo(() => {
    const s = new Set(results.map((r) => r.country).filter(Boolean));
    return ['all', ...Array.from(s).sort()];
  }, [results]);

  const filtered = useMemo(() => {
    return results.filter((r) => {
      if (fProto !== 'all' && r.protocol !== fProto) return false;
      if (fQuality !== 'all' && tierKey(r.quality) !== fQuality) return false;
      if (fCountry !== 'all' && r.country !== fCountry) return false;
      if (search && !r.address?.includes(search)) return false;
      return true;
    }).sort((a, b) => b.score - a.score);
  }, [results, fProto, fQuality, fCountry, search]);

  const pct = progress.total ? Math.round((progress.checked / progress.total) * 100) : 0;

  // ── Export ──
  const download = (content, name, type) => {
    const url = URL.createObjectURL(new Blob([content], { type }));
    const a = document.createElement('a');
    a.href = url; a.download = name; a.click();
    URL.revokeObjectURL(url);
  };
  const exportTxt = () => download(filtered.map((r) => `${r.protocol}://${r.address}`).join('\n'), 'proxies.txt', 'text/plain');
  const exportCsv = () => {
    const head = 'protocol,address,score,quality,anon_level,country,latency_ms\n';
    const rows = filtered.map((r) => `${r.protocol},${r.address},${r.score},${r.quality},${r.anon_level},${r.country},${r.latency_ms}`).join('\n');
    download(head + rows, 'proxies.csv', 'text/csv');
  };
  const exportJson = () => download(JSON.stringify(filtered, null, 2), 'proxies.json', 'application/json');

  return (
    <div className="app">
      <header className="header">
        <div className="logo">
          <span className="logo-icon">🔍</span>
          <div>
            <h1>Proxy Checker <span className="pro">Pro</span></h1>
            <p>Verificación async de proxies en vivo · HTTP/SOCKS · 30+ fuentes</p>
          </div>
        </div>
        <div className="header-stats">
          <div className="hstat"><span>{progress.alive}</span><label>vivas</label></div>
          <div className="hstat"><span>{progress.speed}</span><label>p/s</label></div>
          <div className="hstat"><span>{vault.length}</span><label>baúl</label></div>
        </div>
      </header>

      <nav className="tabs">
        <button className={tab === 'checker' ? 'tab on' : 'tab'} onClick={() => setTab('checker')}>🔍 Checker masivo</button>
        <button className={tab === 'quick' ? 'tab on' : 'tab'} onClick={() => setTab('quick')}>⚡ Test rápido</button>
        <button className={tab === 'clean' ? 'tab on' : 'tab'} onClick={() => setTab('clean')}>🧹 Limpiar lista</button>
        <button className={tab === 'dashboard' ? 'tab on' : 'tab'} onClick={() => setTab('dashboard')}>📊 Dashboard</button>
        <button className={tab === 'vault' ? 'tab on' : 'tab'} onClick={() => setTab('vault')}>🗄️ Baúl</button>
        <button className={tab === 'guide' ? 'tab on' : 'tab'} onClick={() => setTab('guide')}>📖 Guía</button>
      </nav>

      <main className="main">
        {tab === 'quick' && <QuickTest onSave={saveToVault} />}
        {tab === 'clean' && <CleanList />}
        {tab === 'dashboard' && <Dashboard results={results} />}
        {tab === 'vault' && <Vault vault={vault} reloadVault={reloadVault} />}
        {tab === 'guide' && <Guide />}

        {tab === 'checker' && <>
        {/* Config panel */}
        <section className="panel config-panel">
          <div className="config-grid">
            <div className="field">
              <label>Fuente</label>
              <select value={source} onChange={(e) => setSource(e.target.value)} disabled={running}>
                {SOURCES.map((s) => <option key={s.v} value={s.v}>{s.label}</option>)}
              </select>
            </div>
            <div className="field">
              <label>Verificación</label>
              <select value={tests} onChange={(e) => setTests(e.target.value)} disabled={running}>
                {TESTS.map((t) => <option key={t.v} value={t.v}>{t.label}</option>)}
              </select>
            </div>
            <div className="field">
              <label>Concurrencia</label>
              <select value={concurrency} onChange={(e) => setConcurrency(Number(e.target.value))} disabled={running}>
                {CONCURRENCY.map((c) => <option key={c.v} value={c.v}>{c.label}</option>)}
              </select>
            </div>
            <div className="field">
              <label>Límite (0 = todas)</label>
              <input type="number" value={limit} min={0} step={500}
                onChange={(e) => setLimit(Number(e.target.value))} disabled={running} />
            </div>
          </div>

          {tests === 'custom' && (
            <div className="field full">
              <label>URL personalizada</label>
              <input type="text" value={customUrl} placeholder="https://ejemplo.com"
                onChange={(e) => setCustomUrl(e.target.value)} disabled={running} />
            </div>
          )}
          {source === 'paste' && (
            <div className="field full">
              <label>Pega tus proxies (una por línea — ip:puerto, opcional socks5://)</label>
              <textarea value={pasted} rows={5} placeholder="1.2.3.4:8080&#10;socks5://5.6.7.8:1080"
                onChange={(e) => setPasted(e.target.value)} disabled={running} />
            </div>
          )}

          <div className="actions">
            {!running ? (
              <button className="btn btn-start" onClick={start}>▶ Iniciar verificación</button>
            ) : (
              <button className="btn btn-stop" onClick={stop}>■ Detener y guardar</button>
            )}
            {status && <span className="status">{status}</span>}
          </div>
        </section>

        {/* Progress */}
        {(running || progress.checked > 0) && (
          <section className="panel progress-panel">
            <div className="progress-bar-wrap">
              <div className="progress-bar" style={{ width: `${pct}%` }} />
              <span className="progress-label">{progress.checked.toLocaleString()} / {progress.total.toLocaleString()} ({pct}%)</span>
            </div>
            <div className="counters">
              <div className="counter c-alive"><span>{progress.alive}</span><label>✅ Vivas</label></div>
              <div className="counter c-dead"><span>{progress.dead}</span><label>❌ Muertas</label></div>
              <div className="counter c-premium"><span>{progress.premium}</span><label>⭐ Premium</label></div>
              <div className="counter c-high"><span>{progress.high}</span><label>🟢 High</label></div>
              <div className="counter c-speed"><span>{progress.speed}</span><label>🚀 p/seg</label></div>
            </div>
          </section>
        )}

        {/* Results */}
        {results.length > 0 && (
          <section className="panel results-panel">
            <div className="results-header">
              <h2>Proxies vivas <span className="count">{filtered.length}</span></h2>
              <div className="filters">
                <input className="search" placeholder="Buscar IP..." value={search} onChange={(e) => setSearch(e.target.value)} />
                <select value={fProto} onChange={(e) => setFProto(e.target.value)}>
                  <option value="all">Protocolo</option>
                  <option value="http">HTTP</option><option value="https">HTTPS</option>
                  <option value="socks4">SOCKS4</option><option value="socks5">SOCKS5</option>
                </select>
                <select value={fQuality} onChange={(e) => setFQuality(e.target.value)}>
                  <option value="all">Calidad</option>
                  <option value="PREMIUM">Premium</option><option value="HIGH">High</option>
                  <option value="MEDIUM">Medium</option><option value="LOW">Low</option>
                </select>
                <select value={fCountry} onChange={(e) => setFCountry(e.target.value)}>
                  {countries.map((c) => <option key={c} value={c}>{c === 'all' ? 'País' : c}</option>)}
                </select>
                <button className="btn-sm" onClick={exportTxt}>TXT</button>
                <button className="btn-sm" onClick={exportCsv}>CSV</button>
                <button className="btn-sm" onClick={exportJson}>JSON</button>
                <button className="btn-sm save" onClick={() => saveToVault(filtered)}>🗄️ Guardar al baúl</button>
                {savedMsg && <span className="saved-msg">{savedMsg}</span>}
              </div>
            </div>

            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Score</th><th>Proxy</th><th>Protocolo</th><th>Calidad</th>
                    <th>Anonimato</th><th>País</th><th>Latencia</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.slice(0, 500).map((r, i) => (
                    <tr key={r.address + i}>
                      <td><span className="score" style={{ background: `hsl(${Math.min(r.score, 100) * 1.2}, 70%, 45%)` }}>{r.score}</span></td>
                      <td className="mono">{r.address}</td>
                      <td><span className="proto-tag">{r.protocol}</span></td>
                      <td><span className="quality-tag" style={{ color: QUALITY_COLORS[r.quality] || '#94a3b8' }}>{r.quality}</span></td>
                      <td>{r.anon_level}</td>
                      <td>{r.country}</td>
                      <td className="mono">{Math.round(r.latency_ms)}ms</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {filtered.length > 500 && <p className="more-note">Mostrando 500 de {filtered.length} — exporta para ver todas</p>}
            </div>
          </section>
        )}
        </>}
      </main>

      <footer className="footer">
        Proxy Checker Pro · motor async · uso responsable de proxies públicas
      </footer>
    </div>
  );
}
