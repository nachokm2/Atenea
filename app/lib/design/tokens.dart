/// Tokens del sistema de diseño de Atenea — concepto visual "Crónica luminosa".
///
/// Un reino nocturno, elegante y limpio donde el conocimiento es luz: el oro,
/// la experiencia y el dominio brillan sobre fondos profundos. Medieval en la
/// forma, moderno en la ejecución.
///
/// Los colores se consumen SIEMPRE a través de [AteneaPalette] (una
/// `ThemeExtension`), nunca como literales dentro de las pantallas, para que
/// ambos temas — Noche del Reino y Día del Reino — se mantengan coherentes.
library;

import 'dart:ui' show lerpDouble;

import 'package:flutter/material.dart';


/// Escala de espaciado en dp. Toda separación de la interfaz sale de aquí.
abstract final class Espacio {
  static const double xxs = 4;
  static const double xs = 8;
  static const double sm = 12;
  static const double md = 16;
  static const double lg = 24;
  static const double xl = 32;
  static const double xxl = 48;
}

/// Radios de esquina en dp.
abstract final class Redondeo {
  static const double chip = 8;
  static const double boton = 12;
  static const double tarjeta = 16;
  static const double hoja = 24;
  static const double pildora = 999;

  static const BorderRadius rChip = BorderRadius.all(Radius.circular(chip));
  static const BorderRadius rBoton = BorderRadius.all(Radius.circular(boton));
  static const BorderRadius rTarjeta = BorderRadius.all(Radius.circular(tarjeta));
  static const BorderRadius rHoja = BorderRadius.vertical(top: Radius.circular(hoja));
  static const BorderRadius rPildora = BorderRadius.all(Radius.circular(pildora));
}

/// Duraciones de movimiento. Las celebraciones nunca bloquean más de 2,5 s.
abstract final class Movimiento {
  static const Duration micro = Duration(milliseconds: 180);
  static const Duration corta = Duration(milliseconds: 250);
  static const Duration transicion = Duration(milliseconds: 380);
  static const Duration celebracion = Duration(milliseconds: 1400);
  static const Duration celebracionLarga = Duration(milliseconds: 2400);

  static const Curve estandar = Curves.easeOutCubic;
  static const Curve entrada = Curves.easeOutBack;
}

/// Escala tipográfica en dp, según el documento de UX.
abstract final class Tipo {
  static const double leyenda = 12;
  static const double secundario = 14;
  static const double cuerpo = 16;
  static const double subtitulo = 20;
  static const double titulo = 24;
  static const double display = 32;
  static const double heroe = 44;
}

/// Anchura máxima de una columna de lectura (40–60 caracteres por línea).
abstract final class Medida {
  static const double lecturaMax = 640;
  static const double areaTactilMin = 48;
}

/// Las seis rarezas del catálogo de objetos.
///
/// El color nunca es el único portador de significado: en la interfaz la
/// rareza se muestra siempre acompañada de su etiqueta textual.
enum Rareza {
  comun('Común', Color(0xFF9AA3B2), 0),
  pocoComun('Poco común', Color(0xFF4CC38A), 0),
  raro('Raro', Color(0xFF4DA3FF), 6),
  epico('Épico', Color(0xFFA66BFF), 10),
  legendario('Legendario', Color(0xFFFF9A3D), 14),
  mitico('Mítico', Color(0xFFFF4D6D), 18);

  const Rareza(this.etiqueta, this.color, this.brillo);

  /// Nombre visible en español.
  final String etiqueta;

  /// Color de borde y brillo.
  final Color color;

  /// Radio del resplandor en dp (0 = borde plano, sin brillo).
  final double brillo;

  /// Convierte el valor que envía la API (`comun`, `poco_comun`, …).
  static Rareza desdeApi(String valor) => switch (valor) {
        'comun' || 'common' => Rareza.comun,
        'poco_comun' || 'uncommon' => Rareza.pocoComun,
        'raro' || 'rare' => Rareza.raro,
        'epico' || 'epic' => Rareza.epico,
        'legendario' || 'legendary' => Rareza.legendario,
        'mitico' || 'mythic' => Rareza.mitico,
        _ => Rareza.comun,
      };
}

/// Paleta semántica de Atenea, disponible en ambos temas.
///
/// Se lee desde cualquier widget con `context.paleta`.
@immutable
class AteneaPalette extends ThemeExtension<AteneaPalette> {
  const AteneaPalette({
    required this.fondo,
    required this.superficie,
    required this.superficieElevada,
    required this.lectura,
    required this.borde,
    required this.textoPrimario,
    required this.textoSecundario,
    required this.arcano,
    required this.oro,
    required this.brasa,
    required this.dominio,
    required this.exito,
    required this.error,
    required this.advertencia,
    required this.info,
    required this.sobreArcano,
    required this.sobreOro,
  });

  /// Fondo de pantalla.
  final Color fondo;

  /// Superficie de tarjeta.
  final Color superficie;

  /// Superficie elevada: hojas inferiores, modales, tarjetas destacadas.
  final Color superficieElevada;

  /// Superficie de los bloques de lectura de una lección.
  final Color lectura;

  /// Borde sutil de separación.
  final Color borde;

  final Color textoPrimario;
  final Color textoSecundario;

  /// Acción primaria, foco y enlaces.
  final Color arcano;

  /// Oro, experiencia y recompensas.
  final Color oro;

  /// Racha.
  final Color brasa;

  /// Dominio del conocimiento.
  final Color dominio;

  final Color exito;
  final Color error;
  final Color advertencia;
  final Color info;

  /// Color de contenido sobre [arcano] y sobre [oro].
  final Color sobreArcano;
  final Color sobreOro;

  /// Tema oscuro por defecto: "Noche del Reino".
  static const AteneaPalette noche = AteneaPalette(
    fondo: Color(0xFF0F1420),
    superficie: Color(0xFF1A2233),
    superficieElevada: Color(0xFF243048),
    lectura: Color(0xFF1F2940),
    borde: Color(0xFF2E3A54),
    textoPrimario: Color(0xFFF2EDE4),
    textoSecundario: Color(0xFFA9B2C3),
    arcano: Color(0xFF7C6CF0),
    oro: Color(0xFFF2B84B),
    brasa: Color(0xFFFF7A3D),
    dominio: Color(0xFF4DD0E1),
    exito: Color(0xFF3DC48A),
    error: Color(0xFFE5605E),
    advertencia: Color(0xFFF29E4C),
    info: Color(0xFF6FA8FF),
    sobreArcano: Color(0xFFFFFFFF),
    sobreOro: Color(0xFF241A05),
  );

  /// Tema claro: "Día del Reino".
  static const AteneaPalette dia = AteneaPalette(
    fondo: Color(0xFFF6F1E7),
    superficie: Color(0xFFFFFFFF),
    superficieElevada: Color(0xFFFFF9EF),
    lectura: Color(0xFFFFFDF8),
    borde: Color(0xFFE2D9C8),
    textoPrimario: Color(0xFF1B2233),
    textoSecundario: Color(0xFF5B667A),
    arcano: Color(0xFF5B4BD6),
    oro: Color(0xFFC98A12),
    brasa: Color(0xFFE2622A),
    dominio: Color(0xFF0E8FA3),
    exito: Color(0xFF1F9D66),
    error: Color(0xFFC43E3C),
    advertencia: Color(0xFFB86A12),
    info: Color(0xFF2F6FD6),
    sobreArcano: Color(0xFFFFFFFF),
    sobreOro: Color(0xFF2A1D02),
  );

  @override
  AteneaPalette copyWith({
    Color? fondo,
    Color? superficie,
    Color? superficieElevada,
    Color? lectura,
    Color? borde,
    Color? textoPrimario,
    Color? textoSecundario,
    Color? arcano,
    Color? oro,
    Color? brasa,
    Color? dominio,
    Color? exito,
    Color? error,
    Color? advertencia,
    Color? info,
    Color? sobreArcano,
    Color? sobreOro,
  }) {
    return AteneaPalette(
      fondo: fondo ?? this.fondo,
      superficie: superficie ?? this.superficie,
      superficieElevada: superficieElevada ?? this.superficieElevada,
      lectura: lectura ?? this.lectura,
      borde: borde ?? this.borde,
      textoPrimario: textoPrimario ?? this.textoPrimario,
      textoSecundario: textoSecundario ?? this.textoSecundario,
      arcano: arcano ?? this.arcano,
      oro: oro ?? this.oro,
      brasa: brasa ?? this.brasa,
      dominio: dominio ?? this.dominio,
      exito: exito ?? this.exito,
      error: error ?? this.error,
      advertencia: advertencia ?? this.advertencia,
      info: info ?? this.info,
      sobreArcano: sobreArcano ?? this.sobreArcano,
      sobreOro: sobreOro ?? this.sobreOro,
    );
  }

  @override
  AteneaPalette lerp(covariant ThemeExtension<AteneaPalette>? other, double t) {
    if (other is! AteneaPalette) return this;
    Color c(Color a, Color b) => Color.lerp(a, b, t) ?? a;
    return AteneaPalette(
      fondo: c(fondo, other.fondo),
      superficie: c(superficie, other.superficie),
      superficieElevada: c(superficieElevada, other.superficieElevada),
      lectura: c(lectura, other.lectura),
      borde: c(borde, other.borde),
      textoPrimario: c(textoPrimario, other.textoPrimario),
      textoSecundario: c(textoSecundario, other.textoSecundario),
      arcano: c(arcano, other.arcano),
      oro: c(oro, other.oro),
      brasa: c(brasa, other.brasa),
      dominio: c(dominio, other.dominio),
      exito: c(exito, other.exito),
      error: c(error, other.error),
      advertencia: c(advertencia, other.advertencia),
      info: c(info, other.info),
      sobreArcano: c(sobreArcano, other.sobreArcano),
      sobreOro: c(sobreOro, other.sobreOro),
    );
  }
}

/// Sombras y brillos coherentes con la elevación por tono del tema oscuro.
abstract final class Sombra {
  /// Resplandor de color usado en tarjetas de recompensa y de ítem por rareza.
  static List<BoxShadow> brillo(Color color, double radio) {
    if (radio <= 0) return const <BoxShadow>[];
    return <BoxShadow>[
      BoxShadow(
        color: color.withValues(alpha: 0.35),
        blurRadius: radio,
        spreadRadius: radio / 6,
      ),
    ];
  }

  /// Sombra suave para hojas inferiores y modales.
  static List<BoxShadow> hoja(Brightness brillo) => <BoxShadow>[
        BoxShadow(
          color: Colors.black.withValues(alpha: brillo == Brightness.dark ? 0.45 : 0.12),
          blurRadius: 24,
          offset: const Offset(0, -4),
        ),
      ];
}

/// Interpola un tamaño respetando el factor de escala del sistema.
double escalar(double base, double factor) => lerpDouble(base, base * factor, 1)!;

/// Acceso corto a la paleta desde cualquier widget.
extension AteneaThemeX on BuildContext {
  AteneaPalette get paleta =>
      Theme.of(this).extension<AteneaPalette>() ?? AteneaPalette.noche;

  TextTheme get textos => Theme.of(this).textTheme;

  bool get esOscuro => Theme.of(this).brightness == Brightness.dark;
}
