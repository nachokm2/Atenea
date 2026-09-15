import 'package:atenea/datos/repositorios.dart';
import 'package:flutter_test/flutter_test.dart';

/// Reportar contenido daba 422 siempre y la pantalla se tragaba el error.
///
/// La API acepta un vocabulario cerrado y estrecho: el tipo es `block` o
/// `question`, no el `lesson_block` que usa el resto de la app, y los motivos
/// son siete palabras concretas. La pantalla ofrecía cuatro motivos en español
/// que la API rechazaba todos, así que la función no funcionó nunca.
void main() {
  /// El patrón exacto de `ContentReportIn.reason` en el backend.
  const Set<String> admitidos = <String>{
    'incorrect',
    'ambiguous',
    'not_in_material',
    'poorly_written',
    'too_easy',
    'too_hard',
    'other',
  };

  test('todos los motivos que ofrece la app los acepta el Reino', () {
    expect(motivosDeReporte.keys.toSet().difference(admitidos), isEmpty);
  });

  test('cada motivo tiene su texto en español', () {
    for (final MapEntry<String, String> e in motivosDeReporte.entries) {
      expect(e.value.trim(), isNotEmpty, reason: 'sin etiqueta: ${e.key}');
      expect(e.value, isNot(e.key), reason: 'la etiqueta no puede ser la clave');
    }
  });

  test('un motivo desconocido cae en "other" en vez de dar 422', () {
    expect(motivoDeReporte('contenido_incorrecto'), 'other');
    expect(motivoDeReporte('lo-que-sea'), 'other');
  });

  test('un motivo válido viaja tal cual', () {
    expect(motivoDeReporte('not_in_material'), 'not_in_material');
  });
}
