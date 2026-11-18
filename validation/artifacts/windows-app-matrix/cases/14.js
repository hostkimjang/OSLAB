(() => {
  const minute = (hours, minutes) => hours * 60 + minutes;
  const services = [
    { id: 'RC114', town: 'Riverside', start: minute(7, 48), end: minute(7, 56), track: 'C' },
    { id: 'MK452', town: 'Market', start: minute(7, 52), end: minute(8, 4), track: 'A' },
    { id: 'LM291', town: 'Lakeside', start: minute(8, 0), end: minute(8, 10), track: 'B' },
    { id: 'MK708', town: 'Foundry', start: minute(8, 6), end: minute(8, 15), track: 'A' },
    { id: 'LM557', town: 'Lake Jct', start: minute(8, 11), end: minute(8, 23), track: 'B' },
  ];
  const tracks = ['A', 'B', 'C'];
  const clearance = 4;
  const earliest = minute(7, 46);
  const duration = 42;

  function findConflicts(schedule) {
    return schedule.flatMap((current, index) => schedule.slice(0, index).flatMap((older) => {
      const gap = current.start - older.end;
      return current.track === older.track && gap < clearance
        ? [{ first: older.id, second: current.id, track: current.track, gap }]
        : [];
    }));
  }

  function reassign() {
    const revised = [];
    for (const service of services) {
      const preferredTracks = [service.track, ...tracks.filter((track) => track !== service.track)];
      const track = preferredTracks.find((candidate) => revised.every((other) =>
        other.track !== candidate || service.start - other.end >= clearance));
      revised.push({ ...service, track: track ?? 'Unassigned' });
    }
    return revised;
  }

  function label(time) {
    return `${String(Math.floor(time / 60)).padStart(2, '0')}:${String(time % 60).padStart(2, '0')}`;
  }

  function render(step, result) {
    const schedule = result?.schedule ?? services;
    const conflicts = new Set((result?.issues ?? []).map((issue) => issue.second));
    const revised = step === 3;
    const timeline = tracks.map((track) => {
      const stops = schedule.filter((service) => service.track === track).map((service) => {
        const start = (service.start - earliest) * 100 / duration;
        const length = (service.end - service.start) * 100 / duration;
        const moved = revised && services.find(({ id }) => id === service.id).track !== track;
        return `<div class="rail-service ${conflicts.has(service.id) ? 'conflict' : moved ? 'moved' : ''}"
          style="left:${start}%;width:${length}%"><b>${service.id}</b><span>${service.town}</span></div>`;
      }).join('');
      return `<div class="rail-lane"><label>Platform ${track}</label><div class="rail-track">${stops}</div></div>`;
    }).join('');
    const notices = step === 2
      ? result.issues.map(({ first, second, gap, track }) => `<div><b>${first} → ${second}</b> · Platform ${track} · ${gap} min of ${clearance} min required</div>`)
      : revised
        ? ['MK708 moved to C. LM557 moved to A.', 'All arrivals and departures retained. No clearance conflicts.']
        : ['Morning arrivals and departures', 'Minimum turn-around clearance on the same platform is 4 minutes.'];
    return `<section class="rail-schedule">
      <div class="rail-heading"><div><small>UNION CENTRAL</small><h2>Morning service pattern</h2></div><span>${label(earliest)}–${label(earliest + duration)}</span></div>
      <div class="rail-clock">${[7, 14, 21, 28, 35].map((offset) =>
        `<span style="left:${offset * 100 / duration}%">${label(earliest + offset)}</span>`).join('')}</div>
      ${timeline}
      <div class="rail-notice ${step === 2 ? 'warning' : ''}">${notices.map((notice) => `<p>${notice}</p>`).join('')}</div>
    </section>`;
  }

  window.caseDefinition = {
    id: '14',
    title: 'Platform Desk',
    kicker: 'RAIL OPERATIONS',
    scenario: 'Audit occupied platform intervals and reassign two services without moving their times.',
    layout: 'chart',
    accent: '#7ee2ff',
    surface: '#080c27',
    text: '#eef1ff',
    actions: ['Load morning timetable', 'Run clearance audit', 'Reassign and verify timetable'],
    expected: [
      { scheduled: 5, platforms: 3, minimumClearance: 4 },
      { conflicts: 2, affected: 'MK708,LM557', shortestGap: 1 },
      { conflicts: 0, reassigned: 2, unchangedTimes: 5, minimumActualGap: 7 },
    ],
    run(step) {
      if (step === 1) return { scheduled: services.length, platforms: new Set(services.map((service) => service.track)).size, minimumClearance: clearance };
      if (step === 2) {
        const issues = findConflicts(services);
        return {
          issues,
          conflicts: issues.length,
          affected: issues.map((issue) => issue.second).join(','),
          shortestGap: Math.min(...issues.map((issue) => issue.gap)),
        };
      }
      const schedule = reassign();
      const gaps = schedule.flatMap((service, i) => schedule.slice(0, i)
        .filter((other) => service.track === other.track).map((other) => service.start - other.end));
      return {
        schedule,
        conflicts: findConflicts(schedule).length,
        reassigned: schedule.filter((service, i) => service.track !== services[i].track).length,
        unchangedTimes: schedule.filter((service, i) => service.start === services[i].start && service.end === services[i].end).length,
        minimumActualGap: Math.min(...gaps),
      };
    },
    render,
    style: `
      .rail-schedule{background:#121943;border:1px solid #3a4681;border-radius:17px;padding:19px 26px;color:#eff2ff}
      .rail-heading{display:flex;justify-content:space-between;align-items:center}.rail-heading h2{margin:0 0 5px;font-size:29px}
      .rail-heading small,.rail-heading>span{color:#90d6ff;font-weight:bold;font-size:13px;letter-spacing:.12em}
      .rail-clock{position:relative;height:34px;margin-left:110px;color:#bbc6f5;font:12px ui-monospace,monospace}
      .rail-clock span{position:absolute;bottom:5px;transform:translateX(-50%)}
      .rail-lane{display:grid;grid-template-columns:110px 1fr;align-items:center;margin-bottom:10px}
      .rail-lane label{font-size:14px;font-weight:bold;color:#c7caf4}.rail-track{height:58px;position:relative;border:1px solid #455082;border-radius:5px;background:repeating-linear-gradient(90deg,#1b234f 0%,#1b234f 16.4%,#4c5780 16.67%)}
      .rail-service{box-sizing:border-box;overflow:hidden;height:42px;position:absolute;top:7px;border:1px solid #6f9bd7;border-radius:5px;padding:4px 9px;background:#263f78}
      .rail-service b,.rail-service span{display:block}.rail-service b{font:700 14px ui-monospace,monospace}.rail-service span{font-size:11px;color:#d2e2ff}
      .rail-service.conflict{background:#8a2b49;border-color:#ff9cb2}.rail-service.moved{background:#186055;border-color:#7aebcb}
      .rail-notice{border-left:3px solid #79e5ca;color:#e6edff;margin:16px 0 0 110px;padding:0 10px}
      .rail-notice.warning{border-color:#ff8f9f;background:#361d42}.rail-notice p{margin:0;padding:3px 5px}
    `,
  };
})();
