import 'package:atenea/datos/repositorios.dart';
import 'package:flutter_test/flutter_test.dart';

/// Un trabajo que agota sus reintentos queda en `needs_attention`.
///
/// El cliente no lo contaba como fallo, así que la pantalla de generación no
/// mostraba el error con su botón de reintentar, sino el aviso de cobertura:
/// "Tu material no cubre todo el objetivo", con la lista de avisos vacía. El
/// aprendiz subía su PDF, esperaba, y la app le decía que su documento estaba
/// mal y le pedía una decisión de política. Culpar al usuario de un fallo del
/// servidor es el punto exacto donde se abandona.
void main() {
  Trabajo conEstado(EstadoTrabajo estado) =>
      Trabajo.desdeJson(<String, dynamic>{
        'id': 'a3f0e1d2-0000-4000-8000-000000000001',
        'job_type': 'path_design',
        'status': estado.api,
      });

  test('quedarse sin reintentos cuenta como fallo', () {
    expect(conEstado(EstadoTrabajo.requiereAtencion).fallo, isTrue);
  });

  test('los fallos de siempre siguen contando', () {
    expect(conEstado(EstadoTrabajo.fallido).fallo, isTrue);
    expect(conEstado(EstadoTrabajo.cancelado).fallo, isTrue);
  });

  test('lo que sigue en marcha no es un fallo', () {
    expect(conEstado(EstadoTrabajo.pendiente).fallo, isFalse);
    expect(conEstado(EstadoTrabajo.ejecutando).fallo, isFalse);
    expect(conEstado(EstadoTrabajo.logrado).fallo, isFalse);
  });

  test('terminar y fallar son cosas distintas', () {
    expect(conEstado(EstadoTrabajo.requiereAtencion).termino, isFalse);
    expect(conEstado(EstadoTrabajo.logrado).termino, isTrue);
  });
}
