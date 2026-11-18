(() => {
  const blocks = [
    { name: "Clinic", point: [2,2], riders: 30 },
    { name: "River Flats", point: [5,5], riders: 42 },
    { name: "Mill Quarter", point: [8,9], riders: 53 },
    { name: "Orchard", point: [2,4], riders: 35 },
    { name: "Station", point: [10,3], riders: 45 }
  ];
  const originalStops = [
    { name: "West Loop", point: [2,3] },
    { name: "Station Park", point: [10,4] }
  ];
  const candidates = [
    { name: "Riverside", point: [5,6], minutes: 4 },
    { name: "Library Annex", point: [5,4], minutes: 7 },
    { name: "Mill Gate", point: [8,8], minutes: 5 },
    { name: "Yard Crossing", point: [7,6], minutes: 3 }
  ];
  const walkingLimit = 2;
  const detourBudget = 9;

  function assess(additions) {
    const stops = [...originalStops, ...additions];
    const mapped = blocks.map(block => {
      const distance = Math.min(...stops.map(stop =>
        Math.abs(stop.point[0] - block.point[0]) + Math.abs(stop.point[1] - block.point[1])));
      return { ...block, distance, covered: distance <= walkingLimit };
    });
    return {
      hours: "Weekday peak", ridersCovered: mapped.filter(block => block.covered).reduce((total, block) => total + block.riders, 0),
      missedBlocks: mapped.filter(block => !block.covered).length, totalRiders: mapped.reduce((total, block) => total + block.riders, 0),
      detourMinutes: additions.reduce((total, stop) => total + stop.minutes, 0),
      newStops: additions.map(stop => stop.name), stops, mapped
    };
  }

  function chooseStops() {
    const options = Array.from({ length: 2 ** candidates.length }, (_, mask) =>
      assess(candidates.filter((_, index) => mask & (1 << index))));
    return options.filter(option => option.detourMinutes <= detourBudget)
      .sort((first, second) => second.ridersCovered - first.ridersCovered || first.detourMinutes - second.detourMinutes)[0];
  }

  function xy([x, y]) {
    return [32 + x * 58, 20 + y * 36];
  }

  function render(step, result) {
    const state = result ?? assess([]);
    const line = [...state.stops].sort((a, b) => a.point[0] - b.point[0]).map(stop => xy(stop.point).join(",")).join(" ");
    const stops = state.stops.map((stop, i) => {
      const [x, y] = xy(stop.point);
      return `<rect x="${x - 7}" y="${y - 7}" width="14" height="14" rx="4" fill="${i < 2 ? "#0c766e" : "#153dcb"}" stroke="#fff" stroke-width="2"/>`;
    }).join("");
    const sites = state.mapped.map(site => {
      const [x, y] = xy(site.point);
      const uncovered = step >= 2 && !site.covered;
      return `<circle cx="${x}" cy="${y}" r="${uncovered ? 11 : 8}" fill="${uncovered ? "#ba371e" : "#f6fffc"}" stroke="${uncovered ? "#fff" : "#0d6158"}" stroke-width="2.5"/>
        <text x="${site.point[0] >= 8 ? x - 15 : x + 15}" y="${y + 4}" text-anchor="${site.point[0] >= 8 ? "end" : "start"}" fill="#17483c" font-size="15" font-weight="700">${site.name}</text>`;
    }).join("");
    return `<div class="civic-workspace"><div class="civic-map">
      <h2>Neighborhood coverage</h2><svg viewBox="0 0 676 380" role="img" aria-label="Transit stop plan and five simulated ridership blocks">
        <defs><pattern id="civic-blocks" width="58" height="36" patternUnits="userSpaceOnUse"><rect width="54" height="32" rx="4" fill="#deeee3"/></pattern></defs>
        <rect width="676" height="380" fill="url(#civic-blocks)"/>
        <path d="M 436 -10 C 386 65 480 102 431 169 C 377 247 398 278 344 390" fill="none" stroke="#b5e4ed" stroke-width="28"/>
        <polyline points="${line}" stroke="#167e72" stroke-linecap="round" stroke-linejoin="round" stroke-width="5" fill="none"/>
        ${stops}${sites}
      </svg></div><aside class="civic-brief"><div class="civic-tag">SERVICE AREA</div>
        <strong>${step < 2 ? "—" : state.ridersCovered}<span> / ${state.totalRiders}</span></strong><p>riders inside a two-block walk</p>
        <div class="civic-fact"><span>Unserved blocks</span><b>${step < 2 ? "—" : state.missedBlocks}</b></div>
        <div class="civic-fact"><span>Extra route time</span><b>${state.detourMinutes} / ${detourBudget} min</b></div>
        <p class="civic-note">${step === 3 ? `Added ${state.newStops.join(" and ")} within the detour budget.` :
          step === 2 ? "River Flats and Mill Quarter are outside the walking catchment." :
          "Load the baseline route and compare four potential stops."}</p>
      </aside></div>`;
  }

  window.caseDefinition = {
    id: "26", title: "Civic Transit", kicker: "SERVICE PLANNING",
    scenario: "Find stops that bring every rider within a two-block walk and add at most nine minutes to the route.",
    layout: "canvas", accent: "#12785c", surface: "#edf7ef", text: "#193e34",
    actions: ["Load route", "Calculate walking coverage", "Select best stop pair"],
    expected: [
      { missedBlocks: 2, detourMinutes: 0, totalRiders: 205 },
      { ridersCovered: 110, missedBlocks: 2, goalMet: false },
      { ridersCovered: 205, missedBlocks: 0, detourMinutes: 9, newStops: ["Riverside", "Mill Gate"], goalMet: true }
    ],
    run(step) {
      const state = step === 3 ? chooseStops() : assess([]);
      return { ...state, goalMet: state.missedBlocks === 0 };
    },
    render,
    style: `
      .civic-workspace{display:grid;grid-template-columns:minmax(0,2.15fr) minmax(0,1fr);gap:28px;height:460px}
      .civic-map,.civic-brief{border-radius:20px;padding:23px;background:#fafff9;border:1px solid #c9e2d6;color:#193e34}
      .civic-map h2{font-size:26px;margin:0 0 15px}.civic-map svg{display:block;width:100%;height:374px;background:#f2f9f2;border-radius:14px}
      .civic-brief{flex-direction:column;display:flex;justify-content:center}.civic-tag{color:#107361;letter-spacing:.2em;font-weight:800;font-size:12px}
      .civic-brief strong{font-size:67px;line-height:1.05;margin-top:17px}.civic-brief strong span{font-size:28px;color:#427468}
      .civic-brief p{margin:12px 0 24px;color:#395e54}.civic-fact{display:flex;gap:12px;justify-content:space-between;padding:15px 0;border-bottom:1px solid #d0e4dc}
      .civic-brief p.civic-note{background:#ddefe8;border-radius:12px;padding:13px 15px;margin:23px 0 0;color:#154d42}`
  };
})();
