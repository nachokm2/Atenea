/// El equipo que el aprendiz compra tiene que verse en alguna parte.
///
/// No se veía en ninguna. `AvatarCapas` calculaba el equipo, dibujaba la
/// ilustración del héroe y solo pintaba el equipo dentro del `errorBuilder` de
/// esa imagen: como las seis figuras existen en disco, esa rama no se ejecutaba
/// jamás. El oro del Mercado compraba algo invisible.
///
/// No se arregla pintando las piezas encima: la ilustración ya viene vestida y
/// cada pieza está dibujada en su propio encuadre, así que superponerlas daría
/// un collage. Se muestran alrededor, que es lo que prescribe la documentación
/// del propio catálogo de arte.
///
/// Ninguna prueba tocaba este widget antes de esta.
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

  CapaAvatar capa(RanuraItem ranura, String codigo, {String? nombre}) => CapaAvatar(
        clave: nombre ?? ranura.name,
        ranura: ranura,
        codigoItem: codigo,
        z: 50,
      );

  Future<void> pintar(WidgetTester tester, List<CapaAvatar> capas) async {
    await tester.binding.setSurfaceSize(const Size(412, 915));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(
      MaterialApp(
        theme: AteneaTheme.oscuro(),
        debugShowCheckedModeBanner: false,
        home: Scaffold(body: Center(child: AvatarCapas(capas: capas))),
      ),
    );
    await tester.pump();
  }

  group('el equipo puesto se ve', () {
    testWidgets('sin equipo no hay ninguna ficha', (WidgetTester tester) async {
      await pintar(tester, const <CapaAvatar>[]);

      expect(find.byType(ImagenItem), findsNothing);
      expect(tester.takeException(), isNull);
    });

    testWidgets('cada pieza equipada aparece junto al héroe', (WidgetTester tester) async {
      await pintar(tester, <CapaAvatar>[
        capa(RanuraItem.cabeza, 'yelmo_guardia'),
        capa(RanuraItem.arma, 'espada_del_sql'),
      ]);

      expect(find.byType(ImagenItem), findsNWidgets(2));
      expect(tester.takeException(), isNull);
    });

    testWidgets('una capa aporta dos capas pero una sola ficha', (WidgetTester tester) async {
      // El servidor manda `cape_back` y `cape_front`, las dos del mismo ítem.
      await pintar(tester, <CapaAvatar>[
        capa(RanuraItem.capa, 'capa_carmesi', nombre: 'cape_back'),
        capa(RanuraItem.capa, 'capa_carmesi', nombre: 'cape_front'),
      ]);

      expect(find.byType(ImagenItem), findsOneWidget);
    });

    testWidgets('las ocho ranuras del vestidor caben sin desbordar', (WidgetTester tester) async {
      await pintar(tester, <CapaAvatar>[
        for (final RanuraItem ranura in ranurasDelVestidorInterno)
          capa(ranura, 'objeto_${ranura.name}'),
      ]);

      expect(find.byType(ImagenItem), findsNWidgets(ranurasDelVestidorInterno.length));
      expect(tester.takeException(), isNull);
    });

    testWidgets('una capa sin código de ítem no pinta ficha', (WidgetTester tester) async {
      // Es el caso de un rasgo (pelo, rostro): ocupa capa pero no es equipo.
      await pintar(tester, const <CapaAvatar>[
        CapaAvatar(clave: 'hair_front', z: 100),
      ]);

      expect(find.byType(ImagenItem), findsNothing);
    });
  });

  group('la vista previa del Mercado', () {
    test('compone la pieza que se está mirando, con su código', () {
      const Item item = Item(
        id: 'i1',
        codigo: 'yelmo_guardia',
        nombre: 'Yelmo de la Guardia',
        ranura: RanuraItem.cabeza,
      );

      final List<CapaAvatar> compuestas = capasConItem(const <CapaAvatar>[], item);

      expect(compuestas, hasLength(1));
      expect(compuestas.single.ranura, RanuraItem.cabeza);
      // Sin el código no hay ilustración que buscar, y la vista previa vuelve a
      // quedarse en nada.
      expect(compuestas.single.codigoItem, 'yelmo_guardia');
    });

    test('sustituye lo que ya llevabas en esa ranura, no lo borra', () {
      const Item nuevo = Item(
        id: 'i2',
        codigo: 'capucha_estudio',
        nombre: 'Capucha',
        ranura: RanuraItem.cabeza,
      );

      final List<CapaAvatar> compuestas = capasConItem(
        <CapaAvatar>[
          capa(RanuraItem.cabeza, 'yelmo_guardia'),
          capa(RanuraItem.botas, 'botas_de_hierro'),
        ],
        nuevo,
      );

      final Map<RanuraItem?, String?> porRanura = <RanuraItem?, String?>{
        for (final CapaAvatar c in compuestas) c.ranura: c.codigoItem,
      };
      expect(porRanura[RanuraItem.cabeza], 'capucha_estudio');
      expect(porRanura[RanuraItem.botas], 'botas_de_hierro');
    });
  });
}
