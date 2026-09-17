/// El interruptor «Vibración» de Ajustes apaga la vibración de verdad.
///
/// Durante meses no lo hacía, y el modo en que fallaba es el que importa aquí:
/// no estaba desconectado por descuido en un sitio, es que **nunca hubo
/// conexión**. `hapticaActivada` viajaba entero por las cuatro capas del
/// cliente —el DTO lo leía, el repositorio lo mandaba, la sesión lo guardaba y
/// la pantalla lo pintaba— y ninguna de las diez llamadas a `HapticFeedback`
/// lo consultaba jamás. El aprendiz apagaba el interruptor y el móvil seguía
/// vibrando exactamente igual.
///
/// Ninguna prueba lo notó, y no por mala suerte: las 83 que había comprobaban
/// que el valor se guardara y se pintara, que es justo la mitad que sí
/// funcionaba. Un ajuste que se guarda y nadie lee pasa todas las pruebas de
/// ida y ninguna de vuelta.
///
/// Por eso aquí hay dos pruebas de naturaleza distinta. La primera comprueba el
/// comportamiento: con el interruptor apagado, el canal de plataforma no recibe
/// nada. La segunda vigila la forma del código: que nadie vuelva a llamar a
/// `HapticFeedback` por la puerta de atrás. La primera protege lo que hay hoy;
/// la segunda protege lo que se escriba mañana, que es donde se perdió la
/// conexión la vez anterior.
library;

import 'dart:io';

import 'package:atenea/design/components.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  /// Lo que el canal de plataforma recibió desde que empezó la prueba.
  ///
  /// `HapticFeedback.selectionClick()` y sus hermanas no hacen nada más que
  /// invocar `HapticFeedback.vibrate` en `SystemChannels.platform`, así que
  /// escuchar ahí es escuchar al motor de vibración.
  late List<String> vibraciones;

  setUp(() {
    vibraciones = <String>[];
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(SystemChannels.platform,
            (MethodCall llamada) async {
      if (llamada.method == 'HapticFeedback.vibrate') {
        vibraciones.add('${llamada.arguments}');
      }
      return null;
    });
  });

  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(SystemChannels.platform, null);
  });

  /// Una tarjeta que se puede tocar, con o sin la preferencia por encima.
  Future<void> pintarTarjeta(WidgetTester tester, {bool? tacto}) async {
    const Widget tarjeta = TarjetaAtenea(
      alTocar: _noHaceNada,
      hijo: Text('Tócame'),
    );
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: tacto == null
              ? tarjeta
              : PreferenciasDeTacto(activa: tacto, child: tarjeta),
        ),
      ),
    );
  }

  group('el interruptor manda', () {
    testWidgets('encendido, el móvil vibra', (WidgetTester tester) async {
      await pintarTarjeta(tester, tacto: true);
      await tester.tap(find.text('Tócame'));
      await tester.pump();

      expect(vibraciones, <String>['HapticFeedbackType.selectionClick']);
    });

    testWidgets('apagado, el móvil calla', (WidgetTester tester) async {
      await pintarTarjeta(tester, tacto: false);
      await tester.tap(find.text('Tócame'));
      await tester.pump();

      expect(vibraciones, isEmpty);
    });

    testWidgets('sin ajustes todavía, vibra', (WidgetTester tester) async {
      // El acceso y la creación del héroe ocurren antes de que haya ajustes que
      // consultar. Ahí el comportamiento correcto es el de siempre: vibrar.
      await pintarTarjeta(tester);
      await tester.tap(find.text('Tócame'));
      await tester.pump();

      expect(vibraciones, <String>['HapticFeedbackType.selectionClick']);
    });
  });

  test('nadie llama a HapticFeedback por la puerta de atrás', () {
    /// Los dos únicos sitios donde la llamada directa es legítima.
    ///
    /// `components.dart` porque es quien define `Tacto`, que es la puerta. Y
    /// `marco_celebracion.dart` porque vibra dentro de un `addPostFrameCallback`
    /// —cuando la celebración ya se pintó— y para entonces el `context` puede
    /// estar desmontado; allí la preferencia se consulta antes, en `build`, y
    /// eso el análisis de texto no puede verlo.
    const Set<String> permitidos = <String>{
      'lib/design/components.dart',
      'lib/pantallas/celebraciones/marco_celebracion.dart',
    };

    final List<String> infractores = <String>[];
    for (final FileSystemEntity entrada
        in Directory('lib').listSync(recursive: true)) {
      if (entrada is! File || !entrada.path.endsWith('.dart')) continue;
      final String ruta = entrada.path.replaceAll(r'\', '/');
      if (permitidos.contains(ruta)) continue;

      final List<String> lineas = entrada.readAsLinesSync();
      for (int i = 0; i < lineas.length; i++) {
        if (lineas[i].contains('HapticFeedback.')) {
          infractores.add('$ruta:${i + 1}');
        }
      }
    }

    expect(
      infractores,
      isEmpty,
      reason: 'Usa `Tacto.seleccion/ligero/medio(context)`, que pregunta al '
          'aprendiz. `HapticFeedback` directo vibra con el interruptor '
          'apagado, y así es como se rompió la última vez.',
    );
  });
}

void _noHaceNada() {}
