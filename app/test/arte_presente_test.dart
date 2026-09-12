import 'package:atenea/design/arte.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

/// Todo lo que el mapa de arte promete tiene que existir de verdad.
///
/// Una ruta mal escrita o una carpeta que falte en `pubspec.yaml` no rompen la
/// compilación: la app arranca igual y el hueco solo se ve al abrir el Vestidor
/// con ese objeto equipado. Aquí se nota antes.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('cada ítem del catálogo apunta a un archivo que se puede cargar',
      () async {
    final Map<String, String> mapa = Arte.ilustracionesPorItem;
    expect(mapa, isNotEmpty);

    final List<String> rotas = <String>[];
    for (final MapEntry<String, String> entrada in mapa.entries) {
      final String ruta = 'assets/arte/items/${entrada.value}.webp';
      try {
        final ByteData datos = await rootBundle.load(ruta);
        if (datos.lengthInBytes == 0) rotas.add('${entrada.key} -> $ruta (vacío)');
      } catch (_) {
        rotas.add('${entrada.key} -> $ruta');
      }
    }

    expect(rotas, isEmpty, reason: 'ilustraciones que no se pueden cargar: $rotas');
  });

  test('las figuras de personaje también cargan', () async {
    final List<String> rotas = <String>[];
    for (final String clave in Arte.personajes) {
      final String ruta = Arte.personaje(clave);
      try {
        await rootBundle.load(ruta);
      } catch (_) {
        rotas.add(ruta);
      }
    }

    expect(rotas, isEmpty, reason: 'figuras que no se pueden cargar: $rotas');
  });

  test('los guantes tienen dibujo propio', () async {
    // Eran los dos únicos ítems del catálogo que caían al icono de su ranura.
    expect(Arte.item('guantes_cuero'), isNotNull);
    expect(Arte.item('guanteletes_acero'), isNotNull);
  });
}
