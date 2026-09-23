/// El spike de la Fase 0b (`experimento_marcha.dart`): que monte, que la
/// animación corra sin lanzar, y que los cuatro deslizadores existan.
///
/// No hay una prueba de "se ve como caminar" — es la pregunta que este spike
/// existe para responder, y solo un humano mirando el dispositivo real puede
/// contestarla (ver el plan, Fase 0). Lo que sí protege esta prueba es que la
/// composición de recortes/rotaciones no reviente mientras se itera a mano
/// sobre los ángulos y pivotes medidos.
library;

import 'package:atenea/design/theme.dart';
import 'package:atenea/pantallas/aventura/mundo/experimento_marcha.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'ayudas.dart';

void main() {
  setUp(prepararTipografias);

  testWidgets('monta y la marcha corre varios ciclos sin lanzar',
      (WidgetTester tester) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: AteneaTheme.oscuro(),
        home: const PantallaExperimentoMarcha(),
      ),
    );
    await tester.pump();

    // Varios pasos de un ciclo de 900ms: cubre fase 0, cuarto, mitad y
    // vuelta, donde `sin`/`cos` cambian de signo — el punto donde un pivote
    // mal calculado suele reventar primero.
    for (int i = 0; i < 6; i++) {
      await tester.pump(const Duration(milliseconds: 200));
    }

    expect(tester.takeException(), isNull);
  });

  testWidgets('los cuatro deslizadores existen y cambian su valor',
      (WidgetTester tester) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: AteneaTheme.oscuro(),
        home: const PantallaExperimentoMarcha(),
      ),
    );
    await tester.pump();

    expect(find.text('Cadera'), findsOneWidget);
    expect(find.text('Brazos'), findsOneWidget);
    expect(find.text('Bob'), findsOneWidget);
    expect(find.text('Inclinación'), findsOneWidget);
    expect(find.byType(Slider), findsNWidgets(4));

    final Rect elPrimero = tester.getRect(find.byType(Slider).first);
    await tester.tapAt(Offset(elPrimero.right - 1, elPrimero.center.dy));
    await tester.pump();

    expect(tester.takeException(), isNull);
  });
}
