import { useEffect, useRef, useState } from "react";
import { MapContainer, TileLayer, Marker, useMapEvents, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { Search, MapPin, X } from "lucide-react";

// Leaflet's default icons break with Vite's asset pipeline — point to CDN instead
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl:       "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl:     "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});

const BARRANQUILLA = [10.9639, -74.7964];
const ZOOM_CITY   = 13;
const ZOOM_STREET = 17;

// Pans the map when `position` changes. Skips the initial render so the
// MapContainer's own `center` prop handles the first load.
function MapPanner({ position }) {
  const map   = useMap();
  const first = useRef(true);
  useEffect(() => {
    if (first.current) { first.current = false; return; }
    if (position) map.setView(position, ZOOM_STREET, { animate: true });
  }, [position, map]);
  return null;
}

function MapClickHandler({ onMapClick }) {
  useMapEvents({
    click(e) { onMapClick(e.latlng.lat, e.latlng.lng); },
  });
  return null;
}

export default function MapaSelectorAdmin({ lat, lng, address, city, onChange }) {
  const initPos =
    lat != null && lng != null && !isNaN(parseFloat(lat)) && !isNaN(parseFloat(lng))
      ? [parseFloat(lat), parseFloat(lng)]
      : null;

  const [position,  setPosition]  = useState(initPos);
  const [centerOn,  setCenterOn]  = useState(null);
  const [searching, setSearching] = useState(false);
  const [searchErr, setSearchErr] = useState("");

  const setPin = (newLat, newLng) => {
    const p = [newLat, newLng];
    setPosition(p);
    onChange(newLat, newLng);
  };

  const geocode = async () => {
    const query = [address, city].filter(Boolean).join(", ");
    if (!query.trim()) {
      setSearchErr("Completa la dirección y ciudad primero.");
      return;
    }
    setSearching(true);
    setSearchErr("");
    try {
      const res  = await fetch(
        `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(query)}&format=json&limit=1`,
        { headers: { "Accept-Language": "es" } }
      );
      const data = await res.json();
      if (!data.length) {
        setSearchErr("No se encontró esa dirección. Ajusta el pin directamente en el mapa.");
        return;
      }
      const p = [parseFloat(data[0].lat), parseFloat(data[0].lon)];
      setPosition(p);
      setCenterOn(p);
      onChange(p[0], p[1]);
    } catch {
      setSearchErr("Error de conexión al buscar la dirección.");
    } finally {
      setSearching(false);
    }
  };

  const clearPin = () => {
    setPosition(null);
    setSearchErr("");
    onChange(null, null);
  };

  const center = position ?? BARRANQUILLA;
  const zoom   = position ? ZOOM_STREET : ZOOM_CITY;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={geocode}
          disabled={searching}
          className="flex items-center gap-2 px-4 py-2 bg-[#1b5e20] text-white rounded-xl text-sm font-bold hover:bg-[#0d3300] transition disabled:opacity-50"
        >
          <Search className="w-4 h-4" />
          {searching ? "Buscando…" : "Buscar dirección en el mapa"}
        </button>
        {position && (
          <button
            type="button"
            onClick={clearPin}
            className="flex items-center gap-2 px-4 py-2 bg-gray-100 text-gray-600 rounded-xl text-sm font-bold hover:bg-gray-200 transition"
          >
            <X className="w-4 h-4" />
            Quitar pin
          </button>
        )}
      </div>

      {searchErr && (
        <p className="text-xs text-orange-600 font-medium">{searchErr}</p>
      )}

      <div className="rounded-xl overflow-hidden border border-gray-200" style={{ height: 340 }}>
        <MapContainer
          center={center}
          zoom={zoom}
          style={{ height: "100%", width: "100%" }}
        >
          <TileLayer
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          />
          <MapClickHandler onMapClick={setPin} />
          <MapPanner position={centerOn} />
          {position && (
            <Marker
              position={position}
              draggable
              eventHandlers={{
                dragend(e) {
                  const { lat: la, lng: lo } = e.target.getLatLng();
                  setPin(la, lo);
                },
              }}
            />
          )}
        </MapContainer>
      </div>

      <p className="text-xs text-gray-500 flex items-start gap-1">
        {position ? (
          <>
            <MapPin className="w-3 h-3 text-[#4caf50] flex-shrink-0 mt-0.5" />
            Pin en {position[0].toFixed(6)}, {position[1].toFixed(6)} —
            arrastra el pin o haz clic en el mapa para ajustar la posición exacta
          </>
        ) : (
          "Haz clic en «Buscar dirección» o haz clic directamente sobre el mapa para colocar el pin. Sin pin, el footer aproxima la ubicación por texto."
        )}
      </p>
    </div>
  );
}
