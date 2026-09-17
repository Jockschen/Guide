import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";
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

test("fails closed for nullish registry entries", () => {
  for (const entry of [null, undefined]) {
    const result = validateSpotCoordinateRegistry([entry], "WGS84");
    assert.equal(result.usable, false);
    assert.deepEqual(result.spots, []);
    assert(result.errors.some((item) => item.includes("entry 0")));
  }
});

test("fails closed for non-finite location values", () => {
  const previous = { latitude: 31, longitude: 120, accuracy_m: 10, observed_at: 1_000 };
  const next = { latitude: 31.00002, longitude: 120, accuracy_m: 10, observed_at: 6_000 };

  for (const invalid of [Number.NaN, Number.POSITIVE_INFINITY]) {
    assert.equal(isObservationStale(invalid, 31_001, 30_000), true);
    assert.equal(isObservationStale(1_000, invalid, 30_000), true);
    assert.equal(haversineDistanceMeters(
      { latitude: invalid, longitude: 120 },
      next
    ), Number.POSITIVE_INFINITY);
    assert.equal(haversineDistanceMeters(
      previous,
      { latitude: 31, longitude: invalid }
    ), Number.POSITIVE_INFINITY);
    assert.equal(isAbnormalLocationJump(
      { ...previous, observed_at: invalid },
      next
    ), true);
    assert.equal(isAbnormalLocationJump(
      previous,
      { ...next, observed_at: invalid }
    ), true);
    assert.equal(isAbnormalLocationJump(
      { ...previous, accuracy_m: invalid },
      next
    ), true);
    assert.equal(isAbnormalLocationJump(
      previous,
      { ...next, accuracy_m: invalid }
    ), true);
    assert.equal(isAbnormalLocationJump(
      { ...previous, latitude: invalid },
      next
    ), true);
    assert.equal(isAbnormalLocationJump(
      previous,
      { ...next, longitude: invalid }
    ), true);
  }
});

test("declares verified spot coordinates as a readonly imported type", () => {
  const sourceText = readFileSync(new URL("../../lib/spotCoordinates.ts", import.meta.url), "utf8");
  const sourceFile = ts.createSourceFile(
    "spotCoordinates.ts",
    sourceText,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TS
  );
  const declaration = sourceFile.statements
    .filter(ts.isVariableStatement)
    .flatMap((statement) => statement.declarationList.declarations)
    .find((item) => ts.isIdentifier(item.name) && item.name.text === "VERIFIED_SPOT_COORDINATES");
  assert(declaration, "VERIFIED_SPOT_COORDINATES declaration is missing");
  assert.equal(declaration.type?.getText(sourceFile), "readonly SpotCoordinate[]");
  const importsSpotCoordinateAsType = sourceFile.statements.some((statement) =>
    ts.isImportDeclaration(statement)
      && statement.importClause?.isTypeOnly
      && statement.importClause.namedBindings
      && ts.isNamedImports(statement.importClause.namedBindings)
      && statement.importClause.namedBindings.elements.some(
        (element) => element.name.text === "SpotCoordinate"
      )
  );
  assert.equal(importsSpotCoordinateAsType, true);
});
