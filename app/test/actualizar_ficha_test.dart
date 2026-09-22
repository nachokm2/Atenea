/// `PATCH /characters/me`: entero del lado servidor, huérfano en el cliente.
///
/// El endpoint (renombrar o cambiar de Orden, gratis en el MVP, §7.2) estaba
/// completo, y el cliente hasta tenía `RepoPersonaje.actualizar()` ya escrito
/// —pero `grep -rn "RepoPersonaje" app/lib` solo encontraba su propia
/// declaración y la de `Repositorios.personaje`: ningún controlador ni
/// pantalla lo llamaba. `ControladorPersonaje.actualizarFicha()` es el primer
/// llamador real.
library;

import 'dart:convert';
import 'dart:typed_data';

import 'package:atenea/data/api_client.dart';
import 'package:atenea/datos/repositorios.dart';
import 'package:atenea/estado/personaje.dart';
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import 'ayudas.dart';

class _PersonajeFalso implements HttpClientAdapter {
  final List<RequestOptions> pedidos = <RequestOptions>[];
  bool falla = false;

  @override
  Future<ResponseBody> fetch(
    RequestOptions opciones,
    Stream<Uint8List>? cuerpo,
    Future<void>? cancelar,
  ) async {
    pedidos.add(opciones);
    if (falla) {
      return ResponseBody.fromString(
        jsonEncode(<String, dynamic>{
          'error': <String, dynamic>{
            'code': 'validation_failed',
            'message': 'Ese nombre ya lo usa otro héroe.',
          },
        }),
        422,
        headers: <String, List<String>>{
          'content-type': <String>['application/json'],
        },
      );
    }
    final Map<String, dynamic> enviado = opciones.data as Map<String, dynamic>;
    return ResponseBody.fromString(
      jsonEncode(<String, dynamic>{
        'id': 'personaje-1',
        'user_id': 'usuario-1',
        'name': enviado['name'] ?? 'Aria',
        'archetype': enviado['archetype'] ?? 'steel',
        'level': 5,
        'xp_total': 1200,
        'rank_title': 'Iniciado/a',
      }),
      200,
      headers: <String, List<String>>{
        'content-type': <String>['application/json'],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}

ControladorPersonaje _controlador(_PersonajeFalso adaptador) {
  final Repositorios repos = Repositorios(
    ApiClient(
      baseUrl: 'http://pruebas.invalido/api/v1',
      tokens: AlmacenTokensFalso(),
      dio: Dio()..httpClientAdapter = adaptador,
    ),
  );
  return ControladorPersonaje(repos);
}

void main() {
  test('renombrar llama PATCH /characters/me con el nombre nuevo', () async {
    final _PersonajeFalso adaptador = _PersonajeFalso();
    final ControladorPersonaje control = _controlador(adaptador);

    final Personaje? actualizado =
        await control.actualizarFicha(nombre: 'Aria la Firme');

    expect(adaptador.pedidos, hasLength(1));
    expect(adaptador.pedidos.first.method, 'PATCH');
    expect(adaptador.pedidos.first.path, '/characters/me');
    expect(actualizado?.nombre, 'Aria la Firme');
    expect(control.guardandoFicha, false);
    expect(control.errorFicha, isNull);
  });

  test('cambiar de Orden manda solo el arquetipo, no un nombre vacío', () async {
    final _PersonajeFalso adaptador = _PersonajeFalso();
    final ControladorPersonaje control = _controlador(adaptador);

    await control.actualizarFicha(arquetipo: Arquetipo.bosque);

    final Map<String, dynamic> enviado =
        adaptador.pedidos.first.data as Map<String, dynamic>;
    expect(enviado['archetype'], 'forest');
    expect(enviado.containsKey('name'), false);
  });

  test('un 422 del servidor no revienta: guarda el error y no el personaje',
      () async {
    final _PersonajeFalso adaptador = _PersonajeFalso()..falla = true;
    final ControladorPersonaje control = _controlador(adaptador);

    final Personaje? resultado =
        await control.actualizarFicha(nombre: 'Repetido');

    expect(resultado, isNull);
    expect(control.errorFicha?.mensaje, 'Ese nombre ya lo usa otro héroe.');
    expect(control.guardandoFicha, false);
  });
}
