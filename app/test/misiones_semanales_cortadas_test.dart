/// La pestaña «Semanales» no se ofrece mientras no haya semanales.
///
/// El catálogo entero existe —W01 a W06 sembradas—, el motor de avance y pago
/// es agnóstico al horizonte, el endpoint consulta `scope == WEEKLY` y el
/// cliente deserializa y pinta. Lo único que no existe en todo el proyecto es
/// **la función que crea la fila**: no hay nada que escriba un `UserMission`
/// con `scope=WEEKLY`. Así que esa consulta devuelve cero filas en todas las
/// peticiones de todos los usuarios desde que existe el proyecto, y la pestaña
/// lleva desde el principio ofreciendo un vacío.
///
/// La decisión —argumentada con números en `docs/planes/misiones-semanales.md`—
/// fue **recortar, no conectar**: tres semanales por encima del tope blando
/// diario cambian la economía sin que nadie lo haya decidido, los objetivos
/// semanales son absolutos mientras el diario es configurable, y W03 paga 600
/// XP por completar un módulo en siete días.
///
/// Se lee de `missions.weekly.enabled`, que ya viaja en `/config/public`, y no
/// de una constante: el día que se reparta una semanal de verdad, la pestaña
/// vuelve sola sin tocar el cliente. Estas pruebas fijan las dos direcciones.
library;

import 'package:atenea/datos/dtos.dart';
import 'package:atenea/pantallas/inicio/misiones.dart';
import 'package:flutter_test/flutter_test.dart';

import 'ayudas.dart';

ConfigPublica _config({required bool semanalesEncendidas}) =>
    ConfigPublica.desdeJson(<String, dynamic>{
      'values': <String, dynamic>{
        'missions.weekly.enabled': semanalesEncendidas,
      },
    });

void main() {
  setUp(prepararTipografias);

  test('con las semanales apagadas la pestaña no se ofrece', () {
    final List<AmbitoMision> ambitos =
        ambitosVisibles(_config(semanalesEncendidas: false));

    expect(ambitos, isNot(contains(AmbitoMision.semanal)));
    expect(ambitos, containsAll(<AmbitoMision>[
      AmbitoMision.diaria,
      AmbitoMision.especial,
    ]));
  });

  test('encendidas, vuelve sin tocar el cliente', () {
    // Es la mitad que impide que esto sea un borrado: el día que W04 se
    // reparta de verdad, basta con la semilla.
    expect(
      ambitosVisibles(_config(semanalesEncendidas: true)),
      containsAll(AmbitoMision.values),
    );
  });

  test('sin configuración todavía, se oculta', () {
    // `/config/public` se pide sin sesión y puede tardar. Equivocarse hacia
    // ocultar una pestaña vacía cuesta menos que ofrecerla: si apareciera y
    // luego desapareciera, el aprendiz vería el tablón saltar bajo el dedo.
    expect(ambitosVisibles(null), isNot(contains(AmbitoMision.semanal)));
  });

  test('el orden de los horizontes no cambia al filtrar', () {
    // El selector es un `SegmentedButton`: si el orden bailara según el flag,
    // la pestaña activa saltaría de sitio.
    final List<AmbitoMision> conTodas =
        ambitosVisibles(_config(semanalesEncendidas: true));
    final List<AmbitoMision> sinSemanal =
        ambitosVisibles(_config(semanalesEncendidas: false));

    expect(conTodas, AmbitoMision.values);
    expect(sinSemanal, <AmbitoMision>[
      AmbitoMision.diaria,
      AmbitoMision.especial,
    ]);
  });
}
