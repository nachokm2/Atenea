/// La lista de repasos recomendados: server listo desde antes, sin pantalla.
///
/// `GET /reviews/recommended` calculaba de verdad el decaimiento por tema y
/// lo servía paginado con duración estimada; `RepoLeccion.repasosRecomendados`
/// y el DTO `SugerenciaRepaso` estaban escritos y listos. Nadie los llamaba:
/// no existía ni una pantalla, ni una entrada, que los pidiera. Fuera de
/// reprobar un desafío de módulo o terminar una Ruta entera —dos rutas
/// estrechas, con otro origen de datos—, el aprendiz nunca veía esta lista.
///
/// Estas pruebas montan la pantalla real con un adaptador de Dio falso, para
/// atar la llamada real (`GET /reviews/recommended`, con su `cursor`) y no
/// una que se le parezca.
library;

import 'dart:convert';
import 'dart:typed_data';

import 'package:atenea/data/api_client.dart';
import 'package:atenea/datos/repositorios.dart';
import 'package:atenea/design/theme.dart';
import 'package:atenea/estado/leccion.dart';
import 'package:atenea/pantallas/repaso/repasos_recomendados.dart';
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'ayudas.dart';

/// Responde a `GET /reviews/recommended`; cualquier otra ruta falla, así una
/// llamada al endpoint equivocado se nota.
class _RepasosFalso implements HttpClientAdapter {
  _RepasosFalso(this.paginas);

  /// Una entrada por `cursor` pedido; `null` es la primera página.
  final Map<String?, Map<String, dynamic>> paginas;

  final List<String?> cursoresPedidos = <String?>[];

  @override
  Future<ResponseBody> fetch(
    RequestOptions opciones,
    Stream<Uint8List>? cuerpo,
    Future<void>? cancelar,
  ) async {
    if (!opciones.path.contains('/reviews/recommended')) {
      return ResponseBody.fromString('{}', 404);
    }
    final String? cursor = opciones.uri.queryParameters['cursor'];
    cursoresPedidos.add(cursor);
    final Map<String, dynamic>? sobre = paginas[cursor];
    if (sobre == null) {
      return ResponseBody.fromString('{}', 404);
    }
    return ResponseBody.fromString(
      jsonEncode(sobre),
      200,
      headers: <String, List<String>>{
        'content-type': <String>['application/json'],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}

Map<String, dynamic> _sugerencia({
  required String temaId,
  String titulo = 'JOINs',
  String estado = 'at_risk',
  int estimatedSeconds = 300,
}) =>
    <String, dynamic>{
      'topic_id': temaId,
      'title': titulo,
      'status': estado,
      'estimated_seconds': estimatedSeconds,
      'question_count': 6,
    };

Map<String, dynamic> _pagina(
  List<Map<String, dynamic>> items, {
  String? cursorSiguiente,
}) =>
    <String, dynamic>{
      'items': items,
      'page': <String, dynamic>{
        'limit': 10,
        'next_cursor': cursorSiguiente,
        'has_more': cursorSiguiente != null,
        'total': items.length,
      },
    };

Future<_RepasosFalso> _montar(
  WidgetTester tester,
  Map<String?, Map<String, dynamic>> paginas,
) async {
  final _RepasosFalso adaptador = _RepasosFalso(paginas);
  final Repositorios repos = Repositorios(
    ApiClient(
      baseUrl: 'http://pruebas.invalido/api/v1',
      tokens: AlmacenTokensFalso(),
      dio: Dio()..httpClientAdapter = adaptador,
    ),
  );
  await tester.pumpWidget(
    ChangeNotifierProvider<ControladorLeccion>.value(
      value: ControladorLeccion(repos),
      child: MaterialApp(
        theme: AteneaTheme.oscuro(),
        home: const PantallaRepasosRecomendados(),
      ),
    ),
  );
  await tester.pump();
  return adaptador;
}

void main() {
  setUp(prepararTipografias);

  testWidgets('trae la lista real y pinta cada tema con su motivo',
      (WidgetTester tester) async {
    final _RepasosFalso adaptador = await _montar(tester, <String?, Map<String, dynamic>>{
      null: _pagina(<Map<String, dynamic>>[
        _sugerencia(temaId: 'tema-1', titulo: 'JOINs'),
        _sugerencia(temaId: 'tema-2', titulo: 'Subconsultas', estado: 'weakened'),
      ]),
    });

    // Mientras llega, no hay que quedarse mostrando la lista vacía.
    expect(find.text('Nada pendiente de repasar'), findsNothing);

    await tester.pumpAndSettle();

    expect(find.text('JOINs'), findsOneWidget);
    expect(find.text('Subconsultas'), findsOneWidget);
    expect(find.textContaining('6 preguntas'), findsWidgets);
    expect(adaptador.cursoresPedidos, <String?>[null]);
  });

  testWidgets('sin nada que repasar, lo dice y no una lista vacía a secas',
      (WidgetTester tester) async {
    await _montar(tester, <String?, Map<String, dynamic>>{
      null: _pagina(<Map<String, dynamic>>[]),
    });
    await tester.pumpAndSettle();

    expect(find.text('Nada pendiente de repasar'), findsOneWidget);
  });

  testWidgets('un fallo ofrece reintentar, y reintentar pide otra vez',
      (WidgetTester tester) async {
    final _RepasosFalso adaptador = _RepasosFalso(<String?, Map<String, dynamic>>{});
    final Repositorios repos = Repositorios(
      ApiClient(
        baseUrl: 'http://pruebas.invalido/api/v1',
        tokens: AlmacenTokensFalso(),
        dio: Dio()..httpClientAdapter = adaptador,
      ),
    );
    await tester.pumpWidget(
      ChangeNotifierProvider<ControladorLeccion>.value(
        value: ControladorLeccion(repos),
        child: MaterialApp(
          theme: AteneaTheme.oscuro(),
          home: const PantallaRepasosRecomendados(),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('No pudimos traer tus repasos'), findsOneWidget);
    expect(adaptador.cursoresPedidos, <String?>[null]);

    await tester.tap(find.text('Reintentar'));
    await tester.pumpAndSettle();

    expect(adaptador.cursoresPedidos, <String?>[null, null]);
  });

  testWidgets('«Cargar más» pide la página siguiente con su cursor y la agrega',
      (WidgetTester tester) async {
    final _RepasosFalso adaptador = await _montar(tester, <String?, Map<String, dynamic>>{
      null: _pagina(
        <Map<String, dynamic>>[_sugerencia(temaId: 'tema-1', titulo: 'JOINs')],
        cursorSiguiente: 'pagina-2',
      ),
      'pagina-2': _pagina(
        <Map<String, dynamic>>[_sugerencia(temaId: 'tema-2', titulo: 'Índices')],
      ),
    });
    await tester.pumpAndSettle();

    expect(find.text('JOINs'), findsOneWidget);
    expect(find.text('Índices'), findsNothing);
    expect(find.text('Cargar más'), findsOneWidget);

    await tester.tap(find.text('Cargar más'));
    await tester.pumpAndSettle();

    expect(find.text('JOINs'), findsOneWidget, reason: 'la primera página no desaparece');
    expect(find.text('Índices'), findsOneWidget);
    expect(find.text('Cargar más'), findsNothing, reason: 'esa página ya no dice has_more');
    expect(adaptador.cursoresPedidos, <String?>[null, 'pagina-2']);
  });
}
