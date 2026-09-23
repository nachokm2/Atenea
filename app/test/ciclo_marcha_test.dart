/// `CicloDeMarcha`: qué fotograma toca, dada una figura y una distancia — sin
/// árbol de widgets, sin `BuildContext`. Ver `docs/planes/mundo-caminable.md`,
/// Fase A.
library;

import 'package:atenea/pantallas/aventura/mundo/ciclo_marcha.dart';
import 'package:atenea/pantallas/aventura/mundo/figura_del_mundo.dart';
import 'package:atenea/datos/dtos.dart';
import 'package:flutter_test/flutter_test.dart';

const FiguraDelMundo _sinArmas = FiguraDelMundo(familia: 'masculino', arquetipo: Arquetipo.acero);

void main() {
  group('rutas de archivo', () {
    test('la ruta de marcha usa la familia y el arquetipo reales', () {
      final CicloDeMarcha ciclo = CicloDeMarcha(_sinArmas);
      expect(ciclo.rutaDeMarcha(0), 'assets/arte/mundo/masculino/acero/marcha_00.webp');
      expect(ciclo.rutaDeMarcha(2), 'assets/arte/mundo/masculino/acero/marcha_02.webp');
    });

    test('otra familia u Orden da otra carpeta, nunca la misma', () {
      final CicloDeMarcha unoA = CicloDeMarcha(
        const FiguraDelMundo(familia: 'masculino', arquetipo: Arquetipo.acero),
      );
      final CicloDeMarcha unoB = CicloDeMarcha(
        const FiguraDelMundo(familia: 'femenino', arquetipo: Arquetipo.acero),
      );
      final CicloDeMarcha unoC = CicloDeMarcha(
        const FiguraDelMundo(familia: 'masculino', arquetipo: Arquetipo.bosque),
      );
      expect(unoA.rutaDeMarcha(0), isNot(unoB.rutaDeMarcha(0)));
      expect(unoA.rutaDeMarcha(0), isNot(unoC.rutaDeMarcha(0)));
    });

    test('la ruta de marcha envuelve el índice sobre los 4 fotogramas', () {
      final CicloDeMarcha ciclo = CicloDeMarcha(_sinArmas);
      expect(ciclo.rutaDeMarcha(4), ciclo.rutaDeMarcha(0));
      expect(ciclo.rutaDeMarcha(5), ciclo.rutaDeMarcha(1));
    });

    test('la ruta de reposo envuelve el índice sobre los 2 fotogramas', () {
      final CicloDeMarcha ciclo = CicloDeMarcha(_sinArmas);
      expect(ciclo.rutaDeReposo(0), 'assets/arte/mundo/masculino/acero/reposo_00.webp');
      expect(ciclo.rutaDeReposo(2), ciclo.rutaDeReposo(0));
    });
  });

  group('props', () {
    test('sin nada empuñado, las dos rutas de prop son nulas', () {
      final CicloDeMarcha ciclo = CicloDeMarcha(_sinArmas);
      expect(ciclo.rutaDePropDiestro, isNull);
      expect(ciclo.rutaDePropZurdo, isNull);
    });

    test('con un arma equipada, la ruta del prop diestro nombra su clase', () {
      const FiguraDelMundo figura = FiguraDelMundo(
        familia: 'masculino',
        arquetipo: Arquetipo.acero,
        claseArma: ClaseDeArma.hoja,
      );
      expect(CicloDeMarcha(figura).rutaDePropDiestro, 'assets/arte/mundo/props/blade.webp');
    });

    test('con un escudo equipado, la ruta del prop zurdo nombra su clase', () {
      const FiguraDelMundo figura = FiguraDelMundo(
        familia: 'masculino',
        arquetipo: Arquetipo.muro,
        claseSecundaria: ClaseDeArma.escudo,
      );
      expect(CicloDeMarcha(figura).rutaDePropZurdo, 'assets/arte/mundo/props/shield.webp');
    });
  });

  group('fotogramaPorDistancia', () {
    test('a distancia cero, el primer fotograma', () {
      expect(CicloDeMarcha(_sinArmas).fotogramaPorDistancia(0), 0);
    });

    test('avanza un fotograma cada dpPorFotogramaDeMarcha, en orden', () {
      final CicloDeMarcha ciclo = CicloDeMarcha(_sinArmas);
      for (int i = 0; i < 12; i++) {
        final double dp = i * dpPorFotogramaDeMarcha + 1; // +1: nunca justo en el borde
        expect(ciclo.fotogramaPorDistancia(dp), i % fotogramasDeMarcha, reason: 'dp=$dp');
      }
    });

    test('es cíclico: una vuelta entera del ciclo vuelve al fotograma 0', () {
      final CicloDeMarcha ciclo = CicloDeMarcha(_sinArmas);
      final double unaVueltaCompleta = dpPorFotogramaDeMarcha * fotogramasDeMarcha;
      expect(ciclo.fotogramaPorDistancia(unaVueltaCompleta + 1), 0);
    });

    test('una distancia negativa no revienta — se trata como su valor absoluto', () {
      final CicloDeMarcha ciclo = CicloDeMarcha(_sinArmas);
      expect(ciclo.fotogramaPorDistancia(-1), ciclo.fotogramaPorDistancia(1));
    });
  });

  group('fotogramaDeReposoPorFase', () {
    test('la primera mitad de la fase da el primer fotograma', () {
      expect(CicloDeMarcha(_sinArmas).fotogramaDeReposoPorFase(0.1), 0);
    });

    test('la segunda mitad de la fase da el segundo fotograma', () {
      expect(CicloDeMarcha(_sinArmas).fotogramaDeReposoPorFase(0.6), 1);
    });

    test('una fase de 1.0 o más envuelve, nunca sale del rango de fotogramas', () {
      final CicloDeMarcha ciclo = CicloDeMarcha(_sinArmas);
      expect(ciclo.fotogramaDeReposoPorFase(1.1), ciclo.fotogramaDeReposoPorFase(0.1));
      expect(ciclo.fotogramaDeReposoPorFase(2.6), ciclo.fotogramaDeReposoPorFase(0.6));
    });
  });
}
