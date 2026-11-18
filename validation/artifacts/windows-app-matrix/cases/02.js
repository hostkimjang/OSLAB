(() => {
  const width = 180;
  const height = 180;
  const margin = 10;
  const gap = 8;
  const supplied = [
    { id: 'A', name: 'Housing', x: 18, y: 22, w: 70, h: 50, color: '#5259d8' },
    { id: 'B', name: 'Mount', x: 63, y: 43, w: 60, h: 60, color: '#16a89c' },
    { id: 'C', name: 'Cover', x: 117, y: 132, w: 90, h: 50, color: '#e78538' },
  ];

  function inspect(parts) {
    const overflowIds = parts.filter(part => part.x < margin || part.y < margin ||
      part.x + part.w > width - margin || part.y + part.h > height - margin).map(part => part.id);
    const collisions = [];
    for (let i = 0; i < parts.length; i += 1) {
      for (const next of parts.slice(i + 1)) {
        const part = parts[i];
        const w = Math.min(part.x + part.w, next.x + next.w) - Math.max(part.x, next.x);
        const h = Math.min(part.y + part.h, next.y + next.h) - Math.max(part.y, next.y);
        if (w > 0 && h > 0) collisions.push({ pair: part.id + '+' + next.id, area: w * h });
      }
    }
    return {
      parts, overflowIds, collisions,
      clearance: Math.min(...parts.map(part => Math.min(part.x, part.y, width - part.x - part.w, height - part.y - part.h))),
      fits: overflowIds.length === 0 && collisions.length === 0,
    };
  }

  function nest(parts) {
    let x = margin;
    let y = margin;
    let rowHeight = 0;
    return parts.map(part => {
      if (x + part.w > width - margin) {
        x = margin;
        y += rowHeight + gap;
        rowHeight = 0;
      }
      const packed = { ...part, x, y };
      x += part.w + gap;
      rowHeight = Math.max(rowHeight, part.h);
      return packed;
    });
  }

  function plate(parts, alerts) {
    const labels = parts.map(part => {
      const bad = alerts && (alerts.overflowIds.includes(part.id) ||
        alerts.collisions.some(collision => collision.pair.split('+').includes(part.id)));
      return '<rect x="' + part.x + '" y="' + part.y + '" width="' + part.w + '" height="' + part.h +
        '" fill="' + part.color + '" stroke="' + (bad ? '#b92038' : part.color) + '" stroke-width="' +
        (bad ? '2.5' : '1') + '" opacity=".84" rx="3"/><text x="' + (part.x + part.w / 2) +
        '" y="' + (part.y + part.h / 2 + 4) + '" text-anchor="middle" font-size="11" font-weight="700" fill="#fff">' +
        part.id + '</text>';
    }).join('');
    return '<svg viewBox="-18 -16 241 215" role="img" aria-label="Print bed and imported part footprints">' +
      '<defs><pattern id="plate-grid" width="10" height="10" patternUnits="userSpaceOnUse"><path d="M 10 0 H 0 V 10" fill="none" stroke="#dfe2f1" stroke-width=".7"/></pattern></defs>' +
      '<rect width="180" height="180" rx="3" fill="#f8f9ff" stroke="#9ba6d1"/><rect width="180" height="180" fill="url(#plate-grid)"/>' +
      '<rect x="10" y="10" width="160" height="160" rx="2" fill="none" stroke="#a7afcc" stroke-dasharray="3 2"/>' +
      labels + '<text x="90" y="194" text-anchor="middle" fill="#57607c" font-size="7">180 mm build plate</text></svg>';
  }

  function render(step, result) {
    const parts = step === 0 ? [] : step === 1 ? supplied : result.parts;
    const alerts = step >= 2 && !result.fits ? result : null;
    const detail = step === 0 ? 'Import the footprints for the three fixture components.'
      : step === 1 ? 'Three parts are staged at their requested positions. Inspect the plate before nesting.'
        : step === 2 ? 'Housing intersects Mount over ' + result.collisions[0].area + ' mm². Cover crosses the usable boundary.'
          : 'Nested in two rows with ' + result.clearance + ' mm minimum edge clearance. Ready for print planning.';
    return '<style> .plate-app{display:grid;grid-template-columns:1.18fr .82fr;gap:18px;height:100%;padding:6px;color:#273155;font-family:"Segoe UI",sans-serif} .plate-stage,.plate-info{background:#fff;border:1px solid #cacfea;border-radius:13px;padding:15px 19px} .plate-stage svg{height:355px;width:100%;display:block;margin-top:5px} .plate-app h2{font-size:20px;margin:1px 0 4px;letter-spacing:-.04em} .plate-spec{color:#687594;font-size:13px;margin:0 0 12px} .plate-part{display:grid;grid-template-columns:13px 1fr auto;align-items:center;gap:10px;border-top:1px solid #e9ebf7;min-height:49px;font-size:14px} .plate-part i{height:11px;width:11px;border-radius:3px} .plate-part span{color:#566581} .plate-badge{display:inline-block;padding:6px 10px;border-radius:5px;font-size:13px;font-weight:700;background:#e6e9fd;color:#403a9a;margin:17px 0 9px} .plate-badge.invalid{color:#8f1731;background:#ffe4e8} .plate-badge.valid{color:#095548;background:#ccf4e7} .plate-detail{color:#344362;font-size:16px;line-height:1.45} </style><div class="plate-app"><section class="plate-stage"><h2>Print bed preview</h2><p class="plate-spec">180 × 180 mm / ' +
      margin + ' mm edge exclusion</p>' + plate(parts, alerts) + '</section><section class="plate-info"><h2>Part queue</h2>' +
      '<p class="plate-spec">Fixture assembly PR-68</p>' + supplied.map(part => '<div class="plate-part"><i style="background:' +
        part.color + '"></i><strong>' + part.name + '</strong><span>' + part.w + ' × ' + part.h + ' mm</span></div>').join('') +
      '<div class="plate-badge ' + (step === 2 ? 'invalid' : step === 3 ? 'valid' : '') + '">' +
      ['Awaiting parts', '3 footprints loaded', 'Overlap detected / outside bounds', '3 parts fit'][step] +
      '</div><div class="plate-detail">' + detail + '</div></section></div>';
  }

  window.caseDefinition = {
    id: '02', title: 'Build Plate Planner', kicker: 'Additive manufacturing',
    scenario: 'Detect overlapping and out-of-bounds footprints, then nest a printable plate.',
    layout: 'canvas', accent: '#5359d7', surface: '#eef0fb', text: '#202746',
    actions: ['Load part footprints', 'Inspect the plate', 'Auto-nest the parts'],
    expected: [
      { partCount: 3, footprintArea: 11600 },
      { overflowIds: ['C'], collisions: [{ pair: 'A+B', area: 725 }], clearance: -27, fits: false },
      { overflowIds: [], collisions: [], clearance: 10, fits: true },
    ],
    run(step) {
      if (step === 1) return { partCount: supplied.length, footprintArea: supplied.reduce((sum, part) => sum + part.w * part.h, 0) };
      return inspect(step === 2 ? supplied : nest(supplied));
    },
    render,
  };
})();
