/// Ilustraciones del onboarding (P01): tres escenas que cuentan la promesa.
///
/// No hay recursos gráficos todavía, así que las escenas se pintan con el
/// mismo lenguaje visual del resto de la app: fondo nocturno, constelación de
/// nodos y el avatar que va ganando equipo. El muñeco es el mismo
/// [LienzoAvatar] de la creación de personaje, para que la promesa de la
/// pantalla 3 se cumpla literalmente dos minutos después.
library;

import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../../datos/repositorios.dart';
import '../../../design/tokens.dart';
import 'avatar_lienzo.dart';

/// Una de las tres escenas del onboarding.
class IlustracionOnboarding extends StatelessWidget {
  const IlustracionOnboarding({required this.paso, super.key, this.alto = 208});

  /// 0: cargar material · 1: la ruta se construye · 2: el héroe crece.
  final int paso;

  final double alto;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette paleta = context.paleta;

    const RasgosAvatar rasgos = RasgosAvatar(
      tonoPiel: 'skin_03',
      rostro: 'face_01',
      cabello: 'hair_02',
      colorCabello: 'hair_brown',
    );

    return ExcludeSemantics(
      child: SizedBox(
        height: alto,
        child: Stack(
          alignment: Alignment.center,
          children: <Widget>[
            Positioned.fill(
              child: CustomPaint(
                painter: _PintorEscena(
                  paso: paso,
                  tenue: paleta.textoSecundario,
                  arcano: paleta.arcano,
                  oro: paleta.oro,
                  superficie: paleta.superficie,
                  borde: paleta.borde,
                  dominio: paleta.dominio,
                ),
              ),
            ),
            LienzoAvatar(
              rasgos: rasgos,
              orden: paso == 2 ? Arquetipo.arcano : Arquetipo.acero,
              alto: alto * 0.74,
              conCapa: paso == 2,
              conMarco: false,
              semantica: '',
            ),
          ],
        ),
      ),
    );
  }
}

class _PintorEscena extends CustomPainter {
  const _PintorEscena({
    required this.paso,
    required this.tenue,
    required this.arcano,
    required this.oro,
    required this.superficie,
    required this.borde,
    required this.dominio,
  });

  final int paso;
  final Color tenue;
  final Color arcano;
  final Color oro;
  final Color superficie;
  final Color borde;
  final Color dominio;

  @override
  void paint(Canvas canvas, Size size) {
    _estrellas(canvas, size);
    switch (paso) {
      case 0:
        _pergaminos(canvas, size);
      case 1:
        _sendero(canvas, size);
      default:
        _ascenso(canvas, size);
    }
  }

  /// Polvo de estrellas determinista: la misma escena en cada reconstrucción.
  void _estrellas(Canvas canvas, Size size) {
    final math.Random azar = math.Random(7 + paso);
    final Paint tinta = Paint()..color = tenue.withValues(alpha: 0.35);
    for (int i = 0; i < 28; i++) {
      final double x = azar.nextDouble() * size.width;
      final double y = azar.nextDouble() * size.height;
      canvas.drawCircle(Offset(x, y), azar.nextDouble() * 1.6 + 0.5, tinta);
    }
  }

  /// Escena 1: hojas de material flotando hacia el héroe.
  void _pergaminos(Canvas canvas, Size size) {
    final List<Offset> centros = <Offset>[
      Offset(size.width * 0.16, size.height * 0.30),
      Offset(size.width * 0.84, size.height * 0.38),
      Offset(size.width * 0.20, size.height * 0.72),
    ];
    final List<double> giros = <double>[-0.22, 0.26, 0.12];

    for (int i = 0; i < centros.length; i++) {
      canvas
        ..save()
        ..translate(centros[i].dx, centros[i].dy)
        ..rotate(giros[i]);

      final Rect hoja = Rect.fromCenter(
        center: Offset.zero,
        width: size.width * 0.20,
        height: size.width * 0.26,
      );
      canvas
        ..drawRRect(
          RRect.fromRectAndRadius(hoja, const Radius.circular(Redondeo.chip)),
          Paint()..color = superficie,
        )
        ..drawRRect(
          RRect.fromRectAndRadius(hoja, const Radius.circular(Redondeo.chip)),
          Paint()
            ..color = borde
            ..style = PaintingStyle.stroke
            ..strokeWidth = 1.2,
        );

      final Paint renglon = Paint()
        ..color = tenue.withValues(alpha: 0.55)
        ..strokeWidth = 2
        ..strokeCap = StrokeCap.round;
      for (int r = 0; r < 4; r++) {
        final double y = hoja.top + hoja.height * (0.24 + r * 0.18);
        final double ancho = hoja.width * (r == 3 ? 0.42 : 0.62);
        canvas.drawLine(
          Offset(hoja.left + hoja.width * 0.18, y),
          Offset(hoja.left + hoja.width * 0.18 + ancho, y),
          renglon,
        );
      }
      canvas.restore();
    }
  }

  /// Escena 2: el sendero de nodos que la IA traza con ese material.
  void _sendero(Canvas canvas, Size size) {
    final Path camino = Path()
      ..moveTo(size.width * 0.10, size.height * 0.84)
      ..quadraticBezierTo(
        size.width * 0.28,
        size.height * 0.44,
        size.width * 0.50,
        size.height * 0.52,
      )
      ..quadraticBezierTo(
        size.width * 0.74,
        size.height * 0.60,
        size.width * 0.90,
        size.height * 0.20,
      );

    canvas.drawPath(
      camino,
      Paint()
        ..color = arcano.withValues(alpha: 0.45)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 3
        ..strokeCap = StrokeCap.round,
    );

    final List<Offset> nodos = <Offset>[
      Offset(size.width * 0.10, size.height * 0.84),
      Offset(size.width * 0.29, size.height * 0.55),
      Offset(size.width * 0.71, size.height * 0.57),
      Offset(size.width * 0.90, size.height * 0.20),
    ];
    for (int i = 0; i < nodos.length; i++) {
      final bool hecho = i < 2;
      canvas
        ..drawCircle(
          nodos[i],
          hecho ? 11 : 9,
          Paint()..color = hecho ? arcano : superficie,
        )
        ..drawCircle(
          nodos[i],
          hecho ? 11 : 9,
          Paint()
            ..color = hecho ? arcano : borde
            ..style = PaintingStyle.stroke
            ..strokeWidth = 2,
        );
    }
  }

  /// Escena 3: el héroe sube de nivel y estrena equipo.
  void _ascenso(Canvas canvas, Size size) {
    final Offset centro = Offset(size.width / 2, size.height * 0.52);

    // Rayos de luz detrás del avatar.
    final Paint rayo = Paint()
      ..color = oro.withValues(alpha: 0.18)
      ..strokeWidth = 4
      ..strokeCap = StrokeCap.round;
    for (int i = 0; i < 12; i++) {
      final double angulo = i * math.pi / 6;
      canvas.drawLine(
        centro + Offset(math.cos(angulo), math.sin(angulo)) * (size.height * 0.30),
        centro + Offset(math.cos(angulo), math.sin(angulo)) * (size.height * 0.44),
        rayo,
      );
    }

    // Chispas de dominio.
    final math.Random azar = math.Random(11);
    final Paint chispa = Paint()..color = dominio.withValues(alpha: 0.75);
    for (int i = 0; i < 10; i++) {
      final double angulo = azar.nextDouble() * math.pi * 2;
      final double radio = size.height * (0.22 + azar.nextDouble() * 0.20);
      canvas.drawCircle(
        centro + Offset(math.cos(angulo), math.sin(angulo)) * radio,
        azar.nextDouble() * 2.4 + 1.2,
        chispa,
      );
    }
  }

  @override
  bool shouldRepaint(covariant _PintorEscena anterior) =>
      anterior.paso != paso ||
      anterior.arcano != arcano ||
      anterior.oro != oro ||
      anterior.superficie != superficie;
}
