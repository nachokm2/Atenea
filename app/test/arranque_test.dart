/// Prueba de arranque: la aplicación se levanta con los controladores reales
/// y el enrutador decide bien a dónde llevar al héroe.
///
/// Cubre las tres decisiones de `_redirigir` en `enrutador.dart`:
///
/// - Sin sesión y con el onboarding ya visto → P02, la pantalla de acceso.
/// - Sin sesión y sin onboarding visto → P01, la bienvenida.
/// - Ninguna de las dos hace una sola petición a la red.
library;

import 'package:atenea/app.dart';
import 'package:atenea/datos/repositorios.dart';
import 'package:atenea/estado/aventura.dart';
import 'package:atenea/estado/celebraciones.dart';
import 'package:atenea/estado/evaluacion.dart';
import 'package:atenea/estado/gamificacion.dart';
import 'package:atenea/estado/leccion.dart';
import 'package:atenea/estado/panel.dart';
import 'package:atenea/estado/personaje.dart';
import 'package:atenea/estado/sesion.dart';
import 'package:atenea/navegacion/enrutador.dart';
import 'package:atenea/nucleo/controlador_tema.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';
import 'package:provider/single_child_widget.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'ayudas.dart';

void main() {
  setUp(prepararTipografias);

  testWidgets(
    'arranca sin sesión y muestra la pantalla de acceso',
    (WidgetTester tester) async {
      // El héroe ya vio el onboarding en este dispositivo.
      SharedPreferences.setMockInitialValues(<String, Object>{
        'atenea_onboarding_visto': true,
      });

      final _Montaje montaje = await _montarAplicacion(tester);

      // El enrutador empieza en /inicio y la redirección debe desviarlo.
      expect(montaje.sesion.fase, FaseSesion.sinSesion);
      expect(montaje.sesion.haySesion, isFalse);

      // P02: título, los dos modos y los dos campos del formulario.
      expect(find.text('Crea tu cuenta'), findsOneWidget);
      expect(find.text('Crear cuenta'), findsWidgets);
      expect(find.text('Entrar'), findsWidgets);
      expect(find.byType(TextFormField), findsNWidgets(2));

      // No se coló ninguna pantalla del Reino: sin sesión no hay barra
      // inferior ni panel del héroe.
      expect(find.byType(NavigationBar), findsNothing);

      montaje.liberar();
    },
  );

  testWidgets(
    'sin onboarding visto la primera pantalla es la bienvenida',
    (WidgetTester tester) async {
      SharedPreferences.setMockInitialValues(<String, Object>{});

      final _Montaje montaje = await _montarAplicacion(tester);

      expect(montaje.sesion.onboardingVisto, isFalse);
      // P01: el onboarding, con su marca, su primera promesa y las dos
      // salidas. En ningún caso P02.
      expect(find.text('Crea tu cuenta'), findsNothing);
      expect(find.text('ATENEA'), findsOneWidget);
      expect(find.text('Carga lo que quieres aprender'), findsOneWidget);
      expect(find.text('Saltar'), findsOneWidget);
      expect(find.text('Ya tengo cuenta'), findsOneWidget);

      montaje.liberar();
    },
  );
}

/// Todo lo que la prueba necesita conservar del árbol montado.
class _Montaje {
  _Montaje({required this.sesion, required this.liberar});

  final ControladorSesion sesion;
  final VoidCallback liberar;
}

/// Monta [AplicacionAtenea] con los controladores reales sobre repositorios
/// que apuntan a un servidor inexistente.
Future<_Montaje> _montarAplicacion(WidgetTester tester) async {
  final AlmacenTokensFalso tokens = AlmacenTokensFalso();
  final Repositorios repos = repositoriosDePrueba(tokens);

  final ControladorSesion sesion =
      ControladorSesion(repositorios: repos, tokens: tokens);
  final ControladorTema tema = ControladorTema();
  final ControladorPanel panel = ControladorPanel(repos);
  final ControladorAventura aventura = ControladorAventura(repos);
  final ControladorLeccion leccion = ControladorLeccion(repos);
  final ControladorEvaluacion evaluacion = ControladorEvaluacion(repos);
  final ControladorPersonaje personaje = ControladorPersonaje(repos);
  final ControladorGamificacion gamificacion = ControladorGamificacion(repos);
  final ColaCelebraciones celebraciones = ColaCelebraciones();

  // El mismo orden de encendido que `main()`: primero la sesión, después el
  // enrutador, que ya nace sabiendo a dónde ir.
  await sesion.arrancar();
  final GoRouter enrutador = crearEnrutador(sesion);

  await tester.pumpWidget(
    MultiProvider(
      providers: <SingleChildWidget>[
        Provider<Repositorios>.value(value: repos),
        ChangeNotifierProvider<ControladorSesion>.value(value: sesion),
        ChangeNotifierProvider<ControladorTema>.value(value: tema),
        ChangeNotifierProvider<ControladorPanel>.value(value: panel),
        ChangeNotifierProvider<ControladorAventura>.value(value: aventura),
        ChangeNotifierProvider<ControladorLeccion>.value(value: leccion),
        ChangeNotifierProvider<ControladorEvaluacion>.value(value: evaluacion),
        ChangeNotifierProvider<ControladorPersonaje>.value(value: personaje),
        ChangeNotifierProvider<ControladorGamificacion>.value(
          value: gamificacion,
        ),
        ChangeNotifierProvider<ColaCelebraciones>.value(value: celebraciones),
      ],
      child: AplicacionAtenea(enrutador: enrutador),
    ),
  );
  // Un par de fotogramas: la redirección del enrutador y la primera
  // animación de entrada.
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 600));

  return _Montaje(
    sesion: sesion,
    liberar: () {
      enrutador.dispose();
      celebraciones.dispose();
      gamificacion.dispose();
      personaje.dispose();
      evaluacion.dispose();
      leccion.dispose();
      aventura.dispose();
      panel.dispose();
      tema.dispose();
      sesion.dispose();
    },
  );
}
