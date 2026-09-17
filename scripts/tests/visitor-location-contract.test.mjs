import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

const hookPath = new URL("../../components/useVisitorLocation.ts", import.meta.url);
const locationMathPath = new URL("../../lib/locationMath.ts", import.meta.url);

function evaluateTypeScriptModule(source, fileName, requireModule, globals = {}) {
  const compiled = ts.transpileModule(source, {
    fileName,
    compilerOptions: {
      esModuleInterop: true,
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020
    }
  });
  const module = { exports: {} };
  const evaluate = new Function(
    "require",
    "module",
    "exports",
    "window",
    "navigator",
    "Date",
    `${compiled.outputText}\n//# sourceURL=${fileName}`
  );
  evaluate(
    requireModule,
    module,
    module.exports,
    globals.window,
    globals.navigator,
    globals.Date ?? Date
  );
  return module.exports;
}

const locationMath = evaluateTypeScriptModule(
  readFileSync(locationMathPath, "utf8"),
  "locationMath.behavior-test.ts",
  () => ({})
);

function dependenciesEqual(previous, next) {
  return previous !== undefined
    && next !== undefined
    && previous.length === next.length
    && previous.every((value, index) => Object.is(value, next[index]));
}

function createHookRuntime() {
  const slots = [];
  let cursor = 0;
  let pendingEffects = [];
  let component = null;
  let props = null;
  let current = null;
  let renderQueued = false;
  let flushing = false;
  let batchDepth = 0;
  let unmounted = false;
  let postUnmountUpdates = 0;

  const queueRender = () => {
    renderQueued = true;
    if (batchDepth === 0 && !flushing) flush();
  };

  const react = {
    useState(initialValue) {
      const index = cursor++;
      if (!slots[index]) {
        const slot = {
          kind: "state",
          value: typeof initialValue === "function" ? initialValue() : initialValue,
          setter: null
        };
        slot.setter = (nextValue) => {
          if (unmounted) {
            postUnmountUpdates += 1;
            return;
          }
          const value = typeof nextValue === "function"
            ? nextValue(slot.value)
            : nextValue;
          if (!Object.is(value, slot.value)) {
            slot.value = value;
            queueRender();
          }
        };
        slots[index] = slot;
      }
      return [slots[index].value, slots[index].setter];
    },
    useRef(initialValue) {
      const index = cursor++;
      if (!slots[index]) slots[index] = { kind: "ref", value: { current: initialValue } };
      return slots[index].value;
    },
    useMemo(factory, dependencies) {
      const index = cursor++;
      const previous = slots[index];
      if (!previous || !dependenciesEqual(previous.dependencies, dependencies)) {
        slots[index] = {
          kind: "memo",
          dependencies: dependencies?.slice(),
          value: factory()
        };
      }
      return slots[index].value;
    },
    useCallback(callback, dependencies) {
      return react.useMemo(() => callback, dependencies);
    },
    useEffect(effect, dependencies) {
      const index = cursor++;
      pendingEffects.push({ index, effect, dependencies });
    }
  };

  function flush() {
    if (flushing || unmounted) return;
    flushing = true;
    try {
      while (renderQueued && !unmounted) {
        renderQueued = false;
        cursor = 0;
        pendingEffects = [];
        current = component(props);
        for (const pending of pendingEffects) {
          const previous = slots[pending.index];
          if (previous && dependenciesEqual(previous.dependencies, pending.dependencies)) continue;
          if (typeof previous?.cleanup === "function") previous.cleanup();
          const cleanup = pending.effect();
          slots[pending.index] = {
            kind: "effect",
            dependencies: pending.dependencies?.slice(),
            cleanup
          };
        }
      }
    } finally {
      flushing = false;
    }
  }

  function act(callback) {
    batchDepth += 1;
    try {
      return callback();
    } finally {
      batchDepth -= 1;
      if (batchDepth === 0) flush();
    }
  }

  return {
    react,
    act,
    mount(hook, initialProps) {
      component = hook;
      props = initialProps;
      renderQueued = true;
      flush();
    },
    rerender(nextProps) {
      props = nextProps;
      renderQueued = true;
      flush();
    },
    unmount() {
      for (const slot of slots) {
        if (typeof slot?.cleanup === "function") slot.cleanup();
      }
      unmounted = true;
    },
    get current() {
      return current;
    },
    get postUnmountUpdates() {
      return postUnmountUpdates;
    }
  };
}

function createFakeTimers(startAt = 1_000) {
  let now = startAt;
  let nextId = 1;
  const scheduled = new Map();
  const clearCalls = [];

  const window = {
    isSecureContext: true,
    setTimeout(callback, delay = 0) {
      const id = nextId++;
      scheduled.set(id, { callback, dueAt: now + delay });
      return id;
    },
    clearTimeout(id) {
      clearCalls.push(id);
      scheduled.delete(id);
    }
  };

  return {
    window,
    Date: { now: () => now },
    clearCalls,
    advanceBy(duration) {
      const target = now + duration;
      while (true) {
        const next = [...scheduled.entries()]
          .filter(([, timer]) => timer.dueAt <= target)
          .sort((a, b) => a[1].dueAt - b[1].dueAt || a[0] - b[0])[0];
        if (!next) break;
        const [id, timer] = next;
        scheduled.delete(id);
        now = timer.dueAt;
        timer.callback();
      }
      now = target;
    },
    pendingIds() {
      return [...scheduled.keys()];
    },
    get now() {
      return now;
    }
  };
}

const TEST_SPOT = {
  spot_id: "TEST-001",
  latitude: 31,
  longitude: 120,
  coordinate_system: "WGS84",
  arrival_radius_m: 60,
  source: "behavior-test fixture"
};

function createVisitorLocationHarness(overrides = {}) {
  const runtime = createHookRuntime();
  const timers = createFakeTimers();
  const watches = [];
  const clearedWatches = [];
  let nextWatchId = 1;
  const geolocation = {
    watchPosition(success, error, options) {
      const watch = { id: nextWatchId++, success, error, options };
      watches.push(watch);
      return watch.id;
    },
    clearWatch(id) {
      clearedWatches.push(id);
    }
  };
  const navigator = { geolocation };
  const hookModule = evaluateTypeScriptModule(
    readFileSync(hookPath, "utf8"),
    "useVisitorLocation.behavior-test.ts",
    (specifier) => {
      if (specifier === "react") return runtime.react;
      if (specifier === "@/lib/locationMath") return locationMath;
      throw new Error(`Unexpected behavior-test import: ${specifier}`);
    },
    { window: timers.window, navigator, Date: timers.Date }
  );
  let props = {
    coordinates: [TEST_SPOT],
    eligibleSpotIds: [TEST_SPOT.spot_id],
    demoScenario: null,
    timeoutMs: 8_000,
    staleAfterMs: 30_000,
    ...overrides
  };
  runtime.mount(hookModule.useVisitorLocation, props);

  return {
    runtime,
    timers,
    watches,
    clearedWatches,
    act: runtime.act,
    rerender(nextProps) {
      props = { ...props, ...nextProps };
      runtime.rerender(props);
    },
    position({ latitude = 31, longitude = 120, accuracy = 10, timestamp = timers.now } = {}) {
      return { coords: { latitude, longitude, accuracy }, timestamp };
    },
    unmount: () => runtime.unmount(),
    get current() {
      return runtime.current;
    }
  };
}

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

test("stopping and failed requests clear stale suggestions", () => {
  const hook = readFileSync(hookPath, "utf-8");
  const stopLocation = hook.match(
    /const stopLocation = useCallback\(\(\) => \{([\s\S]*?)\n\s*\}, \[[^\]]*\]\);/
  );
  const finish = hook.match(
    /const finish = \(status: "uncertain" \| "denied" \| "unavailable"\) => \{([\s\S]*?)\n\s*\};/
  );
  assert(stopLocation, "stopLocation block is missing");
  assert(finish, "finish block is missing");
  assert.match(stopLocation[1], /(?:setSuggestedSpotId|updateSuggestion)\(null\)/);
  assert.match(finish[1], /(?:setSuggestedSpotId|updateSuggestion)\(null\)/);
});

test("stale suggestions disappear and stale confirm closures cannot select them", () => {
  const harness = createVisitorLocationHarness();
  harness.act(() => harness.current.startLocation());
  const firstWatch = harness.watches[0];
  harness.act(() => firstWatch.success(harness.position()));
  assert.equal(harness.current.suggestedSpotId, TEST_SPOT.spot_id);
  const oldConfirm = harness.current.confirmSuggestedSpot;

  harness.act(() => harness.timers.advanceBy(30_001));
  assert.equal(harness.current.state.status, "stale");
  assert.equal(harness.current.suggestedSpotId, null);
  harness.act(() => oldConfirm());
  assert.equal(harness.current.state.current_spot_id, null);
  assert.equal(harness.current.state.status, "stale");
  harness.unmount();
});

test("route changes invalidate suggestions and old confirm closures", () => {
  const harness = createVisitorLocationHarness();
  harness.act(() => harness.current.startLocation());
  harness.act(() => harness.watches[0].success(harness.position()));
  assert.equal(harness.current.suggestedSpotId, TEST_SPOT.spot_id);
  const oldConfirm = harness.current.confirmSuggestedSpot;

  harness.rerender({ eligibleSpotIds: ["OTHER-ROUTE-SPOT"] });
  assert.equal(harness.current.suggestedSpotId, null);
  harness.act(() => oldConfirm());
  assert.equal(harness.current.state.current_spot_id, null);
  harness.unmount();
});

test("late callbacks from a stopped session cannot mutate a restarted session", () => {
  const harness = createVisitorLocationHarness();
  harness.act(() => harness.current.startLocation());
  const oldWatch = harness.watches[0];
  harness.act(() => harness.current.stopLocation());
  harness.act(() => harness.current.startLocation());
  assert.equal(harness.watches.length, 2);
  const currentRequestTimer = harness.timers.pendingIds()[0];
  const clearCallCount = harness.timers.clearCalls.length;

  harness.act(() => {
    oldWatch.success(harness.position());
    oldWatch.error({ code: 1, PERMISSION_DENIED: 1, TIMEOUT: 3 });
  });
  assert.equal(harness.current.state.status, "requesting");
  assert.equal(harness.current.suggestedSpotId, null);
  assert.equal(harness.current.isWatching, true);
  assert(harness.timers.pendingIds().includes(currentRequestTimer));
  assert.equal(
    harness.timers.clearCalls.slice(clearCallCount).includes(currentRequestTimer),
    false
  );
  harness.unmount();
});

test("weak demo completion leaves no completed timer for the next start to clear", () => {
  const harness = createVisitorLocationHarness({ demoScenario: "weak" });
  harness.act(() => harness.current.startLocation());
  const completedTimer = harness.timers.pendingIds()[0];
  harness.act(() => harness.timers.advanceBy(350));
  assert.equal(harness.current.state.status, "uncertain");
  assert.equal(harness.current.state.accuracy_m, 180);
  assert.equal(harness.current.suggestedSpotId, null);
  assert.equal(harness.current.isWatching, false);

  const clearCallCount = harness.timers.clearCalls.length;
  harness.act(() => harness.current.startLocation());
  assert.equal(
    harness.timers.clearCalls.slice(clearCallCount).includes(completedTimer),
    false
  );
  harness.unmount();
});

test("geolocation callbacks queued before unmount are ignored", () => {
  const harness = createVisitorLocationHarness();
  harness.act(() => harness.current.startLocation());
  const oldWatch = harness.watches[0];
  harness.unmount();

  oldWatch.success(harness.position());
  assert.equal(harness.runtime.postUnmountUpdates, 0);
  assert.deepEqual(harness.timers.pendingIds(), []);
});
