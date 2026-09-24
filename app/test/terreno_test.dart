/// `TerrenoDelMundo`: el fondo ilustrado del mundo caminable (Parte A).
///
/// Lo único que importa proteger acá es la misma invariante que ya protege
/// `senda_test.dart` para las paradas: la posición/variante de una banda es
/// función de su propio índice, nunca del total de bandas — si dependiera
/// del total, cada módulo nuevo repintaría un terreno distinto bajo las
/// paradas ya visitadas. Ver `docs/planes/mundo-caminable.md`.
library;

import 'package:atenea/pantallas/aventura/mundo/terreno.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Todas las rutas `Image.asset` bajo `TerrenoDelMundo`, en orden de árbol
/// (de arriba hacia abajo, ya que las bandas se listan en ese orden).
List<String> _rutasDeLasBandas(WidgetTester tester) {
  return tester
      .widgetList<Image>(find.byType(Image))
      .map((Image img) => (img.image as AssetImage).assetName)
      .toList();
}

void main() {
  testWidgets(
      'la variante de la banda es función de su índice — no cambia si el '
      'mundo crece', (WidgetTester tester) async {
    // Un mundo de 4 módulos y uno de 6: las primeras bandas tienen que
    // pintar exactamente la misma ruta en ambos casos.
    const Size chico = Size(360, 96 + 4 * 240 + 96);
    const Size grande = Size(360, 96 + 6 * 240 + 96);

    await tester.pumpWidget(
      MaterialApp(home: TerrenoDelMundo(tamano: chico)),
    );
    await tester.pump();
    final List<String> rutasChico = _rutasDeLasBandas(tester);

    await tester.pumpWidget(
      MaterialApp(home: TerrenoDelMundo(tamano: grande)),
    );
    await tester.pump();
    final List<String> rutasGrande = _rutasDeLasBandas(tester);

    expect(rutasChico, isNotEmpty);
    for (int i = 0; i < rutasChico.length; i++) {
      expect(rutasGrande[i], rutasChico[i],
          reason: 'la banda $i cambió de variante solo porque el mundo creció');
    }
  });

  testWidgets('el espejo horizontal alterna con el índice de la banda',
      (WidgetTester tester) async {
    // Con una sola variante declarada hoy, la ruta de la imagen no basta
    // para distinguir bandas (todas piden el mismo archivo) — el espejo
    // horizontal sí varía por índice ya desde ahora, y es lo que de verdad
    // rompe la periodicidad hasta que la Fase T3 sume más láminas.
    const Size tamano = Size(360, 1000);
    await tester.pumpWidget(MaterialApp(home: TerrenoDelMundo(tamano: tamano)));
    await tester.pump();

    final List<bool> espejos = tester
        .widgetList<Transform>(find.byType(Transform))
        .map((Transform t) => t.transform.entry(0, 0) < 0)
        .toList();

    expect(espejos, isNotEmpty);
    for (int i = 0; i < espejos.length; i++) {
      expect(espejos[i], i.isOdd, reason: 'banda $i: se esperaba espejo == ${i.isOdd}');
    }
  });

  testWidgets('las bandas cubren todo el alto declarado, sin pasarse de largo',
      (WidgetTester tester) async {
    const Size tamano = Size(360, 1000);
    await tester.pumpWidget(MaterialApp(home: TerrenoDelMundo(tamano: tamano)));
    await tester.pump();

    final int bandas = _rutasDeLasBandas(tester).length;
    const double alto = 360; // aspectoDelTramo == 1.0, banda == ancho.
    expect(bandas * alto, greaterThanOrEqualTo(tamano.height));
    expect((bandas - 1) * alto, lessThan(tamano.height));
  });

  testWidgets('sin arte real, no explota — cae al color de suelo',
      (WidgetTester tester) async {
    await tester.pumpWidget(
      const MaterialApp(home: TerrenoDelMundo(tamano: Size(360, 720))),
    );
    await tester.pump();

    expect(tester.takeException(), isNull);
    expect(find.byType(ColoredBox), findsWidgets);
  });
}
