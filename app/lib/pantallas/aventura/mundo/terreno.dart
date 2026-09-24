/// El terreno del mundo caminable: fondo ilustrado que se extiende sin
/// límite, en vez de un `CustomPainter` de líneas sobre un fondo liso.
///
/// Rodrigo, con el personaje ya aprobado: "el camino son solo flechas,
/// podemos hacerlo más un reino" — aclarado con `AskUserQuestion`: no eran
/// los íconos (eso se resolvió aparte, `_iconoDeReino`), era el camino y el
/// entorno; quiere "arte mucho más inmersivo", y ante la pregunta de forma
/// concreta eligió "todo el mundo como una ilustración única".
///
/// Eso choca con que los módulos de una Ruta se generan de a uno y el total
/// crece mientras el aprendiz usa la app (`senda.dart`: "la posición de la
/// parada `i` es una función de `i` sola, nunca de `i` y del total"). Una
/// ilustración única y fija no puede acompañar eso. La salida —elegida por
/// Rodrigo entre las alternativas planteadas— es la misma que usan mapas de
/// nivel tipo Candy Crush/Clash Royale: un terreno ilustrado diseñado para
/// repetirse/extenderse sin límite, con el camino y las paradas —lo que sí
/// cambia con cada aprendiz— dibujándose encima por código, en sus
/// posiciones reales. Ver `docs/planes/mundo-caminable.md`.
///
/// No es `Image.asset(repeat: ImageRepeat.repeatY)`: esa rejilla ancla la
/// fase del mosaico al `alignment` del `Image` (centrado, por defecto), así
/// que la fase cambia cada vez que `Senda.tamano.height` crece (240dp por
/// módulo nuevo) y el terreno entero se correría bajo el sendero. Acá cada
/// banda es un `Positioned` explícito anclado en `top: i * alto`, así que la
/// banda `i` queda donde estaba sin importar cuántos módulos se agreguen
/// después — la misma invariante que `senda.dart` ya aplica a las paradas.
library;

import 'package:flutter/material.dart';

/// El arte vive en un lienzo cuadrado — misma convención que ya usa el
/// caminante (`caminante.dart`: "el lienzo maestro del arte real es
/// 1024×1024"). La banda mide `ancho` de alto: a propósito NI 240 ni 480dp
/// (el paso entre paradas y su doble, `pasoDeParada`/`pasoDeParada*2` en
/// `senda.dart`) — si coincidiera, el terreno quedaría en fase con las
/// paradas y cada módulo repetiría el mismo detalle de arte exactamente en
/// el mismo punto del camino.
const double aspectoDelTramo = 1.0;

/// Las variantes del terreno, en orden. Con una sola (la Fase T2), el mundo
/// se ve repetido pero funciona igual: la cantidad de arte es un parámetro,
/// no una rama de código — la Fase T3 solo agrega entradas acá.
const List<String> tramosDeTerreno = <String>[
  'assets/arte/mundo/terreno/tramo_00.webp',
];

/// Color plano dominante del arte (a medir sobre la lámina real cuando
/// exista, no elegido a ojo) — pintado debajo de las bandas para que un
/// fotograma sin resolver, o una variante que falte, nunca abran un agujero
/// al fondo de la app.
const Color colorDeSuelo = Color(0xFF3B4A2F);

/// El fondo ilustrado del mundo, del alto de `tamano` — pensado para vivir
/// como el primer hijo del `Stack` de `_MundoState`, detrás del trazo, las
/// paradas y el caminante.
class TerrenoDelMundo extends StatelessWidget {
  const TerrenoDelMundo({super.key, required this.tamano});

  final Size tamano;

  @override
  Widget build(BuildContext context) {
    final double alto = tamano.width * aspectoDelTramo;
    final int bandas = (tamano.height / alto).ceil();
    return Stack(
      children: <Widget>[
        const Positioned.fill(child: ColoredBox(color: colorDeSuelo)),
        for (int i = 0; i < bandas; i++)
          Positioned(
            top: i * alto,
            left: 0,
            right: 0,
            height: alto,
            child: _Tramo(indice: i),
          ),
      ],
    );
  }
}

class _Tramo extends StatelessWidget {
  const _Tramo({required this.indice});

  final int indice;

  @override
  Widget build(BuildContext context) {
    // Función de `indice` SOLA — nunca del total de bandas: la misma regla
    // que `senda.dart` ya aplica a la posición de las paradas. Si dependiera
    // del total, cada módulo nuevo repintaría un terreno distinto bajo las
    // paradas ya visitadas.
    final String ruta = tramosDeTerreno[indice % tramosDeTerreno.length];
    // Duplica gratis el período visual (de N variantes a 2N bandas). Nunca
    // `flipY`: invertiría cielo/suelo dentro del propio tramo.
    final bool espejo = ((indice ~/ tramosDeTerreno.length) & 1) == 1;
    return Transform.flip(
      flipX: espejo,
      child: Image.asset(
        ruta,
        fit: BoxFit.cover,
        alignment: Alignment.topCenter,
        gaplessPlayback: true,
        errorBuilder: (BuildContext context, Object error, StackTrace? pila) =>
            const SizedBox.expand(),
      ),
    );
  }
}
