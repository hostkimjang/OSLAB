(() => {
  const stops = {
    H: { name: 'Assembly point', x: 67, y: 184 },
    A: { name: 'Lumen Observatory', x: 244, y: 63, open: 15, close: 55, duration: 20 },
    B: { name: 'Kiln Studio', x: 136, y: 117, open: 0, close: 33, duration: 18 },
    C: { name: 'Reed Conservatory', x: 402, y: 188, open: 35, close: 110, duration: 25 },
    D: { name: 'Harbor Market', x: 290, y: 272, open: 48, close: 140, duration: 12 },
  };
  const minutes = {
    HA: 11, HB: 9, HC: 17, HD: 16, AB: 7, AC: 13, AD: 19, BC: 10, BD: 12, CD: 8,
  };
  const requested = ['C', 'D', 'B', 'A'];

  function travel(a, b) {
    return minutes[a + b] ?? minutes[b + a];
  }

  function evaluate(route) {
    let previous = 'H';
    let minute = 0;
    let driving = 0;
    let waiting = 0;
    const visits = [];
    for (const id of route) {
      const stop = stops[id];
      const leg = travel(previous, id);
      driving += leg;
      minute += leg;
      const start = Math.max(stop.open, minute);
      waiting += start - minute;
      visits.push({ id, arrival: minute, start, lateBy: Math.max(0, start - stop.close) });
      minute = start + stop.duration;
      previous = id;
    }
    const home = travel(previous, 'H');
    return {
      route, visits, drivingMinutes: driving + home, waitingMinutes: waiting, roundTripMinutes: minute + home,
      missedReservations: visits.filter(visit => visit.lateBy > 0).map(visit => visit.id),
    };
  }

  function* permutations(source, route = []) {
    if (!source.length) {
      yield route;
    }
    for (const id of source) {
      yield* permutations(source.filter(key => key !== id), [...route, id]);
    }
  }

  function optimum() {
    let best;
    let assessed = 0;
    for (const route of permutations(requested)) {
      const candidate = evaluate(route);
      assessed += 1;
      if (candidate.missedReservations.length) continue;
      if (!best || candidate.roundTripMinutes < best.roundTripMinutes) best = candidate;
    }
    if (!best) throw new Error('No route meets all reservation windows.');
    return { ...best, assessed };
  }

  function clock(offset) {
    return String(9 + Math.floor(offset / 60)).padStart(2, '0') + ':' + String(offset % 60).padStart(2, '0');
  }

  function map(route, missed) {
    const paths = [
      'M0 71 C125 88 58 151 195 152 S275 198 342 168 S429 72 502 84',
      'M24 10 C11 104 212 65 220 160 S109 263 122 316',
      'M350 2 C308 89 412 99 419 147 S411 219 463 317',
      'M85 0 C90 79 195 56 313 111 S410 256 501 236',
      'M0 283 C109 208 227 255 266 230 S331 119 500 131',
    ];
    const base = paths.map(path => '<path d="' + path + '" fill="none" stroke="#efdfba" stroke-width="2"/>').join('');
    const routeStroke = '<polyline points="' + (route.length ? ['H', ...route, 'H'] : []).map(id =>
      stops[id].x + ',' + stops[id].y).join(' ') + '" fill="none" stroke="' +
      (missed.length ? '#b34f69' : '#236596') + '" stroke-width="4" stroke-linejoin="round" stroke-linecap="round"/>';
    const nodes = Object.entries(stops).map(([id, stop]) => {
      const position = route.indexOf(id);
      const tint = missed.includes(id) ? '#ac3c5b' : id === 'H' ? '#152c4e' : '#266c99';
      return '<circle cx="' + stop.x + '" cy="' + stop.y + '" r="15" fill="' + tint +
        '" stroke="#fcf6eb" stroke-width="3"/><text x="' + stop.x + '" y="' + (stop.y + 4.5) +
        '" text-anchor="middle" fill="#fff" font-size="12" font-weight="700">' + (position >= 0 ? position + 1 : id) +
        '</text><text x="' + (stop.x + (id === 'C' ? -17 : 17)) + '" y="' + (stop.y - 14) +
        '" text-anchor="' + (id === 'C' ? 'end' : 'start') + '" fill="#293f55" font-weight="650" font-size="11">' +
        stop.name + '</text>';
    }).join('');
    return '<svg viewBox="0 0 502 318" aria-label="Tour route network" role="img">' +
      '<rect width="502" height="318" rx="11" fill="#fcf6eb"/>' +
      '<path d="M461 0 C420 49 457 75 468 104 S463 162 471 200 S490 238 466 318 H502 V0Z" fill="#cce2e8"/>' +
      '<path d="M6 5 L48 18 133 15 137 53 61 68 7 52Z M345 227 L398 239 429 319 352 318 314 276Z" fill="#dce8d1"/>' +
      base + routeStroke + nodes + '</svg>';
  }

  function render(step, result) {
    const route = step === 0 ? [] : step === 1 ? requested : result.route;
    const missed = step < 2 ? [] : result.missedReservations;
    const visits = step < 2 ? [] : result.visits;
    const status = step === 0 ? 'Import the morning tour and the four scheduled entries.'
      : step === 1 ? 'Timed entries loaded. Check the requested route against booking windows.'
        : step === 2 ? 'Two reservations would be missed. Kiln Studio arrives 59 minutes after its last allowed entry.'
          : 'All 24 orders evaluated. The quickest feasible route returns at ' + clock(result.roundTripMinutes) + '.';
    const rows = (route.length ? route : Object.keys(stops).filter(id => id !== 'H')).map(id => {
      const stop = stops[id];
      const visit = visits.find(event => event.id === id);
      return '<tr><td><b>' + stop.name + '</b></td><td>' + clock(stop.open) + '–' + clock(stop.close) +
        '</td><td class="' + (missed.includes(id) ? 'route-late' : '') + '">' +
        (visit ? clock(visit.start) + (visit.lateBy ? ' +' + visit.lateBy + 'm' : '') : '—') + '</td></tr>';
    }).join('');
    return '<style> .tour{height:100%;display:grid;grid-template-columns:1.17fr .83fr;gap:18px;padding:6px;font-family:"Segoe UI",sans-serif;color:#284059} .tour section{border:1px solid #c4d5e3;border-radius:13px;padding:13px;background:#fffefa;align-self:start} .tour section>svg{width:100%;height:325px;display:block} .tour h2{margin:0 8px 4px;font-size:20px;letter-spacing:-.04em} .tour small{display:block;margin:0 8px 13px;color:#657587;font-size:12px} .tour table{width:100%;border-collapse:collapse;font-size:13px} .tour th{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:#627184} .tour td,.tour th{border-top:1px solid #e3e9ef;text-align:left;padding:10px 7px;white-space:nowrap} .route-late{color:#ab3454;font-weight:700} .tour .tour-status{margin:10px 5px 3px;padding:10px 12px;border-radius:6px;background:#e8f2fa;line-height:1.38;font-size:14px} .tour-status.is-late{background:#f9e3eb;color:#8c284b} .tour-status.is-ready{background:#def0e5;color:#246146} </style><div class="tour"><section><h2>Morning circuit</h2><small>09:00 departure / four reservations</small>' +
      map(route, missed) + '</section><section><h2>Timed entry schedule</h2><small>Local time / last permitted arrival</small>' +
      '<table><thead><tr><th>Stop</th><th>Entry window</th><th>Check-in</th></tr></thead><tbody>' + rows +
      '</tbody></table><p class="tour-status ' + (step === 2 ? 'is-late' : step === 3 ? 'is-ready' : '') + '">' +
      status + '</p></section></div>';
  }

  window.caseDefinition = {
    id: '04', title: 'Streetlight Itinerary', kicker: 'Travel operations',
    scenario: 'Catch missed reservation windows and find the fastest route that honors every booking.',
    layout: 'canvas', accent: '#246b98', surface: '#e5eef4', text: '#20425b',
    actions: ['Import timed bookings', 'Check requested route', 'Find an on-time route'],
    expected: [
      { reservations: 4, requested: ['C', 'D', 'B', 'A'] },
      { missedReservations: ['B', 'A'], drivingMinutes: 55, waitingMinutes: 18, roundTripMinutes: 148 },
      { route: ['B', 'A', 'C', 'D'], missedReservations: [], assessed: 24, drivingMinutes: 53, roundTripMinutes: 128 },
    ],
    run(step) {
      if (step === 1) return { reservations: Object.values(stops).filter(stop => 'open' in stop).length, requested };
      return step === 2 ? evaluate(requested) : optimum();
    },
    render,
  };
})();
