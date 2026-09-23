/// `figuraDelMundo`: de datos reales del avatar a la figura simplificada del
/// mundo caminable — nunca una tabla de código de ítem a clase en el
/// cliente. Ver `docs/planes/mundo-caminable.md`, Fase 0/A.
library;

import 'package:atenea/datos/dtos.dart';
import 'package:atenea/pantallas/aventura/mundo/figura_del_mundo.dart';
import 'package:flutter_test/flutter_test.dart';

CapaAvatar _capa({RanuraItem? ranura, ClaseDeArma? clase}) => CapaAvatar(
      clave: 'weapon',
      ranura: ranura,
      claseArma: clase,
    );

void main() {
  group('familia', () {
    test('trato masculino da la familia masculina, sin importar el cuerpo', () {
      final FiguraDelMundo f = figuraDelMundo(
        capas: const <CapaAvatar>[],
        rasgos: const RasgosAvatar(
          formaTrato: FormaTrato.masculino,
          tipoCuerpo: TipoCuerpo.esbelto,
        ),
        arquetipo: Arquetipo.acero,
      );
      expect(f.familia, 'masculino');
    });

    test('trato femenino da la familia femenina, sin importar el cuerpo', () {
      final FiguraDelMundo f = figuraDelMundo(
        capas: const <CapaAvatar>[],
        rasgos: const RasgosAvatar(
          formaTrato: FormaTrato.femenino,
          tipoCuerpo: TipoCuerpo.robusto,
        ),
        arquetipo: Arquetipo.bosque,
      );
      expect(f.familia, 'femenino');
    });

    test('la misma combinación de rasgos siempre da la misma familia', () {
      const RasgosAvatar rasgos = RasgosAvatar(rostro: 'face_02');
      final String primera = figuraDelMundo(
        capas: const <CapaAvatar>[],
        rasgos: rasgos,
        arquetipo: Arquetipo.acero,
      ).familia;
      final String segunda = figuraDelMundo(
        capas: const <CapaAvatar>[],
        rasgos: rasgos,
        arquetipo: Arquetipo.acero,
      ).familia;
      expect(segunda, primera);
    });
  });

  group('clase de lo empuñado', () {
    test('sin ninguna capa de arma o secundaria, las dos manos van vacías', () {
      final FiguraDelMundo f = figuraDelMundo(
        capas: const <CapaAvatar>[],
        rasgos: const RasgosAvatar(),
        arquetipo: Arquetipo.acero,
      );
      expect(f.claseArma, isNull);
      expect(f.claseSecundaria, isNull);
    });

    test('una capa de arma con clase llena la mano diestra, no la zurda', () {
      final FiguraDelMundo f = figuraDelMundo(
        capas: <CapaAvatar>[
          _capa(ranura: RanuraItem.arma, clase: ClaseDeArma.hoja),
        ],
        rasgos: const RasgosAvatar(),
        arquetipo: Arquetipo.acero,
      );
      expect(f.claseArma, ClaseDeArma.hoja);
      expect(f.claseSecundaria, isNull);
    });

    test('arma y escudo equipados a la vez llenan las dos manos', () {
      // El kit inicial real de la Vigilia del Muro: espada + escudo juntos
      // (backend/app/seeds/items.py, KITS_INICIALES[WALL]).
      final FiguraDelMundo f = figuraDelMundo(
        capas: <CapaAvatar>[
          _capa(ranura: RanuraItem.arma, clase: ClaseDeArma.hoja),
          _capa(ranura: RanuraItem.secundaria, clase: ClaseDeArma.escudo),
        ],
        rasgos: const RasgosAvatar(),
        arquetipo: Arquetipo.muro,
      );
      expect(f.claseArma, ClaseDeArma.hoja);
      expect(f.claseSecundaria, ClaseDeArma.escudo);
    });

    test('una capa de arma SIN clase no inventa una', () {
      // Este es el caso de `pluma_primer_paso`: un ítem empuñado real del
      // catálogo, sin clase a propósito. La mano debe quedar vacía, no caer
      // a una clase por defecto.
      final FiguraDelMundo f = figuraDelMundo(
        capas: <CapaAvatar>[
          _capa(ranura: RanuraItem.arma, clase: null),
        ],
        rasgos: const RasgosAvatar(),
        arquetipo: Arquetipo.acero,
      );
      expect(f.claseArma, isNull);
    });

    test('una capa de otra ranura (p. ej. capa o cabeza) no cuenta como arma', () {
      final FiguraDelMundo f = figuraDelMundo(
        capas: <CapaAvatar>[
          _capa(ranura: RanuraItem.cabeza, clase: ClaseDeArma.hoja),
        ],
        rasgos: const RasgosAvatar(),
        arquetipo: Arquetipo.acero,
      );
      expect(f.claseArma, isNull);
    });
  });

  test('el arquetipo viaja tal cual, es la Orden real del personaje', () {
    final FiguraDelMundo f = figuraDelMundo(
      capas: const <CapaAvatar>[],
      rasgos: const RasgosAvatar(),
      arquetipo: Arquetipo.bosqueAntiguo,
    );
    expect(f.arquetipo, Arquetipo.bosqueAntiguo);
  });
}
