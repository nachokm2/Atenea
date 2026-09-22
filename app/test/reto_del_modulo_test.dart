/// El Reto del módulo: todo el andamiaje existía y nadie lo abría.
///
/// El servidor ya tenía `POST /modules/{id}/challenge/start` completo
/// (§7.6, 22-09): `StudyActivityType.CHALLENGE`, `EventType.CHALLENGE_COMPLETED`
/// y el logro «Retador/a» existían enteros del lado servidor, pero el cliente
/// no tenía ni el método de repositorio, ni la pantalla, ni la entrada.
///
/// Esta prueba monta `PantallaLeccion(moduloId: ...)` de punta a punta —abrir,
/// responder, terminar— con un adaptador de Dio falso, la misma técnica que ya
/// usa `hoja_fuente_test.dart`: ata la llamada real a
/// `POST /modules/{id}/challenge/start` y no una que se le parezca.
///
/// También es la prueba de un bug real que existía antes de este cambio y que
/// ninguna otra prueba tocaba: `ControladorLeccion.esRepaso` leía
/// `_leccion?.esRepaso`, que es `null` (y por tanto `false`) tanto en repaso
/// como en el Reto —no hay Lección de origen en ninguno de los dos—. Sin la
/// corrección, `PantallaFinLeccion` habría mostrado "LECCIÓN COMPLETADA" al
/// terminar un Reto (y también al terminar un repaso, aunque eso no lo cubre
/// esta prueba). Por eso se comprueba el texto exacto de cierre, no solo que
/// la pantalla no truene.
library;

import 'dart:convert';
import 'dart:typed_data';

import 'package:atenea/data/api_client.dart';
import 'package:atenea/datos/repositorios.dart';
import 'package:atenea/design/theme.dart';
import 'package:atenea/estado/celebraciones.dart';
import 'package:atenea/estado/leccion.dart';
import 'package:atenea/pantallas/leccion/leccion.dart';
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'ayudas.dart';

/// Responde a los tres pasos del ciclo de una actividad (empezar, responder,
/// terminar); cualquier otra ruta falla, así una llamada por el endpoint
/// equivocado se nota.
class _ActividadFalsa implements HttpClientAdapter {
  final List<String> rutasPedidas = <String>[];

  @override
  Future<ResponseBody> fetch(
    RequestOptions opciones,
    Stream<Uint8List>? cuerpo,
    Future<void>? cancelar,
  ) async {
    final String ruta = opciones.path;
    rutasPedidas.add(ruta);

    if (ruta.endsWith('/challenge/start')) {
      return _json(<String, dynamic>{
        'activity_id': 'act-1',
        'activity_type': 'challenge',
        'module_id': 'mod-1',
        'learning_path_id': 'ruta-1',
        'questions': <Map<String, dynamic>>[
          <String, dynamic>{
            'question_id': 'q-1',
            'question_type': 'true_false',
            'difficulty': 'medium',
            'stem': '¿Un INNER JOIN devuelve solo las filas que casan en '
                'ambas tablas?',
            'body': <String, dynamic>{},
            'estimated_seconds': 30,
          },
        ],
        'expires_at': '2026-09-22T12:00:00Z',
      });
    }
    if (ruta.endsWith('/answers')) {
      return _json(<String, dynamic>{
        'result': 'correct',
        'is_correct': true,
        'partial_score': 100,
        'xp_awarded': 10,
        'explanation': 'Correcto: eso es justo lo que hace un INNER JOIN.',
        'evaluation_method': 'deterministic',
        'question_id': 'q-1',
      });
    }
    if (ruta.endsWith('/heartbeat')) {
      return _json(<String, dynamic>{'active_seconds': 30});
    }
    if (ruta.endsWith('/complete')) {
      return _json(<String, dynamic>{
        'receipt_id': 'recibo-1',
        'event_type': 'CHALLENGE_COMPLETED',
        'xp': <String, dynamic>{'amount': 200, 'total_after': 1200},
        'gold': <String, dynamic>{'amount': 60, 'balance_after': 460},
        'level': <String, dynamic>{'level': 5, 'progress_pct': 40},
        'presentation_order': <String>['xp', 'gold'],
      });
    }
    return ResponseBody.fromString('{}', 404);
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

Future<void> _montar(WidgetTester tester, _ActividadFalsa adaptador) async {
  final Repositorios repos = Repositorios(
    ApiClient(
      baseUrl: 'http://pruebas.invalido/api/v1',
      tokens: AlmacenTokensFalso(),
      dio: Dio()..httpClientAdapter = adaptador,
    ),
  );
  await tester.pumpWidget(
    MultiProvider(
      providers: [
        ChangeNotifierProvider<ControladorLeccion>(
          create: (_) => ControladorLeccion(repos),
        ),
        ChangeNotifierProvider<ColaCelebraciones>(
          create: (_) => ColaCelebraciones(),
        ),
      ],
      child: MaterialApp(
        theme: AteneaTheme.oscuro(),
        home: const PantallaLeccion(moduloId: 'mod-1'),
      ),
    ),
  );
  await tester.pump();
}

void main() {
  setUp(prepararTipografias);

  testWidgets('abre el Reto del módulo, no una lección ni un repaso',
      (WidgetTester tester) async {
    final _ActividadFalsa adaptador = _ActividadFalsa();
    await _montar(tester, adaptador);
    await tester.pumpAndSettle();

    expect(
      adaptador.rutasPedidas.first,
      '/modules/mod-1/challenge/start',
      reason: 'por la ruta que promete el contrato, no una que se le parezca',
    );
    expect(find.text('Reto del módulo'), findsOneWidget);
    expect(
      find.textContaining('preguntas de todo el módulo'),
      findsOneWidget,
      reason: 'el aviso de Reto, distinto del de repaso',
    );
    expect(find.textContaining('la XP de lección no se vuelve a pagar'),
        findsNothing);
  });

  testWidgets(
      'al terminar, dice "RETO SUPERADO" — no "LECCIÓN COMPLETADA"',
      (WidgetTester tester) async {
    // Este es el bug real: `ControladorLeccion.esRepaso` antes leía
    // `_leccion?.esRepaso`, que es `false` sin Lección de origen —el caso de
    // un Reto (y también el de un repaso)—. `PantallaFinLeccion` se habría
    // quedado mostrando el cierre genérico de lección.
    final _ActividadFalsa adaptador = _ActividadFalsa();
    await _montar(tester, adaptador);
    await tester.pumpAndSettle();

    await tester.tap(find.text('Verdadero'));
    await tester.pump();
    await tester.tap(find.text('Comprobar'));
    await tester.pumpAndSettle();

    expect(find.text('Terminar el reto'), findsOneWidget);
    await tester.tap(find.text('Terminar el reto'));
    await tester.pumpAndSettle();

    expect(find.text('RETO SUPERADO'), findsOneWidget);
    expect(find.text('LECCIÓN COMPLETADA'), findsNothing);
    expect(find.text('Reto del módulo'), findsWidgets);
    expect(
      adaptador.rutasPedidas.where((String r) => r.endsWith('/complete')),
      hasLength(1),
    );
  });
}
