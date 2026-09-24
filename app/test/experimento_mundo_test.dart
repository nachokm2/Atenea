/// El spike de la Fase 0a (`experimento_mundo.dart`): que las paradas de
/// ejemplo existan y que tocar una de verdad mueva —o de verdad detenga— al
/// caminante.
///
/// No es una prueba exhaustiva a propósito: este archivo es descartable por
/// diseño (ver el plan, Fase 0). Lo que sí importa proteger mientras se itera
/// a mano sobre él es el único mecanismo que la Fase 0a existe para evaluar:
/// tocar una parada abierta camina hasta ella, tocar una bloqueada se detiene
/// en el portón y explica por qué — la geometría en sí ya la prueba
/// `senda_test.dart`.
library;

import 'package:atenea/design/theme.dart';
import 'package:atenea/design/tokens.dart';
import 'package:atenea/pantallas/aventura/mundo/caminante.dart';
import 'package:atenea/pantallas/aventura/mundo/experimento_mundo.dart';
import 'package:atenea/pantallas/aventura/mundo/senda.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'ayudas.dart';

// La figura de ejemplo es Acero/masculino, que desde la Fase D ya tiene arte
// real de marcha Y de reposo (`assets/arte/mundo/masculino/acero/`): ni
// reposo ni marcha caen nunca al pintor de mentira para esta combinación, así
// que "¿está en marcha o en reposo?" se lee de qué fotograma pidió la
// `Image` real, no de `PintorDeCaminanteDeMentira`.
//
// `find.descendant(of: Caminante, ...)`, no `find.byType(Image).first`: el
// terreno (Parte A, `terreno.dart`) también pinta `Image`s, detrás de todo
// en el `Stack` pero antes en el árbol — `.first` dejó de ser el caminante
// en cuanto el terreno entró.
String _rutaDeLaImagen(WidgetTester tester) {
  final Image imagen = tester.widget<Image>(
    find.descendant(of: find.byType(Caminante), matching: find.byType(Image)),
  );
  return (imagen.image as AssetImage).assetName;
}

Future<void> _montar(WidgetTester tester) async {
  await tester.binding.setSurfaceSize(const Size(412, 915));
  addTearDown(() => tester.binding.setSurfaceSize(null));
  await tester.pumpWidget(
    MaterialApp(
      theme: AteneaTheme.oscuro(),
      home: const PantallaExperimentoMundo(),
    ),
  );
  await tester.pump();
}

void main() {
  setUp(prepararTipografias);

  testWidgets(
      'el sendero usa el ancho real de la pantalla, no un ancho fijo a mano',
      (WidgetTester tester) async {
    // Bug real, encontrado antes de meter terreno ilustrado (Parte A): la
    // pantalla no limita el ancho de lectura ni pone padding, así que el
    // mundo mide el ancho real de la superficie (412dp en esta prueba), no
    // los 360 que `Senda.desdeDetalle` recibía a mano. Con un trazo de 6px
    // era invisible; con arte que llena el ancho, se nota.
    //
    // Módulo 2 (índice 1), no Módulo 1: la parada 0 cae exactamente en el
    // centro horizontal (`sin(0) == 0` en `puntoEnY`) — un `Column` con
    // `crossAxisAlignment` por defecto centra el mundo (más angosto que la
    // pantalla) dentro del ancho real, y esa segunda centrada cancela por
    // coincidencia el error justo en el punto medio. La parada 1 cae en el
    // extremo de la serpentina (`sin(π/2) == 1`), donde el error de verdad
    // se nota — confirmado reintroduciendo el bug a mano: con `ancho: 360`
    // esta parada aterriza en x≈290,5 en vez de x≈307,1.
    await _montar(tester);

    final double xEsperado = puntoEnY(yDeParada(1), 412).dx;
    final double xReal = tester.getCenter(find.bySemanticsLabel('Módulo 2')).dx;
    expect(xReal, closeTo(xEsperado, 0.5));
  });

  testWidgets('las 6 paradas de ejemplo y el tesoro existen, con su nombre',
      (WidgetTester tester) async {
    await _montar(tester);

    for (int i = 1; i <= 6; i++) {
      expect(find.bySemanticsLabel('Módulo $i'), findsOneWidget);
    }
    expect(find.bySemanticsLabel('Tesoro final'), findsOneWidget);
  });

  testWidgets('tocar una parada abierta no muestra ningún aviso de bloqueo',
      (WidgetTester tester) async {
    await _montar(tester);

    // Módulo 3 (índice 2) es `available` en el detalle de ejemplo — la
    // última parada realmente alcanzable.
    await tester.tap(find.bySemanticsLabel('Módulo 3'));
    await tester.pump(Movimiento.corta);
    await tester.pump(Movimiento.corta);

    expect(find.textContaining('para desbloquear'), findsNothing);
  });

  testWidgets(
      'tocar una parada bloqueada detiene al caminante en el portón y '
      'explica el motivo real que manda el detalle de ejemplo',
      (WidgetTester tester) async {
    await _montar(tester);

    // Módulo 4 (índice 3) es el primer `locked` del detalle de ejemplo, pero
    // cae fuera del viewport inicial — hay que desplazar la cámara primero.
    await tester.ensureVisible(find.bySemanticsLabel('Módulo 4'));
    await tester.pump();
    await tester.tap(find.bySemanticsLabel('Módulo 4'));
    await tester.pump(Movimiento.corta);
    await tester.pump(Movimiento.corta);

    expect(
      find.text('Completa el módulo 3 para desbloquear'),
      findsOneWidget,
      reason: 'el aviso debe repetir el `locked_reason` real, no un texto '
          'genérico inventado en el spike',
    );
  });

  testWidgets(
      'al llegar, el caminante vuelve a reposo — no queda congelado en marcha',
      (WidgetTester tester) async {
    await _montar(tester);
    expect(_rutaDeLaImagen(tester), contains('reposo_'),
        reason: 'antes de tocar nada, ya tiene que estar en reposo');

    await tester.tap(find.bySemanticsLabel('Módulo 3'));
    await tester.pump();
    expect(tester.takeException(), isNull);
    expect(_rutaDeLaImagen(tester), contains('marcha_'),
        reason: 'a mitad de camino tiene que estar en marcha, o no se prueba nada');

    // La duración real depende de la distancia del tramo (a velocidad
    // constante, no a duración fija — ver `_duracionDelTramo`), así que acá
    // no hay un número exacto que pumpear: se pumpea de sobra (el tramo más
    // largo posible no pasa de 4 segundos) para no acoplar la prueba a la
    // fórmula de velocidad.
    await tester.pump(const Duration(seconds: 5));
    // Un pump más: recién acá `Caminante` vuelve a pedir `rutaDeReposo`, y la
    // `Image` real se resuelve async — no dentro del mismo pump que completa
    // la animación.
    await tester.pump();
    expect(_rutaDeLaImagen(tester), contains('reposo_'),
        reason: 'llegado el destino, tiene que volver a reposo');
  });

  group('velocidad constante, no duración fija', () {
    // Rodrigo, en el teléfono, sobre la duración fija anterior (250ms para
    // CUALQUIER tramo): "muy rapido aun". La comparación que de verdad prueba
    // "a velocidad constante" es esta: un tramo de una parada (~254dp, ~1,27s
    // a 200dp/s) y uno de dos (~480dp, ~2,4s) tienen que tardar cosas
    // distintas — con una duración fija, tardarían lo mismo, sea cual sea.
    // 1,8s cae entre las dos duraciones reales (calculado con la geometría
    // real de `senda.dart`, no a ojo), así que a esa espera el tramo corto ya
    // llegó y el largo todavía no.
    testWidgets('un tramo de una parada ya llegó cuando pasan 1,8s',
        (WidgetTester tester) async {
      await _montar(tester);
      await tester.tap(find.bySemanticsLabel('Módulo 2'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 1800));
      await tester.pump();

      expect(_rutaDeLaImagen(tester), contains('reposo_'),
          reason: 'un tramo de una parada (~1,27s) ya debería haber llegado a los 1,8s');
    });

    testWidgets('un tramo de dos paradas sigue en marcha cuando pasan 1,8s',
        (WidgetTester tester) async {
      await _montar(tester);
      await tester.tap(find.bySemanticsLabel('Módulo 3'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 1800));

      expect(_rutaDeLaImagen(tester), contains('marcha_'),
          reason: 'un tramo de dos paradas (~2,4s) no debería haber llegado todavía a '
              'los 1,8s — si tarda lo mismo que el de una parada, la duración es fija, '
              'no depende de la distancia');
    });
  });

  testWidgets('el slider cambia la cantidad de módulos de ejemplo',
      (WidgetTester tester) async {
    await _montar(tester);

    expect(find.bySemanticsLabel('Módulo 6'), findsOneWidget);
    expect(find.bySemanticsLabel('Módulo 8'), findsNothing);

    // Un arrastre bien más allá del borde derecho, en vez de un toque cerca
    // de él, para no depender del relleno interno del `Slider` alrededor de
    // su pista: así el valor queda en el máximo (10) sin ambigüedad.
    await tester.drag(find.byType(Slider), const Offset(1000, 0));
    await tester.pump();

    expect(find.bySemanticsLabel('Módulo 8'), findsOneWidget);
    expect(find.bySemanticsLabel('Módulo 10'), findsOneWidget);
  });
}
