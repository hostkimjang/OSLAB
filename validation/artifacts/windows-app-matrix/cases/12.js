(() => {
  const financeThreshold = 1500;
  const requests = [
    { id: 'PR-069', title: 'Studio lighting', owner: 'Ava', dollars: 360, lead: 'Mona', finance: null, category: 'EQUIPMENT' },
    { id: 'PR-070', title: 'Battery storage', owner: 'Noor', dollars: 1580, lead: 'Max', finance: null, category: 'EQUIPMENT' },
    { id: 'PR-071', title: 'Cloud credits', owner: 'Rae', dollars: 965, lead: 'Rae', finance: null, category: 'SERVICES' },
    { id: 'PR-072', title: 'Captioning contract', owner: 'Blu', dollars: 2450, lead: 'Sela', finance: 'Lia', category: 'ACCESSIBILITY' },
  ];
  const signedAmendments = [
    { id: 'PR-070', role: 'finance', approver: 'Omar' },
    { id: 'PR-071', role: 'lead', approver: 'Dani' },
  ];
  const usd = dollars => '$' + dollars.toLocaleString('en-US');
  const sum = rows => rows.reduce((total, row) => total + row.dollars, 0);

  function route(row) {
    if (row.owner === row.lead || row.owner === row.finance || (row.finance && row.lead === row.finance)) return 'conflict';
    if (row.dollars >= financeThreshold && !row.finance) return 'finance';
    return 'approved';
  }

  function run(step) {
    if (step === 1) return { requestCount: requests.length, queuedTotal: sum(requests), financeThreshold };
    const rows = requests.map(request => {
      const amendment = step === 3 ? signedAmendments.find(row => row.id === request.id) : null;
      const reviewed = amendment ? { ...request, [amendment.role]: amendment.approver } : request;
      return { ...reviewed, route: route(reviewed) };
    });
    const held = status => rows.filter(row => row.route === status).map(row => row.id);
    const approved = rows.filter(row => row.route === 'approved');
    return {
      rows, approvedIds: approved.map(row => row.id), approvedTotal: sum(approved),
      financeHolds: held('finance'), conflicts: held('conflict'),
      gate: approved.length === rows.length ? 'released' : 'held',
      ...(step === 3 && {
        addedSignatures: signedAmendments.map(row => row.id + '/' + row.approver),
        releaseManifest: approved.map(row => ({ id: row.id, amount: row.dollars, approvers: [row.lead, row.finance].filter(Boolean) })),
      }),
    };
  }

  function cards(rows) {
    return rows.map(row => `<article class="al-card">
      <div><small>${row.id} · ${row.category}</small><b>${usd(row.dollars)}</b></div>
      <h3>${row.title}</h3>
      <p>${row.route === 'conflict' ? 'Creator also signed as lead' :
        row.route === 'finance' ? 'Finance signature missing' :
        'Lead ' + row.lead + (row.finance ? ' · Finance ' + row.finance : '')}</p>
    </article>`).join('');
  }

  function render(step, result) {
    const rows = step >= 2 ? result.rows : requests;
    const lanes = step >= 2
      ? [
          { title: 'Finance review', key: 'finance', empty: 'No requests awaiting finance' },
          { title: 'Approval conflict', key: 'conflict', empty: 'No approval conflicts' },
          { title: 'Ready to release', key: 'approved', empty: 'No eligible purchases' },
        ]
      : [
          { title: 'Standard intake', key: 'intake', empty: '' },
          { title: 'Finance required', key: 'review', empty: '' },
          { title: 'Release queue', key: 'approved', empty: 'Review must run before release' },
        ];
    const itemsFor = key => step >= 2 ? rows.filter(row => row.route === key)
      : rows.filter(row => key === (row.dollars >= financeThreshold ? 'review' : 'intake'));
    return `<div class="al-screen">
      <div class="al-top"><div><small>PROCUREMENT CONTROL</small><h2>Review queue</h2></div>
        <div class="al-top-total"><span>${step >= 2 ? 'APPROVED VALUE' : 'VALUE IN INTAKE'}</span>
          <strong>${usd(step >= 2 ? result.approvedTotal : sum(rows))}</strong></div></div>
      <div class="al-lanes">${lanes.map(lane => {
          const items = itemsFor(lane.key);
          return `<section data-lane="${lane.key}"><div class="al-lane-head"><b>${lane.title}</b><span>${items.length}</span></div>
            ${items.length ? cards(items) : '<div class="al-empty">' + lane.empty + '</div>'}</section>`;
        }).join('')}</div>
      <div class="al-banner" data-status="${step === 3 ? 'released' : step === 2 ? 'held' : 'intake'}"><b>${step === 3 ? 'Manifest released' : step === 2 ? 'Release held' : 'Intake loaded'}</b>
        <span>${step === 3 ? 'Finance signed PR-070. Independent lead signed PR-071.' :
          step === 2 ? 'PR-070 requires finance. PR-071 must be assigned to an independent approver.' :
          'Purchases at or above $1,500 need finance. Creators cannot sign their own requests.'}</span></div>
    </div>`;
  }

  window.caseDefinition = {
    id: '12', title: 'Approval Lanes', kicker: 'PROCUREMENT / POLICY REVIEW',
    scenario: 'Catch self-approval and missing finance signatures, then release only independently authorized purchases.',
    layout: 'board', accent: '#733c76', surface: '#f8eaf4', text: '#352238',
    actions: ['Open purchase intake', 'Route through approval policy', 'Apply signed amendments'],
    expected: [
      { requestCount: 4, queuedTotal: 5355, financeThreshold: 1500 },
      { approvedIds: ['PR-069', 'PR-072'], approvedTotal: 2810, financeHolds: ['PR-070'], conflicts: ['PR-071'], gate: 'held' },
      { approvedIds: ['PR-069', 'PR-070', 'PR-071', 'PR-072'], approvedTotal: 5355, financeHolds: [], conflicts: [], gate: 'released', addedSignatures: ['PR-070/Omar', 'PR-071/Dani'] },
    ],
    run, render,
    style: `
      .al-screen{padding:16px 18px;background:#fff9fd;color:#38243f;font:14px/1.3 system-ui;border:1px solid #e6cfe6;border-radius:18px}
      .al-top{display:flex;align-items:center;justify-content:space-between;padding:0 1px 12px}
      .al-top h2{margin:3px 0 0;font-size:27px;line-height:1.05;letter-spacing:-.035em}
      .al-top small,.al-top-total span{font:800 10px/1.3 system-ui;letter-spacing:.11em;color:#804983}
      .al-top-total{display:flex;gap:12px;align-items:baseline}
      .al-top-total strong{font:750 23px Georgia;color:#733c76}
      .al-lanes{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:11px}
      .al-lanes section{min-height:194px;padding:8px;background:#f5ebf5;border-radius:10px;border:1px solid #ead6e9}
      .al-lanes section[data-lane=finance]{background:#fff1e4;border-color:#eddbcb}
      .al-lanes section[data-lane=conflict]{background:#fce4ee;border-color:#f2ccdd}
      .al-lanes section[data-lane=approved]{background:#edf6ec;border-color:#dcead9}
      .al-lane-head{display:flex;align-items:center;justify-content:space-between;padding:3px 3px 8px;text-transform:uppercase;font:800 10px/1.2 system-ui;letter-spacing:.06em}
      .al-lane-head span{border-radius:50%;background:#fff;color:#6f5073;padding:3px 6px;font-size:11px}
      .al-card{background:#fff;padding:8px 10px;margin:0 0 5px;border:1px solid #e9dce9;border-radius:7px}
      .al-card>div{display:flex;justify-content:space-between;align-items:center;gap:5px;white-space:nowrap}
      .al-card small{font:700 10px/1.2 Consolas,monospace;color:#866987}
      .al-card h3{font-size:14px;margin:2px 0;line-height:1.15;color:#39213e}
      .al-card p{font-size:11px;color:#70596e;margin:0}
      .al-card b{font:700 12px/1.1 Consolas,monospace;color:#4b304c}
      .al-empty{margin-top:17px;color:#816881;padding:8px;text-align:center;border:1px dashed #ceb6ce;border-radius:7px}
      .al-banner{display:flex;align-items:center;gap:10px;margin-top:11px;padding:8px 10px;border-radius:7px;background:#eee2f0;color:#6d3e73;font-size:12px}
      .al-banner[data-status=held]{background:#fbe3e8;color:#96374c}
      .al-banner[data-status=released]{background:#e2f1df;color:#355f40}
      .al-banner b{white-space:nowrap}
    `,
  };
})();
