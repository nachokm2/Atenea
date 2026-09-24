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

// Generaliza `_rutaDeLaImagen` a la estructura ilustrada de una parada: cada
// `_ParadaSpike` lleva la clave `ValueKey('parada-$indice')`
// (`_MundoState.build()`), y adentro de ella hay como máximo una `Image` —
// la de la estructura; el círculo pinta un `Icon`, no una `Image`. Lee la
// ruta pedida sin que el archivo tenga que existir: `Image.asset` guarda su
// `AssetImage` de configuración aunque el `errorBuilder` haya reemplazado lo
// que en verdad se pintó (mismo principio que ya usa `_rutaDeLaImagen`).
String? _rutaDeEstructuraEnParada(WidgetTester tester, int indice) {
  final Finder estructuras = find.descendant(
    of: find.byKey(ValueKey<String>('parada-$indice')),
    matching: find.byType(Image),
  );
  if (estructuras.evaluate().isEmpty) return null;
  final Image imagen = tester.widget<Image>(estructuras);
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

    // Módulo 3 (índice 2) es `EstiloNodo.enConstruccion` en el detalle de
    // ejemplo — no bloqueada (el Reino sigue escribiendo su contenido, pero
    // ya se puede pisar), así que sigue sin aviso aunque ya no sea la
    // última parada alcanzable (esa es el Módulo 4, índice 3).
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

    // Módulo 5 (índice 4) es el primer `locked` del detalle de ejemplo, pero
    // cae fuera del viewport inicial — hay que desplazar la cámara primero.
    await tester.ensureVisible(find.bySemanticsLabel('Módulo 5'));
    await tester.pump();
    await tester.tap(find.bySemanticsLabel('Módulo 5'));
    await tester.pump(Movimiento.corta);
    await tester.pump(Movimiento.corta);

    expect(
      find.text('Completa el módulo 4 para desbloquear'),
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

  testWidgets(
      'cada EstiloNodo (y el tesoro) piden un archivo de estructura propio y '
      'distinto — protege el mapeo de `_rutaDeEstructura` de un caso que se '
      'cae del switch o de dos estados que colapsan al mismo archivo',
      (WidgetTester tester) async {
    await _montar(tester);
    // Módulo 5 (índice 4, bloqueado — ver `_detalleDeEjemplo`) cae fuera del
    // viewport inicial. `find.byKey` no necesita que el widget esté visible
    // en pantalla (`SingleChildScrollView` monta su único hijo entero), pero
    // desplazar igual documenta por qué esta prueba no es frágil ante ese
    // detalle.
    await tester.ensureVisible(find.bySemanticsLabel('Módulo 5'));
    await tester.pump();

    // Índices 0 a 4: completado, actual, enConstruccion, disponible,
    // bloqueado — los cinco `EstiloNodo`, uno por índice, tal como los arma
    // `_detalleDeEjemplo`.
    final Map<int, String> rutaPorIndice = <int, String>{
      for (final int i in <int>[0, 1, 2, 3, 4])
        i: _rutaDeEstructuraEnParada(tester, i) ??
            (throw StateError(
              'la parada $i no pinta ninguna Image de estructura — '
              '¿_ParadaSpike dejó de componerla?',
            )),
    };

    expect(
      rutaPorIndice.values.toSet().length,
      5,
      reason: 'dos EstiloNodo distintos están pidiendo el mismo archivo de '
          'estructura: $rutaPorIndice',
    );

    // El tesoro (índice 6 con los 6 módulos por defecto) no es un caso más
    // del switch de `EstiloNodo` — tiene su propio archivo aunque, como acá,
    // su `EstiloNodo` subyacente (bloqueado, la Ruta no está completa)
    // coincida con el de otra parada.
    final String? rutaTesoro = _rutaDeEstructuraEnParada(tester, 6);
    expect(rutaTesoro, isNotNull);
    expect(
      rutaPorIndice.values.contains(rutaTesoro),
      isFalse,
      reason: 'el tesoro debe pedir su propio archivo, no el de '
          '`EstiloNodo.bloqueado`',
    );

    // Con arte real ya wireado, las seis `Image.asset` resuelven — y aunque
    // no resolvieran (una combinación futura sin arte), el `errorBuilder`
    // nunca debe filtrarse como una excepción de prueba.
    expect(tester.takeException(), isNull);
  });

  testWidgets(
      'la caja de la estructura es cuadrada, no un rectángulo angosto',
      (WidgetTester tester) async {
    // Rodrigo, en el teléfono: "el personaje se ve más grande que las
    // estructuras, se ve raro que sea más grande que un castillo". Mismo
    // bug que ya se encontró y arregló para `Caminante`
    // (`caminante_test.dart`, "la caja es cuadrada..."): el lienzo maestro
    // del arte es cuadrado (1024×1024), y una caja de despliegue más
    // angosta que alta hace que `BoxFit.contain` la encoja al lado corto.
    await _montar(tester);

    final Finder estructura = find.descendant(
      of: find.byKey(const ValueKey<String>('parada-0')),
      matching: find.byType(SizedBox),
    );
    // Dos `SizedBox` bajo la parada 0: el de layout (56×56, el círculo) y el
    // de la estructura — el de la estructura es el que no mide 56×56.
    final SizedBox caja = tester
        .widgetList<SizedBox>(estructura)
        .firstWhere((SizedBox s) => s.width != 56);

    expect(caja.width, caja.height,
        reason: 'la caja de la estructura tiene que ser cuadrada, para que '
            'BoxFit.contain no encoja el lienzo 1024×1024 al lado corto');
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
