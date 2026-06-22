/**
 * Guía in-app: qué es, para qué sirve y cómo se usa.
 */
import React from 'react';

export default function Guide() {
  return (
    <div className="guide">
      {/* Hero / pitch */}
      <section className="panel guide-hero">
        <h2 className="tool-title">📖 ¿Qué es Proxy Checker Pro?</h2>
        <p className="tool-desc">
          Una herramienta que <b>obtiene miles de proxies</b> de más de 30 fuentes, <b>verifica cuáles funcionan</b> de verdad
          (doble comprobación), y las <b>clasifica por velocidad, anonimato, país y calidad</b>. Lo que normalmente harías a mano
          durante horas, aquí toma minutos.
        </p>
        <div className="why-grid">
          <div className="why-card"><span>⏱️</span><b>Ahorra horas</b><p>~20.000 proxies verificadas automáticamente en paralelo.</p></div>
          <div className="why-card"><span>🎯</span><b>Solo las que sirven</b><p>Doble verificación elimina las muertas y los falsos positivos.</p></div>
          <div className="why-card"><span>🛡️</span><b>Anonimato real</b><p>Detecta si el proxy filtra tu IP (transparente / anónimo / elite).</p></div>
          <div className="why-card"><span>🗄️</span><b>Tu baúl</b><p>Guarda las mejores y reúsalas cuando quieras, exporta a TXT/CSV/JSON.</p></div>
        </div>
      </section>

      {/* Para qué sirve */}
      <section className="panel">
        <h3 className="guide-h">🎯 ¿Para qué sirve un proxy?</h3>
        <ul className="guide-list">
          <li><b>Web scraping:</b> recopilar datos de muchas páginas sin que te bloqueen por IP.</li>
          <li><b>Automatización:</b> ejecutar bots / múltiples cuentas o tareas sin restricciones de IP.</li>
          <li><b>Acceso geográfico:</b> ver contenido o precios como si estuvieras en otro país.</li>
          <li><b>Privacidad:</b> ocultar tu IP real al navegar o probar.</li>
          <li><b>Testing / QA:</b> verificar cómo se ve tu sitio desde distintas ubicaciones.</li>
        </ul>
      </section>

      {/* Tipos */}
      <section className="panel">
        <h3 className="guide-h">🔌 ¿Qué tipo de proxy uso?</h3>
        <div className="type-table">
          <div className="type-row head"><span>Tipo</span><span>Mejor para</span><span>Notas</span></div>
          <div className="type-row"><span className="proto-tag">HTTP</span><span>Scraping de sitios públicos, monitoreo de precios</span><span>Rápido, universal. No para datos sensibles.</span></div>
          <div className="type-row"><span className="proto-tag">HTTPS</span><span>Login, formularios, tráfico cifrado</span><span>Más seguro que HTTP.</span></div>
          <div className="type-row"><span className="proto-tag">SOCKS4</span><span>Apps genéricas, TCP</span><span>Más flexible que HTTP.</span></div>
          <div className="type-row"><span className="proto-tag">SOCKS5</span><span>Lo que sea: torrents, gaming, apps, máxima anonimato</span><span>★ El más versátil y anónimo.</span></div>
        </div>
        <p className="guide-tip">💡 Para la mayoría de casos serios usa <b>SOCKS5</b> con calidad <b>PREMIUM</b> o <b>HIGH</b> y anonimato <b>Elite</b>.</p>
      </section>

      {/* Cómo se usa la app */}
      <section className="panel">
        <h3 className="guide-h">🚀 Cómo usar esta herramienta</h3>
        <ol className="guide-steps">
          <li><b>Checker masivo:</b> elige fuente (Todas / SOCKS / HTTP…), nivel de verificación, concurrencia y dale <b>Iniciar</b>. Verás el progreso en vivo y las proxies vivas apareciendo.</li>
          <li><b>Filtra y exporta:</b> filtra por protocolo, calidad o país; exporta a TXT / CSV / JSON.</li>
          <li><b>Test rápido:</b> ¿tienes UN proxy? Pégalo y comprueba al instante si sirve.</li>
          <li><b>Limpiar lista:</b> ¿lista desordenada con basura y duplicados? Pégala y obtén una limpia.</li>
          <li><b>Baúl:</b> guarda tus mejores proxies para reusarlas más tarde.</li>
        </ol>
      </section>

      {/* Integración */}
      <section className="panel">
        <h3 className="guide-h">🧩 Cómo conectar las proxies a tus herramientas</h3>

        <div className="code-block">
          <div className="code-head">cURL</div>
          <pre>{`curl -x http://IP:PUERTO https://api.ipify.org
curl -x socks5://IP:PUERTO https://api.ipify.org`}</pre>
        </div>

        <div className="code-block">
          <div className="code-head">Python (requests)</div>
          <pre>{`import requests
proxies = {"http": "http://IP:PUERTO", "https": "http://IP:PUERTO"}
r = requests.get("https://api.ipify.org", proxies=proxies, timeout=10)
print(r.text)`}</pre>
        </div>

        <div className="code-block">
          <div className="code-head">Python — rotación con el motor incluido</div>
          <pre>{`from proxy_checker_v2 import ProxyPool
pool = ProxyPool(results)
proxy = pool.get_next(protocol="socks5", min_score=60)  # rota automáticamente`}</pre>
        </div>

        <div className="code-block">
          <div className="code-head">Scrapy (settings.py)</div>
          <pre>{`# usa una proxy por request
request.meta["proxy"] = "http://IP:PUERTO"`}</pre>
        </div>
      </section>

      <section className="panel guide-warn">
        <h3 className="guide-h">⚠️ Uso responsable</h3>
        <p>Las proxies públicas son de terceros y tienen vida corta — vuelve a verificar antes de cada sesión.
        Usa esta herramienta para fines legítimos y respeta los términos de servicio de los sitios y las leyes aplicables.</p>
      </section>
    </div>
  );
}
