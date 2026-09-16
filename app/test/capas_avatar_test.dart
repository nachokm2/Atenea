import 'package:atenea/datos/dtos.dart';
import 'package:flutter_test/flutter_test.dart';

/// El cliente y el servidor tienen que nombrar igual una capa del avatar.
///
/// No lo hacían, y de ahí salieron varios fallos a la vez: el servidor mandaba
/// `key` con el código del ítem y el cliente lo tomaba por el nombre de la capa;
/// mandaba `item_code` y el cliente buscaba `item_id`; y el archivo a pintar
/// viajaba en `src` mientras el cliente miraba `asset_key`.
///
/// El JSON de abajo es, literalmente, lo que devuelve hoy `GET /avatar` para una
/// capa carmesí equipada.
void main() {
  Map<String, dynamic> capaDelServidor(String nombre, int z) => <String, dynamic>{
        'slot': 'cape',
        'item_code': 'capa_carmesi',
        'key': nombre,
        'z': z,
        'src': 'items/capa_carmesi/$nombre.v1.webp',
        'x': 0,
        'y': 0,
        'w': 1024,
        'h': 1024,
        'tint': null,
      };

  group('una capa del avatar', () {
    test('la clave es el nombre de la capa, no el código del ítem', () {
      final CapaAvatar c = CapaAvatar.desdeJson(capaDelServidor('cape_back', 20));

      expect(c.clave, 'cape_back');
      expect(c.codigoItem, 'capa_carmesi');
      expect(c.ranura, RanuraItem.capa);
    });

    test('trae el archivo que hay que pintar', () {
      final CapaAvatar c = CapaAvatar.desdeJson(capaDelServidor('cape_front', 140));

      expect(c.assetKey, 'items/capa_carmesi/cape_front.v1.webp');
    });

    test('trae su rectángulo dentro del lienzo maestro', () {
      final CapaAvatar c = CapaAvatar.desdeJson(capaDelServidor('cape_back', 20));

      expect(c.ancho, 1024);
      expect(c.alto, 1024);
      expect(c.desplazamientoX, 0);
      expect(c.desplazamientoY, 0);
    });
  });

  group('el avatar completo', () {
    test('una capa aporta dos capas distintas, y se ordenan por z', () {
      final Avatar a = Avatar.desdeJson(<String, dynamic>{
        'traits': <String, dynamic>{},
        'archetype': 'acero',
        'equipment': <String, dynamic>{},
        // A propósito en orden inverso: el cliente ordena por z al leer.
        'layers': <dynamic>[
          capaDelServidor('cape_front', 140),
          capaDelServidor('cape_back', 20),
        ],
        'etag': 'x',
      });

      expect(a.capas.map((CapaAvatar c) => c.clave).toList(), <String>[
        'cape_back',
        'cape_front',
      ]);
      // Dos filas del mismo ítem, pero no la misma capa: eso era el fallo.
      expect(a.capas.first.clave, isNot(a.capas.last.clave));
      expect(a.capas.first.codigoItem, a.capas.last.codigoItem);
    });
  });
}
