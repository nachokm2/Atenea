import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import 'tokens.dart';

/// Construcción de los dos temas de Atenea a partir de los tokens.
///
/// - **Noche del Reino** (oscuro, por defecto).
/// - **Día del Reino** (claro).
///
/// Reglas tipográficas del documento de UX:
/// - `Cinzel` solo para display y títulos de celebración, nunca en cuerpo ni
///   en botones, y siempre a 20 dp o más.
/// - `Nunito Sans` para toda la interfaz y el cuerpo de texto, mínimo 16 dp y
///   interlineado 1,5.
/// - Cifras con numerales tabulares para que no "bailen" al animarse.
abstract final class AteneaTheme {
  static ThemeData oscuro() => _construir(AteneaPalette.noche, Brightness.dark);

  static ThemeData claro() => _construir(AteneaPalette.dia, Brightness.light);

  static ThemeData _construir(AteneaPalette p, Brightness brillo) {
    final ColorScheme esquema = ColorScheme(
      brightness: brillo,
      primary: p.arcano,
      onPrimary: p.sobreArcano,
      primaryContainer: p.arcano.withValues(alpha: brillo == Brightness.dark ? 0.22 : 0.14),
      onPrimaryContainer: p.textoPrimario,
      secondary: p.oro,
      onSecondary: p.sobreOro,
      secondaryContainer: p.oro.withValues(alpha: brillo == Brightness.dark ? 0.20 : 0.16),
      onSecondaryContainer: p.textoPrimario,
      tertiary: p.dominio,
      onTertiary: p.sobreOro,
      error: p.error,
      onError: Colors.white,
      errorContainer: p.error.withValues(alpha: 0.18),
      onErrorContainer: p.textoPrimario,
      surface: p.superficie,
      onSurface: p.textoPrimario,
      surfaceContainerLowest: p.fondo,
      surfaceContainerLow: p.superficie,
      surfaceContainer: p.superficie,
      surfaceContainerHigh: p.superficieElevada,
      surfaceContainerHighest: p.superficieElevada,
      onSurfaceVariant: p.textoSecundario,
      outline: p.borde,
      outlineVariant: p.borde.withValues(alpha: 0.6),
      shadow: Colors.black,
      scrim: Colors.black,
      inverseSurface: p.textoPrimario,
      onInverseSurface: p.fondo,
      inversePrimary: p.arcano,
    );

    final TextTheme base = GoogleFonts.nunitoSansTextTheme(
      brillo == Brightness.dark ? ThemeData.dark().textTheme : ThemeData.light().textTheme,
    );

    final TextStyle display = GoogleFonts.cinzel(
      color: p.textoPrimario,
      fontWeight: FontWeight.w700,
      letterSpacing: 0.5,
      height: 1.15,
    );

    final TextTheme textos = base
        .copyWith(
          displayLarge: display.copyWith(fontSize: Tipo.heroe),
          displayMedium: display.copyWith(fontSize: Tipo.display),
          displaySmall: display.copyWith(fontSize: Tipo.titulo),
          headlineMedium: base.headlineMedium?.copyWith(
            fontSize: Tipo.titulo,
            fontWeight: FontWeight.w800,
            height: 1.25,
          ),
          headlineSmall: base.headlineSmall?.copyWith(
            fontSize: Tipo.subtitulo,
            fontWeight: FontWeight.w800,
            height: 1.3,
          ),
          titleLarge: base.titleLarge?.copyWith(
            fontSize: Tipo.subtitulo,
            fontWeight: FontWeight.w700,
            height: 1.3,
          ),
          titleMedium: base.titleMedium?.copyWith(
            fontSize: Tipo.cuerpo,
            fontWeight: FontWeight.w700,
            height: 1.4,
          ),
          bodyLarge: base.bodyLarge?.copyWith(
            fontSize: Tipo.cuerpo,
            height: 1.5,
          ),
          bodyMedium: base.bodyMedium?.copyWith(
            fontSize: Tipo.secundario,
            height: 1.5,
          ),
          bodySmall: base.bodySmall?.copyWith(
            fontSize: Tipo.leyenda,
            height: 1.45,
          ),
          labelLarge: base.labelLarge?.copyWith(
            fontSize: Tipo.cuerpo,
            fontWeight: FontWeight.w700,
            letterSpacing: 0.2,
          ),
          labelSmall: base.labelSmall?.copyWith(
            fontSize: Tipo.leyenda,
            fontWeight: FontWeight.w700,
            letterSpacing: 0.8,
          ),
        )
        .apply(
          bodyColor: p.textoPrimario,
          displayColor: p.textoPrimario,
        );

    return ThemeData(
      useMaterial3: true,
      brightness: brillo,
      colorScheme: esquema,
      scaffoldBackgroundColor: p.fondo,
      canvasColor: p.fondo,
      textTheme: textos,
      splashFactory: InkSparkle.splashFactory,
      extensions: <ThemeExtension<dynamic>>[p],
      visualDensity: VisualDensity.standard,
      appBarTheme: AppBarTheme(
        backgroundColor: p.fondo,
        surfaceTintColor: Colors.transparent,
        foregroundColor: p.textoPrimario,
        elevation: 0,
        scrolledUnderElevation: 0,
        centerTitle: false,
        titleTextStyle: textos.titleLarge,
      ),
      cardTheme: CardThemeData(
        color: p.superficie,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        margin: EdgeInsets.zero,
        shape: RoundedRectangleBorder(
          borderRadius: Redondeo.rTarjeta,
          side: BorderSide(color: p.borde),
        ),
      ),
      dividerTheme: DividerThemeData(color: p.borde, thickness: 1, space: 1),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: p.arcano,
          foregroundColor: p.sobreArcano,
          disabledBackgroundColor: p.borde,
          disabledForegroundColor: p.textoSecundario,
          minimumSize: const Size.fromHeight(Medida.areaTactilMin),
          padding: const EdgeInsets.symmetric(horizontal: Espacio.lg, vertical: Espacio.sm),
          shape: const RoundedRectangleBorder(borderRadius: Redondeo.rBoton),
          textStyle: textos.labelLarge,
        ),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: p.arcano,
          foregroundColor: p.sobreArcano,
          elevation: 0,
          minimumSize: const Size.fromHeight(Medida.areaTactilMin),
          shape: const RoundedRectangleBorder(borderRadius: Redondeo.rBoton),
          textStyle: textos.labelLarge,
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: p.textoPrimario,
          minimumSize: const Size.fromHeight(Medida.areaTactilMin),
          side: BorderSide(color: p.borde),
          shape: const RoundedRectangleBorder(borderRadius: Redondeo.rBoton),
          textStyle: textos.labelLarge,
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: p.arcano,
          textStyle: textos.labelLarge,
          minimumSize: const Size(0, Medida.areaTactilMin),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: p.superficieElevada,
        contentPadding: const EdgeInsets.symmetric(
          horizontal: Espacio.md,
          vertical: Espacio.sm + 2,
        ),
        hintStyle: textos.bodyLarge?.copyWith(color: p.textoSecundario),
        labelStyle: textos.bodyMedium?.copyWith(color: p.textoSecundario),
        border: OutlineInputBorder(
          borderRadius: Redondeo.rBoton,
          borderSide: BorderSide(color: p.borde),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: Redondeo.rBoton,
          borderSide: BorderSide(color: p.borde),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: Redondeo.rBoton,
          borderSide: BorderSide(color: p.arcano, width: 2),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: Redondeo.rBoton,
          borderSide: BorderSide(color: p.error),
        ),
      ),
      chipTheme: ChipThemeData(
        backgroundColor: p.superficieElevada,
        side: BorderSide(color: p.borde),
        labelStyle: textos.bodySmall!.copyWith(fontWeight: FontWeight.w700),
        shape: const RoundedRectangleBorder(borderRadius: Redondeo.rPildora),
        padding: const EdgeInsets.symmetric(horizontal: Espacio.sm, vertical: Espacio.xxs),
      ),
      navigationBarTheme: NavigationBarThemeData(
        backgroundColor: p.superficie,
        surfaceTintColor: Colors.transparent,
        indicatorColor: p.arcano.withValues(alpha: 0.20),
        indicatorShape: const RoundedRectangleBorder(borderRadius: Redondeo.rPildora),
        height: 68,
        labelTextStyle: WidgetStateProperty.resolveWith(
          (Set<WidgetState> estados) => textos.labelSmall!.copyWith(
            letterSpacing: 0.2,
            color: estados.contains(WidgetState.selected) ? p.textoPrimario : p.textoSecundario,
          ),
        ),
        iconTheme: WidgetStateProperty.resolveWith(
          (Set<WidgetState> estados) => IconThemeData(
            size: 24,
            color: estados.contains(WidgetState.selected) ? p.arcano : p.textoSecundario,
          ),
        ),
      ),
      bottomSheetTheme: BottomSheetThemeData(
        backgroundColor: p.superficieElevada,
        surfaceTintColor: Colors.transparent,
        modalBackgroundColor: p.superficieElevada,
        shape: const RoundedRectangleBorder(borderRadius: Redondeo.rHoja),
        showDragHandle: true,
        dragHandleColor: p.borde,
      ),
      dialogTheme: DialogThemeData(
        backgroundColor: p.superficieElevada,
        surfaceTintColor: Colors.transparent,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(Redondeo.hoja),
          side: BorderSide(color: p.borde),
        ),
        titleTextStyle: textos.headlineSmall,
        contentTextStyle: textos.bodyLarge,
      ),
      snackBarTheme: SnackBarThemeData(
        backgroundColor: p.superficieElevada,
        contentTextStyle: textos.bodyLarge,
        actionTextColor: p.oro,
        behavior: SnackBarBehavior.floating,
        shape: const RoundedRectangleBorder(borderRadius: Redondeo.rBoton),
      ),
      progressIndicatorTheme: ProgressIndicatorThemeData(
        color: p.arcano,
        linearTrackColor: p.borde,
        circularTrackColor: p.borde,
      ),
      listTileTheme: ListTileThemeData(
        iconColor: p.textoSecundario,
        textColor: p.textoPrimario,
        shape: const RoundedRectangleBorder(borderRadius: Redondeo.rTarjeta),
      ),
      iconTheme: IconThemeData(color: p.textoSecundario, size: 24),
      tooltipTheme: TooltipThemeData(
        decoration: BoxDecoration(
          color: p.superficieElevada,
          borderRadius: Redondeo.rChip,
          border: Border.all(color: p.borde),
        ),
        textStyle: textos.bodySmall,
      ),
    );
  }
}

/// Estilos de cifra con numerales tabulares.
///
/// Se usan en contadores de XP, oro, porcentajes de dominio y temporizadores,
/// para que el ancho no cambie mientras el número se anima.
abstract final class Cifras {
  static const List<FontFeature> _tabular = <FontFeature>[FontFeature.tabularFigures()];

  static TextStyle heroe(BuildContext context) => GoogleFonts.nunitoSans(
        fontSize: Tipo.heroe,
        fontWeight: FontWeight.w800,
        height: 1.05,
        color: context.paleta.textoPrimario,
        fontFeatures: _tabular,
      );

  static TextStyle grande(BuildContext context) => GoogleFonts.nunitoSans(
        fontSize: Tipo.titulo,
        fontWeight: FontWeight.w800,
        height: 1.1,
        color: context.paleta.textoPrimario,
        fontFeatures: _tabular,
      );

  static TextStyle media(BuildContext context) => GoogleFonts.nunitoSans(
        fontSize: Tipo.subtitulo,
        fontWeight: FontWeight.w700,
        height: 1.2,
        color: context.paleta.textoPrimario,
        fontFeatures: _tabular,
      );

  static TextStyle pequena(BuildContext context) => GoogleFonts.nunitoSans(
        fontSize: Tipo.secundario,
        fontWeight: FontWeight.w700,
        height: 1.2,
        color: context.paleta.textoSecundario,
        fontFeatures: _tabular,
      );
}
