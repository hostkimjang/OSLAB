(() => {
  const delivery = [
    { file: 'bill-of-lading', title: 'Bill of lading', pages: [1, 2] },
    { file: 'inspection', title: 'Inspection checklist', pages: [2, 4] },
    { file: 'signature', title: 'Signed receipt', pages: [5] },
  ];
  const correctedInspection = { file: 'inspection-reissue', title: 'Reissued inspection', pages: [3, 4] };
  const packetPages = [1, 2, 3, 4, 5];

  function collate(files) {
    const suppliedPages = files.flatMap((file) => file.pages);
    return {
      files: files.length,
      pages: suppliedPages.length,
      missing: packetPages.filter((page) => !suppliedPages.includes(page)),
      duplicates: packetPages.filter((page) => suppliedPages.filter((current) => current === page).length > 1),
    };
  }

  function render(step, result) {
    const repaired = step === 3;
    const files = repaired ? [delivery[0], correctedInspection, delivery[2]] : delivery;
    const annotations = [
      ['01', 'Arrival details', 'Manifest · 6 pallets'],
      ['02', 'Cargo manifest', 'Seal RB-1954'],
      ['03', 'Inspection form', 'Temperature and seal'],
      ['04', 'Inspection notes', 'No damage observed'],
      ['05', 'Recipient signature', 'Received at 14:28'],
    ];
    const sheets = annotations.map(([number, title, note], index) => {
      const absent = step > 0 && !files.some((file) => file.pages.includes(index + 1));
      const duplicate = step > 1 && result.duplicates.includes(index + 1);
      return '<div class="binder-paper ' + (absent ? 'binder-absent' : '') + '">' +
        '<b>' + number + '</b><strong>' + title + '</strong><span>' + note + '</span>' +
        '<div class="binder-lines"></div><small>' + (absent ? 'Missing page' : duplicate ? 'Duplicate page' : 'Packet B-204') +
        '</small></div>';
    }).join('');
    const fileList = files.map((file) => '<li>' + file.title + '<span>' + file.pages.join(', ') + '</span></li>').join('');
    const banner = step < 2 ? 'COLLATION PREVIEW' : repaired ? '5 PAGES / READY TO SHIP' : 'BLOCKED / PAGE 03 MISSING';

    return '<div class="binder"><div class="binder-summary"><div><small>RECEIVING / EAST DOCK</small>' +
      '<h2>Delivery packet B-204</h2><p>Collate the shipping records into their original order before release.</p></div>' +
      '<b class="binder-stamp">' + banner + '</b></div>' +
      '<div class="binder-sheets">' + sheets + '</div>' +
      '<div class="binder-detail"><strong>Source pages</strong><ul>' + fileList + '</ul></div></div>';
  }

  window.caseDefinition = {
    id: '05',
    title: 'Binder Desk',
    kicker: 'Document collation',
    scenario: 'Prevent release of a delivery packet with a missing page and a duplicate page.',
    layout: 'canvas',
    accent: '#9a4c21',
    surface: '#f3eee2',
    text: '#33261c',
    actions: ['Open source bundle', 'Check page sequence', 'Replace scan and collate'],
    expected: [
      { files: 3, pages: 5 },
      { missing: [3], duplicates: [2], releaseAllowed: false },
      { missing: [], duplicates: [], releaseAllowed: true, pageOrder: [1, 2, 3, 4, 5] },
    ],
    style: '.binder{padding:22px 30px;background:#f3eee2;color:#33261c;border-radius:13px}.binder-summary{display:flex;align-items:center;justify-content:space-between}.binder-summary h2{margin:5px 0;font:700 34px Georgia,serif}.binder-summary p{margin:5px 0 18px}.binder-summary small{letter-spacing:.13em;color:#925c3d}.binder-stamp{border:2px solid #a15730;color:#8e431c;padding:9px 12px;transform:rotate(-3deg);border-radius:3px;font-size:13px}.binder-sheets{display:grid;grid-template-columns:repeat(5,1fr);gap:13px}.binder-paper{padding:14px;background:#fffcf5;box-shadow:0 2px 5px #4b301326;min-height:135px;border-radius:4px;display:grid;align-content:start;gap:7px}.binder-paper b{font:700 25px Georgia,serif;color:#9a4c21}.binder-paper strong{font-size:14px}.binder-paper span,.binder-paper small{font-size:11px}.binder-paper small{color:#9a4c21}.binder-absent{border:2px dashed #b65b3c;box-shadow:none;background:#f4dfd1}.binder-lines{height:26px;background:repeating-linear-gradient(transparent 0 6px,#e3d8c7 6px 7px);margin:3px 0}.binder-detail{margin-top:15px;display:flex;align-items:center;gap:12px}.binder-detail strong{font-size:12px}.binder-detail ul{display:flex;list-style:none;gap:12px;padding:0;margin:0;flex:1}.binder-detail li{flex:1;background:#e9decc;padding:8px;border-radius:4px;font-size:12px}.binder-detail li span{float:right;font-weight:700}',
    run(step) {
      const files = step === 3 ? [delivery[0], correctedInspection, delivery[2]] : delivery;
      const stats = collate(files);
      if (step === 1) return stats;
      const releaseAllowed = stats.missing.length === 0 && stats.duplicates.length === 0;
      return {
        ...stats,
        releaseAllowed,
        pageOrder: releaseAllowed ? files.flatMap((file) => file.pages).sort((left, right) => left - right) : [],
      };
    },
    render,
  };
})();
