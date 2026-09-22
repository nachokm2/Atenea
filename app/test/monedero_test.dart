/// `GET /wallet` estaba entero del lado servidor y ninguna pantalla lo pedía.
///
/// Saldo, oro ganado y gastado de por vida, y el historial paginado de
/// movimientos ya existían enteros: `Monedero.desdeJson`,
/// `RepoTienda.monedero()` y hasta un método de controlador con manejo de
/// error propio. Solo faltaba la pantalla. Esta prueba monta
/// `PantallaMonedero` de punta a punta —carga, totales, movimientos y
/// "Cargar más"— con un adaptador de Dio falso que ata la llamada real a
/// `GET /wallet` y su `cursor`, la misma técnica que ya usa
/// `reto_del_modulo_test.dart`.
library;

import 'dart:convert';
import 'dart:typed_data';

import 'package:atenea/data/api_client.dart';
import 'package:atenea/datos/repositorios.dart';
import 'package:atenea/design/theme.dart';
import 'package:atenea/estado/personaje.dart';
import 'package:atenea/pantallas/personaje/monedero.dart';
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'ayudas.dart';

class _MonederoFalso implements HttpClientAdapter {
  final List<String> rutasPedidas = <String>[];

  @override
  Future<ResponseBody> fetch(
    RequestOptions opciones,
    Stream<Uint8List>? cuerpo,
    Future<void>? cancelar,
  ) async {
    rutasPedidas.add(opciones.uri.toString());
    final bool segundaPagina = opciones.uri.queryParameters['cursor'] == 'pag-2';
    return _json(<String, dynamic>{
      'balance': 480,
      'lifetime_earned': 2000,
      'lifetime_spent': 1520,
      'transactions': <String, dynamic>{
        'items': segundaPagina
            ? <Map<String, dynamic>>[
                <String, dynamic>{
                  'id': 'tx-3',
                  'direction': 'credit',
                  'amount': 50,
                  'balance_after': 100,
                  'source': 'welcome',
                  'reason_code': 'welcome',
                  'created_at': '2026-09-01T09:00:00Z',
                },
              ]
            : <Map<String, dynamic>>[
                <String, dynamic>{
                  'id': 'tx-1',
                  'direction': 'credit',
                  'amount': 60,
                  'balance_after': 480,
                  'source': 'challenge',
                  'reason_code': 'first_completion',
                  'created_at': '2026-09-20T18:30:00Z',
                },
                <String, dynamic>{
                  'id': 'tx-2',
                  'direction': 'debit',
                  'amount': 200,
                  'balance_after': 420,
                  'sink': 'purchase',
                  'reason_code': 'purchase',
                  'created_at': '2026-09-19T12:00:00Z',
                },
              ],
        'page': segundaPagina
            ? <String, dynamic>{'has_more': false, 'next_cursor': null}
            : <String, dynamic>{'has_more': true, 'next_cursor': 'pag-2'},
      },
    });
  }

  ResponseBody _json(Map<String, dynamic> cuerpo) => ResponseBody.fromString(
        jsonEncode(cuerpo),
        200,
        headers: <String, List<String>>{
          'content-type': <String>['application/json'],
        },
      );

  @override
  void close({bool force = false}) {}
}

Future<void> _montar(WidgetTester tester, _MonederoFalso adaptador) async {
  final Repositorios repos = Repositorios(
    ApiClient(
      baseUrl: 'http://pruebas.invalido/api/v1',
      tokens: AlmacenTokensFalso(),
      dio: Dio()..httpClientAdapter = adaptador,
    ),
  );
  await tester.pumpWidget(
    ChangeNotifierProvider<ControladorPersonaje>(
      create: (_) => ControladorPersonaje(repos),
      child: MaterialApp(
        theme: AteneaTheme.oscuro(),
        home: const PantallaMonedero(),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  setUp(prepararTipografias);

  testWidgets('trae GET /wallet, no un endpoint que se le parezca',
      (WidgetTester tester) async {
    final _MonederoFalso adaptador = _MonederoFalso();
    await _montar(tester, adaptador);

    expect(adaptador.rutasPedidas.first, contains('/wallet'));
  });

  testWidgets('muestra saldo, ganado y gastado de por vida',
      (WidgetTester tester) async {
    final _MonederoFalso adaptador = _MonederoFalso();
    await _montar(tester, adaptador);

    expect(find.text('480'), findsOneWidget);
    expect(find.text('2.000'), findsOneWidget);
    expect(find.text('1.520'), findsOneWidget);
  });

  testWidgets('lista los movimientos con su motivo en español',
      (WidgetTester tester) async {
    final _MonederoFalso adaptador = _MonederoFalso();
    await _montar(tester, adaptador);

    expect(find.text('Reto superado'), findsOneWidget);
    expect(find.text('Compra'), findsOneWidget);
    expect(find.text('+60'), findsOneWidget);
    expect(find.text('−200'), findsOneWidget);
  });

  testWidgets('"Cargar más" pide la página siguiente y la agrega al final',
      (WidgetTester tester) async {
    final _MonederoFalso adaptador = _MonederoFalso();
    await _montar(tester, adaptador);

    expect(find.text('Cargar más'), findsOneWidget);
    await tester.tap(find.text('Cargar más'));
    await tester.pumpAndSettle();

    expect(
      adaptador.rutasPedidas.last,
      contains('cursor=pag-2'),
      reason: 'debe reenviar el cursor tal cual, sin interpretarlo',
    );
    expect(find.text('Bienvenida'), findsOneWidget);
    expect(find.text('Reto superado'), findsOneWidget, reason: 'la primera página sigue');
    expect(find.text('Cargar más'), findsNothing, reason: 'ya no quedan más páginas');
  });
}
