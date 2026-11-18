(() => {
  const cartons = [
    { size: 'S', dimensions: [280, 210, 110], limit: 2000 },
    { size: 'M', dimensions: [360, 230, 160], limit: 5000 },
    { size: 'L', dimensions: [440, 280, 190], limit: 8000 },
  ];
  const order = [
    { sku: 'EN-301', name: 'Sensor enclosure', dimensions: [300, 150, 80], grams: 960 },
    { sku: 'TP-475', name: 'Survey tripod', dimensions: [475, 140, 110], grams: 2500 },
    { sku: 'BT-265', name: 'Battery tray', dimensions: [265, 195, 70], grams: 1300 },
    { sku: 'AN-310', name: 'Radio antenna', dimensions: [310, 70, 65], grams: 380 },
  ];

  function assign(item) {
    const axes = [...item.dimensions].sort((a, b) => b - a);
    const carton = cartons.find(({ dimensions, limit }) =>
      item.grams <= limit && axes.every((value, i) => value <= dimensions[i]));
    return { ...item, carton: carton?.size ?? 'Unfitted' };
  }

  function dispatch() {
    const tripod = order.find((item) => item.sku === 'TP-475');
    const sections = [
      { ...tripod, sku: 'TP-475-A', name: 'Tripod leg assembly', dimensions: [310, 140, 110], grams: 1700 },
      { ...tripod, sku: 'TP-475-B', name: 'Tripod head', dimensions: [190, 140, 110], grams: 800 },
    ];
    const parcels = order.flatMap((item) => item === tripod ? sections : [item]).map(assign);
    return {
      parcels,
      labels: parcels.filter((item) => item.carton !== 'Unfitted').length,
      small: parcels.filter((item) => item.carton === 'S').length,
      medium: parcels.filter((item) => item.carton === 'M').length,
      packedGrams: parcels.reduce((grams, item) => grams + item.grams, 0),
    };
  }

  function packagingGraphic() {
    return `<svg viewBox="0 0 380 224" role="img" aria-label="Isometric illustration of the longest carton">
      <path d="M57 84 222 34 328 78 164 134Z" fill="#f7bd55" stroke="#a65e1c" stroke-width="2"/>
      <path d="M57 84 164 134 164 211 57 161Z" fill="#da8435" stroke="#a65e1c" stroke-width="2"/>
      <path d="M164 134 328 78 328 155 164 211Z" fill="#efaa48" stroke="#a65e1c" stroke-width="2"/>
      <path d="M103 70 214 117 239 109 128 63Z" fill="#fff0ad" opacity=".8"/>
      <text x="210" y="164" fill="#6c3411" font-size="20" font-weight="800">440 MM</text>
      <path d="M58 184 160 228M177 223 329 173" fill="none" stroke="#885732" stroke-width="2" stroke-dasharray="5 4"/>
    </svg>`;
  }

  function render(step, result) {
    const items = result?.parcels ?? order;
    const detail = step === 2
      ? '<strong class="hold">TP-475 needs repack</strong><span>The 475 mm longest edge exceeds carton L by 35 mm.</span>'
      : step === 3
        ? '<strong>Five labels released</strong><span>Two tripod assemblies replace the oversize parcel. Total weight is unchanged.</span>'
        : '<strong>Carton fit rules</strong><span>Each parcel must fit all three internal axes and its weight limit.</span>';
    return `<div class="carton-workspace">
      <aside>${packagingGraphic()}<div class="carton-note">${detail}</div></aside>
      <section>
        <div class="carton-strip">${cartons.map((carton) =>
          `<div><b>${carton.size}</b><span>${carton.dimensions.join(' × ')} mm</span></div>`).join('')}</div>
        <table aria-label="Packing list">
          <thead><tr><th>Parcel</th><th>Dimensions (mm)</th><th>Weight</th><th>Carton</th></tr></thead>
          <tbody>${items.map((item) => `<tr class="${item.carton === 'Unfitted' ? 'oversize' : ''}">
            <td><b>${item.name}</b><small>${item.sku}</small></td>
            <td>${item.dimensions.join(' × ')}</td><td>${item.grams} g</td><td>${item.carton ?? '—'}</td>
          </tr>`).join('')}</tbody>
        </table>
      </section>
    </div>`;
  }

  window.caseDefinition = {
    id: '13',
    title: 'Carton Fit',
    kicker: 'PACK STATION',
    scenario: 'Fit a mixed order into approved cartons, then repack one oversize item.',
    layout: 'board',
    accent: '#a75517',
    surface: '#fff4dd',
    text: '#3d2a1b',
    actions: ['Load shipping order', 'Check carton fit', 'Split tripod and release labels'],
    expected: [
      { items: 4, inputGrams: 5140 },
      { fitted: 3, oversizeSku: 'TP-475', excessMm: 35 },
      { labels: 5, small: 2, medium: 3, packedGrams: 5140 },
    ],
    run(step) {
      if (step === 1) {
        return { items: order.length, inputGrams: order.reduce((sum, item) => sum + item.grams, 0) };
      }
      if (step === 2) {
        const parcels = order.map(assign);
        const held = parcels.find((item) => item.carton === 'Unfitted');
        return {
          parcels,
          fitted: parcels.filter((item) => item.carton !== 'Unfitted').length,
          oversizeSku: held.sku,
          excessMm: Math.max(...held.dimensions) - cartons.at(-1).dimensions[0],
        };
      }
      return dispatch();
    },
    render,
    style: `
      .carton-workspace{display:grid;grid-template-columns:minmax(255px,.75fr) minmax(440px,1.55fr);gap:24px}
      .carton-workspace section,.carton-workspace aside{border:1px solid #edd7b7;border-radius:14px;background:#fffbef;overflow:hidden}
      .carton-workspace aside{padding:18px;display:flex;flex-direction:column;justify-content:center}
      .carton-workspace svg{height:221px;width:100%}
      .carton-note{line-height:1.4;margin-top:17px;border-top:1px solid #eac89b;padding:16px 4px}
      .carton-note strong,.carton-note span{display:block}.carton-note strong{font-size:23px}.carton-note .hold{color:#922f20}
      .carton-strip{display:flex;justify-content:space-around;padding:14px;background:#f5e3bd;gap:10px}
      .carton-strip div{display:flex;align-items:center;gap:10px;font-size:14px}.carton-strip b{background:#f2bc60;padding:6px 9px;border-radius:5px}
      .carton-workspace table{width:100%;border-collapse:collapse;text-align:left}.carton-workspace td,.carton-workspace th{padding:9px 14px;border-bottom:1px solid #eeddbf}
      .carton-workspace th{font-size:12px;color:#745535;text-transform:uppercase}.carton-workspace td{font-size:15px;white-space:nowrap}
      .carton-workspace td small{display:block;color:#765d49}.carton-workspace .oversize{background:#fad5bd;color:#802c20}
    `,
  };
})();
