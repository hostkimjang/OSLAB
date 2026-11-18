(() => {
  const inventory = [
    { sku: 'GC17', name: 'Ground coffee', zone: 'A-03', stock: 72 },
    { sku: 'FP01', name: 'Filter packs', zone: 'A-06', stock: 96 },
    { sku: 'CC31', name: 'Ceramic cups', zone: 'B-02', stock: 48 },
    { sku: 'PS02', name: 'Pour-over sets', zone: 'B-09', stock: 38 },
  ];
  const scans = [
    { label: 'CA-01', sku: 'GC17', qty: 42 },
    { label: 'CA-02', sku: 'GC17', qty: 28 },
    { label: 'FI-01', sku: 'FP01', qty: 48 },
    { label: 'FI-02', sku: 'FP01', qty: 48 },
    { label: 'CU-01', sku: 'CC31', qty: 27 },
    { label: 'CU-02', sku: 'CC31', qty: 24 },
    { label: 'PO-01', sku: 'PS02', qty: 18 },
    { label: 'PO-02', sku: 'PS02', qty: 20 },
    { label: 'CA-02', sku: 'GC17', qty: 28 },
  ];
  const recounts = { 'CA-02': 30, 'CU-01': 24 };

  function reconcile(entries, useRecounts) {
    const labels = new Set();
    const counts = new Map();
    const duplicateLabels = [];
    for (const scan of entries) {
      if (labels.has(scan.label)) {
        duplicateLabels.push(scan.label);
        continue;
      }
      labels.add(scan.label);
      const qty = useRecounts && scan.label in recounts ? recounts[scan.label] : scan.qty;
      counts.set(scan.sku, (counts.get(scan.sku) || 0) + qty);
    }
    const lines = inventory.map(row => {
      const counted = counts.get(row.sku) || 0;
      return { ...row, counted, variance: counted - row.stock };
    });
    const discrepancies = lines.filter(line => line.variance !== 0);
    return {
      uniqueScans: labels.size,
      duplicateLabels,
      countedUnits: lines.reduce((sum, line) => sum + line.counted, 0),
      variance: lines.reduce((sum, line) => sum + line.variance, 0),
      discrepancies: discrepancies.map(line => line.sku),
      released: useRecounts && discrepancies.length === 0,
      recountsApplied: useRecounts ? Object.keys(recounts).length : 0,
      lines,
    };
  }

  function stats(metrics) {
    return '<div class="stock-metrics">' + metrics.map(([label, value]) =>
      '<div><span>' + label + '</span><b>' + value + '</b></div>').join('') + '</div>';
  }

  function render(step, result) {
    const rows = step >= 2 ? result.lines : inventory;
    const metrics = step === 0 ? [['Bins in scope', 4], ['Ledger units', 254], ['Pending batch', 'SC-28']]
      : step === 1 ? [['Labels ingested', result.rawScans], ['Raw units', result.rawUnits], ['Queue', 'Unposted']]
        : [['Counted units', result.countedUnits], ['Variance lines', result.discrepancies.length],
          ['Run state', result.released ? 'Released' : 'Held']];
    const status = step === 0 ? 'Cycle count for the North Warehouse.'
      : step === 1 ? 'Batch received. Match scans against the approved ledger before posting.'
        : step === 2 ? 'CA-02 scanned twice. GC17 is short by 2 and CC31 is over by 3.'
          : 'Two verified recounts applied. Duplicate scan ignored and stock balances.';
    const grid = rows.map(row => '<div class="stock-row"><div><strong>' + row.name + '</strong><small>' +
      row.sku + ' / Bin ' + row.zone + '</small></div><div class="stock-bars"><i style="width:' + row.stock + '%"></i>' +
      (step >= 2 ? '<b style="width:' + row.counted + '%"></b>' : '') + '</div><em>' + row.stock +
      '</em><em>' + (step >= 2 ? row.counted : '–') + '</em><em class="' +
      (step >= 2 && row.variance ? 'stock-discrepancy' : '') + '">' +
      (step >= 2 ? (row.variance > 0 ? '+' : '') + row.variance : '–') + '</em></div>').join('');
    return '<style> .stock{height:100%;display:grid;align-content:start;gap:16px;padding:6px;color:#c9dfd4;font-family:"Segoe UI",sans-serif} .stock-metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:14px} .stock-metrics>div,.stock-grid,.stock-note{background:#16352e;border:1px solid #2b574a;border-radius:12px;padding:12px 20px} .stock-metrics span,.stock-row small{display:block;font-size:12px;color:#99b8a8;font-weight:650;margin-bottom:4px;letter-spacing:.07em} .stock-metrics b{font-size:31px;letter-spacing:-.035em;color:#d6f8e1} .stock-grid{padding:7px 20px} .stock-row{display:grid;align-items:center;grid-template-columns:1.55fr 2fr .55fr .55fr .55fr;gap:14px;min-height:54px;border-bottom:1px solid #2b574a} .stock-row:last-child{border-bottom:0} .stock-row small{margin:2px 0 0;letter-spacing:0} .stock-row em{font-style:normal;text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums} .stock-bars{display:grid;gap:4px} .stock-bars>i,.stock-bars>b{display:block;height:5px;border-radius:3px;background:#4a6e5e} .stock-bars>b{background:#8ee9af} .stock-discrepancy{color:#ffb294;font-weight:700} .stock-note{font-size:15px;color:#a6ecc2} .stock-label{font-size:12px;min-height:36px;color:#99b8a8} </style><section class="stock">' + stats(metrics) + '<div class="stock-grid"><div class="stock-row stock-label">' +
      '<b>Inventory</b><b>Ledger / counted</b><em>Ledger</em><em>Count</em><em>Delta</em></div>' + grid +
      '</div><div class="stock-note">' + status + '</div></section>';
  }

  window.caseDefinition = {
    id: '01', title: 'Stockroom Reconciler', kicker: 'Inventory control',
    scenario: 'Block a duplicate-labeled warehouse cycle count, then release a verified recount.',
    layout: 'table', accent: '#8ee9af', surface: '#0c2720', text: '#edfbf2',
    actions: ['Load handheld scans', 'Reconcile against ledger', 'Apply verified recount'],
    expected: [
      { rawScans: 9, rawUnits: 283, ledgerUnits: 254 },
      { uniqueScans: 8, duplicateLabels: ['CA-02'], countedUnits: 255, variance: 1, discrepancies: ['GC17', 'CC31'], released: false },
      { countedUnits: 254, variance: 0, discrepancies: [], recountsApplied: 2, released: true },
    ],
    run(step) {
      if (step === 1) return {
        rawScans: scans.length,
        rawUnits: scans.reduce((sum, scan) => sum + scan.qty, 0),
        ledgerUnits: inventory.reduce((sum, row) => sum + row.stock, 0),
      };
      return reconcile(scans, step === 3);
    },
    render,
  };
})();
