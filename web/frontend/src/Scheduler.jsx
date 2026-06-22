/**
 * Scheduler — auto-refresh del baúl en segundo plano.
 */
import React, { useState, useEffect, useCallback } from 'react';
import { IcClock, IcCheck } from './Icons.jsx';

export default function Scheduler({ adminHeaders }) {
  const [st, setSt] = useState(null);
  const [interval, setIntervalV] = useState(30);
  const [limit, setLimit] = useState(600);
  const [verify, setVerify] = useState(true);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await fetch('/api/scheduler');
      const d = await r.json();
      setSt(d); setIntervalV(d.interval); setLimit(d.limit); setVerify(d.verify);
    } catch {}
  }, []);

  useEffect(() => { load(); const t = setInterval(load, 5000); return () => clearInterval(t); }, [load]);

  const save = useCallback(async (enabled) => {
    setSaving(true);
    try {
      const r = await fetch('/api/scheduler', {
        method: 'POST', headers: { 'Content-Type': 'application/json', ...adminHeaders },
        body: JSON.stringify({ enabled, interval, limit, verify }),
      });
      if (r.status === 403) { alert('Token de admin requerido o inválido'); return; }
      setSt(await r.json());
    } finally { setSaving(false); }
  }, [interval, limit, verify, adminHeaders]);

  return (
    <section className="panel">
      <h2 className="tool-title"><IcClock size={20} /> Auto-refresh del baúl (Scheduler)</h2>
      <p className="tool-desc">
        Mantén tu API siempre con proxies frescas: el servidor re-escanea y re-verifica el baúl
        automáticamente cada cierto tiempo, en segundo plano.
      </p>

      <div className={`sched-status ${st?.enabled ? 'on' : 'off'}`}>
        <span className="dot" />
        {st?.enabled ? `Activo — cada ${st.interval} min` : 'Inactivo'}
        {st?.running && <span className="running">· ejecutando ahora…</span>}
      </div>

      <div className="rotator-bar">
        <div className="field">
          <label>Intervalo (minutos)</label>
          <input type="number" min={1} value={interval} onChange={(e) => setIntervalV(Number(e.target.value))} />
        </div>
        <div className="field">
          <label>Proxies por escaneo</label>
          <input type="number" min={100} step={100} value={limit} onChange={(e) => setLimit(Number(e.target.value))} />
        </div>
        <div className="field">
          <label>Re-verificar baúl</label>
          <select value={verify ? '1' : '0'} onChange={(e) => setVerify(e.target.value === '1')}>
            <option value="1">Sí (elimina muertas)</option>
            <option value="0">No</option>
          </select>
        </div>
      </div>

      <div className="actions">
        {!st?.enabled ? (
          <button className="btn btn-start" onClick={() => save(true)} disabled={saving}>Activar auto-refresh</button>
        ) : (
          <button className="btn btn-stop" onClick={() => save(false)} disabled={saving}>Detener</button>
        )}
        <button className="btn-sm" onClick={() => save(st?.enabled)} disabled={saving}>Guardar config</button>
      </div>

      {st?.last_run && (
        <div className="sched-last">
          <IcCheck size={14} /> Último ciclo: {new Date(st.last_run).toLocaleString()}
          {st.last_result && !st.last_result.error && ` · ${st.last_result.alive} vivas, ${st.last_result.added} nuevas (baúl: ${st.last_result.total})`}
          {st.last_result?.error && ` · error: ${st.last_result.error}`}
        </div>
      )}
    </section>
  );
}
