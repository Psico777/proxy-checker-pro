/**
 * Dashboard de estadísticas de los proxies verificados.
 */
import React, { useMemo } from 'react';

const COLORS = ['#00d4ff', '#7c3aed', '#10b981', '#f59e0b', '#ef4444', '#3b82f6', '#ec4899', '#14b8a6'];
const QUALITY_ORDER = ['⭐ PREMIUM', '🟢 HIGH', '🟡 MEDIUM', '🔴 LOW'];
const QUALITY_COLOR = { '⭐ PREMIUM': '#10b981', '🟢 HIGH': '#3b82f6', '🟡 MEDIUM': '#f59e0b', '🔴 LOW': '#ef4444' };

function Bars({ data, max }) {
  return (
    <div className="bar-chart">
      {data.map((d, i) => (
        <div className="bar-row" key={d.name}>
          <span className="bar-label" title={d.name}>{d.name}</span>
          <div className="bar-track">
            <div className="bar-fill" style={{ width: `${(d.value / max) * 100}%`, background: d.color || COLORS[i % COLORS.length] }} />
          </div>
          <span className="bar-value">{d.value}</span>
        </div>
      ))}
    </div>
  );
}

export default function Dashboard({ results }) {
  const stats = useMemo(() => {
    const n = results.length;
    const byProto = {}, byQuality = {}, byCountry = {}, byAnon = {};
    let sumScore = 0, sumLat = 0, premium = 0, high = 0;
    for (const r of results) {
      byProto[r.protocol] = (byProto[r.protocol] || 0) + 1;
      byQuality[r.quality] = (byQuality[r.quality] || 0) + 1;
      byCountry[r.country] = (byCountry[r.country] || 0) + 1;
      byAnon[r.anon_level] = (byAnon[r.anon_level] || 0) + 1;
      sumScore += r.score || 0; sumLat += r.latency_ms || 0;
      if ((r.quality || '').includes('PREMIUM')) premium++;
      if ((r.quality || '').includes('HIGH')) high++;
    }
    const proto = Object.entries(byProto).map(([name, value]) => ({ name: name.toUpperCase(), value })).sort((a, b) => b.value - a.value);
    const countries = Object.entries(byCountry).map(([name, value]) => ({ name, value })).sort((a, b) => b.value - a.value).slice(0, 8);
    const anon = Object.entries(byAnon).map(([name, value]) => ({ name, value })).sort((a, b) => b.value - a.value);
    const quality = QUALITY_ORDER.filter((q) => byQuality[q]).map((q) => ({ name: q, value: byQuality[q], color: QUALITY_COLOR[q], pct: n ? (byQuality[q] / n) * 100 : 0 }));
    return { n, proto, countries, anon, quality, avgScore: n ? sumScore / n : 0, avgLat: n ? sumLat / n : 0, premium, high };
  }, [results]);

  const pie = useMemo(() => {
    let cum = 0;
    return stats.quality.map((d) => {
      const start = cum; const sweep = (d.pct / 100) * 360; cum += sweep;
      const large = sweep > 180 ? 1 : 0; const r = 70, cx = 80, cy = 80;
      const x1 = cx + r * Math.cos(Math.PI * (start - 90) / 180);
      const y1 = cy + r * Math.sin(Math.PI * (start - 90) / 180);
      const x2 = cx + r * Math.cos(Math.PI * (start + sweep - 90) / 180);
      const y2 = cy + r * Math.sin(Math.PI * (start + sweep - 90) / 180);
      return { d: `M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2} Z`, color: d.color };
    });
  }, [stats.quality]);

  if (!results.length) {
    return (
      <section className="panel">
        <h2 className="tool-title">📊 Dashboard</h2>
        <p className="tool-desc">Corre una verificación en <b>Checker masivo</b> y aquí verás las estadísticas: protocolos, calidad, países y anonimato.</p>
        <div className="empty-dash">📊<br />Sin datos todavía</div>
      </section>
    );
  }

  const maxProto = Math.max(...stats.proto.map((d) => d.value), 1);
  const maxCountry = Math.max(...stats.countries.map((d) => d.value), 1);
  const maxAnon = Math.max(...stats.anon.map((d) => d.value), 1);

  return (
    <section className="panel">
      <h2 className="tool-title">📊 Dashboard del último escaneo</h2>

      <div className="kpi-grid">
        <div className="kpi kpi-main"><span>{stats.n}</span><label>Proxies vivas</label></div>
        <div className="kpi"><span>{stats.premium}</span><label>⭐ Premium</label></div>
        <div className="kpi"><span>{stats.high}</span><label>🟢 High</label></div>
        <div className="kpi"><span>{stats.avgScore.toFixed(0)}</span><label>Score prom.</label></div>
        <div className="kpi"><span>{stats.avgLat.toFixed(0)}ms</span><label>Latencia prom.</label></div>
        <div className="kpi"><span>{stats.countries.length}+</span><label>Países</label></div>
      </div>

      <div className="charts-row">
        <div className="chart-card">
          <h3 className="chart-title">Por protocolo</h3>
          <Bars data={stats.proto} max={maxProto} />
        </div>
        <div className="chart-card">
          <h3 className="chart-title">Distribución por calidad</h3>
          <div className="pie-container">
            <svg viewBox="0 0 160 160" className="pie-svg">
              {pie.map((s, i) => <path key={i} d={s.d} fill={s.color} stroke="#0a0f1e" strokeWidth="1" />)}
              <circle cx="80" cy="80" r="40" fill="#1a2236" />
              <text x="80" y="78" textAnchor="middle" className="pie-c-label">VIVAS</text>
              <text x="80" y="95" textAnchor="middle" className="pie-c-value">{stats.n}</text>
            </svg>
            <div className="pie-legend">
              {stats.quality.map((d) => (
                <div className="legend-item" key={d.name}>
                  <span className="legend-dot" style={{ background: d.color }} />
                  <span className="legend-name">{d.name}</span>
                  <span className="legend-pct">{d.pct.toFixed(0)}%</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="charts-row">
        <div className="chart-card">
          <h3 className="chart-title">Top países</h3>
          <Bars data={stats.countries} max={maxCountry} />
        </div>
        <div className="chart-card">
          <h3 className="chart-title">Anonimato</h3>
          <Bars data={stats.anon} max={maxAnon} />
        </div>
      </div>
    </section>
  );
}
