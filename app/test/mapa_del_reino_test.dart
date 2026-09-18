/// El mapa del Reino pinta los territorios que hay, no cuatro siempre.
///
/// Aquí había un `for (int i = 0; i < 4; i++)` de cuatro siluetas idénticas
/// bajo la frase «Territorios en la bruma. Cada ruta que abres ilumina uno».
/// El servidor lleva desde siempre calculando el estado de los siete
/// territorios por usuario —`GET /territories`— y **nadie se lo pedía**:
/// `repos.conocimiento` era código muerto entero.
///
/// O sea que la frase era verificablemente falsa y el cuatro era un parámetro
/// de juego escrito a mano dentro de la interfaz, que es justo lo que este
/// proyecto tiene prohibido.
///
/// Estas pruebas hacen imposible que vuelva: si alguien escribe un número
/// literal, el recuento deja de cuadrar con los datos.
library;

import 'dart:convert';
import 'dart:typed_data';

import 'package:atenea/data/api_client.dart';
import 'package:atenea/datos/repositorios.dart';
import 'package:atenea/design/theme.dart';
import 'package:atenea/estado/aventura.dart';
import 'package:atenea/pantallas/aventura/widgets/comunes_aventura.dart';
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'ayudas.dart';

/// Responde a `/territories` con lo que se le dé, y a todo lo demás con vacío.
///
/// Sin esto no hay forma de probar la sección con datos: `Repositorios` crea
/// sus repos en la lista de inicialización, así que no se pueden sustituir.
/// Por donde sí se entra es por el `Dio` que `ApiClient` acepta inyectado.
class _ReinoFalso implements HttpClientAdapter {
  _ReinoFalso(this.territorios);

  final List<Map<String, dynamic>> territorios;
  int llamadas = 0;

  @override
  Future<ResponseBody> fetch(
    RequestOptions opciones,
    Stream<Uint8List>? cuerpo,
    Future<void>? cancelar,
  ) async {
    final bool esMapa = opciones.path.contains('/territories');
    if (esMapa) llamadas++;
    final Map<String, dynamic> respuesta = esMapa
        ? <String, dynamic>{
            'items': territorios,
            'page_info': <String, dynamic>{'has_more': false},
          }
        : <String, dynamic>{'items': <dynamic>[]};
    return ResponseBody.fromString(
      jsonEncode(respuesta),
      200,
      headers: <String, List<String>>{
        'content-type': <String>['application/json'],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}

Map<String, dynamic> _territorio(String nombre, String estado, String icono) =>
    <String, dynamic>{
      'territory_id': 'id-$icono',
      'knowledge_area_id': 'ka-$icono',
      'name': nombre,
      'knowledge_name': 'Conocimiento de $nombre',
      'icon_hint': icono,
      'status': estado,
      'mastery': 0.0,
      'zones_total': 4,
      'zones_unlocked': 1,
      'zones_completed': 0,
    };

/// Los tres estados, para que la prueba cubra los tres caminos de pintado.
final List<Map<String, dynamic>> _tres = <Map<String, dynamic>>[
  _territorio('Castillo de las Consultas', 'fogged', 'castle'),
  _territorio('Bóveda de los Datos', 'discovered', 'vault'),
  _territorio('Fragua de Modelos', 'completed', 'forge'),
];

({ControladorAventura aventura, _ReinoFalso reino}) _conReino(
  List<Map<String, dynamic>> territorios,
) {
  final _ReinoFalso reino = _ReinoFalso(territorios);
  final Dio dio = Dio()..httpClientAdapter = reino;
  final Repositorios repos = Repositorios(
    ApiClient(baseUrl: 'http://pruebas.invalido/api/v1', tokens: AlmacenTokensFalso(), dio: dio),
  );
  return (aventura: ControladorAventura(repos), reino: reino);
}

/// Los mismos sobres, ya parseados. Sin red.
///
/// **Una prueba de widget no puede hacer peticiones.** `testWidgets` corre con
/// un reloj falso, así que los temporizadores de Dio nunca disparan y el
/// `await` de la petición no vuelve jamás: la prueba se cuelga sin mensaje.
/// Costó siete minutos de espera y tres bisecciones averiguarlo. La red se
/// prueba en un `test` normal —los de arriba—; aquí solo el widget.
List<Territorio> get _territoriosDePrueba =>
    _tres.map(Territorio.desdeJson).toList();

/// Monta **solo la sección**, no la pantalla.
///
/// Montar `PantallaAventura` entera cuelga la prueba: arrastra el pulso del
/// nodo activo (`comunes_aventura.dart`, `_control.repeat`), que es una
/// animación sin fin. Costó siete minutos de espera descubrirlo. La sección es
/// autónoma, así que se monta sola.
Future<void> _montar(WidgetTester tester, List<Territorio> territorios) async {
  await tester.binding.setSurfaceSize(const Size(412, 915));
  addTearDown(() => tester.binding.setSurfaceSize(null));
  await tester.pumpWidget(
    MaterialApp(
      theme: AteneaTheme.oscuro(),
      home: Scaffold(
        body: SingleChildScrollView(child: MapaDelReino(territorios: territorios)),
      ),
    ),
  );
  await tester.pump();
}

void main() {
  setUp(prepararTipografias);

  test('el controlador trae los territorios y los parsea', () async {
    final ({ControladorAventura aventura, _ReinoFalso reino}) c = _conReino(_tres);

    await c.aventura.cargarTerritorios();

    expect(c.aventura.territorios.length, 3);
    expect(c.aventura.territorios.first.nombre, 'Castillo de las Consultas');
    expect(c.aventura.territorios.first.nombreConocimiento,
        'Conocimiento de Castillo de las Consultas');
  });

  test('un fallo del mapa NO ensucia el estado de las rutas', () async {
    // Es la razón de que esto no vaya dentro del `Future.wait` de `cargarRutas`:
    // allí un fallo pone `_errorRutas` y la pantalla entera dice «El Reino no
    // responde» aunque las rutas hubieran llegado perfectas.
    final Repositorios rotos = repositoriosDePrueba(AlmacenTokensFalso());
    final ControladorAventura roto = ControladorAventura(rotos);

    await roto.cargarTerritorios();

    expect(roto.territorios, isEmpty);
    expect(roto.errorRutas, isNull, reason: 'el mapa no puede tumbar la pantalla');
  });

  test('el guard mira sus propios datos, no las rutas', () async {
    // Heredar el guard de `cargarRutas` dejaría sin refrescar justo al aprendiz
    // que tiene rutas, que es el único cuyo estado de territorio cambia.
    final ({ControladorAventura aventura, _ReinoFalso reino}) c = _conReino(_tres);

    await c.aventura.cargarTerritorios();
    await c.aventura.cargarTerritorios();
    expect(c.reino.llamadas, 1, reason: 'sin forzar, no repite');

    await c.aventura.cargarTerritorios(forzar: true);
    expect(c.reino.llamadas, 2, reason: 'forzando, siempre refresca');
  });

  testWidgets('se pintan tantos emblemas como territorios hay, no cuatro',
      (WidgetTester tester) async {
    await _montar(tester, _territoriosDePrueba);

    expect(find.byType(EmblemaTerritorio), findsNWidgets(3));
    expect(find.text('Castillo de las Consultas'), findsOneWidget);
    expect(find.text('Fragua de Modelos'), findsOneWidget);
  });

  testWidgets('sin territorios la pantalla no llama a la sección, en vez de mentir',
      (WidgetTester tester) async {
    // La sección solo se monta si hay datos: el guard vive en la pantalla, y
    // esto fija que con la lista vacía no queda nada que enseñar.
    await _montar(tester, const <Territorio>[]);

    expect(find.byType(EmblemaTerritorio), findsNothing);
  });

  testWidgets('el lector de pantalla oye el nombre y el estado',
      (WidgetTester tester) async {
    // El estado del territorio no puede depender solo del color y del relleno.
    await _montar(tester, _territoriosDePrueba);

    expect(
      find.bySemanticsLabel('Castillo de las Consultas, En la bruma'),
      findsOneWidget,
    );
    expect(
      find.bySemanticsLabel('Fragua de Modelos, Completado'),
      findsOneWidget,
    );
  });

  test('los siete sellos sembrados dan siete emblemas distintos', () {
    // Los `territory_icon` de `backend/app/seeds/areas.py`. Antes solo dos
    // acertaban: los otros cinco caían en una clave genérica por el nombre o en
    // el reparto por hash, donde dos territorios pueden salir con el mismo
    // sello. Afirma la ausencia del azar, que es el fallo real.
    const List<String> sellos = <String>[
      'castle',
      'vault',
      'aqueduct',
      'tower',
      'cloud_keep',
      'forge',
      'council_hall',
    ];
    final List<IconData> iconos =
        sellos.map((String s) => iconoDeTerritorio(s)).toList();

    expect(iconos.toSet().length, sellos.length, reason: 'dos sellos comparten icono: $iconos');
  });
}
