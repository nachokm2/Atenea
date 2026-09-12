import 'package:atenea/data/almacen_tokens.dart';
import 'package:atenea/data/api_client.dart';
import 'package:atenea/datos/repositorios.dart';
import 'package:atenea/design/theme.dart';
import 'package:atenea/estado/celebraciones.dart';
import 'package:atenea/estado/sesion.dart';
import 'package:atenea/pantallas/entrada/acceso.dart';
import 'package:atenea/pantallas/entrada/bienvenida.dart';
import 'package:atenea/pantallas/entrada/crear_personaje.dart';
import 'package:atenea/pantallas/entrada/widgets/avatar_lienzo.dart';
import 'package:atenea/pantallas/entrada/widgets/catalogo_avatar.dart';
import 'package:atenea/pantallas/entrada/widgets/ilustraciones.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

Repositorios _repos() {
  final AlmacenTokens tokens = AlmacenTokens();
  return Repositorios(ApiClient(baseUrl: 'http://localhost/api/v1', tokens: tokens));
}

Widget _envolver(Widget hijo, {ControladorSesion? sesion}) {
  final Repositorios repos = _repos();
  final ControladorSesion s = sesion ??
      ControladorSesion(repositorios: repos, tokens: AlmacenTokens());
  return MultiProvider(
    providers: [
      Provider<Repositorios>.value(value: repos),
      ChangeNotifierProvider<ControladorSesion>.value(value: s),
      ChangeNotifierProvider<ColaCelebraciones>.value(value: ColaCelebraciones()),
    ],
    child: MaterialApp(theme: AteneaTheme.oscuro(), home: hijo),
  );
}

void main() {
  testWidgets('P01 pinta el splash y el onboarding', (WidgetTester tester) async {
    final ControladorSesion sesion = ControladorSesion(
      repositorios: _repos(),
      tokens: AlmacenTokens(),
    );
    await tester.pumpWidget(_envolver(const PantallaBienvenida(), sesion: sesion));
    await tester.pump();
    expect(find.text('Atenea'), findsOneWidget);

    sesion.alPerderSesion();
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));
    expect(find.text('Carga lo que quieres aprender'), findsOneWidget);
    expect(find.text('Saltar'), findsOneWidget);
  });

  testWidgets('P02 pinta el formulario y cambia de modo', (WidgetTester tester) async {
    final Repositorios repos = _repos();
    final ControladorSesion sesion =
        ControladorSesion(repositorios: repos, tokens: AlmacenTokens());
    final GoRouter enrutador = GoRouter(
      initialLocation: '/acceso',
      routes: <RouteBase>[
        GoRoute(
          path: '/acceso',
          builder: (BuildContext c, GoRouterState s) => const PantallaAcceso(),
        ),
      ],
    );
    await tester.pumpWidget(
      MultiProvider(
        providers: [
          Provider<Repositorios>.value(value: repos),
          ChangeNotifierProvider<ControladorSesion>.value(value: sesion),
          ChangeNotifierProvider<ColaCelebraciones>.value(
            value: ColaCelebraciones(),
          ),
        ],
        child: MaterialApp.router(
          theme: AteneaTheme.oscuro(),
          routerConfig: enrutador,
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Crea tu cuenta'), findsOneWidget);
    await tester.tap(find.text('Entrar').first);
    await tester.pumpAndSettle();
    expect(find.text('Entra al Reino'), findsOneWidget);
  });

  testWidgets('P03 pinta el retrato y recorre las pestañas', (WidgetTester tester) async {
    await tester.pumpWidget(_envolver(const PantallaCrearPersonaje()));
    await tester.pumpAndSettle();
    expect(find.text('Crea tu personaje'), findsOneWidget);
    expect(find.byType(LienzoAvatar), findsWidgets);

    const Map<String, String> esperado = <String, String>{
      'Cuerpo': 'Tono de piel',
      'Rostro': 'Orejas',
      'Cabello': 'Estilo',
      'Orden': 'Tu Orden',
    };
    for (final MapEntry<String, String> e in esperado.entries) {
      await tester.tap(find.text(e.key));
      await tester.pumpAndSettle();
      expect(find.text(e.value.toUpperCase()), findsOneWidget, reason: e.key);
    }
    await tester.tap(find.byTooltip('Aleatorio'));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });

  testWidgets('El lienzo pinta todos los estilos y rostros', (WidgetTester tester) async {
    for (final OpcionAvatar pelo in CatalogoAvatar.cabellos) {
      for (final OpcionAvatar cara in CatalogoAvatar.rostros) {
        await tester.pumpWidget(
          MaterialApp(
            theme: AteneaTheme.oscuro(),
            home: Scaffold(
              body: Center(
                child: LienzoAvatar(
                  rasgos: RasgosAvatar(
                    cabello: pelo.clave,
                    rostro: cara.clave,
                    orejas: 'pointed',
                    tipoCuerpo: TipoCuerpo.robusto,
                  ),
                  orden: Arquetipo.arcano,
                  conCapa: true,
                ),
              ),
            ),
          ),
        );
        await tester.pump();
      }
    }
    expect(tester.takeException(), isNull);
  });

  testWidgets('Las tres ilustraciones se pintan', (WidgetTester tester) async {
    for (int i = 0; i < 3; i++) {
      await tester.pumpWidget(
        MaterialApp(
          theme: AteneaTheme.oscuro(),
          home: Scaffold(body: Center(child: IlustracionOnboarding(paso: i))),
        ),
      );
      await tester.pump();
    }
    expect(tester.takeException(), isNull);
  });
}
