/// Vista previa del avatar por capas para la creación de personaje (P03).
///
/// El muñeco se compone en el mismo orden de apilado que usará el manifiesto
/// del servidor (§6.4 del documento de UX): capa → cuerpo → cuello → cabeza →
/// orejas → rostro → cabello → atuendo → hombreras → emblema. Cada capa se
/// dibuja a partir de los rasgos que viajarán a la API, de modo que cualquier
/// cambio se ve **al instante**, sin esperar a la red.
///
/// Cuando existan los recursos gráficos por capa, este pintor se sustituye por
/// un `Stack` de imágenes ordenadas por `z` sin tocar el resto de la pantalla.
library;

import 'package:flutter/material.dart';

import '../../../datos/repositorios.dart';
import '../../../design/components.dart';
import '../../../design/tokens.dart';
import 'catalogo_avatar.dart';

/// Colores del catálogo de assets que no dependen del tema (ojos y sombras
/// del muñeco), igual que los tonos de piel y de cabello.
const Color _blancoOjo = Color(0xFFF7F1E6);
const Color _pupila = Color(0xFF2A2438);

/// Retrato del personaje: marco de carta, aura de la Orden y muñeco por capas.
class LienzoAvatar extends StatelessWidget {
  const LienzoAvatar({
    required this.rasgos,
    required this.orden,
    super.key,
    this.alto = 220,
    this.ancho,
    this.conCapa = false,
    this.conMarco = true,
    this.conOrnamentos = true,
    this.semantica,
  });

  /// Rasgos elegidos, con las claves literales de la API.
  final RasgosAvatar rasgos;

  /// Orden elegida: define el atuendo y el emblema.
  final Arquetipo orden;

  /// Alto del retrato en dp.
  final double alto;

  /// Ancho del retrato; por defecto, proporción de carta (0,78 del alto).
  final double? ancho;

  /// Dibuja la capa del héroe sobre los hombros.
  final bool conCapa;

  /// Marco, aura y fondo de carta.
  final bool conMarco;

  /// Filigranas en las esquinas del marco.
  final bool conOrnamentos;

  /// Etiqueta para el lector de pantalla.
  final String? semantica;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette paleta = context.paleta;
    final OrdenVisual visual = CatalogoAvatar.orden(orden);
    final double w = ancho ?? alto * 0.78;

    final Widget figura = CustomPaint(
      painter: _PintorAvatar(
        rasgos: rasgos,
        visual: visual,
        conCapa: conCapa,
        aura: visual.acento,
      ),
      isComplex: true,
    );

    if (!conMarco) {
      return Semantics(
        label: semantica ?? _descripcion(visual),
        image: true,
        child: SizedBox(width: w, height: alto, child: figura),
      );
    }

    return Semantics(
      label: semantica ?? _descripcion(visual),
      image: true,
      child: AnimatedContainer(
        duration: Movimiento.corta,
        curve: Movimiento.estandar,
        width: w,
        height: alto,
        decoration: BoxDecoration(
          borderRadius: Redondeo.rTarjeta,
          border: Border.all(color: visual.acento.withValues(alpha: 0.55), width: 1.5),
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: <Color>[
              paleta.superficieElevada,
              Color.lerp(paleta.superficie, visual.principal, 0.22) ?? paleta.superficie,
            ],
          ),
          boxShadow: Sombra.brillo(visual.acento, 12),
        ),
        clipBehavior: Clip.antiAlias,
        child: Stack(
          fit: StackFit.expand,
          children: <Widget>[
            figura,
            if (conOrnamentos) ...<Widget>[
              Positioned(
                top: Espacio.xs,
                left: Espacio.xs,
                child: OrnamentoEsquina(color: visual.acento, tamano: 22),
              ),
              Positioned(
                top: Espacio.xs,
                right: Espacio.xs,
                child: Transform.flip(
                  flipX: true,
                  child: OrnamentoEsquina(color: visual.acento, tamano: 22),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  String _descripcion(OrdenVisual visual) {
    final String piel = CatalogoAvatar.tonosPiel
        .firstWhere((OpcionAvatar o) => o.clave == rasgos.tonoPiel,
            orElse: () => CatalogoAvatar.tonosPiel.first)
        .etiqueta;
    final String pelo = CatalogoAvatar.cabellos
        .firstWhere((OpcionAvatar o) => o.clave == rasgos.cabello,
            orElse: () => CatalogoAvatar.cabellos.first)
        .etiqueta;
    final String color = CatalogoAvatar.coloresCabello
        .firstWhere((OpcionAvatar o) => o.clave == rasgos.colorCabello,
            orElse: () => CatalogoAvatar.coloresCabello.first)
        .etiqueta;
    return 'Tu personaje: silueta ${rasgos.tipoCuerpo.etiqueta.toLowerCase()}, '
        'piel $piel, cabello $pelo de color $color, '
        'atuendo de la ${orden.etiqueta}.';
  }
}

// ---------------------------------------------------------------------------
// Pintor por capas
// ---------------------------------------------------------------------------

class _PintorAvatar extends CustomPainter {
  const _PintorAvatar({
    required this.rasgos,
    required this.visual,
    required this.conCapa,
    required this.aura,
  });

  final RasgosAvatar rasgos;
  final OrdenVisual visual;
  final bool conCapa;
  final Color aura;

  // Geometría del muñeco en coordenadas normalizadas (0–1 sobre el alto).
  static const double _cx = 0.5;
  static const double _cabezaY = 0.335;
  static const double _cabezaRx = 0.112;
  static const double _cabezaRy = 0.132;

  @override
  void paint(Canvas canvas, Size size) {
    final double s = size.height;
    Offset p(double x, double y) =>
        Offset(size.width / 2 + (x - _cx) * s, y * s);
    double u(double v) => v * s;

    final Color piel = CatalogoAvatar.piel(rasgos.tonoPiel);
    final Color pelo = CatalogoAvatar.cabello(rasgos.colorCabello);
    final double hw = switch (rasgos.tipoCuerpo) {
      TipoCuerpo.esbelto => 0.138,
      TipoCuerpo.robusto => 0.188,
      TipoCuerpo.neutro => 0.160,
    };

    _aura(canvas, size, p, u);
    if (conCapa) _capa(canvas, p, u, hw);
    _cabelloDetras(canvas, p, u, pelo);
    _cuello(canvas, p, u, piel);
    _torso(canvas, p, u, hw);
    _hombreras(canvas, p, u, hw);
    _cinturon(canvas, p, u, hw);
    _emblema(canvas, p, u);
    _cabeza(canvas, p, u, piel);
    _orejas(canvas, p, u, piel);
    _rostro(canvas, p, u);
    _cabelloDelante(canvas, p, u, pelo);
  }

  // --- Capas ---------------------------------------------------------------

  void _aura(Canvas canvas, Size size, Offset Function(double, double) p,
      double Function(double) u) {
    final Rect caja = Rect.fromCircle(center: p(_cx, 0.42), radius: u(0.46));
    canvas.drawCircle(
      caja.center,
      caja.width / 2,
      Paint()
        ..shader = RadialGradient(
          colors: <Color>[
            aura.withValues(alpha: 0.24),
            aura.withValues(alpha: 0.0),
          ],
        ).createShader(caja),
    );
  }

  void _capa(Canvas canvas, Offset Function(double, double) p,
      double Function(double) u, double hw) {
    final Path capa = Path()
      ..moveTo(p(_cx - hw * 1.05, 0.545).dx, p(_cx, 0.545).dy)
      ..quadraticBezierTo(
        p(_cx - hw * 1.9, 0.80).dx,
        p(_cx, 0.80).dy,
        p(_cx - hw * 1.85, 1.02).dx,
        p(_cx, 1.02).dy,
      )
      ..lineTo(p(_cx + hw * 1.85, 1.02).dx, p(_cx, 1.02).dy)
      ..quadraticBezierTo(
        p(_cx + hw * 1.9, 0.80).dx,
        p(_cx, 0.80).dy,
        p(_cx + hw * 1.05, 0.545).dx,
        p(_cx, 0.545).dy,
      )
      ..close();
    canvas.drawPath(capa, Paint()..color = _oscurecer(visual.principal, 0.28));
    canvas.drawPath(
      capa,
      Paint()
        ..color = visual.acento.withValues(alpha: 0.55)
        ..style = PaintingStyle.stroke
        ..strokeWidth = u(0.008),
    );
  }

  void _cuello(Canvas canvas, Offset Function(double, double) p,
      double Function(double) u, Color piel) {
    final Rect cuello = Rect.fromCenter(
      center: p(_cx, 0.468),
      width: u(0.085),
      height: u(0.085),
    );
    canvas.drawRRect(
      RRect.fromRectAndRadius(cuello, Radius.circular(u(0.022))),
      Paint()..color = _oscurecer(piel, 0.12),
    );
  }

  void _torso(Canvas canvas, Offset Function(double, double) p,
      double Function(double) u, double hw) {
    final Path torso = Path()
      ..moveTo(p(_cx - 0.048, 0.470).dx, p(_cx, 0.470).dy)
      ..lineTo(p(_cx + 0.048, 0.470).dx, p(_cx, 0.470).dy)
      ..quadraticBezierTo(
        p(_cx + hw, 0.500).dx,
        p(_cx, 0.500).dy,
        p(_cx + hw, 0.610).dx,
        p(_cx, 0.610).dy,
      )
      ..lineTo(p(_cx + hw * 1.06, 1.02).dx, p(_cx, 1.02).dy)
      ..lineTo(p(_cx - hw * 1.06, 1.02).dx, p(_cx, 1.02).dy)
      ..lineTo(p(_cx - hw, 0.610).dx, p(_cx, 0.610).dy)
      ..quadraticBezierTo(
        p(_cx - hw, 0.500).dx,
        p(_cx, 0.500).dy,
        p(_cx - 0.048, 0.470).dx,
        p(_cx, 0.470).dy,
      )
      ..close();

    final Rect caja = torso.getBounds();
    canvas.drawPath(
      torso,
      Paint()
        ..shader = LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: <Color>[
            _aclarar(visual.principal, 0.12),
            _oscurecer(visual.principal, 0.18),
          ],
        ).createShader(caja),
    );

    // Escote en V con el ribete de la Orden.
    final Path escote = Path()
      ..moveTo(p(_cx - 0.055, 0.474).dx, p(_cx, 0.474).dy)
      ..quadraticBezierTo(
        p(_cx, 0.545).dx,
        p(_cx, 0.545).dy,
        p(_cx + 0.055, 0.474).dx,
        p(_cx, 0.474).dy,
      );
    canvas.drawPath(
      escote,
      Paint()
        ..color = visual.acento
        ..style = PaintingStyle.stroke
        ..strokeWidth = u(0.014)
        ..strokeCap = StrokeCap.round,
    );
  }

  void _hombreras(Canvas canvas, Offset Function(double, double) p,
      double Function(double) u, double hw) {
    for (final double lado in <double>[-1, 1]) {
      final Rect hombro = Rect.fromCenter(
        center: p(_cx + lado * hw * 0.92, 0.565),
        width: u(hw * 0.98),
        height: u(0.105),
      );
      canvas.drawArc(
        hombro,
        3.14159,
        3.14159,
        true,
        Paint()
          ..shader = LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: <Color>[
              _aclarar(visual.metal, 0.18),
              _oscurecer(visual.metal, 0.25),
            ],
          ).createShader(hombro),
      );
      canvas.drawArc(
        hombro,
        3.14159,
        3.14159,
        false,
        Paint()
          ..color = _oscurecer(visual.metal, 0.45)
          ..style = PaintingStyle.stroke
          ..strokeWidth = u(0.006),
      );
    }
  }

  void _cinturon(Canvas canvas, Offset Function(double, double) p,
      double Function(double) u, double hw) {
    final Rect cinto = Rect.fromCenter(
      center: p(_cx, 0.905),
      width: u(hw * 2.1),
      height: u(0.058),
    );
    canvas.drawRRect(
      RRect.fromRectAndRadius(cinto, Radius.circular(u(0.012))),
      Paint()..color = _oscurecer(visual.acento, 0.30),
    );
    canvas.drawCircle(
      p(_cx, 0.905),
      u(0.026),
      Paint()..color = visual.metal,
    );
    canvas.drawCircle(
      p(_cx, 0.905),
      u(0.026),
      Paint()
        ..color = _oscurecer(visual.metal, 0.45)
        ..style = PaintingStyle.stroke
        ..strokeWidth = u(0.005),
    );
  }

  void _emblema(Canvas canvas, Offset Function(double, double) p,
      double Function(double) u) {
    final double tamano = u(0.115);
    final TextPainter pintor = TextPainter(
      text: TextSpan(
        text: String.fromCharCode(visual.emblema.codePoint),
        style: TextStyle(
          fontSize: tamano,
          fontFamily: visual.emblema.fontFamily,
          package: visual.emblema.fontPackage,
          color: visual.acento.withValues(alpha: 0.92),
        ),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    final Offset centro = p(_cx, 0.700);
    pintor.paint(
      canvas,
      Offset(centro.dx - pintor.width / 2, centro.dy - pintor.height / 2),
    );
  }

  void _cabeza(Canvas canvas, Offset Function(double, double) p,
      double Function(double) u, Color piel) {
    final Rect cabeza = Rect.fromCenter(
      center: p(_cx, _cabezaY),
      width: u(_cabezaRx * 2),
      height: u(_cabezaRy * 2),
    );
    canvas.drawOval(
      cabeza,
      Paint()
        ..shader = LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: <Color>[_aclarar(piel, 0.10), _oscurecer(piel, 0.10)],
        ).createShader(cabeza),
    );
  }

  void _orejas(Canvas canvas, Offset Function(double, double) p,
      double Function(double) u, Color piel) {
    final Paint tinta = Paint()..color = _oscurecer(piel, 0.06);
    final bool puntiagudas = rasgos.orejas == 'pointed';
    for (final double lado in <double>[-1, 1]) {
      if (puntiagudas) {
        final Path oreja = Path()
          ..moveTo(p(_cx + lado * _cabezaRx * 0.86, 0.385).dx, p(_cx, 0.385).dy)
          ..lineTo(p(_cx + lado * _cabezaRx * 1.62, 0.268).dx, p(_cx, 0.268).dy)
          ..lineTo(p(_cx + lado * _cabezaRx * 0.86, 0.318).dx, p(_cx, 0.318).dy)
          ..close();
        canvas.drawPath(oreja, tinta);
      } else {
        canvas.drawCircle(
          p(_cx + lado * _cabezaRx * 0.98, 0.352),
          u(0.028),
          tinta,
        );
      }
    }
  }

  void _rostro(Canvas canvas, Offset Function(double, double) p,
      double Function(double) u) {
    final int cara = CatalogoAvatar.indiceRostro(rasgos.rostro);
    final double ojoY = 0.343;
    final double ojoX = 0.046;
    final double altoOjo = switch (cara) {
      1 => 0.014,
      3 => 0.013,
      _ => 0.018,
    };

    for (final double lado in <double>[-1, 1]) {
      final Rect ojo = Rect.fromCenter(
        center: p(_cx + lado * ojoX, ojoY),
        width: u(0.050),
        height: u(altoOjo * 2),
      );
      canvas.drawOval(ojo, Paint()..color = _blancoOjo);
      canvas.drawCircle(p(_cx + lado * ojoX, ojoY), u(0.013), Paint()..color = _pupila);
      canvas.drawCircle(
        p(_cx + lado * ojoX - 0.005, ojoY - 0.005),
        u(0.004),
        Paint()..color = _blancoOjo.withValues(alpha: 0.9),
      );

      // Cejas: su inclinación es lo que define el gesto.
      final double cejaY = ojoY - 0.043;
      final double caidaExterior = switch (cara) {
        0 => 0.004,
        1 => -0.008,
        2 => 0.010,
        _ => -0.014,
      };
      final Path ceja = Path()
        ..moveTo(p(_cx + lado * (ojoX + 0.030), cejaY + caidaExterior).dx,
            p(_cx, cejaY + caidaExterior).dy)
        ..quadraticBezierTo(
          p(_cx + lado * ojoX, cejaY - 0.010).dx,
          p(_cx, cejaY - 0.010).dy,
          p(_cx + lado * (ojoX - 0.026), cejaY).dx,
          p(_cx, cejaY).dy,
        );
      canvas.drawPath(
        ceja,
        Paint()
          ..color = _pupila.withValues(alpha: 0.85)
          ..style = PaintingStyle.stroke
          ..strokeWidth = u(cara == 3 ? 0.013 : 0.010)
          ..strokeCap = StrokeCap.round,
      );
    }

    // Nariz: un trazo mínimo.
    canvas.drawLine(
      p(_cx, 0.372),
      p(_cx + 0.010, 0.390),
      Paint()
        ..color = _pupila.withValues(alpha: 0.28)
        ..strokeWidth = u(0.006)
        ..strokeCap = StrokeCap.round,
    );

    // Boca: la curvatura cambia con el rostro.
    final double curva = switch (cara) {
      0 => 0.020,
      1 => 0.004,
      2 => 0.030,
      _ => -0.010,
    };
    final Path boca = Path()
      ..moveTo(p(_cx - 0.030, 0.410).dx, p(_cx, 0.410).dy)
      ..quadraticBezierTo(
        p(_cx, 0.410 + curva).dx,
        p(_cx, 0.410 + curva).dy,
        p(_cx + 0.030, 0.410).dx,
        p(_cx, 0.410).dy,
      );
    canvas.drawPath(
      boca,
      Paint()
        ..color = _pupila.withValues(alpha: 0.7)
        ..style = PaintingStyle.stroke
        ..strokeWidth = u(0.009)
        ..strokeCap = StrokeCap.round,
    );
  }

  void _cabelloDetras(Canvas canvas, Offset Function(double, double) p,
      double Function(double) u, Color pelo) {
    final int estilo = CatalogoAvatar.indiceCabello(rasgos.cabello);
    final bool hayMelena = estilo == 1 || estilo == 2 || estilo == 6;
    if (!hayMelena) return;

    final double abajo = estilo == 2 ? 0.68 : 0.58;
    final Rect melena = Rect.fromCenter(
      center: p(_cx, (0.24 + abajo) / 2),
      width: u(_cabezaRx * 2.75),
      height: u(abajo - 0.24),
    );
    canvas.drawRRect(
      RRect.fromRectAndRadius(melena, Radius.circular(u(0.09))),
      Paint()..color = _oscurecer(pelo, 0.22),
    );
  }

  void _cabelloDelante(Canvas canvas, Offset Function(double, double) p,
      double Function(double) u, Color pelo) {
    final int estilo = CatalogoAvatar.indiceCabello(rasgos.cabello);
    final Paint tinta = Paint()..color = pelo;
    final Paint sombra = Paint()..color = _oscurecer(pelo, 0.18);

    // Casquete común a todos los estilos, más bajo en el rapado.
    final double alto = estilo == 7 ? 0.232 : 0.196;
    final Path casquete = Path()
      ..moveTo(p(_cx - _cabezaRx * 1.08, 0.362).dx, p(_cx, 0.362).dy)
      ..quadraticBezierTo(
        p(_cx - _cabezaRx * 1.20, alto).dx,
        p(_cx, alto).dy,
        p(_cx, alto).dx,
        p(_cx, alto).dy,
      )
      ..quadraticBezierTo(
        p(_cx + _cabezaRx * 1.20, alto).dx,
        p(_cx, alto).dy,
        p(_cx + _cabezaRx * 1.08, 0.362).dx,
        p(_cx, 0.362).dy,
      )
      ..quadraticBezierTo(
        p(_cx + _cabezaRx * 0.92, 0.300).dx,
        p(_cx, 0.300).dy,
        p(_cx + _cabezaRx * 0.46, 0.290).dx,
        p(_cx, 0.290).dy,
      )
      ..quadraticBezierTo(
        p(_cx, 0.262).dx,
        p(_cx, 0.262).dy,
        p(_cx - _cabezaRx * 0.46, 0.290).dx,
        p(_cx, 0.290).dy,
      )
      ..quadraticBezierTo(
        p(_cx - _cabezaRx * 0.92, 0.300).dx,
        p(_cx, 0.300).dy,
        p(_cx - _cabezaRx * 1.08, 0.362).dx,
        p(_cx, 0.362).dy,
      )
      ..close();
    canvas.drawPath(casquete, estilo == 7 ? sombra : tinta);

    switch (estilo) {
      case 1: // Ondulada: dos mechones laterales.
        for (final double lado in <double>[-1, 1]) {
          final Rect mecha = Rect.fromCenter(
            center: p(_cx + lado * _cabezaRx * 1.12, 0.420),
            width: u(0.062),
            height: u(0.185),
          );
          canvas.drawRRect(
            RRect.fromRectAndRadius(mecha, Radius.circular(u(0.030))),
            tinta,
          );
        }
      case 2: // Larga: mechones hasta el pecho.
        for (final double lado in <double>[-1, 1]) {
          final Rect mecha = Rect.fromCenter(
            center: p(_cx + lado * _cabezaRx * 1.18, 0.480),
            width: u(0.058),
            height: u(0.300),
          );
          canvas.drawRRect(
            RRect.fromRectAndRadius(mecha, Radius.circular(u(0.028))),
            tinta,
          );
        }
      case 3: // Coleta atada atrás.
        canvas.drawCircle(p(_cx + _cabezaRx * 1.18, 0.286), u(0.030), sombra);
        final Path coleta = Path()
          ..moveTo(p(_cx + _cabezaRx * 1.12, 0.292).dx, p(_cx, 0.292).dy)
          ..quadraticBezierTo(
            p(_cx + _cabezaRx * 2.00, 0.400).dx,
            p(_cx, 0.400).dy,
            p(_cx + _cabezaRx * 1.30, 0.520).dx,
            p(_cx, 0.520).dy,
          );
        canvas.drawPath(
          coleta,
          Paint()
            ..color = pelo
            ..style = PaintingStyle.stroke
            ..strokeWidth = u(0.050)
            ..strokeCap = StrokeCap.round,
        );
      case 4: // Rizada: corona de bucles.
        for (int i = 0; i < 7; i++) {
          final double t = i / 6;
          final double x = _cx - _cabezaRx * 1.05 + t * _cabezaRx * 2.10;
          final double y = 0.268 - 0.052 * (1 - (2 * t - 1).abs());
          canvas.drawCircle(p(x, y), u(0.042), tinta);
        }
      case 5: // Moño alto.
        canvas.drawCircle(p(_cx, 0.176), u(0.056), tinta);
        canvas.drawCircle(
          p(_cx, 0.176),
          u(0.056),
          Paint()
            ..color = _oscurecer(pelo, 0.30)
            ..style = PaintingStyle.stroke
            ..strokeWidth = u(0.006),
        );
      case 6: // Trenzas: dos cuerdas con sus nudos.
        for (final double lado in <double>[-1, 1]) {
          final double x = _cx + lado * _cabezaRx * 1.16;
          final Rect trenza = Rect.fromCenter(
            center: p(x, 0.470),
            width: u(0.050),
            height: u(0.280),
          );
          canvas.drawRRect(
            RRect.fromRectAndRadius(trenza, Radius.circular(u(0.025))),
            tinta,
          );
          for (int i = 0; i < 3; i++) {
            canvas.drawCircle(p(x, 0.390 + i * 0.070), u(0.027), sombra);
          }
        }
      default:
        break;
    }

    if (estilo != 7) {
      // Reflejo: una sola pincelada, discreta.
      final Path brillo = Path()
        ..moveTo(p(_cx - _cabezaRx * 0.70, 0.256).dx, p(_cx, 0.256).dy)
        ..quadraticBezierTo(
          p(_cx - _cabezaRx * 0.10, 0.228).dx,
          p(_cx, 0.228).dy,
          p(_cx + _cabezaRx * 0.42, 0.250).dx,
          p(_cx, 0.250).dy,
        );
      canvas.drawPath(
        brillo,
        Paint()
          ..color = _aclarar(pelo, 0.42).withValues(alpha: 0.55)
          ..style = PaintingStyle.stroke
          ..strokeWidth = u(0.016)
          ..strokeCap = StrokeCap.round,
      );
    }
  }

  @override
  bool shouldRepaint(covariant _PintorAvatar anterior) =>
      anterior.conCapa != conCapa ||
      anterior.aura != aura ||
      anterior.visual.principal != visual.principal ||
      anterior.visual.emblema != visual.emblema ||
      anterior.rasgos.tipoCuerpo != rasgos.tipoCuerpo ||
      anterior.rasgos.tonoPiel != rasgos.tonoPiel ||
      anterior.rasgos.rostro != rasgos.rostro ||
      anterior.rasgos.orejas != rasgos.orejas ||
      anterior.rasgos.cabello != rasgos.cabello ||
      anterior.rasgos.colorCabello != rasgos.colorCabello;
}

/// Aclara un color del catálogo sin salirse de su tono.
Color _aclarar(Color c, double t) {
  final HSLColor h = HSLColor.fromColor(c);
  return h.withLightness((h.lightness + t).clamp(0.0, 1.0)).toColor();
}

/// Oscurece un color del catálogo sin salirse de su tono.
Color _oscurecer(Color c, double t) {
  final HSLColor h = HSLColor.fromColor(c);
  return h.withLightness((h.lightness - t).clamp(0.0, 1.0)).toColor();
}
