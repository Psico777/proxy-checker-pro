/**
 * Proxy Checker Pro - Web UI
 */
import React, { useState, useRef, useCallback, useMemo, useEffect } from 'react';
import QuickTest from './QuickTest.jsx';
import CleanList from './CleanList.jsx';
import Dashboard from './Dashboard.jsx';
import Vault from './Vault.jsx';
import Guide from './Guide.jsx';
import Rotator from './Rotator.jsx';
import ApiKeys from './ApiKeys.jsx';
import Landing from './Landing.jsx';
import Scheduler from './Scheduler.jsx';
import {
  IcSearch, IcZap, IcEraser, IcChart, IcArchive, IcRotate, IcKey, IcBook,
  IcHome, IcClock, IcDownload, IcStop, IcPlay, IcShield,
} from './Icons.jsx';

const SOURCES = [
  { v: 'all', label: 'Todas las fuentes (~20k)' },
  { v: 'api', label: 'Solo APIs (~8k)' },
  { v: 'github', label: 'Solo GitHub (~15k)' },
  { v: 'http', label: 'Solo HTTP/HTTPS' },
  { v: 'socks', label: 'Solo SOCKS4/5' },
  { v: 'paste', label: 'Pegar mi lista' },
];
const TESTS = [
  { v: 'hq', label: 'HQ Riguroso (5 targets)' },
  { v: 'google', label: 'Google + Cloudflare' },
  { v: 'alive', label: 'Solo vida (rápido)' },
  { v: 'custom', label: 'URL personalizada' },
];
const CONCURRENCY = [
  { v: 200, label: '200 · conservador' },
  { v: 500, label: '500 · recomendado' },
  { v: 800, label: '800 · agresivo' },
  { v: 1200, label: '1200 · extremo' },
];
const QUALITY_COLORS = { '⭐ PREMIUM': '#10b981', '🟢 HIGH': '#3b82f6', '🟡 MEDIUM': '#f59e0b', '🔴 LOW': '#ef4444' };
const cleanQ = (q) => (q || '').replace(/[^A-Za-z ]/g, '').trim();
function tierKey(q) { return (q || '').replace(/[^A-Z]/g, ''); }

const TABS = [
  { id: 'home', label: 'Inicio', Ic: IcHome },
  { id: 'checker', label: 'Checker', Ic: IcSearch },
  { id: 'quick', label: 'Test rápido', Ic: IcZap },
  { id: 'clean', label: 'Limpiar', Ic: IcEraser },
  { id: 'dashboard', label: 'Dashboard', Ic: IcChart },
  { id: 'vault', label: 'Baúl', Ic: IcArchive },
  { id: 'rotator', label: 'Rotador', Ic: IcRotate },
  { id: 'scheduler', label: 'Auto-refresh', Ic: IcClock },
  { id: 'keys', label: 'API Keys', Ic: IcKey },
  { id: 'guide', label: 'Guía', Ic: IcBook },
];

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

  const [fProto, setFProto] = useState('all');
  const [fQuality, setFQuality] = useState('all');
  const [fCountry, setFCountry] = useState('all');
  const [search, setSearch] = useState('');

  const [tab, setTab] = useState('home');
  const [vault, setVault] = useState([]);
  const [keys, setKeys] = useState([]);
  const [savedMsg, setSavedMsg] = useState('');
  const [adminToken, setAdminToken] = useState(() => localStorage.getItem('pck_admin') || '');
  const wsRef = useRef(null);

  const adminHeaders = useMemo(() => (adminToken ? { 'X-Admin-Token': adminToken } : {}), [adminToken]);
  useEffect(() => { localStorage.setItem('pck_admin', adminToken); }, [adminToken]);

  const reloadKeys = useCallback(async () => {
    try {
      const r = await fetch('/api/keys', { headers: adminHeaders });
      if (!r.ok) { setKeys([]); return; }
      const d = await r.json();
      setKeys(d.keys || []);
    } catch {}
  }, [adminHeaders]);

  const reloadVault = useCallback(async () => {
    try {
      const r = await fetch('/api/vault');
      const d = await r.json();
      setVault(d.proxies || []);
    } catch {}
  }, []);

  useEffect(() => { reloadKeys(); reloadVault(); }, [reloadKeys, reloadVault]);

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
      setSavedMsg(`${d.added} guardada(s) en el baúl`);
      setTimeout(() => setSavedMsg(''), 2500);
    } catch {}
  }, []);

  const start = useCallback(() => {
    setResults([]);
    setProgress({ checked: 0, alive: 0, dead: 0, total: 0, speed: 0, premium: 0, high: 0 });
    setStatus('Conectando...');
    setRunning(true);
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${proto}//${window.location.host}/api/ws/check`);
    wsRef.current = ws;
    ws.onopen = () => ws.send(JSON.stringify({ source, tests, concurrency, limit, custom_url: customUrl, pasted }));
    ws.onmessage = (ev) => {
      const m = JSON.parse(ev.data);
      switch (m.type) {
        case 'status': setStatus(m.msg); break;
        case 'started':
          setStatus(`Verificando ${m.total.toLocaleString()} proxies · ${m.concurrency} conexiones`);
          setProgress((p) => ({ ...p, total: m.total })); break;
        case 'progress':
          setProgress({ checked: m.checked, alive: m.alive, dead: m.dead, total: m.total, speed: m.speed, premium: m.premium, high: m.high });
          if (m.new?.length) setResults((prev) => [...prev, ...m.new]); break;
        case 'done':
          if (m.new?.length) setResults((prev) => [...prev, ...m.new]);
          setProgress((p) => ({ ...p, checked: m.checked, alive: m.alive, dead: m.dead, total: m.total }));
          setStatus(m.stopped ? `Detenido · ${m.alive} vivas en ${m.elapsed}s` : `Completado · ${m.alive} vivas en ${m.elapsed}s`);
          setRunning(false); ws.close(); break;
        case 'error': setStatus('Error: ' + m.msg); setRunning(false); ws.close(); break;
        default: break;
      }
    };
    ws.onerror = () => { setStatus('Error de conexión'); setRunning(false); };
    ws.onclose = () => setRunning(false);
  }, [source, tests, concurrency, limit, customUrl, pasted]);

  const stop = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ action: 'stop' }));
      setStatus('Deteniendo...');
    }
  }, []);

  useEffect(() => () => wsRef.current?.close(), []);

  const countries = useMemo(() => ['all', ...Array.from(new Set(results.map((r) => r.country).filter(Boolean))).sort()], [results]);
  const filtered = useMemo(() => results.filter((r) => {
    if (fProto !== 'all' && r.protocol !== fProto) return false;
    if (fQuality !== 'all' && tierKey(r.quality) !== fQuality) return false;
    if (fCountry !== 'all' && r.country !== fCountry) return false;
    if (search && !r.address?.includes(search)) return false;
    return true;
  }).sort((a, b) => b.score - a.score), [results, fProto, fQuality, fCountry, search]);

  const pct = progress.total ? Math.round((progress.checked / progress.total) * 100) : 0;

  const download = (content, name, type) => {
    const url = URL.createObjectURL(new Blob([content], { type }));
    const a = document.createElement('a'); a.href = url; a.download = name; a.click(); URL.revokeObjectURL(url);
  };
  const exportTxt = () => download(filtered.map((r) => `${r.protocol}://${r.address}`).join('\n'), 'proxies.txt', 'text/plain');
  const exportCsv = () => download('protocol,address,score,quality,anon_level,country,latency_ms\n' +
    filtered.map((r) => `${r.protocol},${r.address},${r.score},${cleanQ(r.quality)},${r.anon_level},${r.country},${r.latency_ms}`).join('\n'), 'proxies.csv', 'text/csv');
  const exportJson = () => download(JSON.stringify(filtered, null, 2), 'proxies.json', 'application/json');

  return (
    <div className="app">
      <header className="header">
        <div className="logo" onClick={() => setTab('home')} style={{ cursor: 'pointer' }}>
          <span className="logo-icon"><IcSearch size={26} /></span>
          <div>
            <h1>Proxy Checker <span className="pro">Pro</span></h1>
            <p>API de proxies · HTTP / SOCKS · 30+ fuentes</p>
          </div>
        </div>
        <div className="header-stats">
          <div className="hstat"><span>{progress.alive}</span><label>vivas</label></div>
          <div className="hstat"><span>{progress.speed}</span><label>p/s</label></div>
          <div className="hstat"><span>{vault.length}</span><label>baúl</label></div>
          <div className="admin-box" title="Token de admin (para panel de keys/scheduler en producción)">
            <IcShield size={14} />
            <input type="password" placeholder="admin token" value={adminToken}
              onChange={(e) => setAdminToken(e.target.value)} />
          </div>
        </div>
      </header>

      <nav className="tabs">
        {TABS.map(({ id, label, Ic }) => (
          <button key={id} className={tab === id ? 'tab on' : 'tab'} onClick={() => setTab(id)}>
            <Ic size={15} /> {label}
          </button>
        ))}
      </nav>

      <main className="main">
        {tab === 'home' && <Landing onEnter={() => setTab('checker')} />}
        {tab === 'quick' && <QuickTest onSave={saveToVault} />}
        {tab === 'clean' && <CleanList />}
        {tab === 'dashboard' && <Dashboard results={results} />}
        {tab === 'vault' && <Vault vault={vault} reloadVault={reloadVault} adminHeaders={adminHeaders} />}
        {tab === 'rotator' && <Rotator keys={keys} vaultCount={vault.length} reloadVault={reloadVault} adminHeaders={adminHeaders} />}
        {tab === 'scheduler' && <Scheduler adminHeaders={adminHeaders} />}
        {tab === 'keys' && <ApiKeys keys={keys} reloadKeys={reloadKeys} adminHeaders={adminHeaders} />}
        {tab === 'guide' && <Guide />}

        {tab === 'checker' && <>
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
              <input type="number" value={limit} min={0} step={500} onChange={(e) => setLimit(Number(e.target.value))} disabled={running} />
            </div>
          </div>
          {tests === 'custom' && (
            <div className="field full">
              <label>URL personalizada</label>
              <input type="text" value={customUrl} placeholder="https://ejemplo.com" onChange={(e) => setCustomUrl(e.target.value)} disabled={running} />
            </div>
          )}
          {source === 'paste' && (
            <div className="field full">
              <label>Pega tus proxies (una por línea — ip:puerto, opcional socks5://)</label>
              <textarea value={pasted} rows={5} placeholder={'1.2.3.4:8080\nsocks5://5.6.7.8:1080'} onChange={(e) => setPasted(e.target.value)} disabled={running} />
            </div>
          )}
          <div className="actions">
            {!running
              ? <button className="btn btn-start" onClick={start}><IcPlay size={16} /> Iniciar verificación</button>
              : <button className="btn btn-stop" onClick={stop}><IcStop size={16} /> Detener y guardar</button>}
            {status && <span className="status">{status}</span>}
          </div>
        </section>

        {(running || progress.checked > 0) && (
          <section className="panel progress-panel">
            <div className="progress-bar-wrap">
              <div className="progress-bar" style={{ width: `${pct}%` }} />
              <span className="progress-label">{progress.checked.toLocaleString()} / {progress.total.toLocaleString()} ({pct}%)</span>
            </div>
            <div className="counters">
              <div className="counter c-alive"><span>{progress.alive}</span><label>Vivas</label></div>
              <div className="counter c-dead"><span>{progress.dead}</span><label>Muertas</label></div>
              <div className="counter c-premium"><span>{progress.premium}</span><label>Premium</label></div>
              <div className="counter c-high"><span>{progress.high}</span><label>High</label></div>
              <div className="counter c-speed"><span>{progress.speed}</span><label>p/seg</label></div>
            </div>
          </section>
        )}

        {results.length > 0 && (
          <section className="panel results-panel">
            <div className="results-header">
              <h2>Proxies vivas <span className="count">{filtered.length}</span></h2>
              <div className="filters">
                <input className="search" placeholder="Buscar IP..." value={search} onChange={(e) => setSearch(e.target.value)} />
                <select value={fProto} onChange={(e) => setFProto(e.target.value)}>
                  <option value="all">Protocolo</option><option value="http">HTTP</option><option value="https">HTTPS</option>
                  <option value="socks4">SOCKS4</option><option value="socks5">SOCKS5</option>
                </select>
                <select value={fQuality} onChange={(e) => setFQuality(e.target.value)}>
                  <option value="all">Calidad</option><option value="PREMIUM">Premium</option><option value="HIGH">High</option>
                  <option value="MEDIUM">Medium</option><option value="LOW">Low</option>
                </select>
                <select value={fCountry} onChange={(e) => setFCountry(e.target.value)}>
                  {countries.map((c) => <option key={c} value={c}>{c === 'all' ? 'País' : c}</option>)}
                </select>
                <button className="btn-sm" onClick={exportTxt}><IcDownload size={13} /> TXT</button>
                <button className="btn-sm" onClick={exportCsv}>CSV</button>
                <button className="btn-sm" onClick={exportJson}>JSON</button>
                <button className="btn-sm save" onClick={() => saveToVault(filtered)}><IcArchive size={13} /> Guardar al baúl</button>
                {savedMsg && <span className="saved-msg">{savedMsg}</span>}
              </div>
            </div>
            <div className="table-wrap">
              <table>
                <thead><tr><th>Score</th><th>Proxy</th><th>Protocolo</th><th>Calidad</th><th>Anonimato</th><th>País</th><th>Latencia</th></tr></thead>
                <tbody>
                  {filtered.slice(0, 500).map((r, i) => (
                    <tr key={r.address + i}>
                      <td><span className="score" style={{ background: `hsl(${Math.min(r.score, 100) * 1.2}, 70%, 45%)` }}>{r.score}</span></td>
                      <td className="mono">{r.address}</td>
                      <td><span className="proto-tag">{r.protocol}</span></td>
                      <td><span className="quality-tag" style={{ color: QUALITY_COLORS[r.quality] || '#94a3b8' }}>{cleanQ(r.quality)}</span></td>
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

      <footer className="footer">Proxy Checker Pro · motor async · uso responsable de proxies públicas</footer>
    </div>
  );
}
