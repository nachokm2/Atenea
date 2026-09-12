import 'package:atenea/data/almacen_tokens.dart';
import 'package:atenea/data/api_client.dart';
import 'package:atenea/datos/repositorios.dart';
import 'package:atenea/design/theme.dart';
import 'package:atenea/estado/celebraciones.dart';
import 'package:atenea/estado/sesion.dart';
import 'package:atenea/pantallas/entrada/acceso.dart';
import 'package:atenea/pantallas/entrada/bienvenida.dart';
import 'package:atenea/pantallas/entrada/crear_personaje.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:nested/nested.dart';
import 'package:provider/provider.dart';

void main() {
  for (final Size tamano in <Size>[
    const Size(320, 568),
  ]) {
    for (final double escala in <double>[1.3]) {
      testWidgets('$tamano x$escala', (WidgetTester tester) async {
        tester.view.physicalSize = tamano;
        tester.view.devicePixelRatio = 1.0;
        addTearDown(tester.view.reset);
        final List<String> errores = <String>[];
        final FlutterExceptionHandler? previo = FlutterError.onError;
        FlutterError.onError = (FlutterErrorDetails d) => errores.add(d.toString());
        addTearDown(() => FlutterError.onError = previo);

        final AlmacenTokens t = AlmacenTokens();
        final Repositorios repos = Repositorios(
            ApiClient(baseUrl: 'http://localhost/api/v1', tokens: t));
        final ControladorSesion sesion =
            ControladorSesion(repositorios: repos, tokens: t);
        List<SingleChildWidget> provs() => <SingleChildWidget>[
              Provider<Repositorios>.value(value: repos),
              ChangeNotifierProvider<ControladorSesion>.value(value: sesion),
              ChangeNotifierProvider<ColaCelebraciones>.value(
                  value: ColaCelebraciones()),
            ];
        Widget escalar(BuildContext c, Widget? w) => MediaQuery(
            data: MediaQuery.of(c).copyWith(textScaler: TextScaler.linear(escala)),
            child: w!);

        await tester.pumpWidget(MultiProvider(
          providers: provs(),
          child: MaterialApp(
              theme: AteneaTheme.oscuro(),
              builder: escalar,
              home: const PantallaCrearPersonaje()),
        ));
        await tester.pumpAndSettle();
        for (final String p in <String>['Cuerpo', 'Rostro', 'Cabello', 'Orden']) {
          await tester.tap(find.text(p), warnIfMissed: false);
          await tester.pumpAndSettle();
        }

        sesion.alPerderSesion();
        await tester.pumpWidget(MultiProvider(
          providers: provs(),
          child: MaterialApp(
              theme: AteneaTheme.oscuro(),
              builder: escalar,
              home: const PantallaBienvenida()),
        ));
        await tester.pumpAndSettle();
        await tester.tap(find.text('Siguiente'), warnIfMissed: false);
        await tester.pumpAndSettle();
        await tester.tap(find.text('Siguiente'), warnIfMissed: false);
        await tester.pumpAndSettle();

        final GoRouter r = GoRouter(
          initialLocation: '/acceso',
          routes: <RouteBase>[
            GoRoute(
                path: '/acceso',
                builder: (BuildContext c, GoRouterState s) =>
                    const PantallaAcceso()),
          ],
        );
        await tester.pumpWidget(MultiProvider(
          providers: provs(),
          child: MaterialApp.router(
              theme: AteneaTheme.oscuro(), routerConfig: r, builder: escalar),
        ));
        await tester.pumpAndSettle();
        await tester.tap(find.text('Entrar').first, warnIfMissed: false);
        await tester.pumpAndSettle();

        for (final String e in errores) {
          for (final String l in e.split('\n')) {
            debugPrint('>> $l');
          }
        }
        expect(errores, isEmpty, reason: '$tamano x$escala');
      });
    }
  }
}
