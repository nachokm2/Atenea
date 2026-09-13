import 'package:atenea/datos/repositorios.dart';
import 'package:flutter_test/flutter_test.dart';

/// La clave de idempotencia tiene que ser un UUID o el Reino responde 400.
///
/// Esto no es una formalidad: `claveDeterminista` la usan todos los
/// controladores del bucle central (empezar lección, responder, completar,
/// empezar y enviar evaluación, reclamar misión). Cuando devolvía un texto
/// legible como `lesson-start:<id>:1`, la app real no podía ejecutar ni una
/// sola de esas acciones, y ninguna prueba lo veía porque el recorrido contra
/// la API pasaba su propia clave a mano.
void main() {
  final RegExp uuid = RegExp(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
  );

  test('la clave aleatoria es un UUID v4', () {
    for (int i = 0; i < 200; i++) {
      final String clave = claveIdempotencia();
      expect(uuid.hasMatch(clave), isTrue, reason: 'no es un UUID: $clave');
      expect(clave[14], '4', reason: 'debe declarar versión 4');
    }
  });

  test('la clave aleatoria no se repite', () {
    final Set<String> vistas = <String>{
      for (int i = 0; i < 500; i++) claveIdempotencia(),
    };

    expect(vistas.length, 500);
  });

  test('la clave determinista es un UUID v5', () {
    final String clave = claveDeterminista('lesson-start', 'f97e54cd-0ae8-5c1e-b6d4-188078a9046d');

    expect(uuid.hasMatch(clave), isTrue, reason: 'no es un UUID: $clave');
    expect(clave[14], '5', reason: 'debe declarar versión 5');
  });

  test('la misma acción sobre la misma entidad da siempre la misma clave', () {
    // Es la razón de ser de esta función: reintentar no puede duplicar nada.
    expect(
      claveDeterminista('lesson-complete', 'abc'),
      claveDeterminista('lesson-complete', 'abc'),
    );
  });

  test('acciones o entidades distintas no colisionan', () {
    final Set<String> claves = <String>{
      claveDeterminista('lesson-start', 'abc'),
      claveDeterminista('lesson-complete', 'abc'),
      claveDeterminista('lesson-start', 'def'),
      claveDeterminista('lesson-start', 'abc', 2),
      claveDeterminista('answer', 'abc:1'),
      claveDeterminista('mission-claim', 'abc'),
    };

    expect(claves.length, 6, reason: 'cada acción necesita su propia clave');
  });

  test('un identificador vacío sigue dando una clave válida', () {
    expect(uuid.hasMatch(claveDeterminista('review-start', '')), isTrue);
  });

  test('coincide con la implementación de referencia de UUID v5', () {
    // Vectores comprobados contra `uuid.uuid5` de Python sobre el espacio
    // `uuid5(NAMESPACE_DNS, 'atenea.cl')` = a4e8e9cb-b17f-5908-8cc1-a97b3c640fd4.
    //
    // Fijarlos aquí protege dos cosas a la vez: que la derivación sea un UUID v5
    // de verdad y no algo que solo lo parezca, y que la clave de una acción no
    // cambie nunca entre versiones de la app. Si cambiara, un reintento después
    // de actualizar dejaría de deduplicar y el aprendiz cobraría dos veces.
    expect(
      claveDeterminista('lesson-start', 'f97e54cd-0ae8-5c1e-b6d4-188078a9046d'),
      '3994dbad-b723-506c-9df3-b96e7e3234c3',
    );
    expect(claveDeterminista('answer', 'abc:1'), 'a42e8204-a6ae-5a12-b8a3-20c38b2dbbdd');
    expect(
      claveDeterminista('mission-claim', '', 3),
      '0f989482-4ab2-5d09-a8c2-edada83684fe',
    );
    // Con acentos, que es donde suelen romperse las implementaciones a mano.
    expect(
      claveDeterminista('repaso-ñ', 'áéí', 2),
      '35966e11-415c-59c6-8f6b-5e2f25965056',
    );
  });
}
