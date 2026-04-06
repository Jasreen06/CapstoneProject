const EARTH_RADIUS_NM = 3440.065;

function toRad(deg) {
  return (deg * Math.PI) / 180;
}

function toDeg(rad) {
  return (rad * 180) / Math.PI;
}

function movePosition(lat, lon, bearingDeg, distanceNm) {
  const d = distanceNm / EARTH_RADIUS_NM;
  const b = toRad(bearingDeg);
  const rlat = toRad(lat);
  const rlon = toRad(lon);

  const newLat = Math.asin(
    Math.sin(rlat) * Math.cos(d) + Math.cos(rlat) * Math.sin(d) * Math.cos(b)
  );
  const newLon =
    rlon +
    Math.atan2(
      Math.sin(b) * Math.sin(d) * Math.cos(rlat),
      Math.cos(d) - Math.sin(rlat) * Math.sin(newLat)
    );

  return [toDeg(newLat), toDeg(newLon)];
}

/**
 * Great circle distance between two points in nautical miles.
 */
export function haversineNm(lat1, lon1, lat2, lon2) {
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return EARTH_RADIUS_NM * c;
}

/**
 * Estimate time of arrival in hours based on distance and speed.
 * Uses 90% of SOG as average speed to account for slowdowns.
 * Returns null if speed is too low.
 */
export function estimateEta(distNm, sogKnots) {
  if (!distNm || !sogKnots || sogKnots < 0.5) return null;
  const avgSpeed = sogKnots * 0.9;
  return distNm / avgSpeed;
}

/**
 * Project vessel trajectory using dead reckoning.
 * @param {number} lat - Current latitude
 * @param {number} lon - Current longitude
 * @param {number} sogKnots - Speed over ground in knots
 * @param {number} cogDegrees - Course over ground in degrees (0-360)
 * @param {number} hours - Number of hours to project (default 72)
 * @returns {Array<{lat, lon, hoursFromNow}>}
 */
export function projectTrajectory(lat, lon, sogKnots, cogDegrees, hours = 72) {
  if (!lat || !lon || sogKnots <= 0) return [];

  const positions = [];
  let curLat = lat;
  let curLon = lon;
  const speed = Math.max(sogKnots, 0.5);

  for (let h = 1; h <= hours; h++) {
    const distanceNm = speed * 1.0; // 1 hour
    [curLat, curLon] = movePosition(curLat, curLon, cogDegrees, distanceNm);
    positions.push({ lat: curLat, lon: curLon, hoursFromNow: h });
  }

  return positions;
}

/**
 * Convert lat/lon to canvas pixel coordinates.
 * @param {number} lat
 * @param {number} lon
 * @param {object} viewport - {minLat, maxLat, minLon, maxLon, width, height}
 */
export function latLonToPixel(lat, lon, viewport) {
  const { minLat, maxLat, minLon, maxLon, width, height } = viewport;
  const x = ((lon - minLon) / (maxLon - minLon)) * width;
  const y = ((maxLat - lat) / (maxLat - minLat)) * height;
  return [x, y];
}

/**
 * Convert canvas pixel to lat/lon.
 */
export function pixelToLatLon(x, y, viewport) {
  const { minLat, maxLat, minLon, maxLon, width, height } = viewport;
  const lon = minLon + (x / width) * (maxLon - minLon);
  const lat = maxLat - (y / height) * (maxLat - minLat);
  return [lat, lon];
}
