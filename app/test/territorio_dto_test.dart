/// El DTO del territorio tiene que leer lo que el Reino manda de verdad.
///
/// `Territorio` se escribió copiando los alias de `ResumenRuta`, que sí usa
/// `knowledge_area_name`. Pero `TerritoryOut` manda **`knowledge_name`**
/// (`backend/app/modules/content/schemas.py`), así que `nombreConocimiento`
/// valía `null` siempre.
///
/// Nadie lo notó porque **nadie llamaba al endpoint**: `repos.conocimiento` era
/// código muerto entero. El desajuste llevaba ahí desde que se escribió el DTO,
/// esperando al día en que alguien conectara la pantalla y pareciera que el
/// fallo lo había traído ese cambio.
///
/// Esta es la prueba que faltaba: no necesita red, ni pantalla, ni que nadie
/// use el endpoint. Solo el sobre real y el DTO. Un vocabulario de API se puede
/// comprobar el día que se escribe, no el día que se estrena.
library;

import 'package:atenea/datos/dtos.dart';
import 'package:flutter_test/flutter_test.dart';

/// Copiado de `TerritoryOut` campo a campo, con los nombres del servidor.
Map<String, dynamic> _sobreDelReino({String estado = 'fogged'}) => <String, dynamic>{
      'territory_id': '3f2a1c44-0000-4000-8000-000000000001',
      'knowledge_area_id': '3f2a1c44-0000-4000-8000-000000000002',
      'name': 'Castillo de las Consultas',
      'knowledge_name': 'SQL y Bases de Datos',
      'icon_hint': 'castle',
      'description': 'Donde se aprende a preguntar bien.',
      'status': estado,
      'mastery': 0.42,
      'zones_total': 8,
      'zones_unlocked': 3,
      'zones_completed': 1,
    };

void main() {
  test('el nombre del conocimiento llega, que es el campo que no llegaba', () {
    final Territorio t = Territorio.desdeJson(_sobreDelReino());

    expect(
      t.nombreConocimiento,
      'SQL y Bases de Datos',
      reason: 'el servidor lo manda en `knowledge_name`, no en `knowledge_area_name`',
    );
  });

  test('y el resto del sobre también', () {
    final Territorio t = Territorio.desdeJson(_sobreDelReino());

    expect(t.id, '3f2a1c44-0000-4000-8000-000000000001');
    expect(t.nombre, 'Castillo de las Consultas');
    expect(t.iconoKey, 'castle');
    expect(t.descripcion, 'Donde se aprende a preguntar bien.');
    expect(t.estado, EstadoTerritorio.bruma);
    expect(t.dominio, closeTo(0.42, 0.001));
    expect(t.zonasTotales, 8);
    expect(t.zonasDesbloqueadas, 3);
  });

  test('los tres estados del contrato se reconocen', () {
    // Si el servidor añadiera un cuarto, aquí saldría como «bruma» y la
    // pantalla lo pintaría apagado en vez de romperse, que es lo correcto.
    expect(Territorio.desdeJson(_sobreDelReino(estado: 'fogged')).estado, EstadoTerritorio.bruma);
    expect(
      Territorio.desdeJson(_sobreDelReino(estado: 'discovered')).estado,
      EstadoTerritorio.descubierto,
    );
    expect(
      Territorio.desdeJson(_sobreDelReino(estado: 'completed')).estado,
      EstadoTerritorio.completado,
    );
    expect(
      Territorio.desdeJson(_sobreDelReino(estado: 'lo_que_sea')).estado,
      EstadoTerritorio.bruma,
      reason: 'un estado desconocido apaga el territorio, no rompe la pantalla',
    );
  });

  test('un sobre viejo con los alias de antes sigue leyéndose', () {
    // El alias nuevo se **añade**, no sustituye: si algún despliegue quedara
    // atrás, la pantalla no se queda sin nombres.
    final Territorio t = Territorio.desdeJson(<String, dynamic>{
      'territory_id': 'x',
      'name': 'Torre',
      'knowledge_area_name': 'Estadística',
      'status': 'discovered',
    });

    expect(t.nombreConocimiento, 'Estadística');
  });
}
