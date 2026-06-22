/**
 * Limpia, normaliza y deduplica listas de proxies.
 */
import React, { useState } from 'react';

export default function CleanList() {
  const [text, setText] = useState('');
  const [fmt, setFmt] = useState('plain'); // plain | prefixed
  const [res, setRes] = useState(null);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  const run = async () => {
    if (!text.trim()) return;
    setLoading(true); setRes(null);
    try {
      const r = await fetch('/api/clean', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      });
      setRes(await r.json());
    } finally { setLoading(false); }
  };

  const output = res ? (fmt === 'plain' ? res.plain : res.prefixed).join('\n') : '';

  const copy = async () => {
    await navigator.clipboard.writeText(output);
    setCopied(true); setTimeout(() => setCopied(false), 1500);
  };
  const download = () => {
    const url = URL.createObjectURL(new Blob([output], { type: 'text/plain' }));
    const a = document.createElement('a'); a.href = url; a.download = 'proxies_limpias.txt'; a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <section className="panel">
      <h2 className="tool-title">Limpiar y deduplicar lista</h2>
      <p className="tool-desc">Pega una lista desordenada (con texto basura, duplicados, IPs inválidas) y obtén una lista limpia.</p>

      <textarea className="clean-input" rows={8} value={text} disabled={loading}
        placeholder={'Pega aquí tu lista...\n1.2.3.4:8080\nsocks5://5.6.7.8:1080  # comentario\n1.2.3.4:8080  (duplicado)\ntexto basura 9.9.9.9:3128 más texto'}
        onChange={(e) => setText(e.target.value)} />

      <div className="actions">
        <button className="btn btn-start" onClick={run} disabled={loading}>{loading ? 'Procesando...' : 'Limpiar lista'}</button>
      </div>

      {res && (
        <>
          <div className="clean-stats">
            <div className="cstat"><span>{res.input_lines}</span><label>líneas entrada</label></div>
            <div className="cstat ok"><span>{res.valid}</span><label>válidas únicas</label></div>
            <div className="cstat bad"><span>{res.removed}</span><label>eliminadas</label></div>
            {Object.entries(res.by_protocol).map(([p, n]) => (
              <div className="cstat" key={p}><span>{n}</span><label>{p}</label></div>
            ))}
          </div>

          <div className="clean-out-head">
            <div className="fmt-toggle">
              <button className={fmt === 'plain' ? 'on' : ''} onClick={() => setFmt('plain')}>ip:puerto</button>
              <button className={fmt === 'prefixed' ? 'on' : ''} onClick={() => setFmt('prefixed')}>protocolo://ip:puerto</button>
            </div>
            <div className="filters">
              <button className="btn-sm" onClick={copy}>{copied ? '✓ Copiado' : 'Copiar'}</button>
              <button className="btn-sm" onClick={download}>Descargar</button>
            </div>
          </div>
          <textarea className="clean-output mono" rows={10} readOnly value={output} />
        </>
      )}
    </section>
  );
}
