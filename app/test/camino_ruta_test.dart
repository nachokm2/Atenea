/// El camino de la Ruta: que los nodos existan y que digan la verdad.
///
/// Los dos huecos que esto cierra los encontró la revisión adversarial del
/// 18-09, y los dos eran del mismo tipo: **código que nadie ejecutaba en una
/// prueba**, porque vivía dentro de `_PantallaMapaRutaState` y montar esa
/// pantalla exige proveedor, enrutador y una llamada de red.
///
/// El coste estaba medido. Con `if (evaluacion != null && false)` —o sea, el
/// nodo de la prueba no se añade nunca al camino, que es literalmente el fallo
/// que se acababa de arreglar— las 178 pruebas del cliente seguían verdes. Y
/// con `_estiloDesafio` devolviendo siempre `EstiloNodo.disponible` —o sea,
/// `can_start`, `content_status` y `passed` dejando de significar nada— también.
///
/// Ahora esas dos piezas viven en `widgets/camino_ruta.dart` y se prueban
/// directamente: las reglas de estilo como funciones puras, y el camino
/// montándolo de verdad a partir del sobre que manda el servidor.
library;

import 'package:atenea/datos/dtos.dart';
import 'package:atenea/design/theme.dart';
import 'package:atenea/pantallas/aventura/widgets/camino_ruta.dart';
import 'package:atenea/pantallas/aventura/widgets/nodos_mapa.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'ayudas.dart';

// -------------------------------------------------------------------------
// Sobres del servidor
// -------------------------------------------------------------------------

Map<String, dynamic> _leccion(
  String id, {
  String estado = 'not_started',
  String contenido = 'ready',
}) =>
    <String, dynamic>{
      'lesson_id': id,
      'title': 'Lección $id',
      'position': 1,
      'status': estado,
      'content_status': contenido,
      'estimated_seconds': 540,
    };

Map<String, dynamic> _desafio({
  bool aprobada = false,
  bool puedeEmpezar = true,
  String contenido = 'ready',
  int intentosUsados = 0,
}) =>
    <String, dynamic>{
      'assessment_id': 'eval-1',
      'module_id': 'mod-1',
      'title': 'Prueba del Castillo',
      'question_count': 4,
      'pass_score': 80.0,
      'max_attempts_per_day': 3,
      'content_status': contenido,
      'attempts_used': intentosUsados,
      'best_score': null,
      'passed': aprobada,
      'can_start': puedeEmpezar,
      'cooldown_until': null,
    };

Map<String, dynamic> _modulo(
  String id, {
  String estado = 'in_progress',
  String contenido = 'ready',
  Map<String, dynamic>? desafio,
  List<Map<String, dynamic>>? lecciones,
  int leccionesCompletadas = 0,
}) {
  final List<Map<String, dynamic>> ls = lecciones ?? <Map<String, dynamic>>[];
  return <String, dynamic>{
    'module_id': id,
    'title': 'Módulo $id',
    'position': 1,
    'status': estado,
    'content_status': contenido,
    'lessons_total': ls.length,
    'lessons_completed': leccionesCompletadas,
    'mastery': 0.0,
    'assessment_best_score': null,
    'assessment_passed': false,
    'assessment': desafio,
    'topics': <Map<String, dynamic>>[
      <String, dynamic>{
        'topic_id': 'tema-$id',
        'module_id': id,
        'title': 'Tema de $id',
        'position': 1,
        'lessons': ls,
      },
    ],
  };
}

DetalleRuta _ruta(List<Map<String, dynamic>> modulos, {String estado = 'active'}) =>
    DetalleRuta.desdeJson(<String, dynamic>{
      'path': <String, dynamic>{
        'path_id': 'ruta-1',
        'title': 'El Castillo de las Consultas',
        'status': estado,
      },
      'status': estado,
      'modules': modulos,
    });

// -------------------------------------------------------------------------
// Montaje
// -------------------------------------------------------------------------

/// Monta el camino entero.
///
/// **Con `pump()`, nunca `pumpAndSettle()`.** El nodo del módulo actual usa
/// `PulsoSuave`, que llama a `_control.repeat(reverse: true)`
/// (`comunes_aventura.dart:298`): una animación sin fin que deja a
/// `pumpAndSettle` esperando para siempre, sin mensaje. Un solo fotograma basta
/// para comprobar qué nodos existen.
Future<List<String>> _montar(
  WidgetTester tester,
  DetalleRuta detalle, {
  bool abierto = true,
}) async {
  final List<String> tocados = <String>[];
  await tester.binding.setSurfaceSize(const Size(412, 915));
  addTearDown(() => tester.binding.setSurfaceSize(null));
  await tester.pumpWidget(
    MaterialApp(
      theme: AteneaTheme.oscuro(),
      home: Scaffold(
        body: SingleChildScrollView(
          child: CaminoDeLaRuta(
            detalle: detalle,
            expandido: (ModuloRuta _) => abierto,
            alTocarModulo: (ModuloRuta m) => tocados.add('modulo:${m.id}'),
            alTocarLeccion: (ModuloRuta _, ResumenLeccion l, EstiloNodo _) =>
                tocados.add('leccion:${l.id}'),
            alTocarDesafio:
                (ModuloRuta _, ResumenEvaluacion e, EstiloNodo estilo) =>
                    tocados.add('desafio:${e.id}:${estilo.name}'),
            alVerLaForja: () => tocados.add('forja'),
          ),
        ),
      ),
    ),
  );
  await tester.pump();
  return tocados;
}

void main() {
  setUp(prepararTipografias);

  // -----------------------------------------------------------------------
  // El nodo existe en el camino
  // -----------------------------------------------------------------------

  testWidgets('el módulo con prueba pinta su nodo de prueba',
      (WidgetTester tester) async {
    // La mutación que sobrevivía a las 178 pruebas anteriores:
    // `if (evaluacion != null && false)`.
    await _montar(
      tester,
      _ruta(<Map<String, dynamic>>[
        _modulo('mod-1', desafio: _desafio(), lecciones: <Map<String, dynamic>>[
          _leccion('lec-1'),
        ]),
      ]),
    );

    expect(find.byType(ContenidoDesafio), findsOneWidget);
    expect(find.text('Prueba del Castillo'), findsOneWidget);
  });

  testWidgets('el módulo sin prueba no inventa el nodo',
      (WidgetTester tester) async {
    await _montar(
      tester,
      _ruta(<Map<String, dynamic>>[
        _modulo('mod-1', lecciones: <Map<String, dynamic>>[_leccion('lec-1')]),
      ]),
    );

    expect(find.byType(ContenidoLeccion), findsOneWidget);
    expect(find.byType(ContenidoDesafio), findsNothing);
  });

  testWidgets('cada módulo lleva su prueba, y van después de sus lecciones',
      (WidgetTester tester) async {
    await _montar(
      tester,
      _ruta(<Map<String, dynamic>>[
        _modulo('mod-1',
            desafio: _desafio(), lecciones: <Map<String, dynamic>>[_leccion('a')]),
        _modulo('mod-2',
            desafio: _desafio(), lecciones: <Map<String, dynamic>>[_leccion('b')]),
      ]),
    );

    expect(find.byType(ContenidoDesafio), findsNWidgets(2));

    // El orden es parte de lo que se prueba: la prueba remata el módulo, así
    // que va debajo de sus lecciones y encima del módulo siguiente.
    final double leccionA = tester.getCenter(find.text('Lección a')).dy;
    final double desafio1 = tester.getCenter(find.byType(ContenidoDesafio).first).dy;
    final double modulo2 = tester.getCenter(find.text('Módulo mod-2')).dy;
    expect(leccionA, lessThan(desafio1));
    expect(desafio1, lessThan(modulo2));
  });

  testWidgets('con el módulo plegado no se cuelan ni lecciones ni prueba',
      (WidgetTester tester) async {
    await _montar(
      tester,
      _ruta(<Map<String, dynamic>>[
        _modulo('mod-1',
            desafio: _desafio(), lecciones: <Map<String, dynamic>>[_leccion('a')]),
      ]),
      abierto: false,
    );

    expect(find.byType(ContenidoModulo), findsOneWidget);
    expect(find.byType(ContenidoLeccion), findsNothing);
    expect(find.byType(ContenidoDesafio), findsNothing);
  });

  testWidgets('el camino siempre termina en el tesoro',
      (WidgetTester tester) async {
    await _montar(tester, _ruta(<Map<String, dynamic>>[_modulo('mod-1')]));

    expect(find.byType(ContenidoTesoro), findsOneWidget);
  });

  testWidgets('una ruta sin módulos ofrece ver la forja, no un camino vacío',
      (WidgetTester tester) async {
    final List<String> tocados =
        await _montar(tester, _ruta(<Map<String, dynamic>>[]));

    expect(find.byType(ContenidoModulo), findsNothing);
    expect(find.text('El camino aún no está trazado'), findsOneWidget);

    await tester.tap(find.text('Ver el avance de la forja'));
    expect(tocados, <String>['forja']);
  });

  testWidgets('tocar la prueba avisa con el estilo con el que se pintó',
      (WidgetTester tester) async {
    // El estilo viaja al manejador: de ahí sale el diálogo que explica el
    // bloqueo. Si se pintara con un estilo y se avisara con otro, el aprendiz
    // vería un nodo apagado y un mensaje que no le corresponde.
    final List<String> tocados = await _montar(
      tester,
      _ruta(<Map<String, dynamic>>[
        _modulo(
          'mod-1',
          desafio: _desafio(puedeEmpezar: false, intentosUsados: 3),
          lecciones: <Map<String, dynamic>>[_leccion('a')],
        ),
      ]),
    );

    await tester.tap(find.byType(ContenidoDesafio));
    expect(tocados, <String>['desafio:eval-1:bloqueado']);
  });

  // -----------------------------------------------------------------------
  // Las reglas de estilo, que son puras
  // -----------------------------------------------------------------------

  group('estiloDeDesafio traduce el sobre a lo que se ve', () {
    ModuloRuta modulo({
      String estado = 'in_progress',
      int total = 2,
      int hechas = 0,
    }) =>
        ModuloRuta.desdeJson(<String, dynamic>{
          'module_id': 'mod-1',
          'title': 'Módulo',
          'status': estado,
          'content_status': 'ready',
          'lessons_total': total,
          'lessons_completed': hechas,
          'topics': <dynamic>[],
        });

    ResumenEvaluacion evaluacion({
      bool aprobada = false,
      bool puedeEmpezar = true,
      String contenido = 'ready',
    }) =>
        ResumenEvaluacion.desdeJson(_desafio(
          aprobada: aprobada,
          puedeEmpezar: puedeEmpezar,
          contenido: contenido,
        ));

    test('aprobada gana a todo lo demás', () {
      expect(
        estiloDeDesafio(modulo(estado: 'locked'), evaluacion(aprobada: true)),
        EstiloNodo.completado,
      );
    });

    test('el módulo bloqueado cierra la prueba', () {
      expect(
        estiloDeDesafio(modulo(estado: 'locked'), evaluacion()),
        EstiloNodo.bloqueado,
      );
    });

    test('un banco de preguntas a medio escribir se pinta en construcción', () {
      expect(
        estiloDeDesafio(modulo(), evaluacion(contenido: 'generating')),
        EstiloNodo.enConstruccion,
      );
    });

    test('sin autorización del servidor queda bloqueada', () {
      // `can_start` en falso: enfriamiento o cupo agotado. Son frenos de la
      // prueba, no del módulo, y por eso el módulo sigue en progreso.
      expect(
        estiloDeDesafio(modulo(), evaluacion(puedeEmpezar: false)),
        EstiloNodo.bloqueado,
      );
    });

    test('con las lecciones terminadas late; con lecciones pendientes no', () {
      expect(
        estiloDeDesafio(modulo(total: 2, hechas: 2), evaluacion()),
        EstiloNodo.actual,
      );
      expect(
        estiloDeDesafio(modulo(total: 2, hechas: 1), evaluacion()),
        EstiloNodo.disponible,
      );
    });

    test('un módulo sin lecciones no promete que esté todo hecho', () {
      // `leccionesTotales > 0` está en la regla a propósito: sin él, un módulo
      // recién creado —cero de cero— pasaría por «todo listo» y el nodo
      // latiría invitando a una prueba que nadie ha preparado.
      expect(
        estiloDeDesafio(modulo(total: 0, hechas: 0), evaluacion()),
        EstiloNodo.disponible,
      );
    });
  });

  group('estiloDeModulo', () {
    DetalleRuta conModulo(Map<String, dynamic> m) =>
        _ruta(<Map<String, dynamic>>[m]);

    test('en construcción gana a disponible, y por eso content_status importa',
        () {
      // El orden de las comprobaciones es el fallo del 18-09: «en construcción»
      // se mira antes que «actual» y «disponible», así que un módulo cuyo
      // `content_status` no llegue arrastra a todo el resto.
      final DetalleRuta detalle =
          conModulo(_modulo('mod-1', contenido: 'generating'));
      expect(
        estiloDeModulo(detalle, detalle.modulos.first),
        EstiloNodo.enConstruccion,
      );

      final DetalleRuta listo = conModulo(_modulo('mod-1'));
      expect(
        estiloDeModulo(listo, listo.modulos.first),
        isNot(EstiloNodo.enConstruccion),
      );
    });

    test('completado y bloqueado se reconocen', () {
      final DetalleRuta hecho = conModulo(_modulo('mod-1', estado: 'completed'));
      expect(estiloDeModulo(hecho, hecho.modulos.first), EstiloNodo.completado);

      final DetalleRuta cerrado = conModulo(_modulo('mod-1', estado: 'locked'));
      expect(estiloDeModulo(cerrado, cerrado.modulos.first), EstiloNodo.bloqueado);
    });
  });

  group('estiloDeLeccion', () {
    ModuloRuta abierto() => ModuloRuta.desdeJson(_modulo('mod-1'));
    ModuloRuta cerrado() =>
        ModuloRuta.desdeJson(_modulo('mod-1', estado: 'locked'));

    test('completada, bloqueada, en construcción y la siguiente', () {
      final ResumenLeccion hecha =
          ResumenLeccion.desdeJson(_leccion('a', estado: 'completed'));
      final ResumenLeccion lista = ResumenLeccion.desdeJson(_leccion('b'));
      final ResumenLeccion sinEscribir =
          ResumenLeccion.desdeJson(_leccion('c', contenido: 'pending'));

      expect(
        estiloDeLeccion(abierto(), hecha, esSiguiente: false),
        EstiloNodo.completado,
      );
      expect(
        estiloDeLeccion(cerrado(), lista, esSiguiente: true),
        EstiloNodo.bloqueado,
      );
      expect(
        estiloDeLeccion(abierto(), sinEscribir, esSiguiente: true),
        EstiloNodo.enConstruccion,
      );
      expect(
        estiloDeLeccion(abierto(), lista, esSiguiente: true),
        EstiloNodo.actual,
      );
      expect(
        estiloDeLeccion(abierto(), lista, esSiguiente: false),
        EstiloNodo.disponible,
      );
    });
  });

  test('primeraPendiente salta las hechas y las que aún no están escritas', () {
    final List<ResumenLeccion> lecciones = <Map<String, dynamic>>[
      _leccion('a', estado: 'completed'),
      _leccion('b', contenido: 'pending'),
      _leccion('c'),
    ].map(ResumenLeccion.desdeJson).toList();

    expect(primeraPendiente(lecciones)?.id, 'c');
    expect(primeraPendiente(<ResumenLeccion>[]), isNull);
  });
}
