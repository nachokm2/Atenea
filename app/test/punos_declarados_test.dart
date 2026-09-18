/// Lo que `Arte.conPunoPropio` promete tiene que existir en el disco.
///
/// Esa lista no es informativa: **decide que se apague la mano del cuerpo**. Si
/// declara una pieza cuyo `_puno.webp` no está exportado, el aprendiz se queda
/// con el brazo cortado —la mano apagada y nada en su lugar— y no falla nada:
/// `Image.asset` de un recurso que falta pinta su respaldo y sigue.
///
/// Al revés también importa. Un puño exportado que nadie declara es una mano
/// dibujada encima de la del cuerpo, que es el fallo original de las dos manos.
///
/// La lista la emite `scripts/quitar_punos.py` y se pega a mano en
/// `arte.dart`: este es el paso que puede olvidarse, y es exactamente lo que
/// pasó con `arco_fresno` femenino, que estuvo sin declarar mientras su pieza
/// seguía trayendo el puño dibujado dentro.
library;

import 'dart:io';

import 'package:atenea/design/arte.dart';
import 'package:flutter_test/flutter_test.dart';

/// Los recursos que Flutter empaqueta de verdad, leídos del manifiesto.
///
/// No se listan los ficheros del disco: lo que llega al APK es lo que declara
/// `pubspec.yaml`, y las entradas de directorio de Flutter **no son
/// recursivas**. Una carpeta sin declarar existe en el repositorio y no en el
/// teléfono, que es una forma de fallar que solo se ve instalando.
///
/// Y por eso se leen las carpetas del `pubspec` en vez de `AssetManifest`: en
/// una prueba de `test` normal no hay `rootBundle` con el manifiesto del APK,
/// y usarlo dejaría fuera justo el error que esto busca.
Set<String> _recursosDeclarados() {
  final File manifiesto = File('pubspec.yaml');
  final List<String> carpetas = <String>[];
  for (final String linea in manifiesto.readAsLinesSync()) {
    final String t = linea.trim();
    if (t.startsWith('- assets/')) carpetas.add(t.substring(2));
  }
  final Set<String> rutas = <String>{};
  for (final String carpeta in carpetas) {
    final Directory d = Directory(carpeta);
    if (!d.existsSync()) continue;
    for (final FileSystemEntity e in d.listSync()) {
      if (e is File) rutas.add(e.path.replaceAll(r'\', '/'));
    }
  }
  return rutas;
}

void main() {
  late Set<String> recursos;

  setUpAll(() => recursos = _recursosDeclarados());

  test('el manifiesto declara las carpetas de capas', () {
    // Si esto falla, todo lo demás de este fichero mide el vacío.
    expect(
      recursos.where((String r) => r.contains('/capas/')).length,
      greaterThan(50),
      reason: 'no encuentro las capas: revisa las carpetas de pubspec.yaml',
    );
  });

  test('cada pieza declarada con puño propio tiene su puño exportado', () {
    final List<String> faltan = <String>[];
    Arte.conPunoPropio.forEach((String familia, Set<String> piezas) {
      final String figura = 'base_${familia}_002';
      for (final String pieza in piezas) {
        final String ruta =
            Arte.punoDeLaPieza(figura: figura, src: '$pieza.webp');
        if (!recursos.contains(ruta)) faltan.add(ruta);
      }
    });

    expect(
      faltan,
      isEmpty,
      reason: 'declaran puño propio y no lo tienen: la mano del cuerpo se '
          'apagaría y no habría nada en su lugar',
    );
  });

  test('cada puño exportado está declarado', () {
    // El otro lado del mismo error, y el que produjo el fallo original: una
    // pieza que trae su puño dibujado y no está en la lista pinta dos manos.
    final List<String> sinDeclarar = <String>[];
    for (final String familia in Arte.conPunoPropio.keys) {
      final String prefijo = 'assets/arte/capas/$familia/';
      for (final String ruta in recursos) {
        if (!ruta.contains(prefijo) || !ruta.endsWith('_puno.webp')) continue;
        final String pieza = ruta
            .substring(ruta.indexOf(prefijo) + prefijo.length)
            .replaceAll('_puno.webp', '');
        if (!Arte.conPunoPropio[familia]!.contains(pieza)) {
          sinDeclarar.add('$familia/$pieza');
        }
      }
    }

    expect(
      sinDeclarar,
      isEmpty,
      reason: 'tienen puño exportado y no lo declaran: se verían dos manos',
    );
  });

  test('las dos familias declaran piezas, y no las mismas por casualidad', () {
    // Va por familia a propósito: hay piezas con puño en una y no en la otra
    // —`espada_entrenamiento` es la que lo prueba—. Con una lista común, el
    // cliente apagaría la mano de la figura equivocada.
    expect(Arte.conPunoPropio.keys.toSet(), <String>{'masculino', 'femenino'});
    for (final Set<String> piezas in Arte.conPunoPropio.values) {
      expect(piezas, isNotEmpty);
    }
    expect(
      Arte.conPunoPropio['femenino'],
      isNot(equals(Arte.conPunoPropio['masculino'])),
      reason: 'si fueran iguales, la lista por familia no haría falta',
    );
  });
}
