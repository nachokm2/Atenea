/// El caminante del mundo: reposo o marcha, un solo widget para los dos.
///
/// Fase B (`docs/planes/mundo-caminable.md`): todavía no hay arte real, así
/// que [Caminante] se pinta con un rectángulo y dos "piernas" que alternan
/// (`PintorDeCaminanteDeMentira`) — lo único que hace falta para juzgar el *timing*
/// real (¿patina al frenar?, ¿la cadencia se lee como caminar?) sin gastar
/// un centavo en arte. Cuando llegue el arte real (Fase D), este pintor se
/// reemplaza por `Image.asset(ciclo.rutaDeMarcha(fotograma))`; la posición,
/// el anclaje en los pies y el espejo de [CaminanteEnSenda] no cambian.
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
            return CustomPaint(
              size: Size(widget.alto * 0.6, widget.alto),
              painter: PintorDeCaminanteDeMentira(enMarcha: enMarcha, fotograma: fotograma),
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
    final double ancho = alto * 0.6;

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
