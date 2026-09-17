"use client";

import { KeyboardEvent, useMemo, useState } from "react";

type Pair = [string, number];

function maxOf(data: Pair[]) {
  return Math.max(1, ...data.map((item) => item[1]));
}

export function BarList({ data, compact = false }: { data: Pair[]; compact?: boolean }) {
  const max = maxOf(data);
  return (
    <div className="bar-list">
      {data.slice(0, compact ? 5 : 8).map(([label, value]) => (
        <div className="bar-row" key={label} data-tip={`${label}：${value.toLocaleString("zh-CN")}`}>
          <span>{label}</span>
          <div className="bar-track">
            <i style={{ width: `${Math.max(4, (value / max) * 100)}%` }} />
          </div>
          <b>{value.toLocaleString("zh-CN")}</b>
        </div>
      ))}
    </div>
  );
}

export function LineTrend({ data, tall = false, onChoose }: { data: Pair[]; tall?: boolean; onChoose?: (label: string) => void }) {
  const normalized = useMemo(() => data.filter(([, value]) => Number.isFinite(value)).slice(-14), [data]);
  const max = maxOf(normalized);
  const [activeIndex, setActiveIndex] = useState(() => Math.max(0, normalized.length - 1));
  const safeActiveIndex = Math.min(activeIndex, Math.max(0, normalized.length - 1));
  const active = normalized[safeActiveIndex];
  const points = normalized.map(([label, value], index) => {
    const x = normalized.length <= 1 ? 300 : 30 + (index / (normalized.length - 1)) * 540;
    const y = 158 - (value / max) * 118;
    return { label, value, x, y };
  });
  const linePoints = points.map((point) => `${point.x},${point.y}`).join(" ");
  const axisY = 174;

  function handlePointKey(event: KeyboardEvent<SVGCircleElement>, label: string) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onChoose?.(label);
    }
  }

  if (!normalized.length) {
    return (
      <div className={tall ? "line-trend-shell tall" : "line-trend-shell"}>
        <div className="empty-chart">暂无日期数据</div>
      </div>
    );
  }

  return (
    <div className={tall ? "line-trend-shell tall" : "line-trend-shell"}>
      {active ? (
        <div className="line-trend-summary" aria-live="polite">
          <span>{formatDateLabel(active[0])}</span>
          <b>{active[1].toLocaleString("zh-CN")} 次</b>
        </div>
      ) : null}
      <svg className={tall ? "line-trend tall" : "line-trend"} viewBox="0 0 600 180" role="img" aria-label="服务趋势日期图" onMouseLeave={() => setActiveIndex(Math.max(0, normalized.length - 1))}>
        {[48, 96, 144].map((y) => (
          <line className="trend-grid-line" key={y} x1="30" x2="570" y1={y} y2={y} />
        ))}
        <polygon points={`30,166 ${linePoints} 570,166`} fill="currentColor" opacity="0.08" />
        <polyline points={linePoints} fill="none" stroke="currentColor" strokeWidth="3.2" strokeLinecap="round" strokeLinejoin="round" />
        {points.map((point, index) => (
          <circle
            aria-label={`${formatDateLabel(point.label)} ${point.value.toLocaleString("zh-CN")} 次`}
            className={index === safeActiveIndex ? "active" : ""}
            cx={point.x}
            cy={point.y}
            fill="currentColor"
            key={point.label}
            onClick={() => onChoose?.(point.label)}
            onFocus={() => setActiveIndex(index)}
            onKeyDown={(event) => handlePointKey(event, point.label)}
            onMouseEnter={() => setActiveIndex(index)}
            r={index === safeActiveIndex ? "4.4" : "3"}
            role="button"
            tabIndex={0}
          >
            <title>{`${formatDateLabel(point.label)}：${point.value.toLocaleString("zh-CN")} 次`}</title>
          </circle>
        ))}
        {points.map((point, index) => (
          <text
            className={index === safeActiveIndex ? "axis-active" : ""}
            key={point.label}
            x={point.x}
            y={axisY}
            textAnchor="middle"
            onClick={() => onChoose?.(point.label)}
            onMouseEnter={() => setActiveIndex(index)}
            role="button"
            tabIndex={0}
          >
            {formatShortDateLabel(point.label)}
          </text>
        ))}
      </svg>
    </div>
  );
}

function formatDateLabel(value: string) {
  const normalized = value.replace("T", " ");
  const datePart = normalized.slice(0, 10);
  if (/^\d{4}-\d{2}-\d{2}$/.test(datePart)) {
    const date = new Date(`${datePart}T00:00:00`);
    if (!Number.isNaN(date.getTime())) {
      return date.toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit", weekday: "short" });
    }
  }
  return normalized;
}

function formatShortDateLabel(value: string) {
  const normalized = value.replace("T", " ");
  const datePart = normalized.slice(0, 10);
  if (/^\d{4}-\d{2}-\d{2}$/.test(datePart)) return datePart.slice(5);
  return normalized.length > 6 ? normalized.slice(-6) : normalized;
}

export function DonutChart({ data }: { data: Pair[] }) {
  const total = Math.max(1, data.reduce((sum, item) => sum + item[1], 0));
  let offset = 25;
  const palette = ["#1d4f82", "#3f7195", "#6f927f", "#b27a45", "#6a7da0", "#9aa9b5"];
  return (
    <div className="donut-chart">
      <svg viewBox="0 0 42 42" role="img" aria-label="分布图">
        <circle cx="21" cy="21" r="15.9" fill="none" stroke="#e0eefb" strokeWidth="6" />
        {data.slice(0, 6).map(([label, value], index) => {
          const dash = (value / total) * 100;
          const segment = (
            <circle
              key={label}
              cx="21"
              cy="21"
              r="15.9"
              fill="none"
              stroke={palette[index % palette.length]}
              strokeDasharray={`${dash} ${100 - dash}`}
              strokeDashoffset={offset}
              strokeLinecap="round"
              strokeWidth="6"
            >
              <title>{`${label}：${value.toLocaleString("zh-CN")}`}</title>
            </circle>
          );
          offset -= dash;
          return segment;
        })}
      </svg>
      <div className="donut-legend">
        {data.slice(0, 6).map(([label, value], index) => (
          <span key={label}>
            <i style={{ background: palette[index % palette.length] }} />
            {label}
            <b>{value.toLocaleString("zh-CN")}</b>
          </span>
        ))}
      </div>
    </div>
  );
}

export function KeywordCloud({ data, onChoose }: { data: Pair[]; onChoose?: (keyword: string) => void }) {
  const max = maxOf(data);
  return (
    <div className="keyword-cloud">
      {data.slice(0, 16).map(([label, value]) => (
        <button
          type="button"
          key={label}
          onClick={() => onChoose?.(label)}
          style={{ fontSize: `${14 + Math.min(12, (value / max) * 12)}px` }}
          data-tip={`${label}：${value} 次，点击查看相关问题`}
        >
          <span>{label}</span>
          <b>{value}</b>
        </button>
      ))}
    </div>
  );
}
