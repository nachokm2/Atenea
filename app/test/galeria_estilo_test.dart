/// La galería del sistema de diseño es la referencia viva del lenguaje
/// visual: si ella desborda, cualquier pantalla que use los mismos tokens
/// desbordará también.
///
/// Esta prueba la recorre en los dos temas y en tres anchos, con la escala de
/// texto al 100 %, al 130 % y al 200 %, y falla ante el primer error de
/// maquetación.
library;

import 'package:atenea/design/theme.dart';
import 'package:atenea/nucleo/controlador_tema.dart';
import 'package:atenea/pantallas/galeria_estilo.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'ayudas.dart';

void main() {
  setUp(prepararTipografias);

  const List<Size> tamanos = <Size>[
    Size(320, 568), // el teléfono más estrecho que soportamos
    Size(412, 915), // teléfono moderno
    Size(800, 1280), // tableta
  ];
  const List<double> escalas = <double>[1.0, 1.3, 2.0];

  for (final bool oscuro in <bool>[true, false]) {
    final String tema = oscuro ? 'Noche del Reino' : 'Día del Reino';
    for (final Size tamano in tamanos) {
      testWidgets(
        'la galería se pinta sin desbordes · $tema · '
        '${tamano.width.round()}×${tamano.height.round()}',
        (WidgetTester tester) async {
          await tester.binding.setSurfaceSize(tamano);
          addTearDown(() => tester.binding.setSurfaceSize(null));

          final ControladorTema controlador = ControladorTema(
            inicial: oscuro ? ThemeMode.dark : ThemeMode.light,
          );
          addTearDown(controlador.dispose);

          for (final double escala in escalas) {
            await tester.pumpWidget(
              ChangeNotifierProvider<ControladorTema>.value(
                value: controlador,
                child: MaterialApp(
                  theme: oscuro ? AteneaTheme.oscuro() : AteneaTheme.claro(),
                  debugShowCheckedModeBanner: false,
                  home: MediaQuery(
                    data: MediaQueryData(
                      size: tamano,
                      textScaler: TextScaler.linear(escala),
                    ),
                    child: const PantallaGaleriaEstilo(),
                  ),
                ),
              ),
            );
            await tester.pump();
            await tester.pump(const Duration(milliseconds: 600));

            expect(
              tester.takeException(),
              isNull,
              reason: 'Escala $escala en $tema a ${tamano.width.round()} dp',
            );
            expect(find.text('Crónica luminosa'), findsOneWidget);
          }
        },
      );
    }
  }
}
