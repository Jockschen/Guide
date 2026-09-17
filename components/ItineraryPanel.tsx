"use client";

import { CSSProperties, useEffect, useMemo, useState } from "react";
import { ChevronRight, Clock3, MapPin, Navigation, Route, X } from "lucide-react";
import type { RoutePlan, RouteStep } from "@/lib/types";

export function ItinerarySummary({ plan, onOpen }: { plan: RoutePlan; onOpen: () => void }) {
  const names = plan.steps.slice(0, 4).map((step) => step.name).join(" · ");
  return (
    <button className="itinerary-summary" type="button" onClick={onOpen} aria-label={`查看当前游线：${plan.title}`}>
      <span className="itinerary-summary-icon"><Route size={20} /></span>
      <span>
        <small>当前游线 · {plan.steps.length} 站</small>
        <strong>{plan.title}</strong>
        <em>{names || plan.mood}</em>
      </span>
      <ChevronRight size={20} />
    </button>
  );
}

export function ItineraryPanel({
  plan,
  onCloseRoute,
  onNarrateStop,
  onReplace
}: {
  plan: RoutePlan;
  onCloseRoute: () => void;
  onNarrateStop: (step: RouteStep) => void;
  onReplace: (interest: string) => void;
}) {
  const [selectedId, setSelectedId] = useState(plan.steps[0]?.spot_id || "");
  useEffect(() => setSelectedId(plan.steps[0]?.spot_id || ""), [plan]);
  const selected = useMemo(
    () => plan.steps.find((step) => step.spot_id === selectedId) || plan.steps[0],
    [plan.steps, selectedId]
  );
  const mapStyle = {
    backgroundImage: `url(${plan.image_url || "/assets/generated/route-map-lingshan-v2.png"})`
  } as CSSProperties;
  const positions = [[18, 88], [34, 75], [50, 61], [65, 44], [76, 22]];
  const routePoints = plan.steps.slice(0, 5).map((step, index) => {
    const [fallbackX, fallbackY] = positions[index] || positions[positions.length - 1];
    return `${step.map_x ?? fallbackX},${step.map_y ?? fallbackY}`;
  }).join(" ");

  return (
    <section className="itinerary-panel" aria-label="当前游线">
      <header className="itinerary-heading">
        <div>
          <span>为你保留的游线</span>
          <h2>{plan.title}</h2>
          <p>{plan.mood || plan.note}</p>
        </div>
        <button type="button" className="quiet-icon-button" onClick={onCloseRoute} aria-label="关闭当前游线">
          <X size={20} />
        </button>
      </header>

      <div className="itinerary-map" style={mapStyle} aria-label="游线示意图">
        <div className="itinerary-map-meta">
          <span><Route size={16} />{plan.steps.length} 站</span>
          <span><Clock3 size={16} />轻松步行</span>
        </div>
        {routePoints ? (
          <svg className="route-track" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
            <polyline className="route-track-keyline" fill="none" points={routePoints} vectorEffect="non-scaling-stroke" />
            <polyline className="route-track-line" fill="none" points={routePoints} vectorEffect="non-scaling-stroke" />
          </svg>
        ) : null}
        {plan.steps.slice(0, 5).map((step, index) => {
          const [fallbackX, fallbackY] = positions[index] || positions[positions.length - 1];
          const x = step.map_x ?? fallbackX;
          const y = step.map_y ?? fallbackY;
          return (
            <button
              className={selected?.spot_id === step.spot_id ? "map-stop active" : "map-stop"}
              key={step.spot_id}
              onClick={() => setSelectedId(step.spot_id)}
              style={{ left: `${x}%`, top: `${y}%` }}
              type="button"
              aria-label={`第 ${index + 1} 站，${step.name}`}
            >
              <MapPin size={24} />
              <span>{index + 1}</span>
            </button>
          );
        })}
      </div>

      {selected ? (
        <article className="current-stop" aria-live="polite">
          <span>当前选中 · 第 {plan.steps.indexOf(selected) + 1} 站</span>
          <h3>{selected.name}</h3>
          <p>{selected.reason}</p>
          <dl>
            <div><dt>位置</dt><dd>{selected.location || "按游线继续前往"}</dd></div>
            <div><dt>开放信息</dt><dd>{selected.opening || "以景区现场公告为准"}</dd></div>
          </dl>
          <button className="primary-action" type="button" onClick={() => onNarrateStop(selected)}>
            <Navigation size={18} />
            讲这一站
          </button>
        </article>
      ) : null}

      <ol className="itinerary-stops" aria-label="游线站点">
        {plan.steps.map((step, index) => (
          <li key={step.spot_id}>
            <button className={selected?.spot_id === step.spot_id ? "active" : ""} type="button" onClick={() => setSelectedId(step.spot_id)}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <b>{step.name}</b>
              <ChevronRight size={17} />
            </button>
          </li>
        ))}
      </ol>

      <div className="itinerary-replace" aria-label="更换游线">
        <span>换一种走法</span>
        {[
          ["亲子轻松", "带孩子的轻松路线"],
          ["文化深游", "历史文化深度路线"],
          ["自然慢游", "自然风光慢游路线"]
        ].map(([label, interest]) => (
          <button type="button" key={label} onClick={() => onReplace(interest)}>{label}</button>
        ))}
      </div>
    </section>
  );
}
