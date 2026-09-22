/// El cambio de rango no se distinguía de subir de nivel dentro del rango.
///
/// El servidor calculaba `rank_changed` y le daba su propio bono de oro
/// (`gold.rank_up_bonus`, aparte del de nivel), pero el modal siempre decía
/// "SUBISTE DE NIVEL" y ese bono se fundía, anónimo, en el oro total del
/// recibo — la prueba de la cola de celebraciones ya ejercitaba el caso
/// exacto (`rank_changed: true`) y ni siquiera lo notaba, porque no había
/// nada en pantalla que lo distinguiera.
library;

import 'package:atenea/design/theme.dart';
import 'package:atenea/estado/celebraciones.dart';
import 'package:atenea/pantallas/celebraciones/modal_nivel.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'ayudas.dart';

NivelRecibo _nivel({
  required bool cambioRango,
  int oroBonusRango = 0,
}) =>
    NivelRecibo(
      antes: 6,
      despues: 7,
      subioNivel: true,
      tituloRangoAntes: 'Iniciado/a',
      tituloRangoDespues: cambioRango ? 'Aprendiz del Reino' : 'Iniciado/a',
      cambioRango: cambioRango,
      oroBonus: 50,
      oroBonusRango: oroBonusRango,
    );

Celebracion _celebracionDeNivel(NivelRecibo nivel) => Celebracion(
      paso: PasoCelebracion.subidaNivel,
      formato: FormatoCelebracion.overlay,
      recibo: ReciboRecompensas(
        id: 'rec-test',
        tipoEvento: 'LESSON_COMPLETED',
        nivel: nivel,
      ),
      titulo: 'Nivel 7',
      duracion: Duration.zero,
    );

Future<void> _montar(WidgetTester tester, NivelRecibo nivel) async {
  await tester.pumpWidget(
    ChangeNotifierProvider<ColaCelebraciones>(
      create: (_) => ColaCelebraciones(),
      child: MaterialApp(
        theme: AteneaTheme.oscuro(),
        home: Scaffold(
          body: ModalSubidaDeNivel(celebracion: _celebracionDeNivel(nivel)),
        ),
      ),
    ),
  );
  await tester.pump();
}

void main() {
  setUp(prepararTipografias);

  test('NivelRecibo.desdeJson lee rank_bonus, aparte de gold_bonus', () {
    final NivelRecibo nivel = NivelRecibo.desdeJson(<String, dynamic>{
      'before': 6,
      'after': 7,
      'leveled_up': true,
      'rank_title_before': 'Iniciado/a',
      'rank_title_after': 'Aprendiz del Reino',
      'rank_changed': true,
      'gold_bonus': 50,
      'rank_bonus': 100,
    });

    expect(nivel.oroBonus, 50);
    expect(nivel.oroBonusRango, 100);
  });

  testWidgets('sin cambio de rango, dice "SUBISTE DE NIVEL" y solo el rango vigente',
      (WidgetTester tester) async {
    await _montar(tester, _nivel(cambioRango: false));

    expect(find.text('SUBISTE DE NIVEL'), findsOneWidget);
    expect(find.text('¡NUEVO RANGO!'), findsNothing);
    expect(find.text('Iniciado/a'), findsOneWidget);
    expect(find.textContaining('→'), findsNothing);
  });

  testWidgets('con cambio de rango, dice "¡NUEVO RANGO!" y el salto completo',
      (WidgetTester tester) async {
    await _montar(tester, _nivel(cambioRango: true, oroBonusRango: 100));

    expect(find.text('¡NUEVO RANGO!'), findsOneWidget);
    expect(find.text('SUBISTE DE NIVEL'), findsNothing);
    expect(find.text('Iniciado/a → Aprendiz del Reino'), findsOneWidget);
  });

  testWidgets('el bono de rango se muestra aparte del de nivel, no fundido',
      (WidgetTester tester) async {
    await _montar(tester, _nivel(cambioRango: true, oroBonusRango: 100));

    expect(find.textContaining('+50 de oro', findRichText: true), findsOneWidget);
    expect(
      find.textContaining('+100 de oro por el rango', findRichText: true),
      findsOneWidget,
    );
  });
}
