/// Render del avatar por capas (§6.4 del documento de experiencia).
///
/// El servidor manda siempre el manifiesto de capas ya ordenado por z; el
/// cliente nunca lo recompone. Mientras el arte definitivo no exista, cada
/// capa se dibuja como una silueta vectorial teñida con el `tint` que envía el
/// manifiesto o, si no viene, con un color semántico de los tokens. Así el
/// Vestidor y el Mercado ya muestran el cambio al equipar sin esperar a los
/// recursos gráficos.
library;

import 'package:flutter/material.dart';

import '../../../datos/repositorios.dart';
import '../../../design/arte.dart';
import '../../../design/tokens.dart';

/// Compone una vista previa: las capas actuales con las de [item] puestas en
/// su ranura.
List<CapaAvatar> capasConItem(List<CapaAvatar> base, Item item) {
  final List<CapaAvatar> compuestas = <CapaAvatar>[
    for (final CapaAvatar c in base)
      if (c.ranura != item.ranura) c,
    if (item.capas.isNotEmpty)
      ...item.capas
    else
      CapaAvatar(
        clave: item.codigo.isEmpty ? item.id : item.codigo,
        ranura: item.ranura,
        itemId: item.id,
        z: 50,
      ),
  ]..sort((CapaAvatar a, CapaAvatar b) => a.z.compareTo(b.z));
  return compuestas;
}

/// Avatar 2D frontal compuesto por capas.
class AvatarCapas extends StatelessWidget {
  const AvatarCapas({
    required this.capas,
    super.key,
    this.rasgos,
    this.tamano = 220,
    this.resplandor = true,
    this.nombre,
  });

  /// Manifiesto de capas tal como lo envía el Reino.
  final List<CapaAvatar> capas;

  /// Rasgos gratuitos (piel, cabello, silueta).
  final RasgosAvatar? rasgos;

  /// Lado del lienzo cuadrado, en dp.
  final double tamano;

  /// Halo de luz detrás del personaje.
  final bool resplandor;

  /// Nombre del personaje, para el lector de pantalla.
  final String? nombre;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final RasgosAvatar r = rasgos ?? const RasgosAvatar();

    final Map<RanuraItem, Color> equipo = <RanuraItem, Color>{};
    for (final CapaAvatar capa in capas) {
      final RanuraItem? ranura = capa.ranura;
      if (ranura == null) continue;
      equipo[ranura] = _colorDeTinte(capa.tinte) ?? _colorPorRanura(ranura, p);
    }

    final List<String> puestos = <String>[
      for (final RanuraItem ranura in ranurasDelVestidorInterno)
        if (equipo.containsKey(ranura)) _nombreRanura(ranura).toLowerCase(),
    ];

    return Semantics(
      label: nombre == null
          ? 'Avatar del personaje'
          : 'Avatar de $nombre',
      value: puestos.isEmpty
          ? 'Sin equipamiento'
          : 'Lleva ${puestos.join(', ')}',
      excludeSemantics: true,
      child: SizedBox(
        width: tamano,
        height: tamano,
        child: Stack(
          alignment: Alignment.center,
          children: <Widget>[
            // El halo se pinta aparte: la figura es una ilustración, no un
            // dibujo vectorial, y el resplandor debe quedar por detrás.
            if (resplandor)
              CustomPaint(
                size: Size.square(tamano),
                painter: _PintorAvatar(
                  paleta: p,
                  equipo: equipo,
                  piel: _tonoDePiel(r.tonoPiel, p),
                  cabello: _colorDeCabello(r.colorCabello, p),
                  esbelto: r.tipoCuerpo == TipoCuerpo.esbelto,
                  robusto: r.tipoCuerpo == TipoCuerpo.robusto,
                  resplandor: true,
                  soloFondo: true,
                ),
              ),
            Image.asset(
              Arte.figura(
                trato: r.formaTrato,
                cuerpo: r.tipoCuerpo,
                rostro: r.rostro,
              ),
              height: tamano,
              fit: BoxFit.contain,
              filterQuality: FilterQuality.medium,
              // Si el arte faltara, el dibujo vectorial sigue siendo una figura
              // válida: la pantalla nunca queda vacía.
              errorBuilder: (BuildContext context, Object error, StackTrace? pila) =>
                  CustomPaint(
                size: Size.square(tamano),
                painter: _PintorAvatar(
                  paleta: p,
                  equipo: equipo,
                  piel: _tonoDePiel(r.tonoPiel, p),
                  cabello: _colorDeCabello(r.colorCabello, p),
                  esbelto: r.tipoCuerpo == TipoCuerpo.esbelto,
                  robusto: r.tipoCuerpo == TipoCuerpo.robusto,
                  resplandor: resplandor,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Marco del Vestidor: pedestal, halo y avatar centrado.
class RetratoAvatar extends StatelessWidget {
  const RetratoAvatar({
    required this.capas,
    super.key,
    this.rasgos,
    this.nombre,
    this.subtitulo,
    this.tamano = 220,
    this.cargando = false,
  });

  final List<CapaAvatar> capas;
  final RasgosAvatar? rasgos;
  final String? nombre;
  final String? subtitulo;
  final double tamano;
  final bool cargando;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;

    if (cargando) {
      return Center(
        child: SizedBox(
          width: tamano,
          height: tamano,
          child: DecoratedBox(
            decoration: BoxDecoration(
              color: p.borde.withValues(alpha: 0.45),
              shape: BoxShape.circle,
            ),
            child: Center(
              child: Icon(
                Icons.person_rounded,
                size: tamano * 0.42,
                color: p.superficie,
              ),
            ),
          ),
        ),
      );
    }

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        AvatarCapas(
          capas: capas,
          rasgos: rasgos,
          tamano: tamano,
          nombre: nombre,
        ),
        if (nombre != null) ...<Widget>[
          const SizedBox(height: Espacio.xs),
          Text(
            nombre!,
            textAlign: TextAlign.center,
            style: context.textos.displaySmall,
          ),
        ],
        if (subtitulo != null)
          Text(
            subtitulo!,
            textAlign: TextAlign.center,
            style: context.textos.bodyMedium?.copyWith(
              color: p.textoSecundario,
            ),
          ),
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// Colores derivados
// ---------------------------------------------------------------------------

/// Las ranuras que el dibujo sabe representar.
const List<RanuraItem> ranurasDelVestidorInterno = <RanuraItem>[
  RanuraItem.cabeza,
  RanuraItem.cuerpo,
  RanuraItem.capa,
  RanuraItem.arma,
  RanuraItem.secundaria,
  RanuraItem.accesorio,
  RanuraItem.guantes,
  RanuraItem.botas,
];

String _nombreRanura(RanuraItem ranura) =>
    ranura == RanuraItem.secundaria ? 'Escudo' : ranura.etiqueta;

/// Lee un tinte `#RRGGBB` del manifiesto.
Color? _colorDeTinte(String? tinte) {
  if (tinte == null) return null;
  final String limpio = tinte.replaceAll('#', '').trim();
  if (limpio.length != 6 && limpio.length != 8) return null;
  final int? valor = int.tryParse(limpio, radix: 16);
  if (valor == null) return null;
  return Color(limpio.length == 6 ? 0xFF000000 | valor : valor);
}

/// Color semántico de reserva para cada ranura.
Color _colorPorRanura(RanuraItem ranura, AteneaPalette p) => switch (ranura) {
      RanuraItem.cabeza => p.arcano,
      RanuraItem.cuerpo => p.info,
      RanuraItem.capa => p.brasa,
      RanuraItem.arma => p.oro,
      RanuraItem.secundaria => p.dominio,
      RanuraItem.accesorio => p.exito,
      RanuraItem.guantes => p.textoSecundario,
      RanuraItem.botas => p.textoSecundario,
      RanuraItem.mascota => p.exito,
      RanuraItem.montura => p.advertencia,
    };

int _indiceDeClave(String clave, int total) {
  final RegExp digitos = RegExp(r'(\d+)');
  final Match? m = digitos.firstMatch(clave);
  if (m != null) {
    final int? n = int.tryParse(m.group(1) ?? '');
    if (n != null) return (n - 1).clamp(0, total - 1);
  }
  int suma = 0;
  for (final int unidad in clave.codeUnits) {
    suma += unidad;
  }
  return suma % total;
}

/// Seis tonos de piel derivados de los tokens, mientras no exista el arte.
Color _tonoDePiel(String clave, AteneaPalette p) {
  final int i = _indiceDeClave(clave, 6);
  final double t = i / 5;
  final Color base = Color.lerp(p.oro, p.brasa, t) ?? p.oro;
  return Color.lerp(base, p.fondo, t * 0.42) ?? base;
}

/// Diez colores de cabello derivados de los tokens.
Color _colorDeCabello(String clave, AteneaPalette p) {
  final List<Color> tonos = <Color>[
    p.fondo,
    p.textoSecundario,
    p.textoPrimario,
    p.brasa,
    p.oro,
    p.arcano,
    p.dominio,
    p.exito,
    p.error,
    p.info,
  ];
  return tonos[_indiceDeClave(clave, tonos.length)];
}

// ---------------------------------------------------------------------------
// Pintor
// ---------------------------------------------------------------------------

class _PintorAvatar extends CustomPainter {
  const _PintorAvatar({
    required this.paleta,
    required this.equipo,
    required this.piel,
    required this.cabello,
    required this.esbelto,
    required this.robusto,
    required this.resplandor,
    this.soloFondo = false,
  });

  final AteneaPalette paleta;
  final Map<RanuraItem, Color> equipo;
  final Color piel;
  final Color cabello;
  final bool esbelto;
  final bool robusto;
  final bool resplandor;

  /// Pinta solo el halo y el pedestal, sin la figura.
  ///
  /// Es lo que se usa detrás de la ilustración del personaje: el escenario sí,
  /// el muñeco vectorial no.
  final bool soloFondo;

  @override
  void paint(Canvas lienzo, Size medida) {
    final double s = medida.shortestSide;
    final double dx = (medida.width - s) / 2;
    lienzo.translate(dx, 0);

    final Paint relleno = Paint()..style = PaintingStyle.fill;

    // Halo de luz y pedestal.
    if (resplandor) {
      relleno.shader = RadialGradient(
        colors: <Color>[
          paleta.arcano.withValues(alpha: 0.28),
          paleta.arcano.withValues(alpha: 0.06),
          Colors.transparent,
        ],
        stops: const <double>[0, 0.55, 1],
      ).createShader(Rect.fromLTWH(0, 0, s, s));
      lienzo.drawCircle(Offset(s * 0.5, s * 0.5), s * 0.5, relleno);
      relleno.shader = null;
    }

    relleno.color = paleta.borde.withValues(alpha: 0.7);
    lienzo.drawOval(
      Rect.fromCenter(
        center: Offset(s * 0.5, s * 0.935),
        width: s * 0.44,
        height: s * 0.06,
      ),
      relleno,
    );

    if (soloFondo) return;

    final double ancho = esbelto ? 0.135 : (robusto ? 0.185 : 0.16);
    final Color cuerpo = equipo[RanuraItem.cuerpo] ?? paleta.superficieElevada;
    final Color botas = equipo[RanuraItem.botas] ?? paleta.borde;
    final Color guantes = equipo[RanuraItem.guantes] ?? piel;

    // Capa, detrás de todo el cuerpo.
    final Color? capa = equipo[RanuraItem.capa];
    if (capa != null) {
      final Path manto = Path()
        ..moveTo(s * (0.5 - ancho - 0.02), s * 0.46)
        ..lineTo(s * (0.5 - ancho - 0.13), s * 0.90)
        ..quadraticBezierTo(s * 0.5, s * 0.96, s * (0.5 + ancho + 0.13), s * 0.90)
        ..lineTo(s * (0.5 + ancho + 0.02), s * 0.46)
        ..close();
      relleno.color = capa.withValues(alpha: 0.92);
      lienzo.drawPath(manto, relleno);
      relleno.color = Color.lerp(capa, paleta.fondo, 0.35) ?? capa;
      lienzo.drawPath(
        Path()
          ..moveTo(s * 0.5, s * 0.48)
          ..lineTo(s * 0.5, s * 0.94)
          ..lineTo(s * (0.5 + ancho + 0.13), s * 0.90)
          ..lineTo(s * (0.5 + ancho + 0.02), s * 0.46)
          ..close(),
        relleno,
      );
    }

    // Piernas y botas.
    relleno.color = piel;
    for (final double lado in <double>[-1, 1]) {
      lienzo.drawRRect(
        RRect.fromRectAndRadius(
          Rect.fromLTWH(
            s * (0.5 + lado * ancho * 0.62 - 0.035),
            s * 0.74,
            s * 0.07,
            s * 0.16,
          ),
          Radius.circular(s * 0.03),
        ),
        relleno,
      );
    }
    relleno.color = botas;
    for (final double lado in <double>[-1, 1]) {
      lienzo.drawRRect(
        RRect.fromRectAndRadius(
          Rect.fromLTWH(
            s * (0.5 + lado * ancho * 0.62 - 0.042),
            s * 0.855,
            s * 0.084,
            s * 0.055,
          ),
          Radius.circular(s * 0.02),
        ),
        relleno,
      );
    }

    // Brazos.
    relleno.color = Color.lerp(cuerpo, paleta.fondo, 0.18) ?? cuerpo;
    for (final double lado in <double>[-1, 1]) {
      lienzo.drawRRect(
        RRect.fromRectAndRadius(
          Rect.fromLTWH(
            s * (0.5 + lado * (ancho + 0.055) - 0.028),
            s * 0.50,
            s * 0.056,
            s * 0.21,
          ),
          Radius.circular(s * 0.028),
        ),
        relleno,
      );
    }
    relleno.color = guantes;
    for (final double lado in <double>[-1, 1]) {
      lienzo.drawCircle(
        Offset(s * (0.5 + lado * (ancho + 0.055)), s * 0.715),
        s * 0.032,
        relleno,
      );
    }

    // Torso.
    relleno.color = cuerpo;
    lienzo.drawRRect(
      RRect.fromRectAndCorners(
        Rect.fromLTWH(s * (0.5 - ancho), s * 0.465, s * ancho * 2, s * 0.30),
        topLeft: Radius.circular(s * 0.08),
        topRight: Radius.circular(s * 0.08),
        bottomLeft: Radius.circular(s * 0.035),
        bottomRight: Radius.circular(s * 0.035),
      ),
      relleno,
    );

    // Cinturón.
    relleno.color = paleta.borde;
    lienzo.drawRRect(
      RRect.fromRectAndRadius(
        Rect.fromLTWH(s * (0.5 - ancho), s * 0.705, s * ancho * 2, s * 0.028),
        Radius.circular(s * 0.012),
      ),
      relleno,
    );

    // Hombreras cuando hay armadura equipada.
    if (equipo.containsKey(RanuraItem.cuerpo)) {
      relleno.color = Color.lerp(cuerpo, paleta.textoPrimario, 0.22) ?? cuerpo;
      for (final double lado in <double>[-1, 1]) {
        lienzo.drawCircle(
          Offset(s * (0.5 + lado * (ancho + 0.01)), s * 0.50),
          s * 0.052,
          relleno,
        );
      }
    }

    // Accesorio en el pecho.
    final Color? accesorio = equipo[RanuraItem.accesorio];
    if (accesorio != null) {
      final Path gema = Path()
        ..moveTo(s * 0.5, s * 0.545)
        ..lineTo(s * 0.528, s * 0.578)
        ..lineTo(s * 0.5, s * 0.612)
        ..lineTo(s * 0.472, s * 0.578)
        ..close();
      relleno.color = accesorio;
      lienzo.drawPath(gema, relleno);
    }

    // Cuello y cabeza.
    relleno.color = Color.lerp(piel, paleta.fondo, 0.2) ?? piel;
    lienzo.drawRRect(
      RRect.fromRectAndRadius(
        Rect.fromLTWH(s * 0.465, s * 0.425, s * 0.07, s * 0.06),
        Radius.circular(s * 0.02),
      ),
      relleno,
    );

    const double centroCabezaY = 0.345;
    final double radioCabeza = s * 0.105;
    relleno.color = piel;
    lienzo.drawCircle(
      Offset(s * 0.5, s * centroCabezaY),
      radioCabeza,
      relleno,
    );

    // Cabello: casquete sobre la mitad superior.
    final Color? yelmo = equipo[RanuraItem.cabeza];
    if (yelmo == null) {
      relleno.color = cabello;
      lienzo.drawArc(
        Rect.fromCircle(
          center: Offset(s * 0.5, s * centroCabezaY),
          radius: radioCabeza * 1.08,
        ),
        3.14159,
        3.14159,
        true,
        relleno,
      );
    }

    // Ojos: dos puntos, siempre visibles.
    relleno.color = paleta.fondo.withValues(alpha: 0.85);
    lienzo
      ..drawCircle(
        Offset(s * 0.468, s * (centroCabezaY + 0.005)),
        s * 0.011,
        relleno,
      )
      ..drawCircle(
        Offset(s * 0.532, s * (centroCabezaY + 0.005)),
        s * 0.011,
        relleno,
      );

    // Yelmo por encima del cabello.
    if (yelmo != null) {
      relleno.color = yelmo;
      lienzo
        ..drawArc(
          Rect.fromCircle(
            center: Offset(s * 0.5, s * centroCabezaY),
            radius: radioCabeza * 1.16,
          ),
          3.14159,
          3.14159,
          true,
          relleno,
        )
        ..drawRRect(
          RRect.fromRectAndRadius(
            Rect.fromLTWH(
              s * 0.489,
              s * (centroCabezaY - 0.01),
              s * 0.022,
              s * 0.085,
            ),
            Radius.circular(s * 0.008),
          ),
          relleno,
        );
    }

    // Arma en la mano derecha.
    final Color? arma = equipo[RanuraItem.arma];
    if (arma != null) {
      final double x = s * (0.5 + ancho + 0.055);
      relleno.color = arma;
      lienzo
        ..drawRRect(
          RRect.fromRectAndRadius(
            Rect.fromLTWH(x - s * 0.014, s * 0.36, s * 0.028, s * 0.34),
            Radius.circular(s * 0.012),
          ),
          relleno,
        )
        ..drawRRect(
          RRect.fromRectAndRadius(
            Rect.fromLTWH(x - s * 0.055, s * 0.655, s * 0.11, s * 0.022),
            Radius.circular(s * 0.01),
          ),
          relleno,
        )
        ..drawCircle(Offset(x, s * 0.345), s * 0.026, relleno);
    }

    // Escudo en la mano izquierda.
    final Color? escudo = equipo[RanuraItem.secundaria];
    if (escudo != null) {
      final double x = s * (0.5 - ancho - 0.075);
      final double y = s * 0.60;
      final double w = s * 0.115;
      final Path forma = Path()
        ..moveTo(x - w / 2, y - w * 0.62)
        ..lineTo(x + w / 2, y - w * 0.62)
        ..lineTo(x + w / 2, y + w * 0.25)
        ..quadraticBezierTo(x, y + w * 0.95, x - w / 2, y + w * 0.25)
        ..close();
      relleno.color = escudo;
      lienzo.drawPath(forma, relleno);
      relleno.color = Color.lerp(escudo, paleta.textoPrimario, 0.35) ?? escudo;
      lienzo.drawCircle(Offset(x, y), w * 0.18, relleno);
    }
  }

  @override
  bool shouldRepaint(covariant _PintorAvatar anterior) =>
      anterior.piel != piel ||
      anterior.cabello != cabello ||
      anterior.esbelto != esbelto ||
      anterior.robusto != robusto ||
      anterior.resplandor != resplandor ||
      anterior.soloFondo != soloFondo ||
      !_mismoEquipo(anterior.equipo, equipo) ||
      anterior.paleta != paleta;

  static bool _mismoEquipo(Map<RanuraItem, Color> a, Map<RanuraItem, Color> b) {
    if (a.length != b.length) return false;
    for (final MapEntry<RanuraItem, Color> e in a.entries) {
      if (b[e.key] != e.value) return false;
    }
    return true;
  }
}
