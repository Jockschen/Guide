import rawCoordinates from "@/data/spot-coordinates.json";
import { validateSpotCoordinateRegistry } from "./locationMath";
import type { SpotCoordinate } from "./types";

const registry = validateSpotCoordinateRegistry(rawCoordinates, "WGS84");
export const VERIFIED_SPOT_COORDINATES: readonly SpotCoordinate[] = registry.spots;
export const SPOT_COORDINATE_REGISTRY_USABLE = registry.usable;
export const SPOT_COORDINATE_REGISTRY_ERRORS = registry.errors;
