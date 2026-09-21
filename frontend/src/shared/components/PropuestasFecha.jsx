import { Calendar, Check, Store, User } from 'lucide-react';

/**
 * La negociación de la fecha, como lo que es: una conversación.
 *
 * La panadería propone un día y dice por qué; el cliente contraoferta otro y
 * dice por qué. Eso se guardaba desde hace tiempo y no se mostraba en ningún
 * lado: el cliente veía la fecha suelta, sin el motivo, y el administrador no
 * veía la contraoferta. Acá se lee de corrido, con el lado de cada mensaje y
 * la última resaltada, que es la que está sobre la mesa.
 *
 * Lo usan el detalle del cliente y el del panel: un solo componente para que
 * las dos partes vean exactamente lo mismo.
 */

const ETIQUETA = {
  propuesta:       'Propuso',
  propuesta_final: 'Contraofertó',
  aceptada:        'Aceptó la fecha',
  rechazada_final: 'No pudo con esa fecha',
};

const fechaCorta = (iso) => {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleDateString('es-CO', {
    weekday: 'short', day: 'numeric', month: 'short',
  });
};

export default function PropuestasFecha({ propuestas, compacto = false }) {
  const lista = propuestas || [];
  if (!lista.length) return null;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <p style={{
        fontSize: 9, fontWeight: 700, color: '#9e9e9e', letterSpacing: 1,
        textTransform: 'uppercase', margin: '0 0 2px',
      }}>
        Fecha de entrega · {lista.length} {lista.length === 1 ? 'propuesta' : 'propuestas'}
      </p>

      {lista.map((p, i) => {
        const esTienda = p.de === 'panaderia';
        const ultima   = i === lista.length - 1;
        const acuerdo  = p.tipo === 'aceptada';
        const borde    = acuerdo ? '#a5d6a7' : esTienda ? '#c5cae9' : '#ffe082';
        const fondo    = acuerdo ? '#f1f8e9' : esTienda ? '#f5f6ff' : '#fffdf5';
        const tinta    = acuerdo ? '#2e7d32' : esTienda ? '#3949ab' : '#a1740a';

        return (
          <div
            key={`${p.cuando || i}-${p.tipo}`}
            style={{
              display: 'flex', gap: 8, alignItems: 'flex-start',
              background: fondo,
              border: `1px solid ${borde}`,
              borderLeft: `3px solid ${tinta}`,
              borderRadius: 10,
              padding: compacto ? '7px 9px' : '9px 11px',
              opacity: ultima ? 1 : 0.72,
            }}
          >
            <div style={{ color: tinta, flexShrink: 0, marginTop: 1 }}>
              {acuerdo ? <Check size={13} />
                : esTienda ? <Store size={13} /> : <User size={13} />}
            </div>

            <div style={{ minWidth: 0, flex: 1 }}>
              <p style={{
                margin: 0, fontSize: 11, fontWeight: 800, color: tinta,
                display: 'flex', alignItems: 'center', gap: 5, flexWrap: 'wrap',
              }}>
                {esTienda ? 'La panadería' : 'Tú'} · {ETIQUETA[p.tipo] || p.tipo}
                {p.fecha && (
                  <span style={{
                    display: 'inline-flex', alignItems: 'center', gap: 3,
                    fontWeight: 700, color: '#424242',
                  }}>
                    <Calendar size={11} /> {fechaCorta(p.fecha)}
                  </span>
                )}
              </p>
              {p.motivo && (
                <p style={{
                  margin: '3px 0 0', fontSize: 11.5, color: '#5b5b5b',
                  lineHeight: 1.4, overflowWrap: 'anywhere',
                }}>
                  {p.motivo}
                </p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
