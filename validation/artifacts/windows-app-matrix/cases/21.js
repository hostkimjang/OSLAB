(() => {
  const intervalMinutes = 15;
  const intervals = 8;
  const onPeakFrom = 60;
  const rates = {offpeak: 15, peak: 29};
  const source = [
    [0, 34120], [15, 34132], [30, 34149], [45, 34159], [45, 34159],
    [75, 34192], [90, 34204], [105, 34220], [120, 34231],
  ];
  const replacement = [60, 34175];
  const clock = minute =>
    [6 + Math.floor(minute / 60), minute % 60].map(part => String(part).padStart(2, "0")).join(":");
  const usd = cents => "$" + (cents / 100).toFixed(2);

  function reconcile(readings) {
    const counters = new Map();
    const duplicates = [];
    for (const [minute, counter] of readings) {
      if (counters.has(minute)) {
        duplicates.push(clock(minute));
        continue;
      }
      counters.set(minute, counter);
    }
    const missing = [];
    const buckets = [];
    for (let i = 0; i <= intervals; i++) {
      const start = i * intervalMinutes;
      if (!counters.has(start)) missing.push(clock(start));
      if (i === intervals) continue;
      const startCounter = counters.get(start);
      const endCounter = counters.get(start + intervalMinutes);
      const usable = startCounter !== undefined && endCounter !== undefined && endCounter >= startCounter;
      buckets.push({
        start: clock(start),
        tariff: start >= onPeakFrom ? "peak" : "offpeak",
        kWh: usable ? endCounter - startCounter : null,
      });
    }
    const sum = tariff => buckets.filter(row => row.tariff === tariff).reduce((total, row) => total + (row.kWh ?? 0), 0);
    const offpeak = sum("offpeak");
    const peak = sum("peak");
    const billable = missing.length === 0 && duplicates.length === 0 && buckets.every(row => row.kWh !== null);
    return {duplicates, missing, buckets, offpeak, peak, kWh: offpeak + peak,
      billCents: offpeak * rates.offpeak + peak * rates.peak, billable};
  }

  function render(step, result) {
    const report = step >= 2 ? result : null;
    const graphRows = report?.buckets ?? Array.from({length: intervals}, (_, index) => ({
      start: clock(index * intervalMinutes), tariff: index < 4 ? "offpeak" : "peak", kWh: 0,
    }));
    return `
      <div class="meter-layout">
        <div class="meter-chart">
          <div class="meter-kicker">NORTH PIER · EL-042</div><h2>Interval load profile</h2>
          <div class="meter-legend"><i></i> Off-peak · 15¢/kWh <i></i> Peak · 29¢/kWh</div>
          <div class="meter-bars">${graphRows.map(row => `<div><b class="${row.kWh === null ? "gap" : row.tariff}"
            style="--bar:${report ? Math.max(5, (row.kWh ?? 2) * 12) : 8}px">${report ? (row.kWh ?? "GAP") : ""}</b>
            <span>${row.start}</span></div>`).join("")}</div>
          <div class="meter-note">${step === 3 ? "Certified replacement reading integrated" :
            step === 2 ? "Two intervals depend on the missing 07:00 reading" :
              "Two-hour settlement window · 15-minute readings"}</div>
        </div>
        <aside class="meter-total">
          <div class="meter-kicker">SETTLEMENT</div>
          <strong>${report ? usd(report.billCents) : "—"}</strong>
          <p>${report ? `${report.kWh} kWh reconciled` : (step ? `${result.readings} counters imported` : "Awaiting meter file")}</p>
          <hr><dl><dt>Off-peak</dt><dd>${report ? `${report.offpeak} kWh` : "—"}</dd>
            <dt>Peak</dt><dd>${report ? `${report.peak} kWh` : "—"}</dd></dl>
          <div class="meter-state ${step === 2 ? "blocked" : ""}">${step === 3 ? "READY TO BILL" :
            step === 2 ? "HOLD · 06:45 duplicate / 07:00 missing" : "METER PERIOD 06:00–08:00"}</div>
        </aside>
      </div>`;
  }

  window.caseDefinition = {
    id: "21",
    title: "Meter Ledger",
    kicker: "ENERGY SETTLEMENT",
    scenario: "Reconcile a duplicate and a missing meter reading before issuing a time-of-use bill.",
    layout: "chart",
    accent: "#a8f353",
    surface: "#141a18",
    text: "#f2f6ee",
    actions: ["Import interval readings", "Audit tariff settlement", "Apply certified reading"],
    expected: [
      {readings: 9, distinctReadings: 8, windowMinutes: 120, tariffCutover: "07:00"},
      {duplicates: ["06:45"], missing: ["07:00"], offpeak: 39, peak: 39, kWh: 78, billCents: 1716, billable: false},
      {duplicates: [], missing: [], offpeak: 55, peak: 56, kWh: 111, billCents: 2449, billable: true},
    ],
    run(step) {
      if (step === 1) {
        return {readings: source.length, distinctReadings: new Set(source.map(([minute]) => minute)).size,
          windowMinutes: intervals * intervalMinutes, tariffCutover: clock(onPeakFrom)};
      }
      if (step === 2) return reconcile(source);
      const distinct = new Map(source);
      distinct.set(...replacement);
      return reconcile([...distinct]);
    },
    render,
    style: `
      .meter-layout{display:grid;grid-template-columns:2.45fr 1fr;gap:20px;padding:10px 0;color:#f2f6ee}
      .meter-chart,.meter-total{border:1px solid #3c4840;border-radius:12px;background:#1d2822;padding:22px;min-width:0}
      .meter-kicker{font:700 12px ui-monospace,monospace;color:#b4caad;letter-spacing:.12em}
      .meter-chart h2{margin:6px 0 8px;font-size:30px}.meter-legend{display:flex;gap:8px;align-items:center;font-size:13px;color:#b4caad}
      .meter-legend i{width:10px;height:10px;background:#95de48;border-radius:2px}.meter-legend i+i{background:#63c7b1;margin-left:12px}
      .meter-bars{display:grid;grid-template-columns:repeat(8,1fr);gap:12px;height:255px;border-bottom:1px solid #546452;margin:6px 0 13px;align-items:end;background:repeating-linear-gradient(180deg,transparent 0 49px,#314036 49px 50px)}
      .meter-bars>div{display:grid;justify-items:center;align-content:end;gap:5px;padding-bottom:7px;font:12px ui-monospace,monospace;color:#c9d3c4}
      .meter-bars b{display:grid;place-items:start center;padding-top:7px;box-sizing:border-box;height:var(--bar);width:68%;border-radius:6px 6px 2px 2px;font-size:13px;color:#192412}
      .meter-bars b.offpeak{background:#a8ed65}.meter-bars b.peak,.meter-legend i:nth-of-type(2){background:#68d0bb}
      .meter-bars b.gap{background:#b76d52;color:#fdf1e6}.meter-note{font-size:14px;color:#bdceba}
      .meter-total{background:#283624}.meter-total strong{display:block;color:#c9ff82;font-size:clamp(42px,5vw,78px);letter-spacing:-.07em;margin-top:32px}
      .meter-total p{color:#bdceba;margin:6px 0 24px}.meter-total hr{border:0;border-top:1px solid #4b5b43}
      .meter-total dl{display:grid;grid-template-columns:1fr 1fr;gap:12px;font-size:15px}.meter-total dd{margin:0;text-align:right}
      .meter-state{margin-top:28px;padding:8px 12px;border-radius:5px;background:#3e5340;color:#d8f6a9;font:700 12px ui-monospace,monospace}
      .meter-state.blocked{background:#57382b;color:#ffcbad}`,
  };
})();
