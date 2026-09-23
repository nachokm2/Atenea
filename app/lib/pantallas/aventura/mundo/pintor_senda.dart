/// El dibujo del sendero: la curva, sus portones y sus paradas.
///
/// Separado del widget que lo monta para que `shouldRepaint` sea barato y
/// honesto — compara la `Senda` (inmutable) y el progreso del caminante, no
/// reconstruye nada.
library;

import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/material.dart';

import '../../../design/tokens.dart';
import '../widgets/nodos_mapa.dart' show EstiloNodo, colorDeNodo;
import 'senda.dart';

/// Pinta la curva del sendero, sus portones y el marcador de cada parada.
///
/// Las paradas en sí no son parte del lienzo — son widgets `Positioned`
/// tocables (`ParadaMundo`, fuera de este archivo) para que conserven
/// `Semantics` y el área táctil mínima. Este pintor solo dibuja lo que
/// *conecta* a las paradas: el trazo, y un anillo detrás de cada una para
/// que el trazo no quede huérfano bajo el widget.
class PintorDeLaSenda extends CustomPainter {
  PintorDeLaSenda({
    required this.senda,
    required this.colorTransitado,
    required this.colorPendiente,
    required this.colorMasAlla,
  });

  final Senda senda;
  final Color colorTransitado;
  final Color colorPendiente;
  final Color colorMasAlla;

  @override
  void paint(Canvas canvas, Size size) {
    if (senda.estaVacia) return;
    _pintarTrazo(canvas);
    _pintarPortones(canvas);
  }

  void _pintarTrazo(Canvas canvas) {
    final ui.Path trazo = ui.Path();
    final double yInicio = senda.paradas.first.centro.dy;
    final double yFin = senda.paradas.last.centro.dy;
    const double paso = 4;
    bool primero = true;
    for (double y = yInicio; y <= yFin; y += paso) {
      final Offset p = puntoEnY(y, senda.tamano.width);
      if (primero) {
        trazo.moveTo(p.dx, p.dy);
        primero = false;
      } else {
        trazo.lineTo(p.dx, p.dy);
      }
    }

    final int ultimo = senda.ultimaAlcanzable;
    final double yLimite = ultimo < 0
        ? yInicio
        : (senda.centroDeParada(ultimo)?.dy ?? yInicio);

    final Paint pinturaTransitada = Paint()
      ..color = colorTransitado
      ..style = PaintingStyle.stroke
      ..strokeWidth = 6
      ..strokeCap = StrokeCap.round;
    final Paint pinturaPendiente = Paint()
      ..color = colorPendiente
      ..style = PaintingStyle.stroke
      ..strokeWidth = 6
      ..strokeCap = StrokeCap.round;
    final Paint pinturaMasAlla = Paint()
      ..color = colorMasAlla
      ..style = PaintingStyle.stroke
      ..strokeWidth = 6
      ..strokeCap = StrokeCap.round;

    // Tres tramos por color: hasta lo alcanzado, hasta el final de las
    // paradas conocidas, y —si el candado corta antes del final— el resto,
    // apenas insinuado.
    _pintarTramo(canvas, trazo, pinturaTransitada, 0, yLimite - yInicio);
    final double finConocido = yFin - yInicio;
    if (yLimite < yFin) {
      _pintarTramo(canvas, trazo, pinturaPendiente, yLimite - yInicio,
          math.min(finConocido, yLimite - yInicio + pasoDeParada));
      _pintarTramo(canvas, trazo, pinturaMasAlla,
          yLimite - yInicio + pasoDeParada, finConocido);
    }
  }

  void _pintarTramo(
    Canvas canvas,
    ui.Path trazoCompleto,
    Paint pintura,
    double desde,
    double hasta,
  ) {
    if (hasta <= desde) return;
    // La longitud de arco del trazo no es exactamente la altura recorrida
    // (el sendero serpentea en X) — se aproxima por fracción de altura, que
    // alcanza para el spike; la Fase 1 puede afinarlo si hace falta.
    final double alturaTotal = _alturaTotal();
    final ui.PathMetrics metricas = trazoCompleto.computeMetrics();
    for (final ui.PathMetric metrica in metricas) {
      final ui.Path extracto = metrica.extractPath(
        metrica.length * (desde / alturaTotal).clamp(0, 1),
        metrica.length * (hasta / alturaTotal).clamp(0, 1),
      );
      canvas.drawPath(extracto, pintura);
    }
  }

  double _alturaTotal() =>
      (senda.paradas.last.centro.dy - senda.paradas.first.centro.dy)
          .clamp(1, double.infinity);

  void _pintarPortones(Canvas canvas) {
    for (final PortonSenda porton in senda.portones) {
      final Paint pintura = Paint()
        ..color = porton.abierto ? colorTransitado : colorMasAlla
        ..style = PaintingStyle.stroke
        ..strokeWidth = 3;
      const double medioAncho = 34;
      canvas.drawLine(
        porton.centro.translate(-medioAncho, 0),
        porton.centro.translate(medioAncho, 0),
        pintura,
      );
      if (!porton.abierto) {
        // Un candado esquemático: dos trazos verticales cortos, para que el
        // portón cerrado se lea distinto del abierto sin depender solo del
        // color.
        canvas.drawLine(
          porton.centro.translate(-8, -6),
          porton.centro.translate(-8, 6),
          pintura,
        );
        canvas.drawLine(
          porton.centro.translate(8, -6),
          porton.centro.translate(8, 6),
          pintura,
        );
      }
    }
  }

  @override
  bool shouldRepaint(PintorDeLaSenda oldDelegate) =>
      oldDelegate.senda != senda ||
      oldDelegate.colorTransitado != colorTransitado ||
      oldDelegate.colorPendiente != colorPendiente ||
      oldDelegate.colorMasAlla != colorMasAlla;
}

/// Construye el pintor con los tres colores del trazo a partir de la paleta
/// activa: lo ya recorrido usa el mismo color que una parada `completado`.
PintorDeLaSenda pintorDeSenda(BuildContext context, Senda senda) {
  final AteneaPalette p = context.paleta;
  return PintorDeLaSenda(
    senda: senda,
    colorTransitado: colorDeNodo(context, EstiloNodo.completado),
    colorPendiente: p.borde,
    colorMasAlla: p.borde.withValues(alpha: 0.4),
  );
}
