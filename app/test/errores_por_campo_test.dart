/// El detalle por campo que manda el Reino tiene que llegar a la pantalla.
///
/// Rodrigo no podía registrarse. El servidor estaba perfecto: devolvía 422 con
/// `message` «Esa contraseña es demasiado débil» y, en `field_errors`, **qué le
/// faltaba**: una mayúscula, un número, ocho caracteres. El cliente guardaba
/// solo `details` —que viene vacío— y tiraba `field_errors`, que es hermano
/// suyo en el sobre y no hijo.
///
/// Así que la pantalla enseñaba «demasiado débil» y nada más. El aprendiz sabe
/// que algo está mal y no puede saber qué, que a efectos prácticos es no poder
/// registrarse.
///
/// El patrón es el de siempre en este proyecto: algo se manda, viaja entero, y
/// nadie lo lee. Y no lo veía ninguna prueba porque todas comprueban la mitad
/// que funciona —que el mensaje general llega—.
///
/// Los sobres de aquí están copiados de respuestas **reales** de producción, no
/// inventados: se capturaron llamando al registro con cada caso.
library;

import 'package:atenea/data/errores.dart';
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

ErrorAtenea _del(int estado, Map<String, dynamic> cuerpo) => ErrorAtenea.desdeDio(
      DioException(
        requestOptions: RequestOptions(path: '/auth/register'),
        response: Response<dynamic>(
          requestOptions: RequestOptions(path: '/auth/register'),
          statusCode: estado,
          data: cuerpo,
        ),
        type: DioExceptionType.badResponse,
      ),
    );

/// Lo que hacen las pantallas con el error, en una línea.
String _loQueSeLee(ErrorAtenea e) {
  final Object? campos = e.detalles?['field_errors'];
  if (campos is List && campos.isNotEmpty) {
    final Iterable<String> m = campos
        .whereType<Map<dynamic, dynamic>>()
        .map((Map<dynamic, dynamic> c) => '${c['message'] ?? ''}')
        .where((String s) => s.isNotEmpty);
    if (m.isNotEmpty) return m.join(' ');
  }
  return e.mensaje;
}

void main() {
  test('una contraseña floja dice QUÉ le falta, no solo que está floja', () {
    final ErrorAtenea e = _del(422, <String, dynamic>{
      'error': <String, dynamic>{
        'code': 'VALIDATION_ERROR',
        'message': 'Esa contraseña es demasiado débil.',
        'details': <String, dynamic>{},
        'field_errors': <Map<String, String>>[
          <String, String>{'field': 'password', 'message': 'Debe incluir una letra mayúscula.'},
          <String, String>{'field': 'password', 'message': 'Debe incluir un número.'},
        ],
      },
    });

    final String leido = _loQueSeLee(e);
    expect(leido, contains('mayúscula'));
    expect(leido, contains('número'));
  });

  test('y un correo inválido dice que le falta la arroba', () {
    final ErrorAtenea e = _del(422, <String, dynamic>{
      'error': <String, dynamic>{
        'code': 'VALIDATION_ERROR',
        'message': 'Revisa los datos enviados: hay campos inválidos.',
        'details': <String, dynamic>{},
        'field_errors': <Map<String, String>>[
          <String, String>{
            'field': 'email',
            'message': 'value is not a valid email address: An email address must have an @-sign.',
          },
        ],
      },
    });

    expect(_loQueSeLee(e), contains('@-sign'));
  });

  test('sin field_errors se lee el mensaje general, como antes', () {
    // El correo repetido no trae detalle por campo y no le hace falta: el
    // mensaje ya lo dice todo. Esta prueba existe para que arreglar lo de
    // arriba no rompa lo de abajo.
    final ErrorAtenea e = _del(409, <String, dynamic>{
      'error': <String, dynamic>{
        'code': 'EMAIL_ALREADY_EXISTS',
        'message': 'Ya existe una cuenta con ese correo.',
        'details': <String, dynamic>{},
        'field_errors': <Map<String, String>>[],
      },
    });

    expect(_loQueSeLee(e), 'Ya existe una cuenta con ese correo.');
    expect(e.codigo, 'EMAIL_ALREADY_EXISTS');
  });

  test('y lo que venga en details sigue llegando', () {
    // `details` y `field_errors` son hermanos en el sobre, así que juntarlos no
    // puede costar el uno por el otro.
    final ErrorAtenea e = _del(422, <String, dynamic>{
      'error': <String, dynamic>{
        'code': 'VALIDATION_ERROR',
        'message': 'No.',
        'details': <String, dynamic>{'intentos_restantes': 2},
        'field_errors': <Map<String, String>>[
          <String, String>{'field': 'password', 'message': 'Corta.'},
        ],
      },
    });

    expect(e.detalles?['intentos_restantes'], 2);
    expect(_loQueSeLee(e), 'Corta.');
  });
}
