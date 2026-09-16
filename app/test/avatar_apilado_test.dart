/// El equipo se pinta encima del cuerpo, no solo al lado.
///
/// Durante mucho tiempo no se podía: las seis figuras eran ilustraciones ya
/// vestidas y cada pieza del catálogo era una ficha recortada a su propio
/// encuadre, así que superponerlas daba un collage. De ahí las fichas al margen,
/// que es lo que prueba `avatar_equipo_test.dart`.
///
/// Ya sí se puede. `scripts/vestir.py` genera cuerpos desnudos y capas que
/// comparten el lienzo maestro de 1024×1024, con la pieza colocada dentro, así
/// que apilarlas centradas las deja en su sitio sin calcular nada.
///
/// Lo que se prueba aquí es el interruptor entre las dos formas de dibujar, que
/// es donde está el riesgo de verdad: el arte por capas llega figura a figura y
/// pieza a pieza, así que las dos formas conviven durante meses. Nada de esto lo
/// tocaba ninguna prueba: la figura por defecto de `avatar_equipo_test.dart` es
/// `base_masculino_002`, que no tiene cuerpo desnudo, así que el camino apilado
/// entero se quedaba sin ejecutar.
library;

import 'package:atenea/datos/dtos.dart';
import 'package:atenea/design/arte.dart';
import 'package:atenea/design/theme.dart';
import 'package:atenea/pantallas/personaje/widgets/avatar_capas.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'ayudas.dart';

void main() {
  setUp(prepararTipografias);

  /// Rasgos que resuelven a una figura **con** cuerpo desnudo.
  ///
  /// `face_03` da variante 3, y `3 % 3 + 1` es la figura 001; el trato
  /// masculino fija la familia. Si algún día cambia el reparto de figuras, esta
  /// prueba lo dirá antes que nadie.
  const RasgosAvatar conCapas = RasgosAvatar(
    formaTrato: FormaTrato.masculino,
    rostro: 'face_03',
  );

  /// Rasgos que resuelven a una figura **sin** cuerpo desnudo todavía.
  const RasgosAvatar sinCapas = RasgosAvatar(
    formaTrato: FormaTrato.masculino,
    rostro: 'face_01',
  );

  Future<void> pintar(
    WidgetTester tester,
    List<CapaAvatar> capas, {
    RasgosAvatar rasgos = conCapas,
  }) async {
    await tester.binding.setSurfaceSize(const Size(412, 915));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(
      MaterialApp(
        theme: AteneaTheme.oscuro(),
        debugShowCheckedModeBanner: false,
        home: Scaffold(
          body: Center(child: AvatarCapas(capas: capas, rasgos: rasgos)),
        ),
      ),
    );
    await tester.pump();
  }

  /// Busca una imagen por la ruta exacta del recurso que pide.
  Finder imagen(String ruta) => find.byWidgetPredicate(
        (Widget w) => w is Image && w.image is AssetImage && (w.image as AssetImage).assetName == ruta,
        description: 'Image($ruta)',
      );

  group('la figura decide cómo se dibuja', () {
    testWidgets('una figura con cuerpo desnudo pinta el cuerpo, no la vestida',
        (WidgetTester tester) async {
      await pintar(tester, const <CapaAvatar>[]);

      expect(imagen('assets/arte/capas/cuerpos/base_masculino_001.webp'), findsOneWidget);
      expect(imagen('assets/arte/personajes/base_masculino_001.webp'), findsNothing);
    });

    testWidgets('una figura sin cuerpo desnudo sigue con la ilustración vestida',
        (WidgetTester tester) async {
      // Es lo que ven hoy cinco de las seis figuras. No es un respaldo de
      // emergencia: es el camino normal mientras no llegue su arte.
      await pintar(tester, const <CapaAvatar>[], rasgos: sinCapas);

      expect(imagen('assets/arte/personajes/base_masculino_002.webp'), findsOneWidget);
      expect(imagen('assets/arte/capas/cuerpos/base_masculino_002.webp'), findsNothing);
    });
  });

  group('las piezas con capa se pintan encima', () {
    testWidgets('una capa con src sale como imagen sobre el cuerpo',
        (WidgetTester tester) async {
      await pintar(tester, const <CapaAvatar>[
        CapaAvatar(
          clave: 'boots',
          ranura: RanuraItem.botas,
          codigoItem: 'botas_reforzadas',
          assetKey: 'botas_reforzadas_boots.webp',
          z: 60,
        ),
      ]);

      expect(
        imagen('assets/arte/capas/masculino/botas_reforzadas_boots.webp'),
        findsOneWidget,
      );
    });

    testWidgets('y entonces no repite ficha al margen', (WidgetTester tester) async {
      // Verla dos veces —puesta y de ficha— sería peor que no verla: el
      // aprendiz no sabría cuál de las dos es su personaje.
      await pintar(tester, const <CapaAvatar>[
        CapaAvatar(
          clave: 'boots',
          ranura: RanuraItem.botas,
          codigoItem: 'botas_reforzadas',
          assetKey: 'botas_reforzadas_boots.webp',
          z: 60,
        ),
      ]);

      expect(find.byType(ImagenItem), findsNothing);
    });

    testWidgets('la familia sale de la figura, no del servidor',
        (WidgetTester tester) async {
      // El mismo `src` con una figura femenina tiene que ir a buscar el otro
      // juego de piezas: el objeto es el mismo, el cuerpo no.
      await pintar(
        tester,
        const <CapaAvatar>[
          CapaAvatar(
            clave: 'boots',
            ranura: RanuraItem.botas,
            assetKey: 'botas_reforzadas_boots.webp',
            z: 60,
          ),
        ],
        rasgos: const RasgosAvatar(formaTrato: FormaTrato.femenino, rostro: 'face_03'),
      );

      expect(
        imagen('assets/arte/capas/masculino/botas_reforzadas_boots.webp'),
        findsNothing,
      );
    });
  });

  group('las piezas sin capa no desaparecen', () {
    testWidgets('sin src, la pieza sigue saliendo de ficha al margen',
        (WidgetTester tester) async {
      // Es el caso de 30 de los 31 objetos que se llevan puestos. Si al
      // estrenar el modo apilado dejaran de verse, el oro del Mercado habría
      // comprado algo invisible: exactamente el fallo que se arregló poniendo
      // las fichas.
      await pintar(tester, const <CapaAvatar>[
        CapaAvatar(clave: 'head', ranura: RanuraItem.cabeza, codigoItem: 'yelmo_guardia', z: 90),
      ]);

      expect(find.byType(ImagenItem), findsOneWidget);
    });

    testWidgets('conviven la pintada y la de ficha', (WidgetTester tester) async {
      await pintar(tester, const <CapaAvatar>[
        CapaAvatar(
          clave: 'boots',
          ranura: RanuraItem.botas,
          codigoItem: 'botas_reforzadas',
          assetKey: 'botas_reforzadas_boots.webp',
          z: 60,
        ),
        CapaAvatar(clave: 'head', ranura: RanuraItem.cabeza, codigoItem: 'yelmo_guardia', z: 90),
      ]);

      expect(
        imagen('assets/arte/capas/masculino/botas_reforzadas_boots.webp'),
        findsOneWidget,
      );
      expect(find.byType(ImagenItem), findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  });

  group('lo que el manifiesto manda', () {
    testWidgets('una capa sin src no pide ninguna imagen de capa',
        (WidgetTester tester) async {
      // Un rasgo (pelo, rostro) ocupa capa y no es equipo: no tiene arte ni
      // ficha, y pedir `capas//.webp` sería una ruta rota.
      await pintar(tester, const <CapaAvatar>[
        CapaAvatar(clave: 'hair_front', z: 100),
      ]);

      expect(find.byType(Image), findsOneWidget); // solo el cuerpo
      expect(tester.takeException(), isNull);
    });

    testWidgets('las capas se pintan en el orden en que llegan',
        (WidgetTester tester) async {
      // El servidor las manda ordenadas por z y el cliente no las recompone.
      // Que el orden se respete es lo que hace que una capa quede por detrás
      // del cuerpo y el broche por delante.
      await pintar(tester, const <CapaAvatar>[
        CapaAvatar(clave: 'cape_back', ranura: RanuraItem.capa, assetKey: 'a.webp', z: 20),
        CapaAvatar(clave: 'boots', ranura: RanuraItem.botas, assetKey: 'b.webp', z: 60),
        CapaAvatar(clave: 'cape_front', ranura: RanuraItem.capa, assetKey: 'c.webp', z: 140),
      ]);

      final List<String> pedidas = tester
          .widgetList<Image>(find.byType(Image))
          .map((Image i) => (i.image as AssetImage).assetName)
          .toList();
      expect(pedidas, <String>[
        'assets/arte/capas/cuerpos/base_masculino_001.webp',
        'assets/arte/capas/masculino/a.webp',
        'assets/arte/capas/masculino/b.webp',
        'assets/arte/capas/masculino/c.webp',
      ]);
    });
  });

  group('el catálogo de rutas', () {
    test('toda figura declarada con cuerpo desnudo es una figura real', () {
      // Un error de dedo aquí no rompe nada visible: la imagen falla, cae al
      // `errorBuilder` y sale el muñeco vectorial. Se vería raro sin que nadie
      // supiera por qué.
      for (final String clave in Arte.conCuerpoDesnudo) {
        expect(Arte.personajes, contains(clave));
      }
    });
  });
}
