/// El cuerpo se dibuja en tres piezas, y cada mano lleva su piel.
///
/// Está partido para poder **apagar** la mano que sostiene algo. Cada pieza
/// empuñada del catálogo trae su propio puño dibujado —el modelo lo añadió
/// porque el estilo le prohibía tocar las manos existentes y a la vez se le
/// pedía un arma empuñada— y ese puño no tapa la mano de debajo: se ven dos.
///
/// Apagarla todavía no se hace. Se compuso la pila fuera de la aplicación y se
/// miró: el puño del arma no cae donde está la mano —de 133 px por encima a
/// 184 px por debajo según la pieza— así que apagarla deja el antebrazo cortado
/// con el puño flotando aparte. Y ese puño va pintado dentro del arma, así que
/// no se tiñe: sería naranja sobre cualquiera de los otros cinco tonos de piel.
/// Falta arte de arma sin puño, con la empuñadura en el sitio de la mano.
///
/// Mientras tanto lo que se comprueba aquí es que partir el cuerpo **no cambió
/// nada**, que es el riesgo de hoy: el aprendiz sin arma —la mayoría— tiene que
/// ver exactamente la misma figura. La igualdad píxel a píxel la garantiza
/// `scripts/separar_manos.py`, que se niega a escribir si recomponer las tres
/// piezas no devuelve el original; lo de aquí es la otra mitad, que la pila las
/// pida todas y ninguna se quede sin teñir.
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

  testWidgets('equipar algo no le quita ninguna mano al cuerpo',
      (WidgetTester tester) async {
    // Apagar una mano deja el antebrazo cortado en seco: se compuso la pila
    // fuera de la aplicación y se miró. Lo que se hizo en su lugar fue quitarle
    // el puño al arma y ponerla donde está la mano.
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
}
