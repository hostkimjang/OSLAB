(() => {
  const agenda = [
    { title: "Daily briefing", room: "Atlas", start: 540, end: 570 },
    { title: "Product review", room: "Atlas", start: 585, end: 675 },
    { title: "Vendor workshop", room: "Atlas", start: 780, end: 840 },
    { title: "Supplier sync", room: "Cypress", start: 600, end: 645 },
    { title: "User interview", room: "Cypress", start: 690, end: 735 }
  ];
  const requested = { title: "Launch handoff", room: "Atlas", start: 630, end: 690 };
  const displayStart = 510;
  const displayEnd = 870;

  function formatTime(minutes) {
    return [Math.floor(minutes / 60), minutes % 60].map((value) => String(value).padStart(2, "0")).join(":");
  }

  function overlaps(bookings, request) {
    return bookings.filter((booking) => booking.room === request.room &&
      request.start < booking.end && booking.start < request.end);
  }

  function reschedule(bookings, request) {
    const duration = request.end - request.start;
    for (let start = request.start; start + duration <= displayEnd; start += 15) {
      const slot = { ...request, start, end: start + duration };
      if (overlaps(bookings, slot).length === 0) return slot;
    }
    return null;
  }

  const percent = (minutes) => (minutes / (displayEnd - displayStart)) * 100;
  const position = (minutes) => percent(minutes - displayStart);

  function card(booking, top, fill, color, border) {
    return `<div title="${booking.title}" style="position:absolute;left:${position(booking.start)}%;top:${top}px;width:${percent(booking.end-booking.start)}%;box-sizing:border-box;overflow:hidden;padding:7px 8px;white-space:nowrap;border-radius:8px;background:${fill};color:${color};border:1px solid ${border}">
      <div style="font-size:12px;font-weight:800;overflow:hidden;text-overflow:ellipsis">${booking.title}</div>
      <div style="font-size:11px;margin-top:2px">${formatTime(booking.start)}–${formatTime(booking.end)}</div>
    </div>`;
  }

  window.caseDefinition = {
    id: "19",
    title: "Slotline",
    kicker: "ROOM SCHEDULING",
    scenario: "Find a conflict-free room booking while keeping the launch handoff one hour long.",
    layout: "board",
    accent: "#325ad2",
    surface: "#e9efff",
    text: "#162345",
    actions: ["Load room calendars", "Check booking conflicts", "Move to the first free slot"],
    expected: [
      { bookings: 5, rooms: 2 },
      { conflictCount: 1, conflict: "Product review", minutes: 45, approved: false },
      { conflictCount: 0, start: "11:15", end: "12:15", duration: 60, approved: true }
    ],
    run(step) {
      if (step === 1) return { bookings: agenda.length, rooms: new Set(agenda.map((entry) => entry.room)).size };
      const slot = step === 2 ? requested : reschedule(agenda, requested);
      if (!slot) return { approved: false, conflictCount: null };
      const conflicts = overlaps(agenda, slot);
      return {
        slot,
        conflictCount: conflicts.length,
        conflict: conflicts.map((entry) => entry.title).join(", "),
        minutes: conflicts.reduce((total, entry) =>
          total + Math.min(entry.end, slot.end) - Math.max(entry.start, slot.start), 0),
        start: formatTime(slot.start), end: formatTime(slot.end), duration: slot.end-slot.start, approved: conflicts.length === 0
      };
    },
    render(step, result) {
      const hours = [510,570,630,690,750,810,870];
      const slot = result?.slot || requested;
      const rotated = step === 2 ? "45 minutes overlap" : step === 3 ? "11:15 → 12:15" : "10:30 → 11:30";
      return `<section style="padding:12px 18px;color:#162345;display:grid;grid-template-columns:3fr 1fr;gap:18px">
        <div style="background:#f9faff;border:1px solid #c7d4fb;border-radius:20px;padding:22px 22px 18px">
          <div style="color:#325ad2;font-size:13px;font-weight:800">MONDAY · TEAM SPACES</div>
          <h2 style="font-size:28px;margin:8px 0 19px">Room calendar</h2>
          <div style="margin-left:70px;position:relative;height:30px;color:#586890;font-size:12px;font-weight:800">
            ${hours.map((hour) => `<span style="position:absolute;left:${position(hour)}%;transform:translateX(-50%)">${formatTime(hour)}</span>`).join("")}
          </div>
          ${["Atlas","Cypress"].map((room) => `<div style="display:grid;grid-template-columns:70px 1fr;border-top:1px solid #cfdaff;height:${room === "Atlas" ? 139 : 82}px">
            <b style="padding-top:16px;font-size:15px">${room}</b>
            <div style="position:relative;background:repeating-linear-gradient(90deg,#e2eaff 0 1px,transparent 1px 16.666%)">
              ${agenda.filter((booking) => booking.room === room).map((booking) => card(booking, 13,
                room === "Atlas" ? "#dbe5ff" : "#dcf5ee", "#213b71", room === "Atlas" ? "#a8bdfa" : "#afdccc")).join("")}
              ${room === "Atlas" ? card(slot, 72, step === 2 ? "#ffe2dc" : step === 3 ? "#bcf1d4" : "#d9d0ff",
                step === 2 ? "#903d2d" : "#25405d", step === 2 ? "#e9a696" : step === 3 ? "#82cfa8" : "#b7aaf2") : ""}
            </div>
          </div>`).join("")}
          <div style="font-size:13px;font-weight:700;color:#475c8b;padding-top:12px">New booking appears in the second lane of its requested room.</div>
        </div>
        <aside style="background:#1f3ca5;border-radius:20px;padding:23px;color:#f3f6ff">
          <div style="color:#cddaff;font-size:13px;font-weight:750">BOOKING REQUEST</div>
          <h2 style="margin:16px 0 5px;font-size:27px">Launch handoff</h2><p style="margin:0;color:#dce6ff">Atlas · 60 minutes</p>
          <p style="font-size:23px;font-weight:850;padding:17px 0;border-bottom:1px solid #6681de;color:${step === 2 ? "#ffcdbc" : "#e4f8db"}">${rotated}</p>
          <p style="line-height:1.45">${step === 2 ? "The room is already booked for Product review." : step === 3 ? "The new slot starts after Product review and leaves the duration unchanged." : "Check the existing room bookings before confirming."}</p>
        </aside>
      </section>`;
    }
  };
})();
