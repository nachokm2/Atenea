# Arte del Reino

Aquí viven las ilustraciones originales. La app **no** las usa tal cual: consume
las versiones procesadas que quedan en `app/assets/arte/`.

## Qué hay

`originales/` contiene los 43 PNG entregados, repartidos en ocho categorías:
seis figuras de personaje, seis peinados y 31 objetos (cabeza, cuerpo, capa,
botas, armas y accesorios). Pesan 78 MB en total.

## Por qué hay un paso intermedio

Los archivos originales traen tres problemas que impiden usarlos en un teléfono:

1. **No tienen transparencia.** El damero que parece fondo transparente está
   pintado en los píxeles: son PNG en RGB, sin canal alfa. Puestos en la app se
   verían con su tablero de ajedrez alrededor.
2. **Pesan demasiado.** Entre 1,5 y 2,4 MB cada uno. Meterlos sin más añadiría
   78 MB al instalador.
3. **Cada uno llena su propio lienzo**, con 28 tamaños distintos y sin un margen
   común.

## Cómo se procesan

```bash
python scripts/preparar_arte.py --origen arte/originales --destino app/assets/arte
```

El script deduce los dos tonos del damero mirando la franja de borde de **cada**
imagen (no todas lo traen igual de claro), lo recorta con un relleno que crece
desde los bordes y se detiene en el contorno del dibujo, descarta las motas
sueltas que quedan, recorta al contenido real y guarda en WebP con alfa.

Resultado: de 78 MB a 1,8 MB, un 97,6 % menos, sin pérdida visible.

La opción `--informe` dice qué haría sin escribir nada.

## Qué no se puede hacer con este arte

El avatar **no se compone apilando prendas**. Las piezas son ilustraciones de
catálogo: cada una está dibujada a su propia escala y la figura base ya viene
vestida, así que no existe un sistema de anclas que permita ponerle encima una
armadura. Por eso la app elige una figura completa entre seis y muestra el
equipamiento como fichas, no superpuesto.

Para llegar al muñeco de papel del documento de diseño haría falta un encargo
distinto: un cuerpo base neutro y cada prenda dibujada sobre ese mismo cuerpo,
recortada y exportada con transparencia real, en un lienzo común. El servidor ya
envía la pila de dibujado en `render_manifest`, así que el día que exista ese
pack solo hay que cambiar el widget `AvatarCapas`.

## Cobertura actual

37 de las 43 ilustraciones están asignadas a los 46 ítems del catálogo; algunas
se comparten entre piezas de la misma familia (los cinco escudos usan el mismo
dibujo, por ejemplo). Lo que todavía no tiene arte cae al icono de su ranura,
que es un marcador honesto: se nota que falta, no se finge que existe.

Quedan sin asignar y disponibles: bolso, cinturón, poción, pergamino y los seis
peinados. El mapa vive en `app/lib/design/arte.dart`.

Sin arte propio todavía: los dos pares de guantes del catálogo.
