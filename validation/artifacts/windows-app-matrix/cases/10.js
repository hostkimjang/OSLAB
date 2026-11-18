(() => {
  const bagLimit = 8000;
  const parcels = [
    { id: 'RMA-5206', site: 'Reno', zip: '89501', grams: 3400 },
    { id: 'RMA-5207', site: 'Reno', zip: '89501', grams: 4300 },
    { id: 'RMA-5208', site: 'Reno', zip: '89501', grams: 2200 },
    { id: 'RMA-5209', site: 'Albany', zip: '12207', grams: 1800 },
    { id: 'RMA-5210', site: 'Albany', zip: '122O7', grams: 2600 },
    { id: 'RMA-5211', site: 'Albany', zip: '12207', grams: 900 },
  ];
  const confirmedPostal = { id: 'RMA-5210', zip: '12207' };
  const kilograms = grams => (grams / 1000).toFixed(1) + ' kg';

  function plan(items) {
    const rejected = [];
    const bags = [];
    for (const item of items) {
      if (!/^\d{5}$/.test(item.zip) || !Number.isInteger(item.grams) || item.grams < 1 || item.grams > bagLimit) {
        rejected.push(item.id);
        continue;
      }
      let bag = bags.find(row => row.site === item.site && row.grams + item.grams <= bagLimit);
      if (!bag) {
        bag = { site: item.site, grams: 0, items: [] };
        bags.push(bag);
      }
      bag.items.push(item);
      bag.grams += item.grams;
    }
    return { bags, rejected };
  }

  function run(step) {
    if (step === 1) {
      return {
        requestCount: parcels.length, hubCount: new Set(parcels.map(row => row.site)).size,
        totalGrams: parcels.reduce((n, row) => n + row.grams, 0),
      };
    }
    const items = step === 3
      ? parcels.map(item => item.id === confirmedPostal.id ? { ...item, zip: confirmedPostal.zip } : item)
      : parcels;
    const { bags, rejected } = plan(items);
    return {
      bags, rejected, bagCount: bags.length, bagGrams: bags.map(bag => bag.grams),
      accepted: bags.reduce((n, bag) => n + bag.items.length, 0),
      printCount: step === 3 && !rejected.length ? bags.reduce((n, bag) => n + bag.items.length, 0) : 0,
      ...(step === 3 && {
        labels: bags.flatMap((bag, index) => bag.items.map(parcel => ({
          returnId: parcel.id, postalCode: parcel.zip, routing: bag.site, bag: index + 1,
        }))),
      }),
    };
  }

  function render(step, result) {
    const rows = step >= 2 ? result.bags : [];
    return `<div class="rr-screen">
      <section>
        <div class="rr-stripe"></div>
        <div class="rr-ledger"><div><small>REVERSE LOGISTICS</small><h2>${step === 3 ? 'Print queue' : 'Manifest builder'}</h2></div>
          <strong>${step >= 2 ? result.accepted + ' ready' : parcels.length + ' queued'}</strong></div>
        <div class="rr-bags">
          ${step >= 2
            ? rows.map((bag, index) => `<article>
                <div class="rr-bag-id">BAG 0${index + 1}<span>${kilograms(bag.grams)} / 8 kg</span></div>
                <h3>${bag.site}</h3><div class="rr-meter"><i style="width:${bag.grams / bagLimit * 100}%"></i></div>
                <ul>${bag.items.map(row => `<li><b>${row.id}</b><span>${row.zip}</span></li>`).join('')}</ul>
                <small>${step === 3 ? bag.items.length + ' labels' : 'Routing draft'}</small>
              </article>`).join('')
            : ['Reno', 'Albany'].map(site => `<article><div class="rr-bag-id">HUB INTAKE</div><h3>${site}</h3>
                <ul>${parcels.filter(row => row.site === site).map(row => `<li><b>${row.id}</b><span>${row.zip}</span></li>`).join('')}</ul>
                <small>Awaiting validation</small></article>`).join('')}
        </div>
      </section>
      <aside><small>RELEASE CONTROL</small><div class="rr-glyph" aria-hidden="true">↪</div>
        <h3>${step === 3 ? result.printCount + ' printable labels' : step === 2 ? 'Postal exception' : 'Hub routing'}</h3>
        <p>${step === 3 ? 'Corrected RMA-5210 to 12207. Every label now has a destination and a compliant bag.'
          : step === 2 ? 'RMA-5210 contains the letter O. Hold the print queue and keep the five eligible returns planned.'
          : 'Validate postal codes and keep each carrier bag at or below 8 kg.'}</p>
        ${step >= 2 ? '<span class="rr-chip">' + result.bagCount + ' bags planned</span>' : ''}
      </aside>
    </div>`;
  }

  window.caseDefinition = {
    id: '10', title: 'Return Relay', kicker: 'WAREHOUSE / CARRIER HANDOFF',
    scenario: 'Reject an invalid postal code and group valid return labels into weight-compliant bags.',
    layout: 'board', accent: '#326213', surface: '#eaf2de', text: '#162b12',
    actions: ['Read return manifest', 'Validate and pack', 'Apply confirmed ZIP and print'],
    expected: [
      { requestCount: 6, hubCount: 2, totalGrams: 15200 },
      { rejected: ['RMA-5210'], bagCount: 3, bagGrams: [7700, 2200, 2700], accepted: 5, printCount: 0 },
      { rejected: [], bagCount: 3, bagGrams: [7700, 2200, 5300], accepted: 6, printCount: 6 },
    ],
    run, render,
    style: `
      .rr-screen{display:grid;grid-template-columns:minmax(0,3fr) minmax(220px,1fr);gap:18px;font:14px/1.45 "Segoe UI",sans-serif;color:#192b14}
      .rr-screen section{border:1px solid #d3e1c4;background:#fafdf5;overflow:hidden}
      .rr-stripe{height:8px;background:repeating-linear-gradient(110deg,#add347,#add347 14px,#294f16 14px,#294f16 28px)}
      .rr-ledger{display:flex;align-items:center;justify-content:space-between;padding:19px 21px 12px}
      .rr-ledger h2{margin:4px 0 0;font-size:30px;line-height:1.15}
      .rr-ledger strong{padding:6px 11px;background:#d6e9bb;color:#274719}
      .rr-screen small{font:700 10px/1.3 Consolas,monospace;letter-spacing:.1em}
      .rr-bags{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;padding:8px 21px 20px}
      .rr-bags article{background:#fff;padding:13px;border:1px dashed #9bb585;min-width:0}
      .rr-bag-id{display:flex;justify-content:space-between;color:#426333;font:700 10px/1.2 Consolas,monospace}
      .rr-bag-id span{white-space:nowrap;margin-left:3px}
      .rr-bags h3{font-size:23px;margin:9px 0 6px}
      .rr-bags ul{list-style:none;margin:7px 0 12px;padding:0}
      .rr-bags li{display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #e4eadc;font-size:12px}
      .rr-bags li span{color:#426333}
      .rr-meter{height:5px;background:#e4ecd8;margin-bottom:12px}
      .rr-meter i{display:block;height:100%;background:#75a837}
      .rr-screen aside{background:#23391c;color:#f3fbdc;padding:23px;border-radius:0 30px 0 0}
      .rr-screen aside h3{font-size:27px;line-height:1.02;margin:12px 0 9px}
      .rr-screen aside p{color:#dcebbd;margin:0 0 16px}
      .rr-glyph{font-size:54px;line-height:1.05;color:#b5d65e}
      .rr-chip{display:inline-block;border:1px solid #add47b;padding:5px 9px;font:13px Consolas,monospace}
    `,
  };
})();
