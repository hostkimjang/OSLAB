(() => {
  const ceiling = 18000;
  const studios = [
    { id: 'STUDIO', name: 'Studio production', dollars: 8500, limit: 8000, color: '#7ee8df' },
    { id: 'FIELD', name: 'Field recording', dollars: 5700, limit: 6200, color: '#8cafff' },
    { id: 'DESIGN', name: 'Design services', dollars: 2600, limit: 3000, color: '#b4a9ff' },
    { id: 'POST', name: 'Post production', dollars: 2200, limit: 2600, color: '#fbcda1' },
  ];
  const deferral = { id: 'PO-718', group: 'STUDIO', dollars: 1200, queuedPeriod: 'Q3', approval: 'FIN-42' };
  const usd = value => (value < 0 ? '−' : '') + '$' + Math.abs(value).toLocaleString('en-US');
  const total = rows => rows.reduce((n, row) => n + row.dollars, 0);

  function run(step) {
    const rows = studios.map(row => step === 3 && row.id === deferral.group
      ? { ...row, dollars: row.dollars - deferral.dollars }
      : row);
    const dollars = total(rows);
    if (step === 1) return { lineCount: rows.length, projected: dollars, ceiling };
    const violations = rows.filter(row => row.dollars > row.limit).map(row => row.id + '_CAP');
    if (dollars > ceiling) violations.unshift('PORTFOLIO_CAP');
    return {
      rows, projected: dollars, ceiling, violations,
      headroom: ceiling - dollars, gate: violations.length ? 'blocked' : 'approved',
      ...(step === 3 && {
        deferredId: deferral.id, deferredValue: deferral.dollars, deferredPeriod: deferral.queuedPeriod,
        committedPolicy: rows.map(row => ({ category: row.id, dollars: row.dollars })),
      }),
    };
  }

  function render(step, result) {
    const rows = step >= 2 ? result.rows : studios;
    const dollars = total(rows);
    const status = step === 3 ? 'Plan approved' : step === 2 ? 'Review blocked' : 'Ready for review';
    return `<div class="sb-screen">
      <aside class="sb-score">
        <p>PERIOD 02 / PRODUCTION PLAN</p>
        <h2>${usd(dollars)}</h2><span>Projected commitments</span>
        <div class="sb-mini"><span>Portfolio cap</span><strong>${usd(ceiling)}</strong></div>
        <div class="sb-mini"><span>Headroom</span><strong data-low="${dollars > ceiling}">${usd(ceiling - dollars)}</strong></div>
        <div class="sb-status" data-error="${step === 2}">${status}</div>
      </aside>
      <section class="sb-report">
        <div class="sb-title"><div><small>COMMITMENTS BY COST CENTER</small><h2>Forecast vs. local cap</h2></div><span><i></i> Cap</span></div>
        <div class="sb-chart" role="img" aria-label="Forecast against cap">
          ${rows.map(row => `<div class="sb-row">
            <span>${row.name}</span>
            <div class="sb-track"><div class="sb-fill" style="--bar:${row.color};width:${row.dollars / 9200 * 100}%"></div>
              <i style="left:${row.limit / 9200 * 100}%"></i></div>
            <b>${usd(row.dollars)}</b>
            <strong data-error="${step > 0 && row.dollars > row.limit}">${row.dollars > row.limit && step > 0 ? 'Over cap' : 'Within plan'}</strong>
          </div>`).join('')}
        </div>
        <div class="sb-audit">${step === 3
          ? '<b>FIN-42</b> &nbsp; PO-718 moved to Q3. $1,200 deferred with authorization.'
          : step === 2
            ? '<b>2 exceptions</b> &nbsp; Portfolio is $1,000 over. Studio is $500 over its cap.'
            : '<b>Plan intake</b> &nbsp; Review all four cost centers against local and portfolio limits.'}</div>
      </section>
    </div>`;
  }

  window.caseDefinition = {
    id: '11', title: 'Signal Budget', kicker: 'OPERATIONS / SPEND CONTROL',
    scenario: 'Block an overspent production plan and verify an approved deferral clears two independent caps.',
    layout: 'chart', accent: '#6f57d8', surface: '#e8e8fa', text: '#202040',
    actions: ['Load Q2 commitment plan', 'Run budget policy', 'Approve deferred purchase'],
    expected: [
      { lineCount: 4, projected: 19000, ceiling: 18000 },
      { projected: 19000, ceiling: 18000, violations: ['PORTFOLIO_CAP', 'STUDIO_CAP'], headroom: -1000, gate: 'blocked' },
      { projected: 17800, ceiling: 18000, violations: [], headroom: 200, gate: 'approved', deferredId: 'PO-718', deferredValue: 1200, deferredPeriod: 'Q3' },
    ],
    run, render,
    style: `
      .sb-screen{display:grid;grid-template-columns:minmax(208px,1fr) minmax(0,3.1fr);gap:0;color:#f4f3ff;font:14px/1.35 "Segoe UI",sans-serif;background:#222045;border-radius:14px;overflow:hidden;box-shadow:0 12px 32px #21163b27}
      .sb-score{padding:32px 22px;background:#332763;border-right:1px solid #524786}
      .sb-score p,.sb-title small{margin:0;color:#c9c4f4;font:700 10px/1.4 Consolas,monospace;letter-spacing:.13em}
      .sb-score h2{margin:30px 0 1px;font-size:clamp(34px,4vw,53px);line-height:1;color:#e1d8ff}
      .sb-score>span{display:block;color:#d7c9fd;margin:4px 0 25px}
      .sb-mini{display:flex;justify-content:space-between;align-items:center;padding:10px 0;border-top:1px solid #71629b;gap:10px}
      .sb-mini strong{color:#a8f4e1;font-family:Consolas,monospace}
      .sb-mini strong[data-low=true]{color:#ffc49e}
      .sb-status{padding:9px;margin-top:13px;text-align:center;background:#276452;color:#b1f5de;border-radius:5px;font-weight:700}
      .sb-status[data-error=true]{background:#704047;color:#ffd4b0}
      .sb-report{padding:24px 24px 21px}
      .sb-title{display:flex;justify-content:space-between;align-items:center;margin-bottom:25px}
      .sb-title h2{font-size:28px;margin:5px 0 0;font-weight:600;line-height:1.05}
      .sb-title>span{color:#d4cbf5;font-size:12px;white-space:nowrap}
      .sb-title>span i{display:inline-block;width:2px;height:11px;margin-right:6px;background:#fff}
      .sb-row{display:grid;grid-template-columns:minmax(100px,1.2fr) minmax(100px,2.4fr) 60px 65px;gap:9px;align-items:center;margin:12px 0}
      .sb-row>span{white-space:nowrap;font-size:12px}
      .sb-row>b{text-align:right;font-family:Consolas,monospace}
      .sb-row>strong{text-align:right;font-size:10px;color:#c1bbde}
      .sb-row>strong[data-error=true]{color:#ffc49e}
      .sb-track{height:15px;background:repeating-linear-gradient(90deg,#38305f,#38305f 2px,#302b53 2px,#302b53 22px);position:relative;border-radius:2px}
      .sb-track i{position:absolute;width:2px;top:-4px;height:23px;background:#fff}
      .sb-fill{height:100%;background:var(--bar);border-radius:2px}
      .sb-audit{margin-top:22px;padding:11px 12px;border:1px solid #575285;color:#ddd6fc;font-size:13px}
      .sb-audit b{color:#a8f4e1}
    `,
  };
})();
