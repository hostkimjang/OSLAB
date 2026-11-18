(() => {
  const prototype = [
    {id: "basket", title: "Open basket", detail: "2 items", mark: "BK", tabIndex: 3},
    {id: "review", title: "Review items", detail: "Totals and quantities", mark: "RV", tabIndex: -1},
    {id: "payment", title: "Payment", detail: "Delivery and billing", mark: "PY", tabIndex: 1},
    {id: "place", title: "Place order", detail: "Final confirmation", mark: "GO", tabIndex: 0},
    {id: "help", title: "Order help", detail: "Checkout support", mark: "?", tabIndex: 0},
  ];
  const expectedOrder = prototype.map(control => control.id);
  const repaired = prototype.map(control => ({...control, tabIndex: 0}));

  function tabOrder(controls) {
    const tabbable = controls.filter(control => control.tabIndex >= 0);
    const priority = tabbable.filter(control => control.tabIndex > 0).sort((a, b) => a.tabIndex - b.tabIndex);
    return priority.concat(tabbable.filter(control => control.tabIndex === 0)).map(control => control.id);
  }

  function audit(controls) {
    const order = tabOrder(controls);
    const omitted = expectedOrder.filter(id => !order.includes(id));
    const positiveOverrides = controls.filter(control => control.tabIndex > 0).length;
    const rank = new Map(expectedOrder.map((id, index) => [id, index]));
    const inversions = order.reduce((count, id, index) => count +
      order.slice(index + 1).filter(next => rank.get(next) < rank.get(id)).length, 0);
    return {order, omitted, positiveOverrides, inversions, reachable: order.length,
      approved: omitted.length === 0 && inversions === 0 && positiveOverrides === 0};
  }

  function render(step, result) {
    const controls = step === 3 ? repaired : prototype;
    const order = step >= 2 ? result.order : [];
    const accepted = step === 3;
    return `
      <div class="focus-app">
        <div class="focus-live">
          <div class="focus-tag">LIVE CHECKOUT PROTOTYPE</div><h2>Order flow</h2>
          <p>Each card uses the same tabindex as the prototype being audited.</p>
          <div class="focus-cards">${controls.map(control => {
            const rank = order.indexOf(control.id) + 1;
            return `<button type="button" class="focus-node ${step >= 2 && rank === 0 ? "focus-off" : ""}" tabindex="${control.tabIndex}"
              data-focus-entry="${control.id}" aria-label="${control.title}">
                <span class="focus-mark">${control.mark}</span>
                <span class="focus-node-label"><b>${control.title}</b><small>${control.detail}</small></span>
                <span class="focus-rank">${step < 2 ? "—" : rank || "SKIP"}</span>
              </button>`;
          }).join("")}</div>
        </div>
        <aside class="focus-report">
          <div class="focus-tag">KEYBOARD PREFLIGHT</div><h2>Focus sequence</h2>
          <strong>${step >= 2 ? `${result.reachable}/${controls.length}` : "—"}</strong>
          <p>controls reachable by Tab</p>
          <ol>${order.map(id => `<li>${controls.find(control => id === control.id).title}</li>`).join("")}</ol>
          <div class="focus-verdict ${step === 2 ? "focus-bad" : ""}">${accepted ?
            "PASS · native order restored" : step === 2 ? "HOLD · the Review items step is skipped" : "Awaiting keyboard audit"}</div>
        </aside>
      </div>`;
  }

  window.caseDefinition = {
    id: "24",
    title: "Focus Path",
    kicker: "ACCESSIBILITY PREFLIGHT",
    scenario: "Detect a keyboard-only checkout blocker and restore the intended reading order.",
    layout: "board",
    accent: "#9eceff",
    surface: "#102740",
    text: "#e8f2ff",
    actions: ["Load checkout prototype", "Audit native tab order", "Restore reading order"],
    expected: [
      {controls: 5, expectedFirst: "basket", expectedLast: "help", positiveOverrides: 2},
      {order: ["payment", "basket", "place", "help"], omitted: ["review"], positiveOverrides: 2, inversions: 1,
        reachable: 4, approved: false},
      {order: ["basket", "review", "payment", "place", "help"], omitted: [], positiveOverrides: 0, inversions: 0,
        reachable: 5, approved: true},
    ],
    run(step) {
      if (step === 1) return {controls: prototype.length, expectedFirst: expectedOrder[0],
        expectedLast: expectedOrder[expectedOrder.length - 1], positiveOverrides: prototype.filter(control => control.tabIndex > 0).length};
      if (step === 2) return audit(prototype);
      return audit(repaired);
    },
    render,
    style: `
      .focus-app{display:grid;grid-template-columns:1.7fr 1fr;gap:20px;padding:10px 0;color:#e8f2ff}
      .focus-live,.focus-report{border:1px solid #3c6280;border-radius:10px;background:#173653;padding:20px;min-width:0}
      .focus-tag{font:700 11px ui-monospace,monospace;letter-spacing:.11em;color:#9eceff}.focus-app h2{margin:5px 0;font-size:28px}
      .focus-app p{color:#c0d8ed;font-size:13px;margin:2px 0 12px}
      .focus-cards{display:grid;gap:6px}.focus-node{border:1px solid #406582;display:flex;align-items:center;padding:7px 8px;
        gap:9px;background:#21496b;color:#f4f9ff;border-radius:6px;text-align:left;cursor:pointer;min-width:0}
      .focus-node:focus-visible{outline:3px solid #ffdb82;outline-offset:1px}.focus-node.focus-off{background:#664052;border-color:#cb788d}
      .focus-mark,.focus-rank{display:grid;place-items:center;background:#9eceff;color:#112b42;width:31px;height:28px;border-radius:5px;
        font:700 12px ui-monospace,monospace;flex-shrink:0}.focus-node-label{min-width:0;flex:1}
      .focus-node-label small{display:block;color:#ccdef0;font-size:11px}.focus-rank{background:#16324b;color:#bddafb}
      .focus-off .focus-rank{color:#ffb4c4;font-size:9px;background:#3b2936}.focus-report{background:#ddecff;color:#13314a}
      .focus-report .focus-tag{color:#326687}.focus-report>strong{display:block;font-size:49px;letter-spacing:-.06em}.focus-report p{color:#326687}
      .focus-report ol{padding-left:23px;min-height:100px;margin:6px 0;font-size:14px}.focus-report li{padding:1px 0}
      .focus-verdict{padding:8px;background:#c5e1d8;color:#174d45;font-weight:700;font-size:12px;border-radius:5px}
      .focus-verdict.focus-bad{background:#f3c5cd;color:#742f44}`,
  };
})();
