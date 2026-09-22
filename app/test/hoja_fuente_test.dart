/// «Ver fuente» pasa de una ficha vacía a citar de verdad.
///
/// `Procedencia` (`ProvenanceOut`, §7.6) solo trae el `chunk_id` que respalda
/// un bloque: **nunca** el título del documento, las páginas ni el texto. Eso
/// es a propósito — mandarlo en toda respuesta de lección multiplicaría el
/// peso por el número de citas, casi ninguna de las cuales se llega a abrir—.
/// El documento, las páginas y el fragmento viven en `GET /chunks/{id}`
/// (CONTRACT.md:3088), y el cliente tenía el DTO `Fragmento`, el repositorio
/// `RepoDocumentos.fragmento` y hasta el propio endpoint construidos, sin que
/// nadie llamara a ninguno.
///
/// Así que el botón que existe precisamente para que el aprendiz compruebe
/// que el Reino no se inventa nada abría una ficha con «Tu material» a secas,
/// en toda lección de toda Ruta. Sin síntoma: la hoja se abría bien.
///
/// Estas pruebas montan la hoja real, con un adaptador de Dio falso en vez de
/// mockear el repositorio: así queda atada la llamada real
/// (`GET /chunks/{id}`) y no una que se le parezca.
library;

import 'dart:convert';
import 'dart:typed_data';

import 'package:atenea/data/api_client.dart';
import 'package:atenea/datos/repositorios.dart';
import 'package:atenea/design/components.dart';
import 'package:atenea/design/theme.dart';
import 'package:atenea/pantallas/leccion/widgets/hoja_fuente.dart';
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'ayudas.dart';

/// Responde a `GET /chunks/{id}` con lo que se le dé; a cualquier otra ruta,
/// con un fallo — así una llamada por el endpoint equivocado se nota.
class _ChunksFalso implements HttpClientAdapter {
  _ChunksFalso(this.fragmentos, {this.fallan = const <String>{}});

  /// `chunk_id` -> sobre `ChunkOut`.
  final Map<String, Map<String, dynamic>> fragmentos;

  /// `chunk_id` a los que se responde con 404.
  final Set<String> fallan;

  final List<String> pedidos = <String>[];

  @override
  Future<ResponseBody> fetch(
    RequestOptions opciones,
    Stream<Uint8List>? cuerpo,
    Future<void>? cancelar,
  ) async {
    final Uri uri = opciones.uri;
    final RegExpMatch? m = RegExp(r'/chunks/([^/?]+)').firstMatch(uri.path);
    if (m == null) {
      return ResponseBody.fromString('{}', 404);
    }
    final String id = m.group(1)!;
    pedidos.add(id);
    if (fallan.contains(id)) {
      return ResponseBody.fromString('{}', 404);
    }
    final Map<String, dynamic>? sobre = fragmentos[id];
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

Map<String, dynamic> _sobreChunk({
  required String id,
  String documentTitle = 'Guía de SQL',
  int pageStart = 34,
  int pageEnd = 35,
  String text = 'Un INNER JOIN une dos tablas por la columna que comparten.',
  List<String> headingPath = const <String>['Capítulo 5. JOINs'],
}) =>
    <String, dynamic>{
      'id': id,
      'document_id': 'doc-1',
      'document_version_id': 'ver-1',
      'document_title': documentTitle,
      'chunk_index': 3,
      'chunk_type': 'prose',
      'heading_path': headingPath,
      'text': text,
      'token_count': 40,
      'page_start': pageStart,
      'page_end': pageEnd,
    };

Procedencia _cita({String id = 'chunk-1'}) => Procedencia.desdeJson(
      <String, dynamic>{
        'content_type': 'block',
        'content_id': 'b-1',
        'origin': 'material',
        'chunk_id': id,
      },
    );

Future<void> _abrirHoja(
  WidgetTester tester,
  List<Procedencia> procedencia,
  HttpClientAdapter adaptador,
) async {
  final Repositorios repos = Repositorios(
    ApiClient(
      baseUrl: 'http://pruebas.invalido/api/v1',
      tokens: AlmacenTokensFalso(),
      dio: Dio()..httpClientAdapter = adaptador,
    ),
  );
  await tester.pumpWidget(
    Provider<Repositorios>.value(
      value: repos,
      child: MaterialApp(
        theme: AteneaTheme.oscuro(),
        home: Scaffold(
          body: Builder(
            builder: (BuildContext context) => Center(
              child: ElevatedButton(
                onPressed: () => mostrarHojaFuente(context, procedencia),
                child: const Text('abrir'),
              ),
            ),
          ),
        ),
      ),
    ),
  );
  await tester.tap(find.text('abrir'));
  await tester.pumpAndSettle();
}

/// `Pildora` pinta con `Text.rich` para incrustar el icono en el mismo
/// párrafo, así que `find.text` —que solo mira `Text.data`— nunca la
/// encuentra. Se busca el widget por su campo, no por su render.
Finder _pildora(String texto) => find.byWidgetPredicate(
      (Widget w) => w is Pildora && w.texto == texto,
      description: 'píldora «$texto»',
    );

void main() {
  setUp(prepararTipografias);

  testWidgets('la ficha cita de verdad: título, páginas y el texto exacto',
      (WidgetTester tester) async {
    final _ChunksFalso adaptador = _ChunksFalso(<String, Map<String, dynamic>>{
      'chunk-1': _sobreChunk(id: 'chunk-1'),
    });

    await _abrirHoja(tester, <Procedencia>[_cita()], adaptador);

    expect(find.text('Guía de SQL'), findsOneWidget);
    expect(_pildora('pp. 34–35'), findsOneWidget);
    expect(
      find.text('Un INNER JOIN une dos tablas por la columna que comparten.'),
      findsOneWidget,
    );
    expect(find.text('Capítulo 5. JOINs'), findsOneWidget);

    // Y por la ruta que promete el contrato, no una que se le parezca.
    expect(adaptador.pedidos, <String>['chunk-1']);
  });

  testWidgets('mientras llega, un esqueleto — nunca "Tu material" a medias',
      (WidgetTester tester) async {
    // Antes de conectar la llamada, esta ficha se veía exactamente así de
    // vacía y ya no volvía a cambiar. Que aparezca aquí, brevemente, es la
    // prueba de que ahora hay una petición en camino: no es el estado final.
    final _ChunksFalso adaptador = _ChunksFalso(<String, Map<String, dynamic>>{
      'chunk-1': _sobreChunk(id: 'chunk-1'),
    });

    final Repositorios repos = Repositorios(
      ApiClient(
        baseUrl: 'http://pruebas.invalido/api/v1',
        tokens: AlmacenTokensFalso(),
        dio: Dio()..httpClientAdapter = adaptador,
      ),
    );
    await tester.pumpWidget(
      Provider<Repositorios>.value(
        value: repos,
        child: MaterialApp(
          theme: AteneaTheme.oscuro(),
          home: Scaffold(
            body: Builder(
              builder: (BuildContext context) => Center(
                child: ElevatedButton(
                  onPressed: () => mostrarHojaFuente(context, <Procedencia>[_cita()]),
                  child: const Text('abrir'),
                ),
              ),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('abrir'));
    await tester.pump();
    await tester.pump();

    expect(find.text('Tu material'), findsNothing);
    expect(find.text('Guía de SQL'), findsNothing);

    await tester.pumpAndSettle();
    expect(find.text('Guía de SQL'), findsOneWidget);
  });

  testWidgets('un fragmento que falla no arrastra a los demás',
      (WidgetTester tester) async {
    // Dos citas del material; la del respaldo A responde 404 y la B llega
    // bien. La de A cae al respaldo de antes —"Tu material", sin página ni
    // extracto—, y no se pierde ni se congela la hoja entera por ella.
    final _ChunksFalso adaptador = _ChunksFalso(
      <String, Map<String, dynamic>>{
        'chunk-b': _sobreChunk(id: 'chunk-b', documentTitle: 'Apuntes de BI'),
      },
      fallan: <String>{'chunk-a'},
    );

    await _abrirHoja(
      tester,
      <Procedencia>[_cita(id: 'chunk-a'), _cita(id: 'chunk-b')],
      adaptador,
    );

    expect(find.text('Apuntes de BI'), findsOneWidget);
    expect(find.text('Tu material'), findsOneWidget);
  });

  testWidgets('sin conocimiento general, la hoja no pide nada',
      (WidgetTester tester) async {
    final _ChunksFalso adaptador = _ChunksFalso(<String, Map<String, dynamic>>{});

    await _abrirHoja(
      tester,
      <Procedencia>[
        Procedencia.desdeJson(<String, dynamic>{
          'content_type': 'block',
          'content_id': 'b-1',
          'origin': 'model_knowledge',
        }),
      ],
      adaptador,
    );

    expect(_pildora('Conocimiento general'), findsOneWidget);
    expect(adaptador.pedidos, isEmpty);
  });

  testWidgets('una página sola se lee "p. 12", no "pp. 12–12"',
      (WidgetTester tester) async {
    final _ChunksFalso adaptador = _ChunksFalso(<String, Map<String, dynamic>>{
      'chunk-1': _sobreChunk(id: 'chunk-1', pageStart: 12, pageEnd: 12),
    });

    await _abrirHoja(tester, <Procedencia>[_cita()], adaptador);

    expect(_pildora('p. 12'), findsOneWidget);
    expect(_pildora('pp. 12–12'), findsNothing);
  });
}
