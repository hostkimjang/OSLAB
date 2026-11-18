(() => {
  const tickets = {
    db: { label: "Snapshot database", code: "CHG-21", x: 26, y: 97 },
    api: { label: "Deploy API", code: "CHG-22", x: 274, y: 97 },
    smoke: { label: "Run smoke tests", code: "CHG-23", x: 522, y: 97 },
    traffic: { label: "Shift traffic", code: "CHG-24", x: 522, y: 265 }
  };
  const draft = { db: [], api: ["db", "smoke"], smoke: ["api"], traffic: ["smoke"] };
  const repaired = { ...draft, api: ["db"] };

  function inspect(dependencies) {
    const order = [];
    const pending = new Set(Object.keys(dependencies));
    while (pending.size) {
      const key = [...pending].find((candidate) =>
        dependencies[candidate].every((required) => !pending.has(required)));
      if (!key) break;
      order.push(key);
      pending.delete(key);
    }
    return { order, blocked: [...pending] };
  }

  function renderGraph(dependencies, blocked, width) {
    const links = Object.entries(dependencies).flatMap(([target, required]) =>
      required.map((source) => {
        const a = tickets[source], b = tickets[target];
        const backwards = a.x > b.x;
        const failing = blocked.includes(target) && blocked.includes(source);
        let path = `M ${a.x + width} ${a.y + 38} H ${b.x - 9}`;
        if (a.x === b.x) path = `M ${a.x + width / 2} ${a.y + 76} V ${b.y - 10}`;
        if (backwards) path = `M ${a.x + width * .72} ${a.y} V ${a.y - 45} H ${b.x + width * .6} V ${b.y - 9}`;
        return `<path d="${path}" fill="none" stroke="${failing ? "#ff9b99" : "#6ee6ca"}" stroke-width="3" marker-end="url(#chg-${failing ? "stop" : "go"})"/>`;
      })
    );
    const nodes = Object.entries(tickets).map(([key, ticket]) => {
      const failing = blocked.includes(key);
      return `<g><rect x="${ticket.x}" y="${ticket.y}" width="${width}" height="76" rx="13" fill="${failing ? "#4b303f" : "#1c3d56"}" stroke="${failing ? "#ff9b99" : "#476578"}"/>
        <text x="${ticket.x + 15}" y="${ticket.y + 29}" fill="#94d7df" font-size="13" font-weight="600">${ticket.code}</text>
        <text x="${ticket.x + 15}" y="${ticket.y + 54}" fill="#f2fafc" font-size="17" font-weight="600">${ticket.label}</text></g>`;
    });
    return `<svg role="img" aria-label="Change-ticket dependency graph" viewBox="0 0 735 360" style="width:100%;height:370px">
      <defs>
        <marker id="chg-go" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0 0 L7 3.5 L0 7 Z" fill="#6ee6ca"/></marker>
        <marker id="chg-stop" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0 0 L7 3.5 L0 7 Z" fill="#ff9b99"/></marker>
      </defs>${links.join("")}${nodes.join("")}</svg>`;
  }

  window.caseDefinition = {
    id: "17",
    title: "Change Graph",
    kicker: "RELEASE ORCHESTRATION",
    scenario: "Block a circular deployment plan, then publish a safe execution order.",
    layout: "canvas",
    accent: "#65e8c6",
    surface: "#142c42",
    text: "#edf8ff",
    actions: ["Import change set", "Simulate rollout", "Remove cycle and publish"],
    expected: [
      { count: 4, edges: 4 },
      { runnable: 1, blocked: "api,smoke,traffic", approved: false },
      { runnable: 4, approved: true, sequence: "db,api,smoke,traffic" }
    ],
    run(step) {
      if (step === 1) {
        return { count: Object.keys(draft).length, edges: Object.values(draft).flat().length };
      }
      const { order, blocked } = inspect(step === 2 ? draft : repaired);
      return { runnable: order.length, blocked: blocked.join(","), approved: blocked.length === 0, sequence: order.join(",") };
    },
    render(step, result) {
      const blocked = result?.blocked ? result.blocked.split(",") : [];
      const title = step === 3 ? "Rollout plan approved" : step === 2 ? "Rollout halted" : "Review change set";
      const description = [
        "Import the change set to review the dependencies before rollout.",
        `${result?.count ?? 4} changes. ${result?.edges ?? 4} dependency rules.`,
        "Deploy API waits on its own smoke test. No downstream change can run.",
        "The published plan now runs the smoke test after deployment and before traffic shifts."
      ][step];
      const list = step === 3 ? result.sequence.split(",") : step === 2 ? blocked : [];
      return `<section style="padding:16px 18px 14px;display:grid;grid-template-columns:2.25fr 1fr;gap:18px;color:#edf8ff">
        <div style="border:1px solid #3a6177;border-radius:22px;background:radial-gradient(ellipse at 58% 37%,#25536e,#132935 74%);overflow:hidden">
          <div style="padding:18px 21px 0;color:#9cc5d4;font-size:14px;font-weight:650">PRODUCTION ROLLOUT · CHANGE SET 84</div>
          ${renderGraph(step === 3 ? repaired : draft, blocked, 187)}
        </div>
        <aside style="border:1px solid #3a6177;border-radius:22px;padding:22px;background:#17374b">
          <div style="color:${step === 2 ? "#ff9b99" : "#65e8c6"};font-size:14px;font-weight:750">DEPLOYMENT SIMULATION</div>
          <h2 style="font-size:25px;margin:14px 0 8px">${title}</h2><p style="line-height:1.45;color:#bed3e0">${description}</p>
          ${list.map((key, i) => `<div style="padding:10px 0;border-top:1px solid #416071"><b style="color:#9cd9df">${step === 3 ? i + 1 + ". " : ""}${tickets[key].code}</b> · ${tickets[key].label}</div>`).join("")}
        </aside>
      </section>`;
    }
  };
})();
