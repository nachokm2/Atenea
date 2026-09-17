/// Las piezas de equipo se colocan sobre la figura que toca.
///
/// Las 46 piezas se generaron **por familia**, editando la ilustración de una
/// figura de cada una. Sobre esa encajan al milímetro; sobre las otras dos, no:
/// el torso varía hasta 28 px por lado y la mano cambia de altura hasta 48. Como
/// cada arma lleva dibujado su propio puño agarrándola, esos 48 px son la
/// distancia entre ese puño y la mano del cuerpo —y se ven las dos manos, que es
/// justo como lo describió el aprendiz que lo encontró.
///
/// Lo que se comprueba aquí no es cómo queda —eso se mira, y se miró componiendo
/// las capas fuera de la aplicación— sino que la tabla esté completa y que cada
/// clase de capa reciba la transformación que le toca. Estirar una espada la
/// engorda; mover una túnica la descoloca.
library;

import 'package:atenea/design/arte.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('la tabla de ajustes', () {
    test('cubre las seis figuras', () {
      // Una figura sin entrada cae al ajuste neutro y se ve mal en silencio.
      for (final String figura in Arte.personajes) {
        expect(
          Arte.ajuste(figura).esNeutro && !figura.endsWith('_002'),
          isFalse,
          reason: '$figura no tiene medidas y no es canónica',
        );
      }
    });

    test('las dos figuras canónicas no se tocan', () {
      // Sobre ellas se dibujó cada pieza, así que su ajuste es la identidad por
      // definición. Si alguna dejara de serlo, es que la tabla se regeneró
      // contra otra figura de referencia.
      expect(Arte.ajuste('base_masculino_002').esNeutro, isTrue);
      expect(Arte.ajuste('base_femenino_002').esNeutro, isTrue);
    });

    test('una figura desconocida no se ajusta', () {
      // Sin medidas es mejor no tocar nada: una pieza sin ajustar se ve regular,
      // una con un ajuste inventado se ve peor.
      expect(Arte.ajuste('base_marciano_007').esNeutro, isTrue);
    });

    test('los ajustes son de la magnitud medida, no de cualquiera', () {
      // Una red contra el dedo gordo: si alguien pega un número con la coma
      // corrida, la pieza se va de la pantalla y nadie lo nota hasta el móvil.
      for (final String figura in Arte.personajes) {
        final AjusteDeFigura a = Arte.ajuste(figura);
        expect(a.escalaTorso, inInclusiveRange(0.7, 1.4), reason: figura);
        expect(a.torsoDx.abs(), lessThan(200), reason: figura);
        expect(a.manoDx.abs(), lessThan(120), reason: figura);
        expect(a.manoDy.abs(), lessThan(120), reason: figura);
      }
    });
  });

  group('qué transformación lleva cada capa', () {
    test('la ropa se ciñe al torso, así que pide talla', () {
      for (final String capa in <String>[
        'outfit',
        'cape_back',
        'cape_front',
        'accessory_body',
      ]) {
        expect(TrazoDeCapa.de(capa), TrazoDeCapa.talla, reason: capa);
      }
    });

    test('lo que se sostiene con la mano pide sitio, no talla', () {
      // Estirar una espada la engorda. Lo que hay que hacer es llevarla a donde
      // está la mano de esta figura.
      for (final String capa in <String>['weapon', 'offhand', 'gloves']) {
        expect(TrazoDeCapa.de(capa), TrazoDeCapa.mano, reason: capa);
      }
    });

    test('la cabeza, el pelo y los pies no se tocan', () {
      // El ajuste del torso no describe la cabeza, y el de la mano la mandaría
      // a cualquier sitio. Sin medidas propias, mejor quietas.
      for (final String capa in <String>[
        'face',
        'hair_front',
        'hair_back',
        'head',
        'boots',
        'ears',
        'pet',
        'mount_back',
      ]) {
        expect(TrazoDeCapa.de(capa), TrazoDeCapa.ninguno, reason: capa);
      }
    });

    test('una capa que no existe todavía no se transforma', () {
      // El catálogo puede crecer desde el servidor sin que el cliente sepa del
      // nombre nuevo. Quieta es la única respuesta segura.
      expect(TrazoDeCapa.de('jetpack'), TrazoDeCapa.ninguno);
    });
  });
}
