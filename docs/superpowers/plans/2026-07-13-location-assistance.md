# 游线内定位辅助 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有“当前游线”面板内实现按需开启、可停止、可降级的定位辅助；GPS 不可靠或不可用时，游客仍可通过手动地标或现有相机识景继续导览。

**Architecture:** `TouristExperience` 只协调定位会话与现有问答、游线和相机链路；`useVisitorLocation` 独占浏览器 Geolocation 生命周期，`locationMath` 承担可单测的精度、距离、陈旧和跳点判断。生产坐标注册表默认空，不猜测景点坐标；后端只接收游客确认的可选 `start_spot_id`，并且只从固定预设游线中该站继续展示。

**Tech Stack:** Next.js 15、React 19、TypeScript 5.6、浏览器 Geolocation API、Node.js 22 内置 test runner、FastAPI、Pydantic、Python unittest。

## Global Constraints

- 功能名称统一为“定位辅助”，只能出现在现有“当前游线”面板，不新增游客页面、真实地图页或导航层级。
- 本计划必须在 `2026-07-13-visitor-demo-polish.md` 完成后执行；修改 `TouristExperience.tsx` 时保留已落地的 `GuideStatus`、数字人 benchmark、分段 TTS 和 WebRTC session 逻辑。
- 页面首次打开不得请求位置权限；只有游客点击“开启定位”后才能调用 `watchPosition`。
- 精度阈值固定为：`<= 50m` 可产生待确认景点建议，`50m < accuracy <= 150m` 为大致位置，`> 150m` 为弱信号；首次请求超时固定为 `8_000ms`。
- 手动地标优先级最高；GPS 恢复只能显示待确认建议，不能静默覆盖手动确认结果。
- `map_x / map_y` 继续只用于现有示意图排版，禁止参与经纬度、距离或最近点计算。
- `data/spot-coordinates.json` 默认必须是空数组；没有来源核验的坐标不得进入生产注册表。
- 原始经纬度只能保存在当前浏览器内存，禁止写入 localStorage、问答日志、后台、Qwen 请求或任何验收报告。
- 后端只允许收到游客已确认的 `spot_id`；没有道路拓扑时不得声称最短路径、实时导航、自动绕行、转弯提示或预计到达时间。
- `location-demo` 只允许 `weak / denied / timeout`，页面必须显示“模拟场景”，模拟结果不得混入真实现场证据。
- 真实手机 Geolocation 验收必须使用 HTTPS 安全来源；局域网 HTTP 页面只能验证不可用降级，不能作为真实 GPS 证据。
- GPS、问答、Vivo TTS、OpenTalking WebRTC 和数字人互不依赖；定位失败不得清空游线或中断已有讲解。
- 不新增前端测试依赖；使用当前 Node.js 22.14.0 的 `--experimental-strip-types` 和内置 test runner。
- 当前工作区按非 Git 工作区处理，本计划不包含提交步骤。

---

## File Map

**Create**

- `data/spot-coordinates.json`：独立、可审计的生产坐标注册表；本轮保持空数组。
- `lib/locationMath.ts`：精度分级、Haversine、最近核验点、注册表校验、陈旧位置、异常跳点和演示参数解析。
- `lib/spotCoordinates.ts`：装载并校验生产坐标注册表。
- `components/useVisitorLocation.ts`：按需权限、`watchPosition`、8 秒超时、陈旧计时、停止监听、手动优先和演示模式。
- `components/LocationAssist.tsx`：定位辅助条与异常提示的纯展示组件。
- `scripts/tests/location-math.test.mjs`：定位纯函数测试；测试文件本身不进入 `tsc`，被测的 `lib/locationMath.ts` 仍由 `tsc` 检查。
- `scripts/tests/visitor-location-contract.test.mjs`：浏览器生命周期、隐私、组件顺序和文案的静态契约测试。
- `backend/tests/test_route_plan_start_spot.py`：`start_spot_id` 兼容与固定游线截取测试。

**Modify**

- `lib/types.ts:51-72`：增加定位域类型和 `RoutePlanRequest`，不改现有 `RoutePlan` 响应结构。
- `tsconfig.json`：允许 no-emit 检查中的显式 `.ts` 类型导入，兼容 Node 原生 TypeScript stripping。
- `package.json:5-23`：增加两个定位测试命令。
- `components/ItineraryPanel.tsx:22-130`：定位辅助、手动地标、当前/下一站语义；仍不访问浏览器 API。
- `components/TouristExperience.tsx:21,179,319-328,357-407,1314-1353,1531-1540`：接入 hook、演示参数、相机降级和确认起点。
- `app/globals.css:949-1232,2648-2760`：定位条、异常提示和移动端布局。
- `scripts/audit-tourist-flow.mjs:1-128`：定位边界和隐私静态审计。
- `scripts/audit-tourist-copy.mjs:5-8`：把新游客组件纳入可见文案扫描。
- `backend/server/schemas.py:15-17`：路线请求增加可选 `start_spot_id`。
- `backend/server/main.py:407-447`：固定路线从已确认站点继续。
- `scripts/self-check.mjs:163-253`：把两个定位测试纳入离线回归。
- `README.md`：增加定位演示入口、隐私和能力边界。

---

### Task 1: 定位类型、空注册表与纯函数

**Files:**
- Create: `data/spot-coordinates.json`
- Create: `lib/locationMath.ts`
- Create: `lib/spotCoordinates.ts`
- Create: `scripts/tests/location-math.test.mjs`
- Modify: `lib/types.ts:51-72`
- Modify: `tsconfig.json`
- Modify: `package.json:5-23`

**Interfaces:**
- Produces: `VisitorLocationState`、`LocationObservation`、`SpotCoordinate`、`RoutePlanRequest`。
- Produces: `classifyAccuracy`、`haversineDistanceMeters`、`isObservationStale`、`isAbnormalLocationJump`、`validateSpotCoordinateRegistry`、`findNearestVerifiedSpot`、`parseLocationDemoScenario`。
- Produces: `VERIFIED_SPOT_COORDINATES: readonly SpotCoordinate[]`。

- [ ] **Step 1: Write the failing pure-function tests**

Create `scripts/tests/location-math.test.mjs`:

```ts
import assert from "node:assert/strict";
import test from "node:test";
import {
  classifyAccuracy,
  findNearestVerifiedSpot,
  haversineDistanceMeters,
  isAbnormalLocationJump,
  isObservationStale,
  parseLocationDemoScenario,
  validateSpotCoordinateRegistry
} from "../../lib/locationMath.ts";

test("classifies exact 50m and 150m boundaries", () => {
  assert.equal(classifyAccuracy(50), "precise");
  assert.equal(classifyAccuracy(50.01), "approximate");
  assert.equal(classifyAccuracy(150), "approximate");
  assert.equal(classifyAccuracy(150.01), "weak");
  assert.equal(classifyAccuracy(null), "unknown");
});

test("only matches a verified point inside its arrival radius", () => {
  const spots = [{
    spot_id: "TEST-001",
    latitude: 31,
    longitude: 120,
    coordinate_system: "WGS84",
    arrival_radius_m: 60,
    source: "unit-test fixture"
  }];
  assert.equal(findNearestVerifiedSpot(
    { latitude: 31.0002, longitude: 120 },
    spots,
    "WGS84"
  )?.spot.spot_id, "TEST-001");
  assert.equal(findNearestVerifiedSpot(
    { latitude: 31.002, longitude: 120 },
    spots,
    "WGS84"
  ), null);
  assert(haversineDistanceMeters(
    { latitude: 0, longitude: 0 },
    { latitude: 0.001, longitude: 0 }
  ) > 110);
});

test("disables missing and mismatched registries", () => {
  assert.deepEqual(validateSpotCoordinateRegistry([], "WGS84"), {
    spots: [],
    usable: false,
    errors: []
  });
  const mismatch = validateSpotCoordinateRegistry([{
    spot_id: "TEST-VALID",
    latitude: 31,
    longitude: 120,
    coordinate_system: "WGS84",
    arrival_radius_m: 60,
    source: "unit-test fixture"
  }, {
    spot_id: "TEST-001",
    latitude: 31,
    longitude: 120,
    coordinate_system: "GCJ02",
    arrival_radius_m: 60,
    source: "unit-test fixture"
  }], "WGS84");
  assert.equal(mismatch.usable, false);
  assert.deepEqual(mismatch.spots, []);
  assert(mismatch.errors.some((item) => item.includes("coordinate_system")));
});

test("detects stale fixes and implausible jumps", () => {
  assert.equal(isObservationStale(1_000, 31_001, 30_000), true);
  assert.equal(isObservationStale(1_000, 31_000, 30_000), false);
  assert.equal(isObservationStale(null, 31_001, 30_000), false);
  const previous = { latitude: 31, longitude: 120, accuracy_m: 10, observed_at: 1_000 };
  assert.equal(isAbnormalLocationJump(previous, {
    latitude: 31.005,
    longitude: 120,
    accuracy_m: 10,
    observed_at: 6_000
  }), true);
  assert.equal(isAbnormalLocationJump(previous, {
    latitude: 31.00002,
    longitude: 120,
    accuracy_m: 10,
    observed_at: 6_000
  }), false);
});

test("only accepts explicit demo scenarios", () => {
  assert.equal(parseLocationDemoScenario("weak"), "weak");
  assert.equal(parseLocationDemoScenario("denied"), "denied");
  assert.equal(parseLocationDemoScenario("timeout"), "timeout");
  assert.equal(parseLocationDemoScenario("real"), null);
});
```

- [ ] **Step 2: Run tests and confirm red**

Run: `node --experimental-strip-types --test scripts/tests/location-math.test.mjs`  
Expected: FAIL with `ERR_MODULE_NOT_FOUND` for `lib/locationMath.ts`.

- [ ] **Step 3: Add exact domain types**

Append to `lib/types.ts` after `RoutePlan`:

```ts
export type LocationSource = "gps" | "manual" | "camera" | "none";
export type LocationStatus =
  | "idle" | "requesting" | "confirmed" | "uncertain"
  | "denied" | "unavailable" | "stale";
export type LocationDemoScenario = "weak" | "denied" | "timeout";
export type LocationAccuracyBand = "precise" | "approximate" | "weak" | "unknown";
export type CoordinateSystem = "WGS84" | "GCJ02" | "BD09";

export type VisitorLocationState = {
  source: LocationSource;
  status: LocationStatus;
  accuracy_m: number | null;
  current_spot_id: string | null;
  observed_at: number | null;
};

export type GeoPoint = { latitude: number; longitude: number };
export type LocationObservation = GeoPoint & {
  accuracy_m: number;
  observed_at: number;
};
export type SpotCoordinate = GeoPoint & {
  spot_id: string;
  coordinate_system: CoordinateSystem;
  arrival_radius_m: number;
  source: string;
};
export type RoutePlanRequest = { interest: string; start_spot_id?: string };
```

- [ ] **Step 4: Implement the pure functions and empty registry**

Create `data/spot-coordinates.json`:

```json
[]
```

Create `lib/locationMath.ts`:

```ts
import type {
  CoordinateSystem, GeoPoint, LocationAccuracyBand,
  LocationDemoScenario, LocationObservation, SpotCoordinate
} from "./types.ts";

export const LOCATION_REQUEST_TIMEOUT_MS = 8_000;
export const LOCATION_STALE_AFTER_MS = 30_000;
const EARTH_RADIUS_M = 6_371_000;

export function classifyAccuracy(value: number | null): LocationAccuracyBand {
  if (value === null || !Number.isFinite(value) || value < 0) return "unknown";
  if (value <= 50) return "precise";
  if (value <= 150) return "approximate";
  return "weak";
}

const radians = (value: number) => value * Math.PI / 180;

export function haversineDistanceMeters(a: GeoPoint, b: GeoPoint): number {
  const lat = radians(b.latitude - a.latitude);
  const lon = radians(b.longitude - a.longitude);
  const first = radians(a.latitude);
  const second = radians(b.latitude);
  const value = Math.sin(lat / 2) ** 2
    + Math.cos(first) * Math.cos(second) * Math.sin(lon / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.sqrt(value));
}

export function isObservationStale(
  observedAt: number | null,
  now: number,
  staleAfterMs = LOCATION_STALE_AFTER_MS
): boolean {
  return observedAt !== null && now - observedAt > staleAfterMs;
}

export function isAbnormalLocationJump(
  previous: LocationObservation | null,
  next: LocationObservation
): boolean {
  if (!previous) return false;
  const elapsedMs = next.observed_at - previous.observed_at;
  if (elapsedMs <= 0 || elapsedMs > 30_000) return false;
  const distance = haversineDistanceMeters(previous, next);
  const uncertainty = Math.max(
    200,
    2 * (Math.max(0, previous.accuracy_m) + Math.max(0, next.accuracy_m))
  );
  return distance > uncertainty && distance / (elapsedMs / 1_000) > 15;
}

export function validateSpotCoordinateRegistry(
  value: unknown,
  expectedSystem: CoordinateSystem = "WGS84"
): { spots: SpotCoordinate[]; usable: boolean; errors: string[] } {
  if (!Array.isArray(value)) {
    return { spots: [], usable: false, errors: ["registry must be an array"] };
  }
  const spots: SpotCoordinate[] = [];
  const errors: string[] = [];
  value.forEach((entry, index) => {
    const item = entry as Partial<SpotCoordinate>;
    const valid = typeof item.spot_id === "string"
      && item.spot_id.trim().length > 0
      && Number.isFinite(item.latitude) && Number(item.latitude) >= -90 && Number(item.latitude) <= 90
      && Number.isFinite(item.longitude) && Number(item.longitude) >= -180 && Number(item.longitude) <= 180
      && item.coordinate_system === expectedSystem
      && Number.isFinite(item.arrival_radius_m) && Number(item.arrival_radius_m) > 0
      && typeof item.source === "string" && item.source.trim().length > 0;
    if (valid) spots.push(item as SpotCoordinate);
    else errors.push(`entry ${index} has invalid fields or coordinate_system`);
  });
  const usable = spots.length > 0 && errors.length === 0;
  return { spots: usable ? spots : [], usable, errors };
}

export function findNearestVerifiedSpot(
  point: GeoPoint,
  spots: readonly SpotCoordinate[],
  system: CoordinateSystem = "WGS84"
): { spot: SpotCoordinate; distance_m: number } | null {
  const nearest = spots
    .filter((spot) => spot.coordinate_system === system)
    .map((spot) => ({ spot, distance_m: haversineDistanceMeters(point, spot) }))
    .sort((a, b) => a.distance_m - b.distance_m)[0];
  return nearest && nearest.distance_m <= nearest.spot.arrival_radius_m ? nearest : null;
}

export function parseLocationDemoScenario(value: string | null): LocationDemoScenario | null {
  return value === "weak" || value === "denied" || value === "timeout" ? value : null;
}
```

Create `lib/spotCoordinates.ts`:

```ts
import rawCoordinates from "@/data/spot-coordinates.json";
import { validateSpotCoordinateRegistry } from "./locationMath";

const registry = validateSpotCoordinateRegistry(rawCoordinates, "WGS84");
export const VERIFIED_SPOT_COORDINATES = registry.spots;
export const SPOT_COORDINATE_REGISTRY_USABLE = registry.usable;
export const SPOT_COORDINATE_REGISTRY_ERRORS = registry.errors;
```

在 `tsconfig.json` 的 `compilerOptions` 增加：

```json
"allowImportingTsExtensions": true
```

该选项只在当前 `noEmit: true` 类型检查下启用，不改变 Next.js 的生产打包输出。

- [ ] **Step 5: Add scripts and confirm green**

Add to `package.json`:

```json
"location-test": "node --experimental-strip-types --test scripts/tests/location-math.test.mjs",
"location-contract:test": "node --test scripts/tests/visitor-location-contract.test.mjs"
```

Run: `npm run location-test`  
Expected: PASS, 5 tests, 0 failures.

Run: `npm run typecheck`  
Expected: exit 0 with no diagnostics.

---

### Task 2: 按需浏览器定位、手动优先与演示状态机

**Files:**
- Create: `components/useVisitorLocation.ts`
- Create: `scripts/tests/visitor-location-contract.test.mjs`

**Interfaces:**
- Consumes: Task 1 types and math.
- Produces:

```ts
type UseVisitorLocationResult = {
  state: VisitorLocationState;
  suggestedSpotId: string | null;
  isWatching: boolean;
  isSimulated: boolean;
  startLocation(): void;
  stopLocation(): void;
  beginCameraAssist(): void;
  confirmSuggestedSpot(): void;
  confirmSpot(spotId: string): void;
  dismissSuggestion(): void;
};
```

Hook options must include `eligibleSpotIds: readonly string[]`; nearest-point matching is limited to the active route so every candidate can be named in the UI and accepted by the fixed-route backend.

- [ ] **Step 1: Write failing lifecycle/privacy contracts**

Create `scripts/tests/visitor-location-contract.test.mjs`:

```js
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import test from "node:test";

const hookPath = new URL("../../components/useVisitorLocation.ts", import.meta.url);

test("permission is opt-in and watcher cleanup is explicit", () => {
  assert.equal(existsSync(hookPath), true);
  const hook = readFileSync(hookPath, "utf-8");
  assert.match(hook, /status:\s*"idle"/);
  assert.match(hook, /const startLocation = useCallback/);
  assert.match(hook, /navigator\.geolocation\.watchPosition/);
  assert.match(hook, /navigator\.geolocation\.clearWatch/);
  assert.match(hook, /window\.isSecureContext/);
  const effects = [...hook.matchAll(/useEffect\(([\s\S]*?)\n\s*\},\s*\[[^\]]*\]\);/g)]
    .map((match) => match[1]);
  assert.equal(effects.some((body) => body.includes("watchPosition(")), false);
});

test("raw coordinates are not persisted or posted", () => {
  const hook = readFileSync(hookPath, "utf-8");
  assert.doesNotMatch(hook, /localStorage|sessionStorage|apiPost|fetch\(/);
  assert.match(hook, /previousObservationRef/);
  assert.match(hook, /clearResources/);
  assert.match(hook, /eligibleSpotIds/);
  assert.match(hook, /eligibleCoordinates/);
});

test("required failure and demo states exist", () => {
  const hook = readFileSync(hookPath, "utf-8");
  for (const value of ["requesting", "uncertain", "denied", "unavailable", "stale"]) {
    assert(hook.includes(`"${value}"`), value);
  }
  for (const value of ["weak", "denied", "timeout"]) {
    assert(hook.includes(`"${value}"`), value);
  }
  assert.match(hook, /beginCameraAssist/);
  assert.match(hook, /source:\s*"manual"/);
});
```

- [ ] **Step 2: Run and confirm red**

Run: `npm run location-contract:test`  
Expected: FAIL because `components/useVisitorLocation.ts` does not exist.

- [ ] **Step 3: Implement this exact transition table**

| Event | Result |
|---|---|
| Initial render | `none / idle`; no permission request |
| User starts | `gps / requesting`; retain an existing confirmed spot |
| No result after 8 seconds | `gps / uncertain`; stop watcher |
| Permission denied | `none / denied`, unless manual confirmation exists |
| Insecure page, unsupported or position unavailable | `none / unavailable`, unless manual confirmation exists |
| Accuracy above 150m | `gps / uncertain`; no candidate |
| Accuracy 50–150m | `gps / uncertain`; no route change |
| Accuracy at most 50m + verified radius match | `gps / uncertain` plus `suggestedSpotId` |
| User confirms suggestion | `gps / confirmed` plus `current_spot_id` |
| Manual landmark | stop watcher; `manual / confirmed` |
| Camera begins | stop watcher; use `camera / uncertain` only when no spot is confirmed, otherwise preserve the confirmed spot while opening the camera |
| Landmark selected after camera | `manual / confirmed`; camera only assists the question and never invents a structured spot result |
| Fix older than 30 seconds | `gps / stale`; retain confirmed spot id |
| Abnormal jump | `gps / uncertain`; never overwrite confirmed spot |
| Stop | clear watcher/timers; preserve confirmed spot, otherwise idle |

Create `components/useVisitorLocation.ts`. The implementation must contain these exact lifecycle blocks:

```ts
"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  classifyAccuracy, findNearestVerifiedSpot, isAbnormalLocationJump,
  LOCATION_REQUEST_TIMEOUT_MS, LOCATION_STALE_AFTER_MS
} from "@/lib/locationMath";
import type {
  LocationDemoScenario, LocationObservation,
  SpotCoordinate, VisitorLocationState
} from "@/lib/types";

const INITIAL_STATE: VisitorLocationState = {
  source: "none", status: "idle", accuracy_m: null,
  current_spot_id: null, observed_at: null
};

export function useVisitorLocation({
  coordinates,
  eligibleSpotIds,
  demoScenario = null,
  timeoutMs = LOCATION_REQUEST_TIMEOUT_MS,
  staleAfterMs = LOCATION_STALE_AFTER_MS
}: {
  coordinates: readonly SpotCoordinate[];
  eligibleSpotIds: readonly string[];
  demoScenario?: LocationDemoScenario | null;
  timeoutMs?: number;
  staleAfterMs?: number;
}) {
  const [state, setState] = useState(INITIAL_STATE);
  const [suggestedSpotId, setSuggestedSpotId] = useState<string | null>(null);
  const [isWatching, setIsWatching] = useState(false);
  const watchIdRef = useRef<number | null>(null);
  const requestTimerRef = useRef<number | null>(null);
  const staleTimerRef = useRef<number | null>(null);
  const previousObservationRef = useRef<LocationObservation | null>(null);
  const eligibleCoordinates = useMemo(
    () => coordinates.filter((spot) => eligibleSpotIds.includes(spot.spot_id)),
    [coordinates, eligibleSpotIds]
  );
  const eligibleCoordinatesRef = useRef<readonly SpotCoordinate[]>(eligibleCoordinates);

  useEffect(() => {
    eligibleCoordinatesRef.current = eligibleCoordinates;
  }, [eligibleCoordinates]);

  const clearResources = useCallback(() => {
    if (watchIdRef.current !== null && typeof navigator !== "undefined" && navigator.geolocation) {
      navigator.geolocation.clearWatch(watchIdRef.current);
    }
    watchIdRef.current = null;
    if (requestTimerRef.current !== null) window.clearTimeout(requestTimerRef.current);
    if (staleTimerRef.current !== null) window.clearTimeout(staleTimerRef.current);
    requestTimerRef.current = null;
    staleTimerRef.current = null;
  }, []);

  const stopLocation = useCallback(() => {
    clearResources();
    setIsWatching(false);
    setState((current) => current.current_spot_id
      ? { ...current, status: "confirmed" }
      : INITIAL_STATE);
  }, [clearResources]);

  const startLocation = useCallback(() => {
    clearResources();
    previousObservationRef.current = null;
    setSuggestedSpotId(null);
    setIsWatching(true);
    setState((current) => current.source === "manual" && current.status === "confirmed"
      ? current
      : { ...current, source: "gps", status: "requesting", accuracy_m: null, observed_at: null });

    const finish = (status: "uncertain" | "denied" | "unavailable") => {
      clearResources();
      setIsWatching(false);
      setState((current) => current.status === "confirmed" && current.current_spot_id
        ? current
        : { ...INITIAL_STATE, source: status === "uncertain" ? "gps" : "none", status });
    };

    if (demoScenario) {
      requestTimerRef.current = window.setTimeout(() => {
        if (demoScenario === "weak") {
          setState((current) => current.source === "manual" ? current : {
            source: "gps", status: "uncertain", accuracy_m: 180,
            current_spot_id: current.current_spot_id, observed_at: Date.now()
          });
          setIsWatching(false);
        } else {
          finish(demoScenario === "denied" ? "denied" : "uncertain");
        }
      }, demoScenario === "timeout" ? timeoutMs : 350);
      return;
    }

    if (typeof window === "undefined" || !window.isSecureContext
      || typeof navigator === "undefined" || !navigator.geolocation) {
      finish("unavailable");
      return;
    }
    requestTimerRef.current = window.setTimeout(() => finish("uncertain"), timeoutMs);
    watchIdRef.current = navigator.geolocation.watchPosition((position) => {
      if (requestTimerRef.current !== null) window.clearTimeout(requestTimerRef.current);
      requestTimerRef.current = null;
      const observation: LocationObservation = {
        latitude: position.coords.latitude,
        longitude: position.coords.longitude,
        accuracy_m: position.coords.accuracy,
        observed_at: position.timestamp || Date.now()
      };
      const jumped = isAbnormalLocationJump(previousObservationRef.current, observation);
      previousObservationRef.current = observation;
      const candidate = !jumped && classifyAccuracy(observation.accuracy_m) === "precise"
        ? findNearestVerifiedSpot(observation, eligibleCoordinatesRef.current, "WGS84")
        : null;
      setSuggestedSpotId(candidate?.spot.spot_id ?? null);
      setState((current) => current.source === "manual" && current.status === "confirmed"
        ? current
        : {
            source: "gps",
            status: "uncertain",
            accuracy_m: observation.accuracy_m,
            current_spot_id: current.current_spot_id,
            observed_at: observation.observed_at
          });
      if (staleTimerRef.current !== null) window.clearTimeout(staleTimerRef.current);
      staleTimerRef.current = window.setTimeout(() => {
        setState((current) => current.source === "manual" ? current : { ...current, status: "stale" });
      }, staleAfterMs);
    }, (error) => {
      finish(error.code === error.PERMISSION_DENIED
        ? "denied"
        : error.code === error.TIMEOUT ? "uncertain" : "unavailable");
    }, { enableHighAccuracy: true, timeout: timeoutMs, maximumAge: 10_000 });
  }, [clearResources, demoScenario, staleAfterMs, timeoutMs]);

  const confirmSuggestedSpot = useCallback(() => {
    if (!suggestedSpotId) return;
    clearResources();
    setIsWatching(false);
    setState((current) => ({
      ...current, source: "gps", status: "confirmed",
      current_spot_id: suggestedSpotId
    }));
    setSuggestedSpotId(null);
  }, [clearResources, suggestedSpotId]);

  const confirmSpot = useCallback((spotId: string) => {
    clearResources();
    setIsWatching(false);
    setSuggestedSpotId(null);
    setState({
      source: "manual", status: "confirmed", accuracy_m: null,
      current_spot_id: spotId, observed_at: Date.now()
    });
  }, [clearResources]);

  const beginCameraAssist = useCallback(() => {
    clearResources();
    setIsWatching(false);
    setSuggestedSpotId(null);
    setState((current) => current.current_spot_id
      ? current
      : { ...INITIAL_STATE, source: "camera", status: "uncertain" });
  }, [clearResources]);

  useEffect(() => () => clearResources(), [clearResources]);

  return {
    state, suggestedSpotId, isWatching, isSimulated: demoScenario !== null,
    startLocation, stopLocation, beginCameraAssist, confirmSuggestedSpot, confirmSpot,
    dismissSuggestion: () => setSuggestedSpotId(null)
  };
}
```

- [ ] **Step 4: Run hook contract and typecheck**

Run: `npm run location-contract:test`  
Expected: PASS, 3 tests.

Run: `npm run typecheck`  
Expected: exit 0.

---

### Task 3: 定位条、异常提示与站点语义

**Files:**
- Create: `components/LocationAssist.tsx`
- Modify: `components/ItineraryPanel.tsx:3-130`
- Modify: `app/globals.css:949-1232,2648-2760`
- Modify: `scripts/tests/visitor-location-contract.test.mjs`
- Modify: `scripts/audit-tourist-copy.mjs:5-8`

**Interfaces:**
- Consumes: `VisitorLocationState`, `RouteStep[]`, Task 2 callbacks.
- Produces: `LocationAssistBar` and `LocationAssistNotice`; neither accesses `navigator`.
- Produces: `ItineraryPanelProps` with location and existing route callbacks.

- [ ] **Step 1: Add failing UI contracts**

Append:

```js
test("itinerary keeps required location order and has no geolocation API", () => {
  const itinerary = readFileSync(new URL(
    "../../components/ItineraryPanel.tsx", import.meta.url
  ), "utf-8");
  assert.doesNotMatch(itinerary, /navigator|geolocation|latitude|longitude|distance_m/);
  const order = [
    "itinerary-heading", "<LocationAssistBar", "itinerary-map",
    "<LocationAssistNotice", "current-stop", "itinerary-stops", "itinerary-replace"
  ].map((token) => itinerary.indexOf(token));
  assert(order.every((index) => index >= 0));
  assert.deepEqual([...order].sort((a, b) => a - b), order);
  for (const copy of ["已到达 ·", "下一站 · 第", "正在查看 · 第"]) {
    assert(itinerary.includes(copy), copy);
  }
});

test("manual and camera fallbacks never show fake distance", () => {
  const assist = readFileSync(new URL(
    "../../components/LocationAssist.tsx", import.meta.url
  ), "utf-8");
  for (const copy of [
    "开启定位，查看附近景点", "正在确认你的位置…",
    "当前位置不够准确，请选择一个你看得到的地标。",
    "未开启位置权限，也可以继续导览。",
    "选择附近地标", "相机识景", "模拟场景"
  ]) assert(assist.includes(copy), copy);
  assert.doesNotMatch(assist, /distance_m|米外|距离你/);
  assert.match(assist, /useEffect\(\(\) => setManualSpotId\(""\), \[props\.steps\]\)/);
  assert.match(assist, /manualSpotValid/);
  assert.match(assist, /isRouteContinuationPending/);
});
```

Run: `npm run location-contract:test`  
Expected: FAIL because the presentation component and props are absent.

- [ ] **Step 2: Create the pure presentation component**

Create `components/LocationAssist.tsx`:

```tsx
"use client";

import { useEffect, useMemo, useState } from "react";
import { Camera, LocateFixed, MapPin, Square } from "lucide-react";
import type { RouteStep, VisitorLocationState } from "@/lib/types";

type LocationAssistProps = {
  state: VisitorLocationState;
  steps: RouteStep[];
  suggestedSpotId: string | null;
  isWatching: boolean;
  isSimulated: boolean;
  isRouteContinuationPending: boolean;
  onStart(): void;
  onStop(): void;
  onConfirmSuggestion(): void;
  onConfirmSpot(spotId: string): void;
  onOpenCamera(): void;
};

function spotName(steps: RouteStep[], spotId: string | null) {
  return steps.find((step) => step.spot_id === spotId)?.name || "";
}

function summary(
  state: VisitorLocationState,
  steps: RouteStep[],
  isWatching: boolean
) {
  const currentName = spotName(steps, state.current_spot_id);
  if (isWatching) {
    return currentName
      ? `正在重新定位，仍按“${currentName}”继续`
      : "正在确认你的位置…";
  }
  if (state.status === "confirmed" && currentName) {
    if (state.source === "manual") return `已按“${currentName}”作为当前位置继续导览。`;
    return `已确认“${currentName}”为当前位置。`;
  }
  if (state.status === "idle") return "开启定位，查看附近景点";
  if (state.status === "denied") return "位置权限未开启";
  if (state.status === "unavailable") return "当前环境无法定位";
  if (state.status === "stale") return "位置需要更新";
  if (state.status === "uncertain" && state.accuracy_m !== null
    && state.accuracy_m <= 50) {
    return "已获取位置，请选择眼前地标确认";
  }
  if (state.status === "uncertain" && state.accuracy_m !== null
    && state.accuracy_m > 50 && state.accuracy_m <= 150) {
    return "已获取大致位置，请选择眼前地标确认";
  }
  return "位置需要你确认";
}

export function LocationAssistBar(props: LocationAssistProps) {
  const [manualSpotId, setManualSpotId] = useState("");
  useEffect(() => setManualSpotId(""), [props.steps]);
  const manualSpotValid = props.steps.some((step) => step.spot_id === manualSpotId);
  const suggestedName = useMemo(
    () => spotName(props.steps, props.suggestedSpotId),
    [props.steps, props.suggestedSpotId]
  );
  return (
    <section className="location-assist-bar" data-location-status={props.state.status}>
      <div className="location-assist-summary">
        <MapPin size={17} />
        <div>
          <span>定位辅助 {props.isSimulated ? <em>模拟场景</em> : null}</span>
          <strong aria-live="polite" aria-atomic="true">
            {props.isRouteContinuationPending
              ? "正在从此处续接游线…"
              : summary(props.state, props.steps, props.isWatching)}
          </strong>
        </div>
      </div>
      <div className="location-assist-actions">
        {props.isWatching ? (
          <button type="button" disabled={props.isRouteContinuationPending} onClick={props.onStop}>
            <Square size={15} />停止定位
          </button>
        ) : (
          <button type="button" disabled={props.isRouteContinuationPending} onClick={props.onStart}>
            <LocateFixed size={15} />
            {props.state.status === "idle" ? "开启定位" : "重新定位"}
          </button>
        )}
        <label>
          <span>选择附近地标</span>
          <select
            disabled={props.isRouteContinuationPending}
            value={manualSpotId}
            onChange={(event) => setManualSpotId(event.target.value)}
          >
            <option value="">选择你看得到的景点</option>
            {props.steps.map((step) => (
              <option key={step.spot_id} value={step.spot_id}>{step.name}</option>
            ))}
          </select>
        </label>
        <button
          type="button"
          disabled={!manualSpotValid || props.isRouteContinuationPending}
          onClick={() => {
            if (manualSpotValid) props.onConfirmSpot(manualSpotId);
          }}
        >
          按此地标继续
        </button>
        <button type="button" disabled={props.isRouteContinuationPending} onClick={props.onOpenCamera}>
          <Camera size={15} />相机识景
        </button>
      </div>
      {suggestedName ? (
        <div className="location-suggestion">
          <span>附近可能是“{suggestedName}”，请确认后再更新当前位置。</span>
          <button type="button" disabled={props.isRouteContinuationPending} onClick={props.onConfirmSuggestion}>确认这个景点</button>
        </div>
      ) : null}
    </section>
  );
}

export function LocationAssistNotice({ state }: { state: VisitorLocationState }) {
  const message = state.status === "denied"
    ? "未开启位置权限，也可以继续导览。"
    : state.status === "unavailable"
      ? "当前设备或页面连接无法定位，请选择你所在的景点。"
      : state.status === "stale"
        ? "位置已有一段时间未更新，请重新定位或选择地标。"
        : state.status === "uncertain"
          && (state.accuracy_m === null || state.accuracy_m > 150)
          ? "当前位置不够准确，请选择一个你看得到的地标。"
          : "";
  return message
    ? <p className="location-assist-notice" role="status">{message}</p>
    : null;
}
```

- [ ] **Step 3: Wire ItineraryPanel in fixed information order**

Add this exact prop type:

```tsx
type ItineraryPanelProps = {
  plan: RoutePlan;
  locationState: VisitorLocationState;
  suggestedSpotId: string | null;
  isLocationWatching: boolean;
  isLocationSimulated: boolean;
  isRouteContinuationPending: boolean;
  onStartLocation(): void;
  onStopLocation(): void;
  onConfirmSuggestedSpot(): void;
  onConfirmSpot(spotId: string): void;
  onOpenCameraRecognition(): void;
  onCloseRoute(): void;
  onNarrateStop(step: RouteStep): void;
  onReplace(interest: string): void;
};
```

Compute:

```tsx
const confirmedIndex = plan.steps.findIndex(
  (step) => step.spot_id === locationState.current_spot_id
);
const nextSpotId = confirmedIndex >= 0
  ? plan.steps[confirmedIndex + 1]?.spot_id ?? null
  : plan.steps[0]?.spot_id ?? null;
const selectedIndex = selected ? plan.steps.indexOf(selected) : -1;
const selectedLabel = selected?.spot_id === locationState.current_spot_id
  ? `已到达 · ${selected.name}`
  : selected?.spot_id === nextSpotId
    ? `下一站 · 第 ${selectedIndex + 1} 站`
    : `正在查看 · 第 ${selectedIndex + 1} 站`;
```

Replace the existing `[plan]` selection effect so a confirmed point selects the following stop when available. Render in this exact order: heading, `LocationAssistBar`, existing map, `LocationAssistNotice`, selected card, all stops, route replacement.

Use this effect and placement:

```tsx
useEffect(() => {
  const next = confirmedIndex >= 0
    ? plan.steps[confirmedIndex + 1] ?? plan.steps[confirmedIndex]
    : plan.steps[0];
  setSelectedId(next?.spot_id || "");
}, [confirmedIndex, plan]);

<LocationAssistBar
  state={locationState}
  steps={plan.steps}
  suggestedSpotId={suggestedSpotId}
  isWatching={isLocationWatching}
  isSimulated={isLocationSimulated}
  isRouteContinuationPending={isRouteContinuationPending}
  onStart={onStartLocation}
  onStop={onStopLocation}
  onConfirmSuggestion={onConfirmSuggestedSpot}
  onConfirmSpot={onConfirmSpot}
  onOpenCamera={onOpenCameraRecognition}
/>
```

Place `<LocationAssistNotice state={locationState} />` immediately after the closing tag of the existing `.itinerary-map` and before the selected `.current-stop` article.

- [ ] **Step 4: Add focused styles and copy coverage**

Add next to itinerary CSS:

```css
.location-assist-bar {
  display: grid;
  gap: 10px;
  margin-top: 14px;
  padding: 12px;
  color: var(--ink-blue);
  background: rgba(248, 245, 238, 0.9);
  border: 1px solid var(--line);
  border-radius: 12px;
}

.location-assist-summary,
.location-assist-actions,
.location-suggestion {
  display: flex;
  align-items: center;
  gap: 8px;
}

.location-assist-summary > div {
  display: grid;
  gap: 2px;
}

.location-assist-summary span {
  color: var(--ink-muted);
  font-size: 12px;
}

.location-assist-summary em {
  margin-left: 6px;
  color: var(--cinnabar);
  font-style: normal;
}

.location-assist-actions {
  flex-wrap: wrap;
}

.location-assist-actions button,
.location-assist-actions select,
.location-suggestion button {
  min-height: 36px;
  border: 1px solid var(--line-strong);
  border-radius: 9px;
}

.location-assist-actions label {
  display: flex;
  align-items: center;
  gap: 6px;
}

.location-assist-actions label > span {
  font-size: 12px;
}

.location-suggestion {
  justify-content: space-between;
  color: #385b72;
  font-size: 12px;
}

.location-assist-notice {
  margin: 10px 0 0;
  padding: 10px 12px;
  color: #77542f;
  background: #fff8e9;
  border: 1px solid rgba(212, 155, 69, 0.55);
  border-radius: 10px;
  font-size: 12px;
}

@media (max-width: 600px) {
  .location-assist-actions,
  .location-suggestion {
    align-items: stretch;
    flex-direction: column;
  }

  .location-assist-actions label {
    align-items: stretch;
    flex-direction: column;
  }

  .location-assist-actions button,
  .location-assist-actions select,
  .location-suggestion button {
    width: 100%;
    min-height: 44px;
  }

  .location-assist-summary span,
  .location-assist-actions label > span,
  .location-suggestion,
  .location-assist-notice {
    font-size: 14px;
  }
}
```

Change `scripts/audit-tourist-copy.mjs`:

```js
const files = [
  path.join(root, "components", "TouristExperience.tsx"),
  path.join(root, "components", "DigitalHuman.tsx"),
  path.join(root, "components", "ItineraryPanel.tsx"),
  path.join(root, "components", "LocationAssist.tsx")
];
```

- [ ] **Step 5: Run UI slice**

Run: `npm run location-contract:test`  
Expected: PASS, 5 tests.

Run: `npm run copy-audit`  
Expected: `tourist copy audit passed`.

Run: `npm run typecheck`  
Expected: exit 0.

---

### Task 4: TouristExperience coordination, camera fallback and privacy

**Files:**
- Modify: `components/TouristExperience.tsx:21,179,319-328,357-407,1314-1353,1531-1540`
- Modify: `scripts/tests/visitor-location-contract.test.mjs`
- Modify: `scripts/audit-tourist-flow.mjs:1-128`

**Interfaces:**
- Consumes: `useVisitorLocation`, `VERIFIED_SPOT_COORDINATES`, `parseLocationDemoScenario`, `RoutePlanRequest`.
- Produces: only confirmed `current_spot_id` as `start_spot_id`; raw coordinates do not cross this boundary.

- [ ] **Step 1: Add failing integration assertions**

Append:

```js
test("tourist shell sends confirmed spot id and reuses camera", () => {
  const tourist = readFileSync(new URL(
    "../../components/TouristExperience.tsx", import.meta.url
  ), "utf-8");
  assert.match(tourist, /useVisitorLocation/);
  assert.match(tourist, /parseLocationDemoScenario/);
  assert.match(tourist, /start_spot_id/);
  assert.match(tourist, /state\.current_spot_id/);
  assert.match(tourist, /continueRouteFromSpot/);
  assert.match(tourist, /routeContinuationRunIdRef/);
  assert.match(tourist, /locationRoutePending/);
  assert.match(tourist, /eligibleLocationSpotIds/);
  assert.match(tourist, /beginCameraAssist/);
  assert.match(tourist, /toggleCamera/);
  assert.doesNotMatch(tourist, /latitude:\s*visitorLocation|longitude:\s*visitorLocation/);
});
```

Run: `npm run location-contract:test`  
Expected: FAIL because `TouristExperience` does not consume the hook.

- [ ] **Step 2: Add hook creation and explicit demo parsing**

Add imports and instantiate:

```tsx
import { parseLocationDemoScenario } from "@/lib/locationMath";
import { VERIFIED_SPOT_COORDINATES } from "@/lib/spotCoordinates";
import type { LocationDemoScenario, RoutePlanRequest } from "@/lib/types";
import { useVisitorLocation } from "./useVisitorLocation";

const [locationDemoScenario, setLocationDemoScenario] =
  useState<LocationDemoScenario | null>(null);
const [locationRoutePending, setLocationRoutePending] = useState(false);
const routeContinuationRunIdRef = useRef(0);

const eligibleLocationSpotIds = useMemo(
  () => visibleRoutePlan?.steps.map((step) => step.spot_id) ?? [],
  [visibleRoutePlan]
);

useEffect(() => {
  setLocationDemoScenario(parseLocationDemoScenario(
    new URLSearchParams(window.location.search).get("location-demo")
  ));
}, []);

const visitorLocation = useVisitorLocation({
  coordinates: VERIFIED_SPOT_COORDINATES,
  eligibleSpotIds: eligibleLocationSpotIds,
  demoScenario: locationDemoScenario
});
```

Do not add `visitorLocation` to the existing localStorage message effect.

- [ ] **Step 3: Send only confirmed spot id**

Replace the route payload:

```tsx
const routePayload: RoutePlanRequest = {
  interest: trimmed,
  start_spot_id: visitorLocation.state.current_spot_id ?? undefined
};
if (routeRequested) {
  routeContinuationRunIdRef.current += 1;
  setLocationRoutePending(false);
}
const routePromise = routeRequested
  ? apiPost<RoutePlan>("/api/route-plan", routePayload).catch(() => null)
  : Promise.resolve(null);
```

`current_spot_id` 只会由 `confirmSuggestedSpot` 或 `confirmSpot` 写入，因此在位置变旧或游客重新定位期间仍可安全保留这个已经确认的站点。再增加即时续接函数，确保游客确认地标后不必重新提问路线：

```tsx
async function continueRouteFromSpot(spotId: string) {
  if (!activeRoutePlan) return;
  const requestId = routeContinuationRunIdRef.current + 1;
  routeContinuationRunIdRef.current = requestId;
  setLocationRoutePending(true);
  try {
    const nextPlan = await apiPost<RoutePlan>("/api/route-plan", {
      interest: activeRoutePlan.interest,
      start_spot_id: spotId
    } satisfies RoutePlanRequest).catch(() => null);
    if (requestId !== routeContinuationRunIdRef.current) return;
    if (!nextPlan?.steps?.length) return;
    setVisibleRoutePlan(nextPlan);
    setGuideMode("itinerary");
  } finally {
    if (requestId === routeContinuationRunIdRef.current) {
      setLocationRoutePending(false);
    }
  }
}
```

- [ ] **Step 4: Reuse existing camera and pass location props**

Add:

```tsx
function openCameraRecognition() {
  visitorLocation.beginCameraAssist();
  setGuideMode("conversation");
  setToolsOpen(true);
  setQuestion("请帮我识别眼前的景点");
  if (!cameraStreamRef.current) void toggleCamera();
}
```

Pass every Task 3 location prop to `ItineraryPanel`:

```tsx
<ItineraryPanel
  plan={activeRoutePlan}
  locationState={visitorLocation.state}
  suggestedSpotId={visitorLocation.suggestedSpotId}
  isLocationWatching={visitorLocation.isWatching}
  isLocationSimulated={visitorLocation.isSimulated}
  isRouteContinuationPending={locationRoutePending}
  onStartLocation={visitorLocation.startLocation}
  onStopLocation={visitorLocation.stopLocation}
  onConfirmSuggestedSpot={() => {
    const spotId = visitorLocation.suggestedSpotId;
    if (!spotId) return;
    visitorLocation.confirmSuggestedSpot();
    void continueRouteFromSpot(spotId);
  }}
  onConfirmSpot={(spotId) => {
    visitorLocation.confirmSpot(spotId);
    void continueRouteFromSpot(spotId);
  }}
  onOpenCameraRecognition={openCameraRecognition}
  onCloseRoute={closeCurrentRoute}
  onNarrateStop={(step) => {
    setGuideMode("conversation");
    void submit(`${step.name}有什么亮点？`);
  }}
  onReplace={(interest) => void submit(interest)}
/>
```

Replace `closeCurrentRoute()` with:

```tsx
function closeCurrentRoute() {
  routeContinuationRunIdRef.current += 1;
  setLocationRoutePending(false);
  visitorLocation.stopLocation();
  setVisibleRoutePlan(null);
  setGuideMode("conversation");
}
```

Do not stop GPS when switching between conversation and itinerary tabs.

- [ ] **Step 5: Extend canonical flow audit**

Read the hook, assist component and coordinate JSON in `scripts/audit-tourist-flow.mjs`, then add:

```js
assert(tourist.includes("useVisitorLocation"), "游客端未接入定位辅助 Hook。");
assert(tourist.includes("start_spot_id") && tourist.includes("state.current_spot_id") && tourist.includes("continueRouteFromSpot"), "路线请求未使用已确认景点即时续接。");
assert(tourist.includes("eligibleLocationSpotIds") && tourist.includes("eligibleSpotIds:"), "最近点匹配未限制在当前游线。");
assert(tourist.includes("routeContinuationRunIdRef") && tourist.includes("requestId !== routeContinuationRunIdRef.current") && locationAssist.includes("isRouteContinuationPending"), "游线续接缺少乱序响应保护或重复确认锁。");
assert(locationHook.includes("watchPosition") && locationHook.includes("clearWatch"), "定位监听缺少启动或清理。");
assert(locationHook.includes("eligibleSpotIds") && locationHook.includes("eligibleCoordinates"), "定位候选未限制在当前游线站点。");
assert(!locationHook.includes("localStorage") && !locationHook.includes("apiPost"), "原始定位数据存在持久化或上传风险。");
assert(!sessionHook.includes("visitorLocation"), "定位状态不应成为 OpenTalking session 依赖。");
assert(!itinerary.includes("navigator.geolocation"), "游线展示组件不应请求浏览器定位。");
assert(!locationAssist.includes("distance_m"), "未核验坐标时不应向游客展示距离。");
assert(JSON.parse(coordinateRegistry).length === 0, "生产坐标注册表本轮必须保持为空。");
```

- [ ] **Step 6: Run frontend regressions**

Run: `npm run location-contract:test`  
Expected: PASS, 6 tests.

Run: `npm run flow-audit`  
Expected: `tourist interaction flow audit passed`.

Run: `npm run copy-audit`  
Expected: `tourist copy audit passed`.

Run: `npm run typecheck`  
Expected: exit 0.

---

### Task 5: Backend optional start_spot_id without route invention

**Files:**
- Create: `backend/tests/test_route_plan_start_spot.py`
- Modify: `backend/server/schemas.py:15-17`
- Modify: `backend/server/main.py:407-447`

**Interfaces:**
- Consumes: `RoutePlanRequest.start_spot_id: str | None`.
- Produces: `_route_ids_from_start(spot_ids: list[str], start_spot_id: str | None) -> list[str]`.
- Preserves: `_make_route_plan(interest)` and `/api/chat` by defaulting `start_spot_id=None`.

- [ ] **Step 1: Write failing backend tests**

Create `backend/tests/test_route_plan_start_spot.py`:

```py
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from server import main

class RoutePlanStartSpotTests(unittest.TestCase):
    def test_absent_start_keeps_fixed_route(self) -> None:
        ids = ["LS-006", "LS-009", "LS-013", "LS-014"]
        self.assertEqual(main._route_ids_from_start(ids, None), ids)

    def test_known_start_continues_from_that_stop(self) -> None:
        ids = ["LS-006", "LS-009", "LS-013", "LS-014"]
        self.assertEqual(
            main._route_ids_from_start(ids, "LS-009"),
            ["LS-009", "LS-013", "LS-014"],
        )

    def test_unknown_start_does_not_reorder(self) -> None:
        ids = ["LS-006", "LS-009", "LS-013", "LS-014"]
        self.assertEqual(main._route_ids_from_start(ids, "LS-999"), ids)

    def test_endpoint_forwards_optional_start(self) -> None:
        client = TestClient(main.app)
        with patch.object(main, "_make_route_plan", return_value={"steps": []}) as build:
            response = client.post(
                "/api/route-plan",
                json={"interest": "亲子轻松", "start_spot_id": "LS-009"},
            )
        self.assertEqual(response.status_code, 200, response.text)
        build.assert_called_once_with("亲子轻松", "LS-009")
```

- [ ] **Step 2: Run and confirm red**

Run: `.\.venv\Scripts\python.exe -m unittest discover -s backend\tests -p test_route_plan_start_spot.py -v`  
Expected: FAIL because `_route_ids_from_start` and `start_spot_id` do not exist.

- [ ] **Step 3: Add the field and fixed-sequence helper**

Change `RoutePlanRequest`:

```py
class RoutePlanRequest(BaseModel):
    interest: str = Field(default="经典半日路线", max_length=300)
    start_spot_id: str | None = Field(default=None, min_length=1, max_length=80)
```

Add before `_make_route_plan`:

```py
def _route_ids_from_start(
    spot_ids: list[str],
    start_spot_id: str | None,
) -> list[str]:
    fixed_ids = list(spot_ids)
    normalized = (start_spot_id or "").strip()
    if not normalized or normalized not in fixed_ids:
        return fixed_ids
    return fixed_ids[fixed_ids.index(normalized) :]
```

Change:

```py
def _make_route_plan(
    interest: str,
    start_spot_id: str | None = None,
) -> dict[str, Any]:
    kind = _route_kind(interest)
    preset = ROUTE_PRESETS[kind]
    steps, source_files = _load_route_steps(
        _route_ids_from_start(preset["ids"], start_spot_id)
    )
    guide_route = _load_guide_route(kind)
    if guide_route and guide_route["source_file"] not in source_files:
        source_files.append(guide_route["source_file"])
    return {
        "title": preset["title"],
        "mood": preset["mood"],
        "interest": interest,
        "image_url": "/assets/generated/route-map-lingshan-v2.png",
        "steps": steps,
        "source_files": source_files,
        "guide_title": guide_route["title"] if guide_route else "",
        "note": "路线节点来自本地资料包，演出与开放信息以景区现场公告为准。",
    }

@app.post("/api/route-plan")
def route_plan(payload: RoutePlanRequest) -> dict[str, Any]:
    return {"ok": True, "data": _make_route_plan(
        payload.interest,
        payload.start_spot_id,
    )}
```

- [ ] **Step 4: Run focused and full backend tests**

Run: `.\.venv\Scripts\python.exe -m unittest discover -s backend\tests -p test_route_plan_start_spot.py -v`  
Expected: PASS, 4 tests.

Run: `.\.venv\Scripts\python.exe -m unittest discover -s backend\tests -p test_*.py`  
Expected: all discovered tests pass with `OK`; report the actual runner count.

---

### Task 6: Self-check, demo documentation and acceptance

**Files:**
- Modify: `scripts/tests/visitor-location-contract.test.mjs`
- Modify: `scripts/self-check.mjs:163-253`
- Modify: `README.md`

**Interfaces:**
- Consumes: both location commands and all completed UI/backend behavior.
- Produces: repeatable real/simulated demo instructions with explicit evidence boundary.

- [ ] **Step 1: Add failing self-check/documentation contract**

Append:

```js
test("self-check and README include location regression and demo boundaries", () => {
  const selfCheck = readFileSync(new URL("../self-check.mjs", import.meta.url), "utf-8");
  const readme = readFileSync(new URL("../../README.md", import.meta.url), "utf-8");
  assert(selfCheck.includes('"location-test"'));
  assert(selfCheck.includes('"location-contract:test"'));
  assert(readme.includes("?location-demo=weak"));
  assert(readme.includes("?location-demo=denied"));
  assert(readme.includes("?location-demo=timeout"));
  assert(readme.includes("模拟场景不属于真实现场定位证据"));
});
```

Run: `npm run location-contract:test`  
Expected: FAIL until self-check and README are updated.

- [ ] **Step 2: Integrate location tests into self-check**

Insert after typecheck and renumber labels to 12:

```js
run(npmCommand, ["run", "location-test"], "3/12 location math tests", npmOptions);
run(npmCommand, ["run", "location-contract:test"], "4/12 location contract tests", npmOptions);
```

The later labels become: copy `5/12`, flow `6/12`, goal `7/12`, backend tests `8/12`, build `9/12`, backend runtime `10/12`, frontend runtime `11/12`, complete `12/12`. Do not change runtime logic.

- [ ] **Step 3: Document exact demo URLs and boundaries**

Add to `README.md`:

```md
### 定位辅助演示

定位辅助位于游客端“当前游线”面板。页面不会自动申请位置权限；请先生成游线，再点击“开启定位”。

- 真实定位：正常游客端地址，点击“开启定位”。
- 弱信号：添加 `?location-demo=weak`。
- 权限拒绝：添加 `?location-demo=denied`。
- 超时：添加 `?location-demo=timeout`。

模拟页面会持续显示“模拟场景”。模拟场景不属于真实现场定位证据。

真实手机定位必须通过 HTTPS 安全地址打开。手机通过局域网 HTTP 访问时，浏览器可能禁止 Geolocation；此时页面应进入“无法定位”降级，而不是把它记为 GPS 失败证据。

生产坐标注册表当前为空；系统不会猜测经纬度，也不会展示未经核验的米级距离。原始经纬度仅存在当前浏览器内存，后端最多接收游客主动确认的景点 ID。

本功能是定位辅助，不是实时地图、转弯导航、室内精准定位、自动绕行或最短路径计算。
```

- [ ] **Step 4: Run complete automated acceptance**

Run each separately:

1. `npm run location-test` — Expected: all math tests pass.
2. `npm run location-contract:test` — Expected: all contracts pass.
3. `npm run startup-audit` — Expected: exit 0.
4. `npm run typecheck` — Expected: exit 0.
5. `npm run copy-audit` — Expected: `tourist copy audit passed`.
6. `npm run flow-audit` — Expected: `tourist interaction flow audit passed`.
7. `npm run admin-audit` — Expected: exit 0.
8. `npm run goal-audit` — Expected: exit 0.
9. `.\.venv\Scripts\python.exe -m unittest discover -s backend\tests -p test_*.py` — Expected: `OK`.
10. `npm run build` — Expected: production build completes.
11. `npm run self-check` — Expected: `12/12 self-check complete` and `reports/self-check-latest.json` contains `"ok": true`. This remains offline regression evidence, not real GPS evidence.

- [ ] **Step 5: Recheck the real digital-human path after location integration**

Restart the persistent services, then use the recorded runtime endpoint:

```powershell
$runtime = Get-Content -LiteralPath 'backend\storage\runtime-ports.json' -Raw -Encoding UTF8 | ConvertFrom-Json
$env:LIVE_CHECK_STRICT = "1"
$env:LIVE_CHECK_BASE_URL = $runtime.api_base
npm run live-check

.\third_party\opentalking\.venv\Scripts\python.exe scripts\validate_opentalking_webrtc.py `
  --base-url $runtime.api_base `
  --target-fps 25 `
  --target-resolution 720x720
```

Expected: strict live check exits 0; real audio/video tracks, continuous frames and visible mouth motion remain true. Starting, stopping and denying location must not create a new OpenTalking session or interrupt current playback.

- [ ] **Step 6: Verify backend continuation live**

With backend running:

```powershell
$runtime = Get-Content -LiteralPath 'backend\storage\runtime-ports.json' -Raw -Encoding UTF8 | ConvertFrom-Json
$body = @{ interest = "亲子轻松"; start_spot_id = "LS-009" } | ConvertTo-Json
$response = Invoke-RestMethod -Method Post -Uri "$($runtime.api_base)/api/route-plan" -ContentType "application/json" -Body $body
$response.data.steps[0].spot_id
```

Expected: `LS-009`. Submit `LS-999` and verify the original fixed order is retained.

- [ ] **Step 7: Complete desktop/mobile acceptance matrix**

| Scenario | Required evidence |
|---|---|
| First load | No location prompt; chat, route and digital human usable |
| Real phone GPS over HTTPS | Permission only after tap; honest confidence state |
| Phone over LAN HTTP | Secure-context limitation produces unavailable fallback; not counted as real GPS evidence |
| Empty registry | No spot or meter distance invented; manual/camera available |
| `location-demo=weak` | “模拟场景”, weak-signal copy, route retained |
| `location-demo=denied` | “模拟场景”, denial copy, manual selection works |
| `location-demo=timeout` | “模拟场景”; uncertain after 8 seconds |
| Manual landmark | `manual / confirmed`; selected spot labeled “已到达” |
| GPS after manual | No silent overwrite; candidate requires confirmation |
| Camera fallback | Existing camera opens; route/manual confirmation still works |
| Stop/leave | Watcher and timers stop; no later UI updates |
| Privacy | No latitude/longitude in storage/network; at most `start_spot_id` |
| Independence | GPS denial does not interrupt question or digital-human playback |
| Mobile | Controls, map, next-stop card and input remain reachable |

- [ ] **Step 8: Apply final claim boundary**

Allowed:

> 系统采用按需定位与置信度分级。室外 GPS 可用时辅助确认当前位置；弱信号、室内遮挡或权限拒绝时，游客可以选择眼前地标或拍照识景，问答与游线不中断。

Do not claim precise GPS navigation, precise indoor positioning, real-scale map, shortest-path recomputation, turn-by-turn directions, or real evidence from `location-demo`.

---

## Completion Definition

- All Task 6 automated commands pass from a clean local start.
- Production coordinate registry remains empty until a human adds source-verified WGS84 points.
- A real phone run, three explicit demo modes, manual selection and camera fallback have recorded evidence.
- Storage/network inspection confirms no raw coordinates leave browser memory.
- FAQ fast path, Qwen streaming, segmented TTS, OpenTalking WebRTC and digital-human timing checks remain green.
