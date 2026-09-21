/* Qué se puede tocar de un pedido según su estado, y por lo tanto cuándo tiene
   sentido abrir el editor. Vive fuera del componente para que Gestión de pedidos
   pueda preguntar antes de ofrecer el botón. */
export const PERMISOS_POR_ESTADO = {
  /* Editar un pedido es corregir CÓMO se paga y CÓMO se entrega. Nada más.
     Todo lo demás tiene su propio camino, con sus propias validaciones, y
     dejarlo entrar por acá es dejar que se las salte:

     - `productos` movía cantidades sin revisar stock ni reabrir la
       negociación de fecha, y sin recalcular el anticipo.
     - `descuento` escribía en `DetalleVenta.Descuento`, que en este esquema
       guarda el CRÉDITO que el cliente usó, no un descuento comercial: cada
       edición borraba el saldo a favor que el pedido ya había consumido. El
       descuento de verdad vive en `DescuentoXVenta`, atado a una promoción.
       El servidor ya no acepta ninguno de los dos campos.
     - El estado nunca estuvo acá, y así se queda: se mueve con sus acciones,
       que validan la transición. */
  "Pendiente": {
    cliente:           false,
    productos:         false,
    metodo_pago:       true,
    domicilio:         true,
    direccion_entrega: true,
    notas:             true,
    descuento:         false,
  },
  "Esperando pago": {
    cliente:           false,
    productos:         false,
    metodo_pago:       true,
    domicilio:         true,
    direccion_entrega: true,
    notas:             true,
    descuento:         false,
  },
  "En producción": {
    cliente:           false,
    productos:         false,
    metodo_pago:       true,
    domicilio:         false,
    direccion_entrega: true,
    notas:             true,
    descuento:         false,
  },
  "Listo": {
    cliente:           false,
    productos:         false,
    metodo_pago:       true,
    domicilio:         true,
    direccion_entrega: true,
    notas:             true,
    descuento:         false,
  },
  "En camino": {
    cliente:           false,
    productos:         false,
    metodo_pago:       false,
    domicilio:         false,
    direccion_entrega: true,
    notas:             true,
    descuento:         false,
  },
};


/* Estados donde el editor tiene algo que ofrecer. "Confirmado" no está en la
   tabla de arriba: el botón de editar se mostraba igual y el editor respondía
   con un cartel de "no editable". En camino queda fuera aparte, porque a esa
   altura el pedido ya va con el domiciliario. */
const NO_EDITABLES_EN_RUTA = ["Asignado", "En camino"];

export const puedeEditarsePedido = (estado) =>
  !!PERMISOS_POR_ESTADO[estado] && !NO_EDITABLES_EN_RUTA.includes(estado);
