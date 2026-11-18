(() => {
  const invoices = [
    { id: 'INV-208', vendor: 'Juniper Lab', cents: 120000 },
    { id: 'INV-209', vendor: 'Northline Supply', cents: 47500 },
    { id: 'INV-210', vendor: 'Cobalt Office', cents: 289950 },
    { id: 'INV-211', vendor: 'Stillwater Print', cents: 62500 },
    { id: 'INV-212', vendor: 'Forma Paper', cents: 9875 },
  ];
  const payments = [
    { id: 'PAY-408', invoice: 'INV-208', cents: 120000 },
    { id: 'PAY-409', invoice: 'INV-209', cents: 47500 },
    { id: 'PAY-410', invoice: 'INV-210', cents: 289950 },
    { id: 'PAY-411', invoice: 'INV-211', cents: 65200 },
    { id: 'PAY-409', invoice: 'INV-209', cents: 47500 },
  ];
  const amendment = { payment: 'PAY-411', statementCents: 62500, approvedBy: 'Treasury' };
  const sum = rows => rows.reduce((total, row) => total + row.cents, 0);
  const currency = cents => '$' + (cents / 100).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  function reconcile(feed) {
    return invoices.map(invoice => {
      const matches = feed.filter(row => row.invoice === invoice.id);
      let decision = 'Matched';
      if (matches.length === 0) decision = 'Unpaid';
      else if (matches.length > 1) decision = 'Duplicate';
      else if (matches[0].cents !== invoice.cents) decision = 'Mismatch';
      return { ...invoice, decision, bankCents: matches.length ? sum(matches) : null };
    });
  }

  function run(step) {
    if (step === 1) {
      return {
        invoiceCount: invoices.length, paymentCount: payments.length,
        invoiceTotalCents: sum(invoices), paymentTotalCents: sum(payments),
      };
    }
    let feed = payments;
    if (step === 3) {
      feed = payments
        .filter((payment, index) => payments.findIndex(row => row.id === payment.id) === index)
        .map(payment => payment.id === amendment.payment
          ? { ...payment, cents: amendment.statementCents }
          : payment);
    }
    const rows = reconcile(feed);
    const cleared = rows.filter(row => row.decision === 'Matched');
    const exceptionIds = rows.filter(row => row.decision !== 'Matched').map(row => row.id);
    return {
      rows, matchedCount: cleared.length, transferTotalCents: sum(cleared), exceptionIds,
      duplicateCount: rows.filter(row => row.decision === 'Duplicate').length,
      mismatchCount: rows.filter(row => row.decision === 'Mismatch').length,
      unpaidTotalCents: sum(rows.filter(row => row.decision === 'Unpaid')),
      ...(step === 3 && {
        removedFeedRows: payments.length - feed.length,
        postedInvoiceIds: cleared.map(row => row.id),
        settlementCsv: ['invoice,amount_cents', ...cleared.map(row => row.id + ',' + row.cents)].join('\n'),
      }),
    };
  }

  function render(step, result) {
    const rows = step >= 2 ? result.rows : invoices;
    const notices = step === 3
      ? ['PAY-409 replay removed', 'PAY-411 statement amended', 'INV-212 remains payable']
      : step === 2
        ? ['INV-209 has two bank entries', 'INV-211 bank amount differs', 'INV-212 has no payment']
        : ['Supplier ledger · 5 invoices', 'Bank feed · 5 payment rows', 'Treasury correction available'];
    return `<div class="lm-board">
      <section class="lm-sheet">
        <header><div><small>ACCOUNTS PAYABLE</small><h2>Settlement worksheet</h2></div><span>Cycle 04</span></header>
        <table aria-label="Settlement worksheet">
          <thead><tr><th>Invoice / supplier</th><th>Ledger</th><th>Bank coverage</th><th>Decision</th></tr></thead>
          <tbody>${rows.map(row => `<tr><td><b>${row.id}</b> <span>${row.vendor}</span></td>
            <td>${currency(row.cents)}</td><td>${row.bankCents == null ? '—' : currency(row.bankCents)}</td>
            <td><strong data-state="${row.decision || 'Loaded'}">${row.decision || 'Loaded'}</strong></td></tr>`).join('')}</tbody>
        </table>
        <footer><span>${step >= 2 ? result.matchedCount + ' matched invoices' : 'Supplier ledger subtotal'}</span>
          <b>${currency(step >= 2 ? result.transferTotalCents : sum(invoices))}</b></footer>
      </section>
      <aside class="lm-review">
        <small>TREASURY REVIEW</small>
        <h2>${step === 3 ? 'Settlement ready' : step === 2 ? 'Exceptions found' : 'Review queue'}</h2>
        <p>${step === 3 ? 'Only matched payments are posted.' : step === 2 ? 'Suspense items stay outside the batch.' : 'Import the bank feed and match to invoice.'}</p>
        <ol>${notices.map(text => '<li>' + text + '</li>').join('')}</ol>
        ${step === 3 ? '<div class="lm-attachment">settlement.csv <b>4 rows</b></div>' : ''}
      </aside>
    </div>`;
  }

  window.caseDefinition = {
    id: '09', title: 'LedgerMatch', kicker: 'FINANCE / BANK RECONCILIATION',
    scenario: 'Catch overlapping bank-feed rows before posting a supplier payment batch.',
    layout: 'table', accent: '#af521d', surface: '#f7eee2', text: '#2e241e',
    actions: ['Load ledger and bank feed', 'Reconcile payment batch', 'Apply correction and post'],
    expected: [
      { invoiceCount: 5, paymentCount: 5, invoiceTotalCents: 529825, paymentTotalCents: 570150 },
      { matchedCount: 2, transferTotalCents: 409950, exceptionIds: ['INV-209', 'INV-211', 'INV-212'], duplicateCount: 1, mismatchCount: 1, unpaidTotalCents: 9875 },
      { matchedCount: 4, transferTotalCents: 519950, exceptionIds: ['INV-212'], duplicateCount: 0, mismatchCount: 0, unpaidTotalCents: 9875, removedFeedRows: 1, postedInvoiceIds: ['INV-208', 'INV-209', 'INV-210', 'INV-211'] },
    ],
    run, render,
    style: `
      .lm-board{display:grid;grid-template-columns:minmax(0,2.3fr) minmax(235px,1fr);gap:20px;font-family:Georgia,serif;color:#34281e}
      .lm-board h2{margin:6px 0 1px;font-size:30px;line-height:1.1;font-weight:600}
      .lm-board small{font:700 10px/1.2 system-ui;letter-spacing:.16em}
      .lm-sheet{background:#fffbf4;box-shadow:0 6px 18px #6438131a;border-left:4px solid #bc7339;padding:19px 21px}
      .lm-sheet header,.lm-sheet footer{position:static;display:flex;justify-content:space-between;align-items:center;padding:0;margin:0 0 15px;background:none;color:inherit}
      .lm-sheet header span{padding:5px 8px;border:1px solid #d8b691;font:600 11px system-ui}
      .lm-sheet table{width:100%;border-collapse:collapse;text-align:left;font:13px/1.35 system-ui}
      .lm-sheet th{font-size:10px;text-transform:uppercase;letter-spacing:.09em;color:#71563d;background:#f1e0c9}
      .lm-sheet td,.lm-sheet th{padding:12px 10px;border-bottom:1px solid #eee2d3;white-space:nowrap}
      .lm-sheet td span{display:inline-block;color:#826953;margin-left:5px}
      .lm-sheet td strong{font-size:11px;padding:4px 7px;background:#ede8e0}
      .lm-sheet td strong[data-state=Matched]{background:#e0eadb;color:#356342}
      .lm-sheet td strong[data-state=Duplicate],.lm-sheet td strong[data-state=Mismatch]{background:#f9ddcf;color:#992d1c}
      .lm-sheet footer{margin:13px 0 0;font:600 13px system-ui;color:#694d34}
      .lm-sheet footer b{font:700 25px Georgia;color:#34281e}
      .lm-review{background:#7c3d1c;color:#fff8e7;padding:24px 22px;border-top:6px solid #cf8d4e}
      .lm-review p{font:14px/1.45 system-ui;color:#ffdcbb;margin:12px 0 17px}
      .lm-review ol{margin:0;padding:0;list-style:none}
      .lm-review li{border-top:1px solid #c58c6490;padding:12px 0;font:600 13px system-ui}
      .lm-attachment{margin-top:14px;padding:10px;border:1px dashed #e2ad7d;display:flex;justify-content:space-between;font:13px system-ui}
    `,
  };
})();
