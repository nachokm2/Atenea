/// El cuerpo se dibuja en tres piezas, y la mano se aparta cuando sobra.
///
/// Cada pieza empuñada del catálogo venía con un puño dibujado dentro: el modelo
/// lo añadió porque el estilo le prohibía tocar las manos existentes y a la vez
/// se le pedía un arma empuñada. En pantalla salían **dos manos**, y así lo
/// encontró el primer aprendiz que equipó una espada.
///
/// El arreglo no fue borrar ese puño ni taparlo —las dos se probaron y se
/// midieron: borrarlo deja un hueco que la mano del cuerpo no alcanza a tapar
/// porque es más pequeña que él, y taparlo deja un fleco naranja alrededor—.
/// Fue reconocer que ese puño **ya agarra el arma**, porque se dibujó
/// agarrándola, y que lo único que le faltaba era ser del color del aprendiz.
/// Así que se saca a su propia capa, se tiñe, y la mano del cuerpo de ese lado
/// se quita de en medio.
///
/// Aquí se fijan las dos mitades, que son las dos formas de estropearlo:
///
/// - **Apagar una mano sin tener puño que ponga en su sitio** deja el brazo
///   cortado en seco. Pasa con las dos piezas a las que no se les pudo sacar.
/// - **No apagarla teniendo puño** devuelve las dos manos, que es el fallo que
///   esto venía a arreglar.
///
/// Ninguna de las dos lanza nada ni rompe ninguna prueba de maquetación: se ven,
/// y ya está. Por eso están escritas.
library;

import 'package:atenea/datos/dtos.dart';
import 'package:atenea/design/arte.dart';
import 'package:atenea/design/theme.dart';
import 'package:atenea/pantallas/entrada/widgets/catalogo_avatar.dart';
import 'package:atenea/pantallas/personaje/widgets/avatar_capas.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'ayudas.dart';

/// Una figura con cuerpo desnudo, que es la que dibuja apilando.
const RasgosAvatar _conCuerpo = RasgosAvatar(
  formaTrato: FormaTrato.masculino,
  rostro: 'base_masculino_002',
  tonoPiel: 'skin_06',
);

CapaAvatar _capa(String clave, RanuraItem ranura, int z) => CapaAvatar(
      clave: clave,
      ranura: ranura,
      assetKey: 'lo_que_sea_$clave.webp',
      z: z,
    );

Future<void> _pintar(WidgetTester tester, List<CapaAvatar> capas) async {
  await tester.binding.setSurfaceSize(const Size(412, 915));
  addTearDown(() => tester.binding.setSurfaceSize(null));
  await tester.pumpWidget(
    MaterialApp(
      theme: AteneaTheme.oscuro(),
      home: Scaffold(
        body: AvatarCapas(capas: capas, rasgos: _conCuerpo, tamano: 300),
      ),
    ),
  );
  await tester.pump();
}

/// Dónde acaba la capa que `_capa` fabrica: el cliente le pone delante la
/// carpeta de la familia, que el servidor no manda.
String _pieza(String clave) => 'assets/arte/capas/masculino/lo_que_sea_$clave.webp';

/// Las rutas de imagen que el avatar pintó de verdad.
List<String> _pintadas(WidgetTester tester) => tester
    .widgetList<Image>(find.byType(Image))
    .map((Image i) => i.image)
    .whereType<AssetImage>()
    .map((AssetImage a) => a.assetName)
    .toList();

void main() {
  setUp(prepararTipografias);

  const String figura = 'base_masculino_002';

  testWidgets('el cuerpo llega entero, en sus tres piezas',
      (WidgetTester tester) async {
    await _pintar(tester, const <CapaAvatar>[]);
    final List<String> rutas = _pintadas(tester);

    expect(rutas, contains(Arte.cuerpoSinManos(figura)));
    expect(rutas, contains(Arte.mano(figura, derecha: true)));
    expect(rutas, contains(Arte.mano(figura, derecha: false)));
    // Y el de una pieza ya no se pinta: quedaría el dibujo por duplicado.
    expect(rutas, isNot(contains(Arte.cuerpo(figura))));
  });

  testWidgets('la piel también, y ninguna mano se queda sin teñir',
      (WidgetTester tester) async {
    // La piel se dibuja POR ENCIMA del cuerpo para teñirlo, así que hubo que
    // partirla igual: entera repintaba el cien por cien de las manos —medido en
    // las seis figuras— y las habría devuelto en cuanto se apagara alguna.
    //
    // Una mano sin su trozo de piel no lanza nada: se ve del color del dibujo.
    // El aprendiz con la piel «Ébano» tendría el cuerpo oscuro y las manos
    // claras, y las seis pruebas de arriba seguirían en verde.
    await _pintar(tester, const <CapaAvatar>[]);
    final List<String> rutas = _pintadas(tester);

    expect(rutas, contains(Arte.pielSinManos(figura)));
    expect(rutas, contains(Arte.manoPiel(figura, derecha: true)));
    expect(rutas, contains(Arte.manoPiel(figura, derecha: false)));
    expect(rutas, isNot(contains(Arte.piel(figura))));

    for (final String pieza in <String>[
      Arte.pielSinManos(figura),
      Arte.manoPiel(figura, derecha: true),
      Arte.manoPiel(figura, derecha: false),
    ]) {
      final Image capa = tester.widget<Image>(
        find.byWidgetPredicate(
          (Widget w) =>
              w is Image && w.image is AssetImage && (w.image as AssetImage).assetName == pieza,
        ),
      );
      expect(capa.color, CatalogoAvatar.piel('skin_06'), reason: pieza);
      expect(capa.colorBlendMode, BlendMode.modulate, reason: pieza);
    }
  });

  testWidgets('el pelo no se parte, porque no toca las manos',
      (WidgetTester tester) async {
    // Se midió: cero píxeles en común, en las seis figuras. Partirlo habría
    // sido trabajo y dos recursos más por figura para nada.
    await _pintar(tester, const <CapaAvatar>[]);

    expect(_pintadas(tester), contains(Arte.pelo(figura)));
  });

  testWidgets('una pieza SIN puño propio no le quita la mano al cuerpo',
      (WidgetTester tester) async {
    // A dos piezas del catálogo no se les pudo sacar el puño: a una no se le
    // encuentra y a la otra le quedaría demasiada muñeca al aire. Esas tienen
    // que seguir teniendo la mano del cuerpo debajo, o el brazo acaba cortado.
    await _pintar(tester, <CapaAvatar>[
      _capa('weapon', RanuraItem.arma, 130),
      _capa('offhand', RanuraItem.secundaria, 80),
    ]);
    final List<String> rutas = _pintadas(tester);

    expect(rutas, contains(Arte.mano(figura, derecha: true)));
    expect(rutas, contains(Arte.mano(figura, derecha: false)));
    expect(rutas, contains(Arte.manoPiel(figura, derecha: true)));
    expect(rutas, contains(Arte.manoPiel(figura, derecha: false)));
  });

  testWidgets('una pieza CON puño propio sí se la quita, y solo esa',
      (WidgetTester tester) async {
    // Las dos mitades del arreglo en una sola prueba: si no se apaga, vuelven
    // las dos manos; si se apagan las dos, la izquierda se queda sin nada.
    await _pintar(tester, <CapaAvatar>[
      const CapaAvatar(
        clave: 'weapon',
        ranura: RanuraItem.arma,
        assetKey: 'espada_corta_acero_weapon.webp',
        z: 130,
      ),
    ]);
    final List<String> rutas = _pintadas(tester);

    expect(
      rutas,
      isNot(contains(Arte.mano(figura, derecha: true))),
      reason: 'el arma trae la suya; con las dos se ven dos manos',
    );
    expect(
      rutas,
      contains(Arte.mano(figura, derecha: false)),
      reason: 'la izquierda no sostiene nada y se quedaría manca',
    );
  });

  testWidgets('y el puño de la pieza se tiñe con el tono elegido',
      (WidgetTester tester) async {
    // Es el motivo de sacarlo a una capa aparte. Dentro del arma se quedaba
    // naranja: sobre la piel «Ébano» era un puño naranja en un brazo marrón
    // oscuro, y los seis tonos volvían a ser seis tonos que no se aplican.
    // Sin esta comprobación, olvidar el tinte no rompe nada: solo se ve.
    const String src = 'espada_corta_acero_weapon.webp';
    await _pintar(tester, const <CapaAvatar>[
      CapaAvatar(clave: 'weapon', ranura: RanuraItem.arma, assetKey: src, z: 130),
    ]);

    final Image puno = tester.widget<Image>(
      find.byWidgetPredicate(
        (Widget w) =>
            w is Image &&
            w.image is AssetImage &&
            (w.image as AssetImage).assetName ==
                Arte.punoDeLaPieza(figura: figura, src: src),
      ),
    );
    expect(puno.color, CatalogoAvatar.piel('skin_06'));
    expect(puno.colorBlendMode, BlendMode.modulate);
  });

  testWidgets('un guante no cuenta como puño, aunque vaya en la mano',
      (WidgetTester tester) async {
    // Se dibuja encima de la mano y la necesita debajo: un guante sin mano es
    // un guante flotando. Es el caso que más fácil se cuela al escribir la regla.
    await _pintar(tester, <CapaAvatar>[_capa('gloves', RanuraItem.guantes, 70)]);
    final List<String> rutas = _pintadas(tester);

    expect(rutas, contains(Arte.mano(figura, derecha: true)));
    expect(rutas, contains(Arte.mano(figura, derecha: false)));
  });


  testWidgets('la mano se pinta SOBRE el arma, que es lo que la hace agarrarla',
      (WidgetTester tester) async {
    // Debajo, se vería el puño que la pieza traía dibujado —naranja, y sin
    // teñir sobre cualquiera de los seis tonos de piel—. Encima, agarra la del
    // aprendiz. El arreglo entero vive en este orden.
    await _pintar(tester, <CapaAvatar>[_capa('weapon', RanuraItem.arma, 130)]);
    final List<String> rutas = _pintadas(tester);

    // Primero que el arma esté; si no, comparar posiciones compara con -1 y la
    // prueba pasa sin haber mirado nada. Me pasó al escribirla.
    expect(rutas, contains(_pieza('weapon')));
    expect(
      rutas.indexOf(Arte.mano(figura, derecha: true)),
      greaterThan(rutas.indexOf(_pieza('weapon'))),
    );
  });

  testWidgets('pero los guantes van sobre la mano', (WidgetTester tester) async {
    // Y por eso no pueden viajar con el resto del equipo: van por z=70, antes
    // que el arma, así que el orden del Reino los dejaría debajo de la mano. Un
    // guante debajo de la mano es un guante que no se ve, y el aprendiz habría
    // pagado por él.
    await _pintar(tester, <CapaAvatar>[
      _capa('gloves', RanuraItem.guantes, 70),
      _capa('weapon', RanuraItem.arma, 130),
    ]);
    final List<String> rutas = _pintadas(tester);

    expect(rutas, containsAll(<String>[_pieza('gloves'), _pieza('weapon')]));
    expect(
      rutas.indexOf(_pieza('gloves')),
      greaterThan(rutas.indexOf(Arte.mano(figura, derecha: true))),
    );
    // Y el arma sigue debajo de la mano, que es lo otro que hay que conservar.
    expect(
      rutas.indexOf(_pieza('weapon')),
      lessThan(rutas.indexOf(Arte.mano(figura, derecha: true))),
    );
  });

  testWidgets('sobre una figura NO canónica, el puño se mueve con su arma',
      (WidgetTester tester) async {
    // Las piezas se dibujaron sobre la figura canónica de cada familia, así que
    // sobre las otras cuatro el cliente las desplaza hasta la mano de esa
    // figura. El puño que trae el arma tiene que viajar con ella.
    //
    // No lo hacía: el arma se movía y el puño se quedaba en el sitio de la
    // canónica, así que salía una mano flotando y el brazo cortado. En cuatro de
    // las seis figuras, es decir en la mayoría de los aprendices. No lo vio
    // ninguna prueba porque todas montaban la canónica, que es justo donde el
    // fallo no existe: su ajuste es la identidad.
    const String otra = 'base_masculino_001';
    expect(Arte.ajuste(otra).esNeutro, isFalse, reason: 'si fuera neutra no probaría nada');

    await tester.binding.setSurfaceSize(const Size(412, 915));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(
      MaterialApp(
        theme: AteneaTheme.oscuro(),
        home: const Scaffold(
          body: AvatarCapas(
            capas: <CapaAvatar>[
              CapaAvatar(
                clave: 'weapon',
                ranura: RanuraItem.arma,
                assetKey: 'espada_corta_acero_weapon.webp',
                z: 130,
              ),
            ],
            rasgos: RasgosAvatar(formaTrato: FormaTrato.masculino, rostro: otra),
            tamano: 300,
          ),
        ),
      ),
    );
    await tester.pump();

    Offset desplazamientoDe(String ruta) {
      final Finder imagen = find.byWidgetPredicate(
        (Widget w) =>
            w is Image && w.image is AssetImage && (w.image as AssetImage).assetName == ruta,
      );
      expect(imagen, findsOneWidget, reason: 'falta $ruta');
      final Iterable<Transform> envoltorios =
          tester.widgetList<Transform>(find.ancestor(of: imagen, matching: find.byType(Transform)));
      for (final Transform t in envoltorios) {
        // La traslación de una Matrix4 vive en las posiciones 12 y 13.
        final double dx = t.transform.storage[12];
        final double dy = t.transform.storage[13];
        if (dx != 0 || dy != 0) return Offset(dx, dy);
      }
      return Offset.zero;
    }

    final Offset arma = desplazamientoDe(Arte.capaDeEquipo(
      figura: otra,
      src: 'espada_corta_acero_weapon.webp',
    ));
    final Offset puno = desplazamientoDe(Arte.punoDeLaPieza(
      figura: otra,
      src: 'espada_corta_acero_weapon.webp',
    ));

    expect(arma, isNot(Offset.zero), reason: 'esta figura sí se ajusta');
    expect(puno, arma, reason: 'el puño tiene que ir donde va su arma');
  });
}
