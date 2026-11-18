(() => {
  const english = {
    receipt: "Order {orderId} for {customer}",
    summary: "{count} items ready to ship",
    window: "Estimated delivery {day}"
  };
  const imported = {
    receipt: "Pedido {orderId} para {customer} {customer}",
    summary: "Artículos listos para envío",
    window: "Entrega estimada: {day}"
  };
  const fixes = {
    receipt: "Pedido {orderId} para {customer}",
    summary: "{count} artículos listos para envío"
  };

  const tokenPattern = /\{([A-Za-z][A-Za-z0-9]*)\}/g;
  const preview = { orderId: "A-1049", customer: "R. Vega", count: "7", day: "viernes" };

  function tokenCounts(message) {
    const counts = new Map();
    for (const match of message.matchAll(tokenPattern)) counts.set(match[1], (counts.get(match[1]) ?? 0) + 1);
    return counts;
  }

  function compare(catalogue) {
    return Object.entries(english).map(([key, source]) => {
      const target = catalogue[key];
      const left = tokenCounts(source), right = tokenCounts(target);
      const lost = [], extra = [];
      for (const name of new Set([...left.keys(), ...right.keys()])) {
        const diff = (left.get(name) ?? 0) - (right.get(name) ?? 0);
        if (diff > 0) lost.push(...Array(diff).fill(name));
        if (diff < 0) extra.push(...Array(-diff).fill(name));
      }
      return { key, source, target, lost, extra };
    });
  }

  const markup = (message) => message.replace(tokenPattern, (_, name) =>
    `<span style="white-space:nowrap;font-family:Consolas,monospace;background:#ede2fb;color:#653389;padding:2px 4px;border-radius:5px">{${name}}</span>`);

  window.caseDefinition = {
    id: "20",
    title: "Locale Proof",
    kicker: "LOCALIZATION QA",
    scenario: "Reject translation strings that omit or duplicate required runtime placeholders.",
    layout: "table",
    accent: "#75439d",
    surface: "#f1e5ff",
    text: "#301b42",
    actions: ["Load language bundle", "Audit placeholders", "Apply fixes and preview"],
    expected: [
      { strings: 3, locale: "es-ES" },
      { problems: 2, missing: "count", duplicate: "customer", exportable: false },
      { problems: 0, exportable: true, receipt: "Pedido A-1049 para R. Vega", summary: "7 artículos listos para envío" }
    ],
    run(step) {
      if (step === 1) return { strings: Object.keys(imported).length, locale: "es-ES" };
      const rows = compare(step === 2 ? imported : { ...imported, ...fixes });
      const problems = rows.filter((row) => row.lost.length || row.extra.length);
      const formatted = Object.fromEntries(rows.map((row) => [row.key,
        row.target.replace(tokenPattern, (token, name) => preview[name] ?? token)]));
      return {
        rows,
        problems: problems.length,
        missing: problems.flatMap((row) => row.lost).join(","),
        duplicate: problems.flatMap((row) => row.extra).join(","),
        exportable: problems.length === 0,
        receipt: formatted.receipt,
        summary: formatted.summary,
        delivery: formatted.window
      };
    },
    render(step, result) {
      const rows = step >= 2 ? result.rows : Object.entries(english).map(([key, source]) =>
        ({ key, source, target: imported[key], lost: [], extra: [] }));
      return `<section style="display:grid;grid-template-columns:2.45fr 1fr;gap:17px;padding:13px 18px;color:#301b42">
        <div style="background:#fffaff;border:1px solid #d9c4ea;border-radius:20px;padding:20px;min-width:0">
          <div style="font-size:13px;font-weight:820;color:#744496">LANGUAGE BUNDLE · CHECKOUT</div>
          <h2 style="font-size:27px;margin:6px 0 17px">Strings and placeholders</h2>
          <div style="display:grid;grid-template-columns:.68fr 1.2fr 1.45fr .8fr;gap:10px;padding:5px 11px;font-size:12px;color:#735a87;font-weight:760">
            <span>KEY</span><span>ENGLISH</span><span>SPANISH</span><span>AUDIT</span>
          </div>
          ${rows.map((row) => {
        const issue = row.lost.length ? `Missing {${row.lost.join(", ")}}` : row.extra.length
          ? `Extra {${row.extra.join(", ")}}` : "";
        return `<div style="display:grid;grid-template-columns:.68fr 1.2fr 1.45fr .8fr;gap:10px;align-items:center;padding:10px 11px;border-radius:10px;margin-top:7px;min-height:56px;background:${issue ? "#fee9ec" : "#f7efff"};font-size:14px;line-height:1.6">
              <b>${row.key}</b><span>${markup(row.source)}</span><span>${markup(row.target)}</span>
              <b style="font-size:13px;color:${issue ? "#8d2146" : "#456836"}">${issue || (step < 2 ? "Queued" : "MATCH")}</b>
            </div>`;
      }).join("")}
        </div>
        <aside style="background:#5b306f;color:#fff4ff;border-radius:20px;padding:21px">
          <div style="font-size:13px;color:#e5c4fc;font-weight:800">es-ES · LIVE PREVIEW</div>
          <h2 style="font-size:23px;line-height:1.15;margin:13px 0">${step === 2 ? "2 placeholders invalid" : step === 3 ? "Bundle ready" : "3 strings to review"}</h2>
          ${step === 3 ? `<div style="border-radius:12px;padding:14px;background:#f8f3ff;color:#3f2855;line-height:1.45">
            <b>${result.receipt}</b><div style="margin-top:9px">${result.summary}</div><div style="margin-top:9px">${result.delivery}</div>
          </div>` : `<p style="line-height:1.45;color:#f1e2f9">${step === 2 ? "Export blocked. A customer name repeats and the item count would disappear." : "Dynamic values must survive translation before export."}</p>`}
        </aside>
      </section>`;
    }
  };
})();
