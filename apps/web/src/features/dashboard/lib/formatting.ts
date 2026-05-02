export function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${Math.round(value / 1024)} KiB`;
  return `${(value / 1024 / 1024).toFixed(1)} MiB`;
}

export function formatPreviewContent(relativePath: string, text: string): string {
  const normalized = normalizePreviewText(text);
  if (/\.json$/i.test(relativePath)) {
    return formatJsonText(normalized) || normalized;
  }
  if (/\.jsonl$/i.test(relativePath)) {
    return formatJsonLines(normalized);
  }
  if (/\.(log|txt)$/i.test(relativePath)) {
    return formatJsonText(normalized) || formatJsonLikeLog(normalized);
  }
  if (/\.xml$/i.test(relativePath)) {
    return formatXmlText(normalized) || normalized;
  }
  return normalized;
}

function normalizePreviewText(text: string): string {
  return text.replace(/^\uFEFF/, "").replace(/\r\n?/g, "\n");
}

function formatJsonText(text: string): string | null {
  const trimmed = text.trim();
  if (!trimmed || (!trimmed.startsWith("{") && !trimmed.startsWith("["))) return null;
  try {
    return JSON.stringify(JSON.parse(trimmed), null, 2);
  } catch {
    return null;
  }
}

function formatJsonLines(text: string): string {
  return text
    .split("\n")
    .map((line) => {
      if (!line.trim()) return "";
      return formatJsonText(line) || line;
    })
    .join("\n\n");
}

function formatJsonLikeLog(text: string): string {
  return text
    .split("\n")
    .map((line) => {
      if (!line.trim()) return line;
      const leadingWhitespace = line.match(/^\s*/)?.[0] || "";
      const formatted = formatJsonText(line);
      return formatted ? formatted.split("\n").map((part) => `${leadingWhitespace}${part}`).join("\n") : line;
    })
    .join("\n");
}

function formatXmlText(text: string): string | null {
  const trimmed = text.trim();
  if (!trimmed.startsWith("<")) return null;
  try {
    let depth = 0;
    return trimmed
      .replace(/>\s*</g, ">\n<")
      .split("\n")
      .map((line) => {
        const value = line.trim();
        if (!value) return "";
        if (/^<\//.test(value)) depth = Math.max(0, depth - 1);
        const output = `${"  ".repeat(depth)}${value}`;
        if (/^<[^!?/][^>]*[^/]?>$/.test(value) && !value.includes("</")) depth += 1;
        return output;
      })
      .join("\n");
  } catch {
    return null;
  }
}

export function relativeTime(value?: string): string {
  if (!value) return "unknown";
  const then = new Date(value).getTime();
  const diffSeconds = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (diffSeconds < 60) return `${diffSeconds}s ago`;
  if (diffSeconds < 3600) return `${Math.round(diffSeconds / 60)}m ago`;
  if (diffSeconds < 86400) return `${Math.round(diffSeconds / 3600)}h ago`;
  return `${Math.round(diffSeconds / 86400)}d ago`;
}

export function parseRunIdTimestamp(runId: string): Date | null {
  const match = /^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})/.exec(runId);
  if (!match) return null;
  const [, year, month, day, hour, minute, second] = match;
  const date = new Date(
    Number(year),
    Number(month) - 1,
    Number(day),
    Number(hour),
    Number(minute),
    Number(second),
  );
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatHumanDateTime(value?: string | Date | null, lang: "en" | "ko" = "ko"): string {
  if (!value) return "<unknown>";
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "<unknown>";
  if (lang === "ko") {
    return `${date.getFullYear()}년 ${date.getMonth() + 1}월 ${date.getDate()}일 ${pad2(date.getHours())}시 ${pad2(date.getMinutes())}분`;
  }
  return new Intl.DateTimeFormat("en", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

export function formatDuration(start?: string | Date | null, end?: string | Date | null, lang: "en" | "ko" = "ko"): string {
  const startDate = start instanceof Date ? start : start ? new Date(start) : null;
  const endDate = end instanceof Date ? end : end ? new Date(end) : null;
  if (!startDate || !endDate || Number.isNaN(startDate.getTime()) || Number.isNaN(endDate.getTime())) return "<unknown>";
  const totalSeconds = Math.max(0, Math.round((endDate.getTime() - startDate.getTime()) / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (lang === "ko") {
    return minutes ? `${minutes}분 ${seconds}초` : `${seconds}초`;
  }
  return minutes ? `${minutes}m ${seconds}s` : `${seconds}s`;
}

function pad2(value: number): string {
  return String(value).padStart(2, "0");
}
