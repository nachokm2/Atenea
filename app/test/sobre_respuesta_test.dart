import 'package:atenea/datos/repositorios.dart';
import 'package:flutter_test/flutter_test.dart';

/// El contrato declara `response` como un **objeto** con una clave concreta por
/// tipo de pregunta (§7.6). Mandar el valor pelado da 422 y ninguna respuesta
/// del aprendiz llega a corregirse.
///
/// Esto se comprueba aquí, sin red, porque es una regla de forma: la prueba de
/// contra la API viva la confirma de verdad, pero solo corre con el Reino
/// levantado y no debería ser el único sitio donde se note una regresión.
void main() {
  test('cada tipo cerrado viaja con la clave que lee el corrector', () {
    expect(sobreDeRespuesta(TipoPregunta.opcionMultiple, 'b'),
        <String, dynamic>{'option_ids': <dynamic>['b']});
    expect(sobreDeRespuesta(TipoPregunta.opcionMultiple, <String>['a', 'c']),
        <String, dynamic>{'option_ids': <dynamic>['a', 'c']});
    expect(sobreDeRespuesta(TipoPregunta.verdaderoFalso, true),
        <String, dynamic>{'value': true});
    expect(sobreDeRespuesta(TipoPregunta.completar, <String>['SELECT', 'FROM']),
        <String, dynamic>{'blanks': <dynamic>['SELECT', 'FROM']});
    expect(sobreDeRespuesta(TipoPregunta.ordenar, <String>['1', '2']),
        <String, dynamic>{'order': <dynamic>['1', '2']});
    expect(sobreDeRespuesta(TipoPregunta.relacionar, <String, String>{'a': 'b'}),
        <String, dynamic>{'pairs': <String, String>{'a': 'b'}});
  });

  test('las abiertas viajan como texto y el SQL como consulta', () {
    expect(sobreDeRespuesta(TipoPregunta.respuestaCorta, 'Un índice acelera.'),
        <String, dynamic>{'text': 'Un índice acelera.'});
    expect(sobreDeRespuesta(TipoPregunta.ejercicioSql, 'SELECT 1;'),
        <String, dynamic>{'sql': 'SELECT 1;'});
  });

  test('un sobre ya armado por la pantalla se respeta', () {
    final Map<String, dynamic> armado = <String, dynamic>{
      'text': 'mi respuesta',
      'hint_shown': true,
    };

    expect(sobreDeRespuesta(TipoPregunta.respuestaCorta, armado), armado);
  });

  test('nada seleccionado sigue siendo un objeto, nunca un valor suelto', () {
    for (final TipoPregunta tipo in TipoPregunta.values) {
      expect(sobreDeRespuesta(tipo, null), isA<Map<String, dynamic>>(),
          reason: '$tipo debe producir un objeto');
    }
    // Y vacío de verdad: el Reino lo registra como `SKIPPED`, no como fallo.
    expect(sobreDeRespuesta(TipoPregunta.opcionMultiple, null),
        <String, dynamic>{'option_ids': <dynamic>[]});
  });
}
