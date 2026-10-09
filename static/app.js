// Campus Quest - Client Map & Live Location Tracker
// Client-side only: fetches /api/config, mounts Leaflet map, watches geolocation.

document.addEventListener('DOMContentLoaded', () => {
  const statusEl = document.getElementById('gps-status');

  function setStatus(message, statusClass) {
    if (!statusEl) return;
    statusEl.textContent = message;
    statusEl.className = 'gps-status-pill ' + statusClass;
  }

  fetch('/api/config')
    .then((response) => {
      if (!response.ok) {
        throw new Error('Server returned status ' + response.status);
      }
      return response.json();
    })
    .then((cfg) => {
      initMap(cfg);
    })
    .catch((err) => {
      setStatus('Failed to load map settings: ' + err.message, 'status-error');
    });

  function initMap(cfg) {
    const sw = L.latLng(cfg.bounds.sw.lat, cfg.bounds.sw.lng);
    const ne = L.latLng(cfg.bounds.ne.lat, cfg.bounds.ne.lng);
    const campusBounds = L.latLngBounds(sw, ne);

    const map = L.map('map', {
      center: [cfg.center.lat, cfg.center.lng],
      zoom: cfg.zoom.start,
      minZoom: cfg.zoom.min,
      maxZoom: cfg.zoom.max,
      maxBounds: campusBounds,
      maxBoundsViscosity: 1.0,
      zoomControl: false,
    });

    // Place zoom control at bottom-right so it does not collide with UI buttons
    L.control.zoom({ position: 'bottomright' }).addTo(map);

    L.tileLayer(cfg.tile_url, {
      attribution: cfg.tile_attribution,
      minZoom: cfg.zoom.min,
      maxZoom: cfg.zoom.max,
    }).addTo(map);

    if (!('geolocation' in navigator)) {
      setStatus('Geolocation is not supported by your browser.', 'status-error');
      return;
    }

    setStatus('Waiting for GPS...', 'status-waiting');

    let locationDot = null;
    let accuracyCircle = null;
    let initialFixApplied = false;

    function onLocationSuccess(position) {
      const lat = position.coords.latitude;
      const lng = position.coords.longitude;
      const accuracy = position.coords.accuracy;
      const latLng = [lat, lng];

      if (!locationDot) {
        accuracyCircle = L.circle(latLng, {
          radius: accuracy,
          color: '#1a73e8',
          weight: 1,
          opacity: 0.6,
          fillColor: '#1a73e8',
          fillOpacity: 0.12,
        }).addTo(map);

        locationDot = L.circleMarker(latLng, {
          radius: 8,
          fillColor: '#1a73e8',
          color: '#ffffff',
          weight: 3,
          opacity: 1,
          fillOpacity: 1,
        }).addTo(map);
      } else {
        locationDot.setLatLng(latLng);
        accuracyCircle.setLatLng(latLng);
        accuracyCircle.setRadius(accuracy);
      }

      if (!initialFixApplied) {
        if (campusBounds.contains(latLng)) {
          map.panTo(latLng);
        }
        initialFixApplied = true;
      }

      const accMetres = Math.round(accuracy);
      setStatus(`Accuracy: ${accMetres} m`, 'status-active');
    }

    function onLocationError(error) {
      let message = 'Unable to determine position.';
      switch (error.code) {
        case error.PERMISSION_DENIED:
          message = 'Location permission denied. Please allow access.';
          break;
        case error.POSITION_UNAVAILABLE:
          message = 'GPS position unavailable. Move outdoors.';
          break;
        case error.TIMEOUT:
          message = 'Waiting for GPS fix (timed out, retrying)...';
          break;
      }
      setStatus(message, 'status-error');
    }

    navigator.geolocation.watchPosition(
      onLocationSuccess,
      onLocationError,
      {
        enableHighAccuracy: true,
        maximumAge: 0,
        timeout: 15000,
      }
    );
  }
});
