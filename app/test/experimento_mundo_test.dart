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
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'ayudas.dart';

PintorDeCaminanteDeMentira _pintorDelCaminante(WidgetTester tester) {
  final Finder buscado = find.byWidgetPredicate(
    (Widget w) => w is CustomPaint && w.painter is PintorDeCaminanteDeMentira,
  );
  return tester.widget<CustomPaint>(buscado).painter! as PintorDeCaminanteDeMentira;
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
    expect(_pintorDelCaminante(tester).enMarcha, isFalse,
        reason: 'antes de tocar nada, ya tiene que estar en reposo');

    await tester.tap(find.bySemanticsLabel('Módulo 3'));
    await tester.pump();
    // La figura de ejemplo es Acero/masculino, que desde la Fase D ya tiene
    // arte real de marcha (`assets/arte/mundo/masculino/acero/`): a mitad de
    // camino se pinta la imagen real, no el pintor de mentira — por eso se
    // comprueba con `Image`, no con `_pintorDelCaminante`.
    expect(tester.takeException(), isNull);
    expect(find.byType(Image), findsWidgets,
        reason: 'a mitad de camino tiene que estar en marcha, o no se prueba nada');

    // Un poco más que `Movimiento.corta`, no justo — a la duración exacta el
    // controlador puede seguir en `forward` hasta el próximo tick.
    await tester.pump(Movimiento.corta + const Duration(milliseconds: 50));
    // Un pump más: recién acá `Caminante` vuelve a pedir `rutaDeReposo` (sin
    // arte real todavía), y el fallo de `Image.asset` que activa el pintor de
    // mentira se resuelve async — no dentro del mismo pump que completa la
    // animación.
    await tester.pump();
    expect(_pintorDelCaminante(tester).enMarcha, isFalse,
        reason: 'llegado el destino, tiene que volver a reposo');
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
