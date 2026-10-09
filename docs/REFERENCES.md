# References to attach to prompts

## OpenStreetMap tiles
- Tile URL template: https://tile.openstreetmap.org/{z}/{x}/{y}.png  (no API key needed). Keep it in TILE_URL, never hard-code it.
- Attribution must be visible on the map: &copy; OpenStreetMap contributors, linking to https://www.openstreetmap.org/copyright
- Policy: https://operations.osmfoundation.org/policies/tiles/
  - Display licence attribution clearly.
  - Browsers send a valid User-Agent and a Referer. Do NOT use Referrer-Policy: no-referrer.
  - Light use only. Heavy use of the volunteer-run servers is not allowed without permission.
  - Do not bulk download or pre-fetch tiles. Do not cache tiles for other people.
  - Do not hard-code the tile URL, so you can switch provider if needed.
- Our protections: setMaxBounds, minZoom, maxZoom, no prefetching.
- You do NOT need the OSM editing API or Nominatim geocoding.

## Leaflet 1.9.4
- Docs: https://leafletjs.com/reference.html
- CSS: https://unpkg.com/leaflet@1.9.4/dist/leaflet.css
- JS:  https://unpkg.com/leaflet@1.9.4/dist/leaflet.js
- Used: L.map, L.tileLayer(url, {attribution, minZoom, maxZoom}), map.setMaxBounds, L.circle, L.marker, L.divIcon, map.on('click', ...), marker draggable option.

## Geolocation API (browser, no key)
- Docs: https://developer.mozilla.org/en-US/docs/Web/API/Geolocation_API
- navigator.geolocation.watchPosition(success, error, { enableHighAccuracy: true, maximumAge: 0, timeout: 15000 })
- success(position) gives position.coords.latitude, longitude, accuracy (metres), heading and position.timestamp.
- Error codes: 1 permission denied, 2 position unavailable, 3 timeout.
- Needs a secure context: https, or http on localhost.

## Screen Wake Lock API
- Docs: https://developer.mozilla.org/en-US/docs/Web/API/Screen_Wake_Lock_API
- navigator.wakeLock.request('screen'). Release happens when the page is hidden, so request again on visibilitychange.
- Not available everywhere, so always show a fallback message.

## Haversine formula (R = 6,371,000 m)
- a = sin^2(dLat/2) + cos(lat1) * cos(lat2) * sin^2(dLng/2)
- distance = 2 * R * asin(sqrt(a))   (all angles in radians)

## FastAPI, Railway
- FastAPI docs: https://fastapi.tiangolo.com
- Railway docs: https://docs.railway.com
- Start command: uvicorn main:app --host 0.0.0.0 --port $PORT
- Railway variables: ENV=production, FORWARDED_ALLOW_IPS=*, DB_PATH=/data/quest.db (Volume mounted at /data)

## Getting coordinates
- Google Maps: right-click a spot, click the coordinates at the top of the menu to copy (latitude first, then longitude).
- Confirm on openstreetmap.org: right-click the spot, "Show address".