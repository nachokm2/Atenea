/// Prueba de la cola de celebraciones (§5.3 del documento de UX y §7.10 del
/// contrato).
///
/// Lo que se verifica, que es la regla más fácil de romper del cliente:
///
/// 1. **`presentation_order` manda.** El recibo de esta prueba trae un orden
///    deliberadamente distinto al canónico; la cola debe respetarlo al pie de
///    la letra y no reordenar nada por su cuenta.
/// 2. **Como máximo tres overlays**, uno detrás de otro, nunca dos a la vez.
/// 3. El resto de los pasos se entrega **como chips** para P10 y P12.
/// 4. Ninguna celebración bloquea más de 2,4 s, y un toque siempre salta.
/// 5. La app **no calcula nada**: las cifras que se pintan son literalmente
///    las del recibo.
library;

import 'package:atenea/design/theme.dart';
import 'package:atenea/estado/celebraciones.dart';
import 'package:atenea/estado/personaje.dart';
import 'package:atenea/navegacion/armazon.dart';
import 'package:atenea/pantallas/celebraciones/overlays.dart';
import 'package:fake_async/fake_async.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:provider/single_child_widget.dart';

import 'ayudas.dart';

/// Recibo de ejemplo con las claves literales del contrato (§7.10).
///
/// El `presentation_order` pone el **ítem antes que la racha y que el nivel**,
/// justo al revés del orden canónico. Si la cola presentara el orden canónico
/// esta prueba fallaría: ahí está su valor.
Map<String, dynamic> _reciboDePrueba() => <String, dynamic>{
      'receipt_id': 'rec-001',
      'event_type': 'LESSON_COMPLETED',
      'occurred_at': '2026-09-10T02:58:41Z',
      'config_version': 17,
      'xp': <String, dynamic>{
        'amount': 80,
        'base_amount': 50,
        'activity_xp': 50,
        'question_xp': 30,
        'multiplier': 1.0,
        'reason_code': 'first_completion',
        'is_educational': true,
        'total_after': 12890,
      },
      'gold': <String, dynamic>{
        'amount': 20,
        'balance_after': 1245,
        'reason_code': 'first_completion',
      },
      'level': <String, dynamic>{
        'before': 6,
        'after': 7,
        'leveled_up': true,
        'rank_title_before': 'Iniciado/a',
        'rank_title_after': 'Aprendiz del Reino',
        'rank_changed': true,
        'xp_to_next': 1360,
        'progress_pct': 4.2,
        'gold_bonus': 50,
        'unlocked_shop_rarities': <String>['raro'],
      },
      'mastery_deltas': <Map<String, dynamic>>[
        <String, dynamic>{
          'scope': 'topic',
          'id': 't-1',
          'name': 'JOINs',
          'before': 63.0,
          'after': 71.0,
          'status': 'in_progress',
        },
      ],
      'streak': <String, dynamic>{
        'current': 8,
        'best': 12,
        'change': 'extended',
        'day_status': 'active',
        'is_first_activity_of_day': true,
        'milestone': null,
      },
      'missions': <Map<String, dynamic>>[
        <String, dynamic>{
          'user_mission_id': 'm-1',
          'template_code': 'D01',
          'title': 'Completa 2 lecciones',
          'progress': 2,
          'target': 2,
          'status': 'completed',
          'auto_claimed': false,
          'reward': <String, dynamic>{'xp': 100, 'gold': 25},
        },
      ],
      'achievements': <Map<String, dynamic>>[
        <String, dynamic>{
          'code': 'ACH_ORACLE',
          'name': 'Oráculo',
          'tier': 'silver',
          'reward': <String, dynamic>{'xp': 75, 'gold': 60},
        },
      ],
      'items': <Map<String, dynamic>>[
        <String, dynamic>{
          'user_item_id': 'ui-1',
          'item_code': 'pluma_primer_paso',
          'name': 'Pluma del Primer Paso',
          'slot': 'accessory',
          'rarity': 'rare',
          'origin': 'achievement',
          'unlock_reason': 'Completaste tu primera lección',
          'can_equip': true,
        },
      ],
      'unlocks': <Map<String, dynamic>>[],
      'assessment_result': null,
      // Orden deliberadamente NO canónico: el ítem va primero.
      'presentation_order': <String>[
        'item',
        'streak',
        'level_up',
        'xp',
        'gold',
        'mastery',
        'achievement',
        'mission',
      ],
      'pending_sync': false,
    };

void main() {
  setUp(prepararTipografias);

  group('ColaCelebraciones', () {
    test('respeta el presentation_order del servidor, no el canónico', () {
      final ReciboRecompensas recibo =
          ReciboRecompensas.desdeJson(_reciboDePrueba());

      // El recibo ya sabe qué pasos tienen contenido y en qué orden.
      expect(
        recibo.overlays,
        <PasoCelebracion>[
          PasoCelebracion.item,
          PasoCelebracion.racha,
          PasoCelebracion.subidaNivel,
        ],
        reason: 'El servidor pidió el ítem primero; el cliente no reordena.',
      );
      expect(recibo.overlays.length, lessThanOrEqualTo(3));
      expect(
        recibo.chips,
        <PasoCelebracion>[
          PasoCelebracion.xp,
          PasoCelebracion.oro,
          PasoCelebracion.dominio,
          PasoCelebracion.logro,
          PasoCelebracion.mision,
        ],
      );

      final ColaCelebraciones cola = ColaCelebraciones()..encolar(recibo);
      addTearDown(cola.dispose);

      expect(cola.pendientes, 3);
      expect(cola.actual?.paso, PasoCelebracion.item);
      cola.descartar();
      expect(cola.actual?.paso, PasoCelebracion.racha);
      cola.descartar();
      expect(cola.actual?.paso, PasoCelebracion.subidaNivel);
      cola.descartar();
      expect(cola.actual, isNull);
      expect(cola.hayPendientes, isFalse);

      // Los chips sobreviven al vaciado de los overlays: P10 y P12 los pintan.
      expect(
        cola.chips.map((Celebracion c) => c.paso).toList(),
        containsAllInOrder(<PasoCelebracion>[
          PasoCelebracion.xp,
          PasoCelebracion.oro,
          PasoCelebracion.dominio,
        ]),
      );
      expect(cola.ultimoRecibo?.id, 'rec-001');
    });

    test('ninguna celebración bloquea más de 2,4 s y el toque salta', () {
      fakeAsync((FakeAsync reloj) {
        final ColaCelebraciones cola = ColaCelebraciones()
          ..encolar(ReciboRecompensas.desdeJson(_reciboDePrueba()));

        expect(cola.listaParaContinuar, isFalse);
        reloj.elapse(ColaCelebraciones.limiteBloqueo);
        expect(
          cola.listaParaContinuar,
          isTrue,
          reason: 'Pasado el tope la celebración libera al usuario.',
        );

        cola.descartar();
        expect(cola.listaParaContinuar, isFalse);
        // Un toque salta la animación sin esperar.
        cola.saltarAnimacion();
        expect(cola.listaParaContinuar, isTrue);

        cola.dispose();
      });
    });

    test('con movimiento reducido la celebración nace lista y sin duración',
        () {
      final ColaCelebraciones cola =
          ColaCelebraciones(movimientoReducido: true)
            ..encolar(ReciboRecompensas.desdeJson(_reciboDePrueba()));
      addTearDown(cola.dispose);

      expect(cola.listaParaContinuar, isTrue);
      expect(cola.actual?.duracion, Duration.zero);
    });

    test('un recibo sin nada que celebrar no encola nada', () {
      final ColaCelebraciones cola = ColaCelebraciones();
      addTearDown(cola.dispose);

      cola.encolar(null);
      expect(cola.hayPendientes, isFalse);

      cola.encolar(
        ReciboRecompensas.desdeJson(<String, dynamic>{
          'receipt_id': 'vacio',
          'presentation_order': <String>['xp', 'gold'],
        }),
      );
      expect(cola.hayPendientes, isFalse);
      expect(cola.chips, isEmpty);
    });
  });

  testWidgets(
    'la capa de celebraciones presenta los overlays en el orden del recibo',
    (WidgetTester tester) async {
      final ColaCelebraciones cola = ColaCelebraciones();
      final ControladorPersonaje personaje = ControladorPersonaje(
        repositoriosDePrueba(AlmacenTokensFalso()),
      );
      addTearDown(cola.dispose);
      addTearDown(personaje.dispose);

      await tester.pumpWidget(
        MultiProvider(
          providers: <SingleChildWidget>[
            ChangeNotifierProvider<ColaCelebraciones>.value(value: cola),
            ChangeNotifierProvider<ControladorPersonaje>.value(
              value: personaje,
            ),
          ],
          child: MaterialApp(
            theme: AteneaTheme.oscuro(),
            debugShowCheckedModeBanner: false,
            home: CapaCelebraciones(
              hijo: const Scaffold(body: Center(child: Text('El Reino'))),
              constructor: constructorDeCelebracion,
            ),
          ),
        ),
      );
      await tester.pump();

      // Antes del recibo no hay ningún overlay encima de la pantalla.
      expect(find.text('El Reino'), findsOneWidget);
      expect(find.text('NUEVO EQUIPAMIENTO'), findsNothing);

      cola.encolar(ReciboRecompensas.desdeJson(_reciboDePrueba()));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));

      // 1 · P14, el ítem: el servidor lo pidió primero.
      expect(find.text('NUEVO EQUIPAMIENTO'), findsOneWidget);
      expect(find.text('Pluma del Primer Paso'), findsOneWidget);
      // Nunca dos celebraciones a la vez.
      expect(find.text('SUBISTE DE NIVEL'), findsNothing);
      expect(find.text('RACHA'), findsNothing);

      // Pasado el tope, el toque cierra en vez de saltar.
      await tester.pump(ColaCelebraciones.limiteBloqueo);
      await tester.tap(find.text('Guardar en el Vestidor'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));

      // 2 · La racha, con los días y la mejor marca que mandó el servidor.
      expect(find.text('RACHA'), findsOneWidget);
      expect(
        find.text('8'),
        findsOneWidget,
        reason: 'La cifra sale del recibo, la app no la calcula.',
      );
      expect(find.text(' días'), findsOneWidget);
      // `Pildora` compone icono y texto en un solo `Text.rich`.
      expect(
        find.textContaining('Tu mejor marca: 12 días', findRichText: true),
        findsOneWidget,
      );
      expect(find.text('NUEVO EQUIPAMIENTO'), findsNothing);

      await tester.pump(ColaCelebraciones.limiteBloqueo);
      await tester.tap(find.text('Continuar'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));

      // 3 · P13, con cambio de rango: no es lo mismo que subir de nivel
      // dentro del mismo rango, y el modal lo distingue en vez de decir
      // siempre "SUBISTE DE NIVEL".
      expect(find.text('¡NUEVO RANGO!'), findsOneWidget);
      expect(find.text('SUBISTE DE NIVEL'), findsNothing);
      expect(find.text('Iniciado/a → Aprendiz del Reino'), findsOneWidget);
      expect(
        find.textContaining('+50 de oro', findRichText: true),
        findsOneWidget,
      );

      await tester.pump(ColaCelebraciones.limiteBloqueo);
      await tester.tap(find.text('Seguir'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));

      // Se acabó la cola: vuelve a verse el Reino, sin overlays.
      expect(find.text('El Reino'), findsOneWidget);
      expect(find.text('¡NUEVO RANGO!'), findsNothing);
      expect(cola.hayPendientes, isFalse);
    },
  );
}
