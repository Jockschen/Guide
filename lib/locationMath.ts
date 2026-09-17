import type {
  CoordinateSystem, GeoPoint, LocationAccuracyBand,
  LocationDemoScenario, LocationObservation, SpotCoordinate
} from "./types.ts";

export const LOCATION_REQUEST_TIMEOUT_MS = 8_000;
export const LOCATION_STALE_AFTER_MS = 30_000;
const EARTH_RADIUS_M = 6_371_000;

function isValidGeoPoint(value: GeoPoint): boolean {
  return Number.isFinite(value.latitude)
    && value.latitude >= -90
    && value.latitude <= 90
    && Number.isFinite(value.longitude)
    && value.longitude >= -180
    && value.longitude <= 180;
}

function isValidLocationObservation(value: LocationObservation): boolean {
  return isValidGeoPoint(value)
    && Number.isFinite(value.accuracy_m)
    && value.accuracy_m >= 0
    && Number.isFinite(value.observed_at);
}

export function classifyAccuracy(value: number | null): LocationAccuracyBand {
  if (value === null || !Number.isFinite(value) || value < 0) return "unknown";
  if (value <= 50) return "precise";
  if (value <= 150) return "approximate";
  return "weak";
}

const radians = (value: number) => value * Math.PI / 180;

export function haversineDistanceMeters(a: GeoPoint, b: GeoPoint): number {
  if (!isValidGeoPoint(a) || !isValidGeoPoint(b)) return Number.POSITIVE_INFINITY;
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
  if (observedAt === null) return false;
  if (!Number.isFinite(observedAt) || !Number.isFinite(now)) return true;
  return now - observedAt > staleAfterMs;
}

export function isAbnormalLocationJump(
  previous: LocationObservation | null,
  next: LocationObservation
): boolean {
  if (!isValidLocationObservation(next)) return true;
  if (!previous) return false;
  if (!isValidLocationObservation(previous)) return true;
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
    if (entry === null || typeof entry !== "object") {
      errors.push(`entry ${index} has invalid fields or coordinate_system`);
      return;
    }
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
