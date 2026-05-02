"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import type { ArtifactPathCheck } from "@oslab/shared";
import type { DashboardText, Lang } from "../model";
import { formatBytes } from "../lib";

export function InfoTooltip({
  text,
  label,
}: {
  text: string;
  label: string;
}) {
  const id = useId();
  const buttonRef = useRef<HTMLButtonElement | null>(null);
  const bubbleRef = useRef<HTMLSpanElement | null>(null);
  const [open, setOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [position, setPosition] = useState({ top: 0, left: 0, placement: "bottom" as "top" | "bottom" });

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!open) return;
    const updatePosition = () => {
      const rect = buttonRef.current?.getBoundingClientRect();
      if (!rect) return;
      const margin = 16;
      const width = Math.min(320, window.innerWidth - margin * 2);
      const left = Math.max(margin, Math.min(rect.left + rect.width / 2 - width / 2, window.innerWidth - width - margin));
      const useTop = rect.bottom + 12 + 120 > window.innerHeight && rect.top > 140;
      setPosition({
        top: useTop ? Math.max(margin, rect.top - 12) : Math.min(window.innerHeight - margin, rect.bottom + 12),
        left,
        placement: useTop ? "top" : "bottom",
      });
    };
    updatePosition();
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (buttonRef.current?.contains(target) || bubbleRef.current?.contains(target)) return;
      setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        buttonRef.current?.focus();
      }
    };
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <span className="infoTooltipWrap" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      <button
        ref={buttonRef}
        type="button"
        className="infoTooltip"
        aria-label={label}
        aria-expanded={open}
        aria-describedby={open ? id : undefined}
        onClick={() => setOpen(true)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
      >
        <span aria-hidden="true">i</span>
      </button>
      {mounted && open && createPortal(
        <span
          ref={bubbleRef}
          id={id}
          className={`infoTooltipBubble ${position.placement}`}
          role="tooltip"
          style={{
            top: position.top,
            left: position.left,
            maxWidth: "min(320px, calc(100vw - 32px))",
          }}
        >
          {text}
        </span>,
        document.body,
      )}
    </span>
  );
}

export function LanguageSwitch({ lang, setLang }: { lang: Lang; setLang: (lang: Lang) => void }) {
  return (
    <div className="segmented" aria-label="language">
      <button type="button" className={lang === "ko" ? "active" : ""} aria-pressed={lang === "ko"} onClick={() => setLang("ko")}>KO</button>
      <button type="button" className={lang === "en" ? "active" : ""} aria-pressed={lang === "en"} onClick={() => setLang("en")}>EN</button>
    </div>
  );
}

export function Metric({ label, value, info, t }: { label: string; value: number; info?: string; t?: DashboardText }) {
  return (
    <div className="metric">
      <span className="cardTitleLine">
        <span>{label}</span>
        {info && t && <InfoTooltip text={info} label={t.infoTooltipLabel} />}
      </span>
      <strong>{value}</strong>
    </div>
  );
}

export function List({ title, items, info, t }: { title: string; items: string[]; info?: string; t?: DashboardText }) {
  return (
    <div className="panel miniListPanel">
      <h3 className="sectionTitleLine">
        <span>{title}</span>
        {info && t && <InfoTooltip text={info} label={t.infoTooltipLabel} />}
      </h3>
      <div className="miniList">
        {items.map((item, index) => <p key={`${title}-${index}-${item}`}>{item}</p>)}
      </div>
    </div>
  );
}

export function CommandPreview({ title, command }: { title: string; command: string }) {
  return (
    <div className="commandPreview">
      <span>{title}</span>
      <code>{command}</code>
    </div>
  );
}

export function ArtifactStatus({ check, checking, t }: { check: ArtifactPathCheck | null; checking: boolean; t: DashboardText }) {
  if (checking) return <p className="artifactStatus checking">{t.artifactChecking}</p>;
  if (!check) return null;
  return (
    <p className={`artifactStatus ${check.exists ? "ok" : "bad"}`}>
      {check.exists ? t.artifactReady : t.artifactMissing}
      {check.kind ? ` · ${check.kind}` : ""}
      {check.size ? ` · ${formatBytes(check.size)}` : ""}
      {check.modifiedAt ? ` · ${new Date(check.modifiedAt).toLocaleString()}` : ""}
    </p>
  );
}

export function RunReadinessFlow({
  title,
  stages,
  info,
  t,
}: {
  title: string;
  stages: Array<{ label: string; status: "ok" | "warning" | "blocked"; detail: string }>;
  info?: string;
  t?: DashboardText;
}) {
  return (
    <div className="readinessFlow" aria-label={title}>
      <strong className="sectionTitleLine">
        <span>{title}</span>
        {info && t && <InfoTooltip text={info} label={t.infoTooltipLabel} />}
      </strong>
      <div className="readinessSteps">
        {stages.map((stage, index) => (
          <div key={`${stage.label}-${index}`} className={`readinessStep ${stage.status}`} title={`${stage.label}: ${stage.detail}`}>
            <span>{index + 1}</span>
            <div>
              <b>{stage.label}</b>
              <small>{stage.detail}</small>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function RunStepSection({
  index,
  title,
  hint,
  tooltipLabel,
  children,
}: {
  index: number;
  title: string;
  hint: string;
  tooltipLabel?: string;
  children: ReactNode;
}) {
  return (
    <section className="runStep">
      <div className="runStepHeader">
        <span>{index}</span>
        <div>
          <strong className="sectionTitleLine">
            <span>{title}</span>
            <InfoTooltip text={hint} label={tooltipLabel ?? title} />
          </strong>
          <p>{hint}</p>
        </div>
      </div>
      <div className="runStepBody">{children}</div>
    </section>
  );
}

export function StatusCell({ label, value, ok, info, t }: { label: string; value?: string; ok?: boolean; info?: string; t?: DashboardText }) {
  return (
    <div className="statusCell">
      <span className={`miniDot ${ok ? "ok" : "bad"}`} />
      <span className="statusCellLabel">
        <span>{label}</span>
        {info && t && <InfoTooltip text={info} label={t.infoTooltipLabel} />}
      </span>
      <strong>{value || "<unknown>"}</strong>
    </div>
  );
}

export function StatusList({ title, items, kind }: { title: string; items: string[]; kind: "issue" | "warning" }) {
  return (
    <div className={`statusList ${kind}`}>
      <strong>{title}</strong>
      {items.map((item) => <span key={item}>{item}</span>)}
    </div>
  );
}
