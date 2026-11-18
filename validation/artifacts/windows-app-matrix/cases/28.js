(() => {
  const lanes = [
    { key: "queue", title: "Queued", tone: "#68627b" },
    { key: "work", title: "In progress", tone: "#7546c9", capacity: 2 },
    { key: "review", title: "Review", tone: "#247568", capacity: 2 }
  ];
  const tickets = [
    { id: "PLAT-17", name: "Normalize signed receipts", team: "Platform", priority: 1, lane: "work", locked: true },
    { id: "API-26", name: "Add delivery metadata", team: "API", priority: 3, lane: "work" },
    { id: "CSV-03", name: "Unblock partner import", team: "Data", priority: 1, lane: "queue" },
    { id: "WEB-08", name: "Polish retry state", team: "Web", priority: 2, lane: "queue" },
    { id: "DOC-11", name: "Publish onboarding update", team: "Docs", priority: 4, lane: "queue" },
    { id: "OPS-31", name: "Verify release sign-off", team: "Ops", priority: 2, lane: "review" },
    { id: "UX-42", name: "Review quiet-hour copy", team: "Design", priority: 3, lane: "review" }
  ];
  const admissions = ["CSV-03", "WEB-08"];
  const workLimit = lanes.find(lane => lane.key === "work").capacity;

  function simulate() {
    return tickets.map(ticket => admissions.includes(ticket.id) ? { ...ticket, lane: "work" } : ticket);
  }

  function plan() {
    const proposed = simulate();
    const work = proposed.filter(ticket => ticket.lane === "work");
    const ranked = work.sort((a, b) => Number(Boolean(b.locked)) - Number(Boolean(a.locked)) ||
      a.priority - b.priority || a.id.localeCompare(b.id, "en"));
    const waiting = new Set(ranked.slice(workLimit).map(ticket => ticket.id));
    return { deferred: [...waiting], board: proposed.map(ticket => waiting.has(ticket.id) ? { ...ticket, lane: "queue" } : ticket) };
  }

  function measure(board, deferred) {
    const columns = Object.fromEntries(lanes.map(lane => [lane.key, board.filter(ticket => ticket.lane === lane.key)]));
    const overLimit = lanes.filter(lane => lane.capacity && columns[lane.key].length > lane.capacity)
      .map(lane => lane.key);
    return { columns, deferred, overLimit, safe: !overLimit.length, inProgress: columns.work.length,
      pinnedRetained: columns.work.some(ticket => ticket.id === "PLAT-17"), review: columns.review.length,
      workIds: columns.work.map(ticket => ticket.id), receivedTickets: board.length };
  }

  function render(step, result) {
    const status = result ?? measure(tickets, []);
    const lists = lanes.map(lane => {
      const cards = status.columns[lane.key];
      const isTight = status.overLimit.includes(lane.key);
      return `<section class="flow-column ${isTight ? "flow-over" : ""}" style="--lane:${lane.tone}">
        <div class="flow-head"><h2>${lane.title}</h2><span>${cards.length}${lane.capacity ? " / " + lane.capacity : ""}</span></div>
        ${cards.map(ticket => `<article class="flow-card"><div><small>${ticket.id}</small><b>${ticket.name}</b></div>
          <aside><span class="flow-priority flow-priority-${ticket.priority}">P${ticket.priority}</span>
          <small>${ticket.locked ? "In service" : ticket.team}</small></aside></article>`).join("")}</section>`;
    }).join("");
    const summary = step === 2 ? "The proposed start puts four tickets in progress. The lane can carry only two." :
      step === 3 ? `Retained the live change and admitted CSV-03. Sent ${result.deferred.join(" and ")} back to the queue.` :
      "Two urgent admissions are waiting for the start-of-day capacity check.";
    return `<div class="flow-workspace">${lists}</div><div class="flow-summary ${step === 2 ? "flow-over" : ""}">
      <strong>${step === 3 ? "CAPACITY RESTORED" : step === 2 ? "WIP LIMIT EXCEEDED" : "START-OF-DAY INTAKE"}</strong><span>${summary}</span></div>`;
  }

  window.caseDefinition = {
    id: "28", title: "Flow Lane", kicker: "DELIVERY CONTROL",
    scenario: "Catch a start-of-day work-in-progress breach and admit urgent work without displacing a live change.",
    layout: "board", accent: "#704ca5", surface: "#f5f0fa", text: "#272033",
    actions: ["Load team board", "Preview intake", "Rebalance by priority"],
    expected: [
      { inProgress: 2, review: 2, receivedTickets: 7, pinnedRetained: true },
      { inProgress: 4, overLimit: ["work"], safe: false, receivedTickets: 7 },
      { inProgress: 2, overLimit: [], safe: true, pinnedRetained: true,
        workIds: ["PLAT-17", "CSV-03"], deferred: ["WEB-08", "API-26"] }
    ],
    run(step) {
      if (step === 3) {
        const repair = plan();
        return measure(repair.board, repair.deferred);
      }
      return measure(step === 2 ? simulate() : tickets, []);
    },
    render,
    style: `
      .flow-workspace{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:17px;height:380px;color:#322743}
      .flow-column{background:#eee6f5;border:1px solid #dfd1ec;border-top:4px solid var(--lane);border-radius:13px;padding:14px;overflow:hidden}
      .flow-head{display:flex;justify-content:space-between;align-items:center;margin:0 0 12px}.flow-head h2{margin:0;font-size:22px}
      .flow-head span{padding:4px 9px;background:#fff9ff;color:var(--lane);font-size:14px;font-weight:770;border-radius:20px}
      .flow-card{display:flex;gap:8px;justify-content:space-between;background:#fffaff;border:1px solid #e0d8ea;border-radius:10px;padding:9px 11px;margin:0 0 7px}
      .flow-card small{color:#5d536a;font-size:11px;letter-spacing:.06em}.flow-card b{display:block;margin-top:3px;font-size:15px}
      .flow-card aside{display:flex;align-items:flex-end;flex-direction:column;flex:none;gap:4px}
      .flow-priority{padding:3px 7px;border-radius:6px;background:#eee7f8;font-size:12px;font-weight:780}
      .flow-priority-1{background:#fce3e6;color:#962a46}.flow-priority-2{background:#ffeccf;color:#834b13}.flow-priority-3{background:#e7e1ff;color:#55419a}
      .flow-summary{display:flex;align-items:center;gap:14px;margin-top:13px;padding:17px 20px;background:#e7ddef;color:#332642;border-radius:12px}
      .flow-summary strong{flex:none;font-size:13px;letter-spacing:.08em}.flow-over{background:#fbe5eb;border-color:#c04864}`
  };
})();
