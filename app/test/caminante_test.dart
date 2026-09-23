/// `Caminante`: reposo y marcha, con el pintor de mentira de la Fase B.
///
/// El fotograma en sí ya está probado en `ciclo_marcha_test.dart` (puro).
/// Lo que este archivo prueba es lo que solo se ve montando el widget de
/// verdad: que el fotograma que llega al pintor viene de la distancia
/// recorrida y no de la fase del reloj, que el reposo tiene su propio loop
/// independiente, y que el espejo/anclaje de `CaminanteEnSenda` hacen lo que
/// dicen. Ver `docs/planes/mundo-caminable.md`, Fase B.
library;

import 'package:atenea/pantallas/aventura/mundo/caminante.dart';
import 'package:atenea/pantallas/aventura/mundo/ciclo_marcha.dart';
import 'package:atenea/pantallas/aventura/mundo/figura_del_mundo.dart';
import 'package:atenea/datos/dtos.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

const FiguraDelMundo _figura = FiguraDelMundo(familia: 'masculino', arquetipo: Arquetipo.acero);

PintorDeCaminanteDeMentira _pintorDe(WidgetTester tester) {
  final Finder buscado = find.byWidgetPredicate(
    (Widget w) => w is CustomPaint && w.painter is PintorDeCaminanteDeMentira,
  );
  return tester.widget<CustomPaint>(buscado).painter! as PintorDeCaminanteDeMentira;
}

void main() {
  group('en reposo (avance nulo)', () {
    testWidgets('corre varios ciclos de reloj sin lanzar', (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(home: Caminante(ciclo: CicloDeMarcha(_figura))),
      );
      await tester.pump();
      for (int i = 0; i < 8; i++) {
        await tester.pump(const Duration(milliseconds: 200));
      }
      expect(tester.takeException(), isNull);
    });

    testWidgets('se pinta como "en reposo", nunca como "en marcha"', (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(home: Caminante(ciclo: CicloDeMarcha(_figura))),
      );
      await tester.pump();
      for (int i = 0; i < 5; i++) {
        await tester.pump(const Duration(milliseconds: 300));
        expect(_pintorDe(tester).enMarcha, isFalse);
      }
    });

    testWidgets('el fotograma de reposo cambia solo por el reloj propio, en loop',
        (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(home: Caminante(ciclo: CicloDeMarcha(_figura))),
      );
      await tester.pump();
      final int primero = _pintorDe(tester).fotograma;

      // A mitad del período del loop de reposo (1400ms), tiene que haber
      // cambiado al otro de los dos fotogramas.
      await tester.pump(const Duration(milliseconds: 700));
      expect(_pintorDe(tester).fotograma, isNot(primero));

      // Y a la otra mitad —una vuelta completa desde el inicio—, vuelve al
      // mismo: 700 + 700 = 1400, el período entero del loop.
      await tester.pump(const Duration(milliseconds: 700));
      expect(_pintorDe(tester).fotograma, primero);
    });
  });

  group('en marcha (avance no nulo)', () {
    testWidgets('el fotograma sale de la distancia recorrida, no de la fase del reloj',
        (WidgetTester tester) async {
      // Un tramo largo: a fase 0.5 del reloj, la distancia recorrida (con
      // easeInOutCubic) NO es la mitad del tramo — si el fotograma dependiera
      // de la fase y no de la distancia, este caso no lo distinguiría. Se
      // arma el `avance` a mano en vez de animar, para fijar una distancia
      // exacta y comparar contra `CicloDeMarcha.fotogramaPorDistancia` puro.
      const double longitud = dpPorFotogramaDeMarcha * 3.2; // cae en el fotograma 3
      final CicloDeMarcha ciclo = CicloDeMarcha(_figura);
      final AnimationController control = AnimationController(vsync: tester, value: 1.0);
      addTearDown(control.dispose);

      await tester.pumpWidget(
        MaterialApp(
          home: Caminante(ciclo: ciclo, avance: control, longitudDelTramo: longitud),
        ),
      );
      await tester.pump();

      final int esperado = ciclo.fotogramaPorDistancia(longitud);
      expect(_pintorDe(tester).fotograma, esperado);
      expect(_pintorDe(tester).enMarcha, isTrue);
    });

    testWidgets('a mitad de tramo, el fotograma es el que toca a esa distancia exacta',
        (WidgetTester tester) async {
      const double longitud = dpPorFotogramaDeMarcha * 5;
      final CicloDeMarcha ciclo = CicloDeMarcha(_figura);
      final AnimationController control = AnimationController(vsync: tester, value: 0.5);
      addTearDown(control.dispose);

      await tester.pumpWidget(
        MaterialApp(
          home: Caminante(ciclo: ciclo, avance: control, longitudDelTramo: longitud),
        ),
      );
      await tester.pump();

      expect(_pintorDe(tester).fotograma, ciclo.fotogramaPorDistancia(longitud * 0.5));
    });
  });

  group('CaminanteEnSenda', () {
    testWidgets('ancla al caminante en los pies del punto, no en su centro',
        (WidgetTester tester) async {
      const Offset destino = Offset(200, 200);
      final AnimationController control = AnimationController(vsync: tester, value: 1.0);
      addTearDown(control.dispose);

      await tester.pumpWidget(
        MaterialApp(
          home: Stack(
            children: <Widget>[
              CaminanteEnSenda(
                ciclo: CicloDeMarcha(_figura),
                origen: const Offset(100, 200),
                destino: destino,
                avance: control,
                alto: 120,
              ),
            ],
          ),
        ),
      );
      await tester.pump();

      final Rect zona = tester.getRect(find.byType(Caminante));
      // El punto del sendero (200,200) tiene que caer en el borde INFERIOR
      // del caminante — ahí están los pies — y centrado en x.
      expect(zona.bottom, closeTo(destino.dy, 0.5));
      expect(zona.center.dx, closeTo(destino.dx, 0.5));
    });

    testWidgets('mira a la derecha cuando el destino queda a la derecha del origen',
        (WidgetTester tester) async {
      final AnimationController control = AnimationController(vsync: tester, value: 0.5);
      addTearDown(control.dispose);
      await tester.pumpWidget(
        MaterialApp(
          home: Stack(
            children: <Widget>[
              CaminanteEnSenda(
                ciclo: CicloDeMarcha(_figura),
                origen: const Offset(50, 100),
                destino: const Offset(250, 100),
                avance: control,
              ),
            ],
          ),
        ),
      );
      await tester.pump();

      final Transform espejo = tester.widget<Transform>(
        find.descendant(of: find.byType(Caminante), matching: find.byType(Transform)),
      );
      expect(espejo.transform.getColumn(0).x, greaterThan(0), reason: 'sin espejar: mira a la derecha');
    });

    testWidgets('mira a la izquierda cuando el destino queda a la izquierda del origen',
        (WidgetTester tester) async {
      final AnimationController control = AnimationController(vsync: tester, value: 0.5);
      addTearDown(control.dispose);
      await tester.pumpWidget(
        MaterialApp(
          home: Stack(
            children: <Widget>[
              CaminanteEnSenda(
                ciclo: CicloDeMarcha(_figura),
                origen: const Offset(250, 100),
                destino: const Offset(50, 100),
                avance: control,
              ),
            ],
          ),
        ),
      );
      await tester.pump();

      final Transform espejo = tester.widget<Transform>(
        find.descendant(of: find.byType(Caminante), matching: find.byType(Transform)),
      );
      expect(espejo.transform.getColumn(0).x, lessThan(0), reason: 'espejado: mira a la izquierda');
    });
  });
}
