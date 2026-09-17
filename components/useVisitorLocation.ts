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
  const mountedRef = useRef(true);
  const generationRef = useRef(0);
  const stateRef = useRef<VisitorLocationState>(INITIAL_STATE);
  const suggestionRef = useRef<{ spotId: string; expiresAt: number } | null>(null);
  const updateSuggestion = useCallback((next: { spotId: string; expiresAt: number } | null) => {
    suggestionRef.current = next;
    setSuggestedSpotId(next?.spotId ?? null);
  }, []);
  const isCurrentSession = useCallback(
    (generation: number) => mountedRef.current && generationRef.current === generation,
    []
  );
  const eligibleCoordinates = useMemo(
    () => coordinates.filter((spot) => eligibleSpotIds.includes(spot.spot_id)),
    [coordinates, eligibleSpotIds]
  );
  const eligibleCoordinatesRef = useRef<readonly SpotCoordinate[]>(eligibleCoordinates);

  useEffect(() => {
    eligibleCoordinatesRef.current = eligibleCoordinates;
    const suggestion = suggestionRef.current;
    if (suggestion && !eligibleCoordinates.some((spot) => spot.spot_id === suggestion.spotId)) {
      updateSuggestion(null);
    }
  }, [eligibleCoordinates, updateSuggestion]);

  useEffect(() => {
    stateRef.current = state;
  }, [state]);

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
    generationRef.current += 1;
    clearResources();
    setIsWatching(false);
    updateSuggestion(null);
    setState((current) => current.current_spot_id
      ? { ...current, status: "confirmed" }
      : INITIAL_STATE);
  }, [clearResources, updateSuggestion]);

  const startLocation = useCallback(() => {
    const generation = generationRef.current + 1;
    generationRef.current = generation;
    clearResources();
    previousObservationRef.current = null;
    updateSuggestion(null);
    setIsWatching(true);
    setState((current) => current.source === "manual" && current.status === "confirmed"
      ? current
      : { ...current, source: "gps", status: "requesting", accuracy_m: null, observed_at: null });

    const finish = (status: "uncertain" | "denied" | "unavailable") => {
      if (!isCurrentSession(generation)) return;
      generationRef.current += 1;
      clearResources();
      setIsWatching(false);
      updateSuggestion(null);
      setState((current) => current.status === "confirmed" && current.current_spot_id
        ? current
        : { ...INITIAL_STATE, source: status === "uncertain" ? "gps" : "none", status });
    };

    if (demoScenario) {
      const requestTimerId = window.setTimeout(() => {
        if (!isCurrentSession(generation) || requestTimerRef.current !== requestTimerId) return;
        requestTimerRef.current = null;
        if (demoScenario === "weak") {
          generationRef.current += 1;
          updateSuggestion(null);
          setState((current) => current.source === "manual" ? current : {
            source: "gps", status: "uncertain", accuracy_m: 180,
            current_spot_id: current.current_spot_id, observed_at: Date.now()
          });
          setIsWatching(false);
        } else {
          finish(demoScenario === "denied" ? "denied" : "uncertain");
        }
      }, demoScenario === "timeout" ? timeoutMs : 350);
      requestTimerRef.current = requestTimerId;
      return;
    }

    if (typeof window === "undefined" || !window.isSecureContext
      || typeof navigator === "undefined" || !navigator.geolocation) {
      finish("unavailable");
      return;
    }
    const requestTimerId = window.setTimeout(() => {
      if (!isCurrentSession(generation) || requestTimerRef.current !== requestTimerId) return;
      requestTimerRef.current = null;
      finish("uncertain");
    }, timeoutMs);
    requestTimerRef.current = requestTimerId;
    watchIdRef.current = navigator.geolocation.watchPosition((position) => {
      if (!isCurrentSession(generation)) return;
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
      if (stateRef.current.source === "manual" && stateRef.current.status === "confirmed") {
        updateSuggestion(null);
        return;
      }
      updateSuggestion(candidate
        ? { spotId: candidate.spot.spot_id, expiresAt: Date.now() + staleAfterMs }
        : null);
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
      const staleTimerId = window.setTimeout(() => {
        if (!isCurrentSession(generation) || staleTimerRef.current !== staleTimerId) return;
        staleTimerRef.current = null;
        updateSuggestion(null);
        setState((current) => current.source === "manual" ? current : { ...current, status: "stale" });
      }, staleAfterMs);
      staleTimerRef.current = staleTimerId;
    }, (error) => {
      if (!isCurrentSession(generation)) return;
      finish(error.code === error.PERMISSION_DENIED
        ? "denied"
        : error.code === error.TIMEOUT ? "uncertain" : "unavailable");
    }, { enableHighAccuracy: true, timeout: timeoutMs, maximumAge: 10_000 });
  }, [clearResources, demoScenario, isCurrentSession, staleAfterMs, timeoutMs, updateSuggestion]);

  const confirmSuggestedSpot = useCallback(() => {
    const suggestion = suggestionRef.current;
    const currentState = stateRef.current;
    const canConfirm = suggestion
      && currentState.source === "gps"
      && currentState.status === "uncertain"
      && Date.now() < suggestion.expiresAt
      && eligibleCoordinatesRef.current.some((spot) => spot.spot_id === suggestion.spotId);
    if (!canConfirm || !suggestion) {
      updateSuggestion(null);
      return;
    }
    const spotId = suggestion.spotId;
    generationRef.current += 1;
    clearResources();
    setIsWatching(false);
    setState((current) => ({
      ...current, source: "gps", status: "confirmed",
      current_spot_id: spotId
    }));
    updateSuggestion(null);
  }, [clearResources, updateSuggestion]);

  const confirmSpot = useCallback((spotId: string) => {
    generationRef.current += 1;
    clearResources();
    setIsWatching(false);
    updateSuggestion(null);
    setState({
      source: "manual", status: "confirmed", accuracy_m: null,
      current_spot_id: spotId, observed_at: Date.now()
    });
  }, [clearResources, updateSuggestion]);

  const beginCameraAssist = useCallback(() => {
    generationRef.current += 1;
    clearResources();
    setIsWatching(false);
    updateSuggestion(null);
    setState((current) => current.current_spot_id
      ? current
      : { ...INITIAL_STATE, source: "camera", status: "uncertain" });
  }, [clearResources, updateSuggestion]);

  const dismissSuggestion = useCallback(() => updateSuggestion(null), [updateSuggestion]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      generationRef.current += 1;
      clearResources();
    };
  }, [clearResources]);

  return {
    state, suggestedSpotId, isWatching, isSimulated: demoScenario !== null,
    startLocation, stopLocation, beginCameraAssist, confirmSuggestedSpot, confirmSpot,
    dismissSuggestion
  };
}
