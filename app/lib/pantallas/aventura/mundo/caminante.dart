/// El caminante del mundo: reposo o marcha, un solo widget para los dos.
///
/// [Caminante] pinta el arte real (`Image.asset(ciclo.rutaDeMarcha(...))`)
/// en cuanto existe, y cae sola a `PintorDeCaminanteDeMentira` —un
/// rectángulo con dos "piernas" que alternan— cuando todavía no hay archivo
/// para esa combinación de familia/Orden/fotograma. No es una rama de
/// código a mano: es el `errorBuilder` de `Image.asset`, el mismo mecanismo
/// que ya usa `AvatarCapas` para caer a su pintor vectorial cuando falta una
/// capa. Así conviven, sin ningún `if`, las Órdenes que ya tienen piloto
/// real (Fase D) con las que todavía no (`docs/planes/mundo-caminable.md`).
///
/// Reposo y marcha comparten el mismo widget a propósito: son el mismo
/// problema (elegir un fotograma de un mismo ciclo y pintarlo), y separarlos
/// forzaría un cruce entre dos widgets justo al arrancar y frenar, que es
/// donde más se nota un salto.
library;

import 'package:flutter/material.dart';

import 'ciclo_marcha.dart';

/// El caminante en sí: sin posición ni cámara, solo el cuerpo que camina o
/// descansa en el sitio.
class Caminante extends StatefulWidget {
  const Caminante({
    super.key,
    required this.ciclo,
    this.alto = 120,
    this.avance,
    this.longitudDelTramo = 0,
    this.miraDerecha = true,
    this.semantica,
  });

  final CicloDeMarcha ciclo;

  /// Alto del caminante en pantalla, en dp.
  final double alto;

  /// `null`: en reposo, con su propio loop de reloj. No nulo: en marcha,
  /// sigue este progreso (`0..1`) para elegir el fotograma por distancia
  /// recorrida — nunca por la fase del reloj, ver `ciclo_marcha.dart`.
  final Animation<double>? avance;

  /// Cuánto mide, en dp, el tramo que recorre `avance` de 0 a 1. Solo hace
  /// falta cuando `avance` no es nulo.
  final double longitudDelTramo;

  /// El arte mira siempre de frente; esto decide el espejo horizontal.
  final bool miraDerecha;

  /// Nombre del aprendiz, para el `Semantics` — `null` en un spike sin uno real.
  final String? semantica;

  @override
  State<Caminante> createState() => _CaminanteState();
}

class _CaminanteState extends State<Caminante> with SingleTickerProviderStateMixin {
  late final AnimationController _reposo;

  @override
  void initState() {
    super.initState();
    _reposo = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1400),
    )..repeat();
  }

  @override
  void dispose() {
    _reposo.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final Animation<double>? avance = widget.avance;
    // Cuadrado, no un rectángulo angosto: el lienzo maestro del arte real es
    // 1024×1024 (misma convención que las capas del avatar detallado), y con
    // una caja más angosta que alta, `BoxFit.contain` la encoge al ancho —el
    // lado corto— y sobra alto vacío arriba y abajo: la figura terminaba
    // pintada a un 60 % del alto pedido. Con la caja cuadrada, el lienzo
    // entra exacto y la figura usa el alto completo.
    final Size medida = Size(widget.alto, widget.alto);
    return Semantics(
      label: widget.semantica,
      child: Transform.flip(
        flipX: !widget.miraDerecha,
        child: AnimatedBuilder(
          animation: avance ?? _reposo,
          builder: (BuildContext context, Widget? child) {
            final bool enMarcha = avance != null;
            final int fotograma = enMarcha
                ? widget.ciclo.fotogramaPorDistancia(avance.value * widget.longitudDelTramo)
                : widget.ciclo.fotogramaDeReposoPorFase(_reposo.value);
            final String ruta = enMarcha
                ? widget.ciclo.rutaDeMarcha(fotograma)
                : widget.ciclo.rutaDeReposo(fotograma);
            return SizedBox(
              width: medida.width,
              height: medida.height,
              child: Image.asset(
                ruta,
                height: medida.height,
                fit: BoxFit.contain,
                errorBuilder: (BuildContext context, Object error, StackTrace? pila) {
                  return CustomPaint(
                    size: medida,
                    painter: PintorDeCaminanteDeMentira(enMarcha: enMarcha, fotograma: fotograma),
                  );
                },
              ),
            );
          },
        ),
      ),
    );
  }
}

/// El caminante ya posicionado en el mundo: traduce el `Offset` del sendero
/// a un `Positioned` anclado en los pies (no en el centro — el disco del
/// spike anterior sí se centraba, pero una figura con pies tiene que pisar
/// el punto, no flotar sobre él con la mitad de su alto hundida en el suelo).
class CaminanteEnSenda extends StatelessWidget {
  const CaminanteEnSenda({
    super.key,
    required this.ciclo,
    required this.origen,
    required this.destino,
    required this.avance,
    this.alto = 120,
    this.semantica,
  });

  final CicloDeMarcha ciclo;
  final Offset origen;
  final Offset destino;

  /// Progreso `0..1` del tramo actual — normalmente el mismo
  /// `AnimationController` que ya mueve la cámara.
  final Animation<double> avance;

  final double alto;
  final String? semantica;

  @override
  Widget build(BuildContext context) {
    final double longitud = (destino - origen).distance;
    // El arte es de frente; espejo horizontal según hacia dónde se avanza.
    // `>= `, no `>`: un tramo vertical puro (misma x) no gira de espaldas.
    final bool miraDerecha = destino.dx >= origen.dx;
    // Mismo ancho que `Caminante` usa por dentro (cuadrado, `alto` × `alto`)
    // — si no coincide, el anclaje de los pies queda centrado sobre una caja
    // que no es la que en verdad se pinta.
    final double ancho = alto;

    // Origen y destino iguales (nada que recorrer, típicamente al llegar a
    // una parada y quedarse): `Caminante` con `avance` no nulo y longitud
    // cero congelaría el fotograma 0 de marcha para siempre en vez de
    // reproducir el reposo. Pasar `avance: null` es lo que de verdad activa
    // el loop de reposo — no basta con que la distancia sea cero.
    if (longitud < 0.5) {
      return Positioned(
        left: origen.dx - ancho / 2,
        top: origen.dy - alto,
        child: Caminante(
          ciclo: ciclo,
          alto: alto,
          miraDerecha: miraDerecha,
          semantica: semantica,
        ),
      );
    }

    return AnimatedBuilder(
      animation: avance,
      builder: (BuildContext context, Widget? child) {
        final Offset posicion = Offset.lerp(origen, destino, avance.value)!;
        return Positioned(
          left: posicion.dx - ancho / 2,
          top: posicion.dy - alto,
          child: child!,
        );
      },
      child: Caminante(
        ciclo: ciclo,
        alto: alto,
        avance: avance,
        longitudDelTramo: longitud,
        miraDerecha: miraDerecha,
        semantica: semantica,
      ),
    );
  }
}

/// El cuerpo del caminante mientras no hay arte real: un tronco y dos
/// "piernas" que alternan cuál va adelante, más el número del fotograma para
/// poder comprobar a ojo que el índice avanza bien. Se borra en cuanto
/// `Caminante` pinte `Image.asset` de verdad.
class PintorDeCaminanteDeMentira extends CustomPainter {
  const PintorDeCaminanteDeMentira({required this.enMarcha, required this.fotograma});

  final bool enMarcha;
  final int fotograma;

  @override
  void paint(Canvas canvas, Size size) {
    final Paint tronco = Paint()
      ..color = enMarcha ? const Color(0xFF6C5CE7) : const Color(0xFF74B9FF);
    final double altoTronco = size.height * 0.55;
    canvas.drawRect(Rect.fromLTWH(0, 0, size.width, altoTronco), tronco);

    // Dos piernas que alternan adelante/atrás con el fotograma. En reposo no
    // hay nada que alternar: los pies quedan juntos.
    final double anchoPierna = size.width * 0.32;
    final double altoPierna = size.height - altoTronco;
    final double corrimiento = enMarcha ? size.width * 0.16 : 0;
    final bool izquierdaAdelante = fotograma.isEven;
    final double dxIzquierda = izquierdaAdelante ? corrimiento : -corrimiento;
    final double dxDerecha = izquierdaAdelante ? -corrimiento : corrimiento;

    final Paint pierna = Paint()..color = const Color(0xFF2D3436);
    canvas.drawRect(
      Rect.fromLTWH(dxIzquierda, altoTronco, anchoPierna, altoPierna),
      pierna,
    );
    canvas.drawRect(
      Rect.fromLTWH(size.width - anchoPierna + dxDerecha, altoTronco, anchoPierna, altoPierna),
      pierna,
    );

    final TextPainter numero = TextPainter(
      text: TextSpan(
        text: '$fotograma',
        style: const TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.bold),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    numero.paint(
      canvas,
      Offset((size.width - numero.width) / 2, (altoTronco - numero.height) / 2),
    );
  }

  @override
  bool shouldRepaint(PintorDeCaminanteDeMentira oldDelegate) =>
      oldDelegate.enMarcha != enMarcha || oldDelegate.fotograma != fotograma;
}
