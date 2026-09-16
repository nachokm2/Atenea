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
/// Lo que se prueba aquí es el interruptor entre las dos formas de dibujar. El arte
/// por capas llegó figura a figura y pieza a pieza, así que las dos convivieron
/// durante semanas: hoy las seis figuras apilan, pero una pieza sin capa sigue
/// saliendo de ficha al margen, y ahí sigue el riesgo.
///
/// Nada de esto lo tocaba ninguna prueba cuando se escribió. La única que rozaba
/// el widget, `avatar_equipo_test.dart`, usa la figura por defecto, y ese día no
/// tenía cuerpo desnudo: el camino apilado entero se quedaba sin ejecutar.
library;

import 'package:atenea/datos/dtos.dart';
import 'package:atenea/design/arte.dart';
import 'package:atenea/design/theme.dart';
import 'package:atenea/pantallas/entrada/widgets/catalogo_avatar.dart';
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

    testWidgets('las seis figuras tienen cuerpo desnudo', (WidgetTester tester) async {
      // Hubo meses en que solo lo tenían algunas, y el widget elegía camino por
      // figura. Ya no hace falta elegir, pero el interruptor se queda: si mañana
      // entra una séptima figura, vuelve a hacer falta el día que llegue sin su
      // arte.
      for (final String clave in Arte.personajes) {
        expect(Arte.conCuerpoDesnudo, contains(clave));
      }
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
      // juego de piezas: el objeto es el mismo, el cuerpo no. Por eso el
      // servidor no manda la familia y el cliente la pone.
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
        imagen('assets/arte/capas/femenino/botas_reforzadas_boots.webp'),
        findsOneWidget,
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

      // Tres: el cuerpo y sus dos capas teñibles, la piel y el pelo. Ninguna
      // imagen de equipo.
      expect(find.byType(Image), findsNWidgets(3));
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
        // La primera va por debajo de `body_base` (z=40), así que el cuerpo se
        // cuela entre ella y las otras dos. Y tras el cuerpo van sus dos capas
        // teñibles, que son parte del aprendiz y no del equipo: una armadura
        // tapa la piel, no al revés.
        'assets/arte/capas/masculino/a.webp',
        'assets/arte/capas/cuerpos/base_masculino_001.webp',
        'assets/arte/capas/cuerpos/base_masculino_001_piel.webp',
        'assets/arte/capas/cuerpos/base_masculino_001_pelo.webp',
        'assets/arte/capas/masculino/b.webp',
        'assets/arte/capas/masculino/c.webp',
      ]);
    });
  });

  group('lo que va por detrás del cuerpo', () {
    testWidgets('la espalda de una capa se pinta antes que el cuerpo',
        (WidgetTester tester) async {
      // El cuerpo no es el fondo de la pila: es `body_base`, en z=40, y hay
      // cuatro capas por debajo. Una capa prendida a los hombros cuelga POR
      // DETRÁS del aprendiz; pintarla encima de todo la convierte en un babero.
      await pintar(tester, const <CapaAvatar>[
        CapaAvatar(clave: 'cape_back', ranura: RanuraItem.capa, assetKey: 'atras.webp', z: 20),
        CapaAvatar(clave: 'cape_front', ranura: RanuraItem.capa, assetKey: 'delante.webp', z: 140),
      ]);

      final List<String> pedidas = tester
          .widgetList<Image>(find.byType(Image))
          .map((Image i) => (i.image as AssetImage).assetName)
          .toList();
      expect(pedidas, <String>[
        'assets/arte/capas/masculino/atras.webp',
        'assets/arte/capas/cuerpos/base_masculino_001.webp',
        'assets/arte/capas/cuerpos/base_masculino_001_piel.webp',
        'assets/arte/capas/cuerpos/base_masculino_001_pelo.webp',
        'assets/arte/capas/masculino/delante.webp',
      ]);
    });
  });

  group('la vista previa del Mercado', () {
    test('lleva el src del ítem, o no enseñaría la pieza puesta', () {
      // `capasConItem` fabricaba una capa mínima sin `src`, así que mirar un
      // objeto en la tienda lo enseñaba de ficha al margen aunque tuviera arte:
      // el aprendiz decidía una compra sin ver lo que compraba. El arreglo está
      // en el servidor, que ahora resuelve `layers` también en `ItemOut`.
      const Item item = Item(
        id: 'i1',
        codigo: 'botas_reforzadas',
        nombre: 'Botas reforzadas',
        ranura: RanuraItem.botas,
        capas: <CapaAvatar>[
          CapaAvatar(
            clave: 'boots',
            ranura: RanuraItem.botas,
            assetKey: 'botas_reforzadas_boots.webp',
            codigoItem: 'botas_reforzadas',
            z: 50,
          ),
        ],
      );

      final List<CapaAvatar> compuestas = capasConItem(const <CapaAvatar>[], item);

      expect(compuestas, hasLength(1));
      expect(compuestas.single.assetKey, 'botas_reforzadas_boots.webp');
    });

    test('sin capas resueltas sigue fabricando la mínima, que da ficha', () {
      // Un ítem sin arte por capas todavía: la vista previa no puede pintarlo
      // encima, pero tampoco puede quedarse sin enseñar nada.
      const Item item = Item(
        id: 'i2',
        codigo: 'yelmo_guardia',
        nombre: 'Yelmo de la Guardia',
        ranura: RanuraItem.cabeza,
      );

      final List<CapaAvatar> compuestas = capasConItem(const <CapaAvatar>[], item);

      expect(compuestas.single.codigoItem, 'yelmo_guardia');
      expect(compuestas.single.assetKey, isEmpty);
    });
  });

  group('la figura se elige, ya no se deriva', () {
    test('si el rostro ya es una figura, esa es la figura', () {
      // Desde que la creación enseña las seis y deja elegir, la elección viaja
      // en `rostro` —que es `face_id` en el servidor, 32 caracteres sin valores
      // tasados—. Sin esto, elegir una figura no serviría de nada.
      for (final String clave in Arte.personajes) {
        expect(Arte.claveDeFigura(rostro: clave), clave);
      }
    });

    test('la elección manda sobre el trato y la silueta', () {
      // Antes el trato decidía la familia. Ahora no: quien elige una figura
      // femenina y el trato masculino recibe la figura que eligió, porque es lo
      // que vio al elegirla. El trato sigue decidiendo cómo se le habla.
      expect(
        Arte.claveDeFigura(
          trato: FormaTrato.masculino,
          cuerpo: TipoCuerpo.robusto,
          rostro: 'base_femenino_003',
        ),
        'base_femenino_003',
      );
    });

    test('un personaje viejo conserva la figura que tenía', () {
      // Los creados antes guardaron `face_01`..`face_04`, no una figura. La
      // derivación se queda para ellos tal cual estaba, defectos incluidos:
      // cambiarla ahora les cambiaría la cara.
      expect(Arte.claveDeFigura(rostro: 'face_01'), 'base_masculino_002');
      expect(
        Arte.claveDeFigura(trato: FormaTrato.femenino, rostro: 'face_02'),
        'base_femenino_003',
      );
    });

    test('la derivación vieja mandaba dos rostros a la misma figura', () {
      // No es una prueba de algo que queramos: es el registro de por qué se
      // cambió. Con la familia ya fijada por el trato, `(variante % 3) + 1`
      // mandaba el rostro 1 y el 4 a la misma ilustración, así que de los cuatro
      // que ofrecía la pantalla salían tres. Nadie podía verlo desde ahí.
      expect(
        Arte.claveDeFigura(trato: FormaTrato.masculino, rostro: 'face_01'),
        Arte.claveDeFigura(trato: FormaTrato.masculino, rostro: 'face_04'),
      );
      // Con trato neutro no chocaban, pero por accidente: la paridad de la
      // variante decidía la familia, así que el rostro 4 se iba a la femenina.
      // Elegir «Rostro 4» cambiaba de sexo a la figura sin decirlo.
      expect(
        Arte.claveDeFigura(rostro: 'face_01'),
        isNot(Arte.claveDeFigura(rostro: 'face_04')),
      );
    });
  });

  group('la piel y el pelo se tiñen con lo que se eligió', () {
    testWidgets('el tono de piel elegido llega a la capa de piel',
        (WidgetTester tester) async {
      // Antes se ofrecían seis tonos y en el arte había dos, uno por familia.
      // Ninguno era elegible.
      await pintar(
        tester,
        const <CapaAvatar>[],
        rasgos: const RasgosAvatar(
          formaTrato: FormaTrato.masculino,
          rostro: 'base_masculino_001',
          tonoPiel: 'skin_06',
        ),
      );

      final Image capa = tester.widget<Image>(
        imagen('assets/arte/capas/cuerpos/base_masculino_001_piel.webp'),
      );
      expect(capa.color, CatalogoAvatar.piel('skin_06'));
      expect(capa.colorBlendMode, BlendMode.modulate);
    });

    testWidgets('y el color de pelo a la capa de pelo', (WidgetTester tester) async {
      await pintar(
        tester,
        const <CapaAvatar>[],
        rasgos: const RasgosAvatar(
          formaTrato: FormaTrato.masculino,
          rostro: 'base_masculino_001',
          colorCabello: 'hair_violet',
        ),
      );

      final Image capa = tester.widget<Image>(
        imagen('assets/arte/capas/cuerpos/base_masculino_001_pelo.webp'),
      );
      expect(capa.color, CatalogoAvatar.cabello('hair_violet'));
    });

    test('los diez colores de pelo son distintos entre sí', () {
      // El pintor de reserva los derivaba con un hash sobre los tokens del tema
      // y mandaba el negro, el verde y el violeta al mismo color. Desde que se
      // usa la paleta de verdad, cada elección es una elección.
      final Set<Color> vistos = <Color>{
        for (final OpcionAvatar o in CatalogoAvatar.coloresCabello)
          CatalogoAvatar.cabello(o.clave),
      };
      expect(vistos, hasLength(CatalogoAvatar.coloresCabello.length));
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
