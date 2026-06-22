/**
 * Test rápido de UN proxy.
 */
import React, { useState } from 'react';

const QUALITY_COLORS = {
  '⭐ PREMIUM': '#10b981', '🟢 HIGH': '#3b82f6',
  '🟡 MEDIUM': '#f59e0b', '🔴 LOW': '#ef4444',
};

export default function QuickTest({ onSave }) {
  const [proxy, setProxy] = useState('');
  const [deep, setDeep] = useState(true);
  const [loading, setLoading] = useState(false);
  const [res, setRes] = useState(null);
  const [err, setErr] = useState('');
  const [saved, setSaved] = useState(false);

  const run = async () => {
    if (!proxy.trim()) return;
    setLoading(true); setErr(''); setRes(null);
    try {
      const r = await fetch('/api/test-one', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ proxy: proxy.trim(), deep }),
      });
      const data = await r.json();
      if (!data.ok) { setErr(data.error || 'Error'); }
      else setRes(data);
    } catch (e) { setErr(e.message); }
    finally { setLoading(false); }
  };

  const onKey = (e) => { if (e.key === 'Enter') run(); };

  return (
    <section className="panel">
      <h2 className="tool-title">⚡ Test rápido de un proxy</h2>
      <p className="tool-desc">Verifica al instante si un proxy funciona, su latencia, anonimato y país.</p>

      <div className="quick-row">
        <input className="quick-input" placeholder="ip:puerto  (ej: 1.2.3.4:8080 o socks5://1.2.3.4:1080)"
          value={proxy} onChange={(e) => setProxy(e.target.value)} onKeyDown={onKey} disabled={loading} />
        <button className="btn btn-start" onClick={run} disabled={loading}>
          {loading ? 'Probando...' : 'Probar'}
        </button>
      </div>
      <label className="check-line">
        <input type="checkbox" checked={deep} onChange={(e) => setDeep(e.target.checked)} disabled={loading} />
        Test profundo (Google + Cloudflare) — más lento pero más confiable
      </label>

      {err && <div className="tool-error">❌ {err}</div>}

      {res && !res.alive && (
        <div className="result-card dead">
          <span className="big-status">❌ Proxy muerto</span>
          <span className="mono">{res.address}</span>
          <p>No respondió o no pasó la verificación.</p>
        </div>
      )}

      {res && res.alive && res.result && (
        <div className="result-card alive">
          <div className="rc-head">
            <span className="big-status">✅ Proxy vivo</span>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              {onSave && (
                <button className="btn-sm save" onClick={() => { onSave(res.result); setSaved(true); setTimeout(() => setSaved(false), 2000); }}>
                  {saved ? '✓ Guardado' : '🗄️ Guardar al baúl'}
                </button>
              )}
              <span className="score-big" style={{ background: `hsl(${Math.min(res.result.score,100)*1.2},70%,45%)` }}>{res.result.score}/100</span>
            </div>
          </div>
          <div className="rc-grid">
            <div><label>Dirección</label><span className="mono">{res.result.address}</span></div>
            <div><label>Protocolo</label><span className="proto-tag">{res.result.protocol}</span></div>
            <div><label>Calidad</label><span style={{ color: QUALITY_COLORS[res.result.quality] }}>{res.result.quality}</span></div>
            <div><label>Anonimato</label><span>{res.result.anon_level}</span></div>
            <div><label>País</label><span>{res.result.country} {res.result.country_name && `· ${res.result.country_name}`}</span></div>
            <div><label>Latencia</label><span className="mono">{Math.round(res.result.latency_ms)}ms</span></div>
            {res.result.targets_ok?.length > 0 && (
              <div className="full"><label>Targets superados</label><span>{res.result.targets_ok.join(', ')}</span></div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
