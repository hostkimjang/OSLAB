(() => {
  const columns = 7;
  const rows = 6;
  const blocked = new Set(['2,0', '2,2', '2,3', '2,4', '2,5', '5,0', '5,1', '5,4', '5,5']);
  const dock = [[0, 3], [6, 3]];
  const stops = [[3, 1], [3, 4]];
  const original = [[0, 3], [1, 3], [2, 3], [3, 3], [3, 2], [3, 1], [3, 2], [3, 3], [3, 4], [4, 4], [5, 4], [6, 4], [6, 3]];
  const key = (point) => point.join(',');
  const same = (left, right) => key(left) === key(right);

  function shortestPath(from, to) {
    const queue = [[from]];
    const visited = new Set([key(from)]);
    for (let index = 0; index < queue.length; index++) {
      const route = queue[index];
      const current = route.at(-1);
      const [x, y] = current;
      if (same(current, to)) return route;
      for (const next of [[x + 1, y], [x, y - 1], [x - 1, y], [x, y + 1]]) {
        const [nx, ny] = next;
        const cell = key(next);
        if (nx >= 0 && nx < columns && ny >= 0 && ny < rows && !blocked.has(cell) && !visited.has(cell)) {
          visited.add(cell);
          queue.push([...route, next]);
        }
      }
    }
    throw new Error(`No walkable route between ${key(from)} and ${key(to)}`);
  }

  function summarize(route) {
    const visited = new Set(route.map(key));
    return {
      route,
      cellsWalked: route.length - 1,
      picksVisited: stops.filter((stop) => visited.has(key(stop))).length,
      blockedCells: [...visited].filter((cell) => blocked.has(cell)).length,
      hasCompleteRoute: same(route[0], dock[0]) && same(route.at(-1), dock[1])
        && route.slice(1).every(([x, y], i) => Math.abs(route[i][0] - x) + Math.abs(route[i][1] - y) === 1),
    };
  }

  function plan() {
    const waypoints = [dock[0], ...stops, dock[1]];
    return summarize(waypoints.slice(1).reduce((route, next, index) =>
      route.concat(shortestPath(waypoints[index], next).slice(1)), [waypoints[0]]));
  }

  function floorplan(step, result) {
    const route = result?.route ?? original;
    const activeColor = step === 2 ? '#c84c38' : '#167b53';
    const cellSize = 60;
    const left = 32;
    const top = 10;
    const center = ([x, y]) => [left + x * cellSize + cellSize / 2, top + y * cellSize + cellSize / 2];
    const grids = Array.from({ length: rows * columns }, (_, i) => {
      const point = [i % columns, Math.floor(i / columns)];
      const [x, y] = center(point);
      const isBlocked = blocked.has(key(point));
      return `<rect x="${x - 26}" y="${y - 26}" width="52" height="52" rx="6" fill="${isBlocked ? 'url(#pick-wall)' : '#efece2'}" stroke="#c8cbbd"/>`;
    }).join('');
    const routeLine = route.map(center).map(key).join(' ');
    const issues = step === 2 ? route.filter((point) => blocked.has(key(point))).map((point) => {
      const [x, y] = center(point);
      return `<path d="M${x - 12},${y - 12}l24,24m0,-24l-24,24" stroke="#6e2510" stroke-width="5" stroke-linecap="round"/>`;
    }).join('') : '';
    const points = [[dock[0], 'IN'], [stops[0], 'A'], [stops[1], 'B'], [dock[1], 'OUT']].map(([point, text]) => {
      const [x, y] = center(point);
      return `<circle cx="${x}" cy="${y}" r="16" fill="#23443a" stroke="#fffef7" stroke-width="2"/>
        <text text-anchor="middle" x="${x}" y="${y + 4}" fill="#fffef7" font-weight="700" font-size="10">${text}</text>`;
    }).join('');
    return `<svg viewBox="0 0 484 378" role="img" aria-label="Aisle map with ${route.length} route points">
      <defs><pattern id="pick-wall" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="7" height="7" fill="#bdcabb"/><path d="M0 0v7" stroke="#96a79a" stroke-width="3"/></pattern></defs>
      ${grids}<polyline points="${routeLine}" fill="none" stroke="${activeColor}" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"
      ${step === 0 ? 'opacity=".5" stroke-dasharray="5 7"' : ''}/>${issues}${points}
    </svg>`;
  }

  function render(step, result) {
    const headline = step === 2 ? 'Release blocked' : step === 3 ? 'Safe route verified' : 'Wave 027';
    const note = step === 2
      ? `Original path crosses ${result.blockedCells} blocked rack cells. Withdraw the unsafe route before releasing the wave.`
      : step === 3
        ? `Route uses ${result.cellsWalked} aisle moves with no blocked cells and visits both pick bins.`
        : 'Enter at west intake, collect two items in sequence, then exit at east dispatch.';
    return `<div class="pick-layout">
      ${floorplan(step, result)}
      <aside>
        <span class="pick-overline">AISLE RELEASE</span><h2>${headline}</h2><p>${note}</p>
        <div class="pick-stop"><b>A</b><span><strong>Pick connector kits</strong><small>Bin F3 · 12 units</small></span></div>
        <div class="pick-stop"><b>B</b><span><strong>Pick mount plates</strong><small>Bin H3 · 4 units</small></span></div>
        <div class="pick-key"><i></i>Blocked rack</div>
      </aside>
    </div>`;
  }

  window.caseDefinition = {
    id: '15',
    title: 'Pick Path',
    kicker: 'WAREHOUSE ROUTES',
    scenario: 'Reject a pick route that crosses two racks and reroute through open aisles.',
    layout: 'canvas',
    accent: '#16724d',
    surface: '#f1f1df',
    text: '#213d32',
    actions: ['Load pick wave', 'Audit rack clearance', 'Calculate safe route'],
    expected: [
      { gridCells: 42, closed: 9, stops: 2 },
      { cellsWalked: 12, blockedCells: 2, picksVisited: 2, hasCompleteRoute: true },
      { cellsWalked: 12, blockedCells: 0, picksVisited: 2, hasCompleteRoute: true },
    ],
    run(step) {
      if (step === 1) return { gridCells: rows * columns, closed: blocked.size, stops: stops.length };
      return step === 2 ? summarize(original) : plan();
    },
    render,
    style: `
      .pick-layout{display:grid;grid-template-columns:minmax(480px,1.2fr) minmax(300px,1fr);gap:30px;align-items:center}
      .pick-layout svg{width:100%;height:380px;background:#e3e6d5;border:1px solid #abbaa9;border-radius:12px}
      .pick-layout aside{background:#fcfbef;border:1px solid #cdccb5;padding:24px;border-radius:12px}
      .pick-layout h2{margin:4px 0 8px;font-size:33px}.pick-layout p{margin:0 0 19px;line-height:1.5;color:#405b51}
      .pick-overline{font-size:12px;color:#4f6b58;font-weight:bold;letter-spacing:.14em}
      .pick-stop{background:#ecefe1;padding:10px;margin:8px 0;border-radius:8px;display:flex;gap:12px;align-items:center}
      .pick-stop b{display:grid;place-content:center;width:28px;height:28px;background:#214739;color:#fff;border-radius:50%}
      .pick-stop strong,.pick-stop small{display:block}.pick-stop small{color:#536159}.pick-key{color:#536159;display:flex;align-items:center;gap:8px;margin-top:18px}
      .pick-key i{width:14px;height:14px;border-radius:3px;background:repeating-linear-gradient(45deg,#c1cabc 0px,#c1cabc 2px,#9da99a 2px,#9da99a 4px)}
    `,
  };
})();
