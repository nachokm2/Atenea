/// Raíz de la aplicación: temas, idioma, enrutador y capa de celebraciones.
library;

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import 'design/theme.dart';
import 'estado/sesion.dart';
import 'navegacion/armazon.dart';
import 'nucleo/controlador_tema.dart';

/// Aplicación de Atenea.
class AplicacionAtenea extends StatelessWidget {
  const AplicacionAtenea({required this.enrutador, super.key});

  /// Enrutador ya construido en `main`, para que sobreviva a las
  /// reconstrucciones del árbol.
  final GoRouter enrutador;

  @override
  Widget build(BuildContext context) {
    final ThemeMode modo = context.select<ControladorTema, ThemeMode>(
      (ControladorTema t) => t.modo,
    );
    final bool reducirPorAjuste = context.select<ControladorSesion, bool>(
      (ControladorSesion s) => s.ajustes?.reducirMovimiento ?? false,
    );

    return MaterialApp.router(
      title: 'Atenea',
      debugShowCheckedModeBanner: false,
      theme: AteneaTheme.claro(),
      darkTheme: AteneaTheme.oscuro(),
      themeMode: modo,
      locale: const Locale('es'),
      supportedLocales: const <Locale>[
        Locale('es'),
        Locale('es', 'CL'),
      ],
      localizationsDelegates: const <LocalizationsDelegate<Object>>[
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      routerConfig: enrutador,
      builder: (BuildContext context, Widget? hijo) {
        final MediaQueryData medios = MediaQuery.of(context);
        // La preferencia de Ajustes (P21) se suma a la del sistema: a partir
        // de aquí, `reducirMovimiento(context)` responde a ambas.
        return MediaQuery(
          data: medios.copyWith(
            disableAnimations: medios.disableAnimations || reducirPorAjuste,
          ),
          // Por encima de cualquier pantalla, incluidos los flujos inmersivos.
          child: CapaCelebraciones(hijo: hijo ?? const SizedBox.shrink()),
        );
      },
    );
  }
}
